import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.models import TriageResult, Urgency

logger = logging.getLogger(__name__)


def result_to_record(result: TriageResult) -> dict:
    return {
        "repo": result.repo,
        "issue_number": result.issue_number,
        "issue_title": result.issue_title,
        "issue_url": result.issue_url,
        "reasoning": result.reasoning,
        "any_team_cares": result.any_team_cares,
        "primary_team": result.primary_team,
        "primary_confidence": result.primary_confidence,
        "secondary_team": result.secondary_team,
        "secondary_confidence": result.secondary_confidence,
        "urgency": result.urgency.value,
        "urgency_reasoning": result.urgency_reasoning,
        "summary": result.summary,
        "recommendation": result.recommendation,
        "confidence_flag": result.confidence_flag,
        "assessed_at": result.assessed_at,
        "created_at": result.created_at,
        "author_association": result.author_association,
        "author_login": result.author_login,
        "labels": result.labels,
        "closed": result.closed,
    }


def record_to_result(record: dict) -> TriageResult:
    return TriageResult(
        repo=record["repo"],
        issue_number=record["issue_number"],
        issue_title=record["issue_title"],
        issue_url=record["issue_url"],
        reasoning=record.get("reasoning", ""),
        any_team_cares=record.get("any_team_cares", True),
        primary_team=record.get("primary_team", "unknown"),
        primary_confidence=record.get("primary_confidence", 0.0),
        secondary_team=record.get("secondary_team"),
        secondary_confidence=record.get("secondary_confidence"),
        urgency=Urgency(record["urgency"]),
        urgency_reasoning=record.get("urgency_reasoning", ""),
        summary=record.get("summary", ""),
        recommendation=record.get("recommendation", ""),
        confidence_flag=record.get("confidence_flag"),
        assessed_at=record.get("assessed_at", ""),
        created_at=record.get("created_at", ""),
        author_association=record.get("author_association", "NONE"),
        author_login=record.get("author_login", ""),
        labels=record.get("labels", []),
        closed=record.get("closed", False),
    )


def append_result(log_path: Path, result: TriageResult) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = result_to_record(result)
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def read_results(
    log_path: Path,
    *,
    since_hours: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    team_filter: str | None = None,
    urgency_filter: str | None = None,
) -> list[dict]:
    if not log_path.exists():
        return []

    cutoff = None
    if since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    records = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if cutoff:
                try:
                    assessed = datetime.fromisoformat(record["assessed_at"])
                    if assessed < cutoff:
                        continue
                except (KeyError, ValueError):
                    continue

            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date)
                    assessed = datetime.fromisoformat(record["assessed_at"])
                    if assessed < start_dt:
                        continue
                except (KeyError, ValueError):
                    continue

            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date)
                    assessed = datetime.fromisoformat(record["assessed_at"])
                    if assessed > end_dt:
                        continue
                except (KeyError, ValueError):
                    continue

            if team_filter and record.get("primary_team") != team_filter:
                continue
            if urgency_filter and record.get("urgency") != urgency_filter:
                continue

            records.append(record)
    return records


def read_results_as_triage(
    log_path: Path,
    **kwargs,
) -> list[TriageResult]:
    records = read_results(log_path, **kwargs)

    # Deduplicate by issue_number, keeping most recent assessment
    seen: dict[int, dict] = {}
    for r in records:
        issue_num = r.get("issue_number")
        if issue_num is None:
            continue

        # Keep the record with the latest assessed_at timestamp
        existing = seen.get(issue_num)
        if existing is None:
            seen[issue_num] = r
        else:
            try:
                existing_time = datetime.fromisoformat(existing.get("assessed_at", ""))
                new_time = datetime.fromisoformat(r.get("assessed_at", ""))
                if new_time > existing_time:
                    seen[issue_num] = r
            except (KeyError, ValueError):
                # If timestamps invalid, keep the first one encountered
                pass

    return [record_to_result(r) for r in seen.values()]


def format_review(records: list[dict]) -> str:
    if not records:
        return "No results found."

    lines = [f"Triage Review — {len(records)} results\n"]

    grouped: dict[str, list[dict]] = {}
    for r in records:
        team = r.get("primary_team", "unknown")
        grouped.setdefault(team, []).append(r)

    for team, team_records in sorted(grouped.items()):
        lines.append(f"\n--- {team} ({len(team_records)} issues) ---")
        for r in team_records:
            urgency = r.get("urgency", "?")
            lines.append(
                f"  #{r.get('issue_number', '?')} [{urgency}] {r.get('issue_title', '?')}"
            )
            lines.append(f"    {r.get('summary', '')}")
            if r.get("recommendation"):
                lines.append(f"    → {r['recommendation']}")

    return "\n".join(lines)
