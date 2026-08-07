from dataclasses import dataclass, field


@dataclass
class PRStatus:
    number: int
    title: str
    url: str
    author: str
    days_open: int
    days_since_author_push: int
    days_since_last_review: int
    review_count: int
    participants: list[str]
    last_activity: str
    is_draft: bool
    gator_label: str | None = None
    actual_reviewers: list[str] = field(default_factory=list)
    requested_non_codeowners: list[str] = field(default_factory=list)
    auto_assigned: list[str] = field(default_factory=list)


@dataclass
class PRHealthFindings:
    total_open: int
    awaiting_review: int
    stale_14d: int
    gator_coverage_pct: int
    merge_velocity: int
    merge_velocity_prev: int
    avg_review_wait_days: float
    stuck_prs: list[PRStatus]
    age_distribution: dict[str, dict]
    codeowners: list[str] = field(default_factory=list)
