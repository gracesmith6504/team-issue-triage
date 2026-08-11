import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import TriageConfig
from app.core.llm import build_llm_client, resolve_model
from app.core.profiles import load_repo_config
from app.core.prompt import build_system_prompt
from app.core.triage_engine import triage_issue
from app.notifications.adapter import ChannelConfig, TeamNotificationConfig
from app.notifications.log import LogAdapter
from app.notifications.router import NotificationRouter
from app.notifications.slack_webhook import SlackWebhookAdapter
from app.reports.birds_eye import BirdsEyeReportGenerator
from app.reports.renderers.markdown import render_markdown
from app.sources.github import GitHubSource
from app.state.assessment_log import (
    append_result,
    format_review,
    read_results,
    read_results_as_triage,
    record_to_result,
)
from app.state.tracker import StateTracker

logger = logging.getLogger(__name__)


def _resolve_env_vars(value: str) -> str:
    return re.sub(
        r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), value
    )


def _build_notification_router(repo_config) -> NotificationRouter:
    adapters = {"slack_webhook": SlackWebhookAdapter(), "log": LogAdapter()}
    team_configs = {}

    for profile in repo_config.team_profiles:
        notif = profile.notifications
        channels = []
        for ch in notif.get("channels", []):
            ch_config = {
                k: _resolve_env_vars(v) if isinstance(v, str) else v
                for k, v in ch.get("config", {}).items()
            }
            channels.append(
                ChannelConfig(
                    adapter_type=ch["adapter"],
                    config=ch_config,
                    immediate_on=ch.get("immediate_on", []),
                )
            )
        team_configs[profile.team_id] = TeamNotificationConfig(
            team_id=profile.team_id,
            receive_secondary=notif.get("receive_secondary", False),
            secondary_min_urgency=notif.get("secondary_min_urgency"),
            channels=channels,
        )

    return NotificationRouter(team_configs=team_configs, adapters=adapters)


def run_triage(config: TriageConfig) -> None:
    tracker = StateTracker(config.state_path, config.default_lookback_hours)
    state = tracker.load()

    repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
    system_prompt = build_system_prompt(repo_config)
    router = _build_notification_router(repo_config)

    llm_client = build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)

    seen_numbers = set()
    for key in state["seen_issues"]:
        key_str = str(key)
        if "#" in key_str:
            try:
                seen_numbers.add(int(key_str.split("#")[1]))
            except (ValueError, IndexError):
                pass
        elif key_str.isdigit():
            seen_numbers.add(int(key_str))

    source = GitHubSource(config.github_token)
    new_issues = source.fetch_new_issues(
        config.watch_repos,
        state["last_checked"],
        seen_numbers,
    )

    logger.info(f"Found {len(new_issues)} new issues")

    for issue in new_issues:
        result = triage_issue(issue, llm_client, model, repo_config, system_prompt)
        if result is None:
            continue

        append_result(config.assessment_log_path, result)
        router.route(result)

        seen_key = f"{issue.repo}#{issue.number}"
        state["seen_issues"].add(seen_key)
        state["seen_timestamps"][seen_key] = datetime.now(timezone.utc).isoformat()

    state["last_checked"] = datetime.now(timezone.utc).isoformat()
    StateTracker.prune_seen(state)
    tracker.save(state)


def run_refresh(config: TriageConfig) -> None:
    """Weekly refresh: re-triage all open issues, smart detection of changes.

    Only re-triages issues where title or body changed since last assessment.
    Marks closed issues. Appends fresh assessments to log (dedup handles rest).
    """
    logger.info("Starting weekly refresh of all open issues")

    # Load existing assessments to compare
    from app.state.assessment_log import append_result, read_results_as_triage

    existing = {
        r.issue_number: r for r in read_results_as_triage(config.assessment_log_path)
    }

    # Load repo config and LLM client
    repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
    llm_client = build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)
    system_prompt = build_system_prompt(repo_config)

    # Fetch ALL open issues from GitHub
    source = GitHubSource(config.github_token)
    all_issues = source.fetch_all_open_issues(config.watch_repos)

    logger.info("Fetched %d open issues from GitHub", len(all_issues))

    # Track stats
    re_triaged = 0
    unchanged = 0
    new_issues = 0

    # Process each issue
    for issue_data in all_issues:
        prev = existing.get(issue_data.number)

        if prev is None:
            # New issue we've never seen
            logger.info("New issue found: #%d", issue_data.number)
            new_issues += 1
            should_triage = True
        else:
            # Check if title or body changed
            title_changed = issue_data.title != prev.issue_title
            # Note: issue_body not stored in TriageResult, so compare against empty
            body_changed = issue_data.body != ""

            if title_changed or body_changed:
                logger.info(
                    "Issue #%d changed (title=%s, body=%s)",
                    issue_data.number,
                    title_changed,
                    body_changed,
                )
                re_triaged += 1
                should_triage = True
            else:
                unchanged += 1
                should_triage = False

        if should_triage:
            # Re-triage with LLM
            result = triage_issue(
                issue_data, llm_client, model, repo_config, system_prompt
            )

            if result:
                # Append to assessment log (dedup keeps latest)
                append_result(config.assessment_log_path, result)

    logger.info(
        "Weekly refresh complete: %d new, %d re-triaged, %d unchanged",
        new_issues,
        re_triaged,
        unchanged,
    )


def check_closed_issues(config: TriageConfig) -> None:
    """Check if any previously-triaged issues are now closed on GitHub.

    Appends new assessment with closed=True to mark them in the log.
    Uses free GitHub API calls (no LLM).
    """
    import requests
    from app.core.models import TriageResult
    from app.state.assessment_log import append_result, read_results_as_triage

    logger.info("Checking for closed issues")

    # Get all open issues from our log
    existing = read_results_as_triage(config.assessment_log_path)
    open_in_log = [r for r in existing if not getattr(r, "closed", False)]

    closed_count = 0

    for result in open_in_log:
        # Check GitHub API for current state
        url = f"https://api.github.com/repos/{result.repo}/issues/{result.issue_number}"
        response = requests.get(
            url, headers={"Authorization": f"token {config.github_token}"}
        )

        if response.status_code == 200:
            issue_state = response.json().get("state")
            if issue_state == "closed":
                logger.info("Issue #%d is now closed", result.issue_number)

                # Create new assessment marking it as closed
                # (Reuse existing classification, just update state)
                closed_result = TriageResult(
                    repo=result.repo,
                    issue_number=result.issue_number,
                    issue_title=result.issue_title,
                    issue_url=result.issue_url,
                    reasoning=result.reasoning,
                    any_team_cares=result.any_team_cares,
                    primary_team=result.primary_team,
                    primary_confidence=result.primary_confidence,
                    secondary_team=result.secondary_team,
                    secondary_confidence=result.secondary_confidence,
                    urgency=result.urgency,
                    urgency_reasoning=result.urgency_reasoning,
                    summary=result.summary,
                    confidence_flag=result.confidence_flag,
                    assessed_at=datetime.now(timezone.utc).isoformat(),
                    created_at=result.created_at,
                    author_association=result.author_association,
                    author_login=result.author_login,
                    closed=True,  # Mark as closed
                )

                append_result(config.assessment_log_path, closed_result)
                closed_count += 1

    logger.info("Marked %d issues as closed", closed_count)


def run_review(
    config: TriageConfig,
    *,
    since_hours: int | None = None,
    team_filter: str | None = None,
) -> None:
    records = read_results(
        config.assessment_log_path,
        since_hours=since_hours,
        team_filter=team_filter,
    )
    print(format_review(records))


def run_digest(config: TriageConfig) -> None:
    tracker = StateTracker(config.state_path)
    state = tracker.load()

    last_digest = state.get("last_digest")
    since_hours = 24
    if last_digest:
        try:
            last_dt = datetime.fromisoformat(last_digest)
            delta = datetime.now(timezone.utc) - last_dt
            since_hours = max(1, int(delta.total_seconds() / 3600))
        except ValueError:
            pass

    records = read_results(config.assessment_log_path, since_hours=since_hours)
    medium_low = [r for r in records if r.get("urgency") in ("medium", "low")]

    if medium_low:
        results = [record_to_result(r) for r in medium_low]

        repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
        router = _build_notification_router(repo_config)
        router.send_digest(results)

    state["last_digest"] = datetime.now(timezone.utc).isoformat()
    tracker.save(state)


def _detect_format(output_path: Path | None, explicit_format: str | None) -> str:
    if explicit_format:
        return explicit_format
    if output_path and output_path.suffix == ".html":
        return "html"
    return "markdown"


def run_report(
    config: TriageConfig,
    *,
    output_path: Path | None = None,
    fmt: str | None = None,
) -> None:
    from app.metrics.compute import build_sparklines, compute_snapshot
    from app.metrics.store import JsonlMetricsStore
    from app.reports.enrich import enrich_report
    from app.reports.periods import compute_period

    repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)

    now = datetime.now(timezone.utc)
    current_start, previous_start, period_label = compute_period(
        repo_config.reporting, now
    )

    current = read_results_as_triage(
        config.assessment_log_path,
        start_date=current_start.isoformat(),
    )
    previous = read_results_as_triage(
        config.assessment_log_path,
        start_date=previous_start.isoformat(),
        end_date=current_start.isoformat(),
    )

    llm_client = build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)

    generator = BirdsEyeReportGenerator(
        current, previous, llm_client, model, period_label
    )
    report = generator.generate()

    enrich_report(report, config, repo_config)

    sparklines = None
    try:
        store = JsonlMetricsStore(config.metrics_path)
        snapshot = compute_snapshot(report, now)
        store.append(snapshot)
        recent = store.read(limit=7)
        sparklines = build_sparklines(recent)
    except Exception:
        logger.exception("Metrics collection failed")

    dest = output_path or config.report_output_path
    resolved_fmt = _detect_format(dest, fmt)

    if resolved_fmt == "html":
        from app.reports.renderers.html import render_html
        from app.sources.enrichment import enrich_issues

        enrichment = {}
        try:
            enrichment = enrich_issues(current, config.github_token)
        except Exception:
            logger.exception("Enrichment failed, rendering without enrichment")

        output = render_html(report, enrichment=enrichment, sparklines=sparklines)
    else:
        output = render_markdown(report)

    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(output)
        logger.info(f"Report written to {dest}")

        # Write dated archive copy
        date_str = now.strftime("%Y-%m-%d")
        archive = dest.parent / f"{dest.stem}-{date_str}{dest.suffix}"
        archive.write_text(output)
        logger.info(f"Archive copy written to {archive}")
    else:
        print(output)
