from dataclasses import dataclass, field


@dataclass
class PendingVouch:
    author: str
    discussion_number: int
    url: str
    wait_days: int
    created_at: str


@dataclass
class BlockedPR:
    pr_number: int
    pr_title: str
    pr_url: str
    author: str
    vouch_discussion: int
    vouch_wait_days: int


@dataclass
class CompletedVouch:
    author: str
    discussion_number: int
    url: str
    vouched_at: str


@dataclass
class VouchFindings:
    total_pending: int
    responded_in_7d: int
    longest_wait_days: int
    over_30d_count: int
    pending_vouches: list[PendingVouch]
    completed_vouches: list[CompletedVouch] = field(default_factory=list)
    blocked_prs: list[BlockedPR] = field(default_factory=list)
