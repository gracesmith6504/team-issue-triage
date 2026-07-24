import logging
from datetime import datetime, timezone

from app.config import TriageConfig
from app.core.assessment import assess_issue
from app.core.llm import create_llm_client, resolve_model
from app.core.models import DigestEntry, Verdict
from app.core.profiles import find_profile_for_repo
from app.notifications.log import LogNotifier
from app.notifications.slack import SlackNotifier
from app.sources.github import GitHubSource
from app.state.tracker import StateTracker

logger = logging.getLogger(__name__)


def _build_notifier(config: TriageConfig):
    if config.slack_webhook_url:
        return SlackNotifier(webhook_url=config.slack_webhook_url)
    return LogNotifier()


def _build_llm_client(config: TriageConfig):
    kwargs = {}
    if config.llm_provider == "anthropic":
        kwargs["api_key"] = config.anthropic_api_key
    elif config.llm_provider == "vertex":
        kwargs["project_id"] = config.vertex_project_id
        kwargs["region"] = config.vertex_region
    return create_llm_client(config.llm_provider, **kwargs)


def run_triage(config: TriageConfig) -> None:
    tracker = StateTracker(
        config.state_path, lookback_hours=config.default_lookback_hours
    )
    state = tracker.load()
    notifier = _build_notifier(config)
    source = GitHubSource(token=config.github_token)
    llm_client = _build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)

    issues = source.fetch_new_issues(
        repos=config.watch_repos,
        since=state["last_checked"],
        seen_ids=state["seen_issues"],
    )

    logger.info(f"Found {len(issues)} new issues to assess")

    for issue in issues:
        profile = find_profile_for_repo(issue.repo, profiles_dir=config.profiles_dir)
        assessment = assess_issue(issue, llm_client, model, profile=profile)

        if assessment is None:
            logger.warning(f"Failed to assess {issue.repo}#{issue.number}")
            continue

        logger.info(
            f"Assessed {issue.repo}#{issue.number}: {assessment.verdict.value} "
            f"(total={assessment.total})"
        )

        if assessment.verdict == Verdict.ESCALATE:
            notifier.send_escalation(assessment)
        elif assessment.verdict == Verdict.TRACK:
            entry = DigestEntry(
                issue_number=assessment.issue_number,
                title=assessment.issue_title,
                repo=assessment.repo,
                relevance=assessment.relevance,
                urgency=assessment.urgency,
                action_clarity=assessment.action_clarity,
                verdict=assessment.verdict.value,
                reason=assessment.summary,
                url=assessment.issue_url,
                assessed_at=assessment.assessed_at,
            )
            state["digest_buffer"].append(
                {
                    "issue_number": entry.issue_number,
                    "title": entry.title,
                    "repo": entry.repo,
                    "relevance": entry.relevance,
                    "urgency": entry.urgency,
                    "action_clarity": entry.action_clarity,
                    "verdict": entry.verdict,
                    "reason": entry.reason,
                    "url": entry.url,
                    "assessed_at": entry.assessed_at,
                }
            )

        state["seen_issues"].add(issue.number)
        now_str = datetime.now(timezone.utc).isoformat()
        state.setdefault("seen_timestamps", {})[str(issue.number)] = now_str

    state["last_checked"] = datetime.now(timezone.utc).isoformat()
    state = tracker.prune_seen(state)
    tracker.save(state)
    logger.info("Triage run complete")


def run_digest(config: TriageConfig) -> None:
    tracker = StateTracker(
        config.state_path, lookback_hours=config.default_lookback_hours
    )
    state = tracker.load()
    notifier = _build_notifier(config)

    buffer = state.get("digest_buffer", [])
    if buffer:
        entries = [
            DigestEntry(
                issue_number=item["issue_number"],
                title=item["title"],
                repo=item["repo"],
                relevance=item["relevance"],
                urgency=item["urgency"],
                action_clarity=item["action_clarity"],
                verdict=item["verdict"],
                reason=item["reason"],
                url=item["url"],
                assessed_at=item["assessed_at"],
            )
            for item in buffer
        ]
        notifier.send_digest(entries)
        logger.info(f"Sent digest with {len(entries)} items")
    else:
        logger.info("Digest buffer empty, nothing to send")

    state["digest_buffer"] = []
    tracker.save(state)
