from dataclasses import dataclass


@dataclass
class PendingVouch:
    author: str
    discussion_number: int
    url: str
    wait_days: int
    created_at: str


@dataclass
class VouchFindings:
    total_pending: int
    responded_in_7d: int
    longest_wait_days: int
    over_30d_count: int
    pending_vouches: list[PendingVouch]
