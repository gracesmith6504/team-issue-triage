from dataclasses import dataclass


@dataclass
class MetricsSnapshot:
    timestamp: str
    period_label: str

    total_issues: int
    by_urgency: dict[str, int]

    by_team: dict[str, int]

    triage_needed: int
    total_open: int

    pr_total_open: int | None
    pr_awaiting_review: int | None
    pr_stale_14d: int | None
    merge_velocity: int | None
    avg_review_wait_days: float | None

    vouch_pending: int | None
    vouch_responded_7d: int | None
    vouch_longest_wait: int | None
