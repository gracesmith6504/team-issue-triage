from datetime import datetime

from app.metrics.models import MetricsSnapshot
from app.reports.models import BirdsEyeReport


def compute_snapshot(report: BirdsEyeReport, now: datetime) -> MetricsSnapshot:
    summary = report.summary
    by_team = {team_id: ts.total for team_id, ts in report.team_breakdown.items()}

    pr = report.pr_health
    vouch = report.vouch_status

    return MetricsSnapshot(
        timestamp=now.isoformat(),
        period_label=summary.period_label,
        total_issues=summary.new_this_period,
        by_urgency=dict(summary.by_urgency),
        by_team=by_team,
        triage_needed=summary.triage_needed,
        total_open=summary.total_open,
        pr_total_open=pr["total_open"] if pr else None,
        pr_awaiting_review=pr["awaiting_review"] if pr else None,
        pr_stale_14d=pr["stale_14d"] if pr else None,
        merge_velocity=pr["merge_velocity"] if pr else None,
        avg_review_wait_days=pr["avg_review_wait_days"] if pr else None,
        vouch_pending=vouch["total_pending"] if vouch else None,
        vouch_responded_7d=vouch["responded_in_7d"] if vouch else None,
        vouch_longest_wait=vouch["longest_wait_days"] if vouch else None,
    )


def build_sparklines(snapshots: list[MetricsSnapshot]) -> dict[str, list[int]]:
    return {
        "triage": [s.triage_needed for s in snapshots],
        "prs": [s.pr_awaiting_review or 0 for s in snapshots],
        "blocked": [s.vouch_pending or 0 for s in snapshots],
        "velocity": [s.merge_velocity or 0 for s in snapshots],
    }
