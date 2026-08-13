from dataclasses import dataclass, field


@dataclass
class OpenPRSummary:
    number: int
    title: str
    url: str
    author: str
    created_at: str
    updated_at: str
    has_requested_reviewers: bool
    is_draft: bool
    has_gator_label: bool
    author_association: str = "NONE"
    review_count: int = 0
    last_review_at: str = ""
    last_human_comment_at: str = ""
    last_author_comment_at: str = ""
    participants: list[str] = field(default_factory=list)


@dataclass
class PRHealthFindings:
    total_open: int
    awaiting_review: int
    stale_14d: int
    gator_coverage_pct: int
    merge_velocity: int
    merge_velocity_prev: int
    avg_review_wait_days: float
    age_distribution: dict[str, dict]
    codeowners: list[str] = field(default_factory=list)
    all_open_pr_summaries: list[OpenPRSummary] = field(default_factory=list)
    merged_dates: list[str] = field(default_factory=list)
