import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import TriageConfig
from app.core.llm import create_llm_client, resolve_model
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


def _build_llm_client(config: TriageConfig):
    if config.llm_provider == "anthropic":
        return create_llm_client("anthropic", api_key=config.anthropic_api_key)
    return create_llm_client(
        "vertex",
        project_id=config.vertex_project_id,
        region=config.vertex_region,
    )


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

    llm_client = _build_llm_client(config)
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
    repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
    reporting = repo_config.reporting

    now = datetime.now(timezone.utc)
    period_days = 7 if reporting.get("period") == "weekly" else 1

    # Compute current period start (most recent period_start day)
    weekday_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    target_weekday = weekday_map.get(reporting.get("period_start", "monday"), 0)
    days_since = (now.weekday() - target_weekday) % 7
    current_start = (now - timedelta(days=days_since)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    previous_start = current_start - timedelta(days=period_days)

    current = read_results_as_triage(
        config.assessment_log_path,
        start_date=current_start.isoformat(),
    )
    previous = read_results_as_triage(
        config.assessment_log_path,
        start_date=previous_start.isoformat(),
        end_date=current_start.isoformat(),
    )

    period_label = f"{current_start.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"

    llm_client = _build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)

    generator = BirdsEyeReportGenerator(
        current, previous, llm_client, model, period_label
    )
    report = generator.generate()

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

        output = render_html(report, enrichment=enrichment)
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
