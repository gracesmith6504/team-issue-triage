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

            if team_filter and record.get("primary_team") != team_filter:
                continue
            if urgency_filter and record.get("urgency") != urgency_filter:
                continue

            records.append(record)
    return records


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
