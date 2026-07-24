from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    ESCALATE = "ESCALATE"
    TRACK = "TRACK"
    WATCH = "WATCH"
    SKIP = "SKIP"


@dataclass
class IssueData:
    repo: str
    number: int
    title: str
    body: str
    labels: list[str]
    comments: list[dict]
    url: str
    created_at: str


@dataclass
class Assessment:
    repo: str
    issue_number: int
    issue_title: str
    issue_url: str
    relevance: int
    relevance_reason: str
    urgency: int
    urgency_reason: str
    action_clarity: int
    action_clarity_reason: str
    total: int
    verdict: Verdict
    override_applied: str | None
    summary: str
    recommendation: str
    assessed_at: str


@dataclass
class DigestEntry:
    issue_number: int
    title: str
    repo: str
    relevance: int
    urgency: int
    action_clarity: int
    verdict: str
    reason: str
    url: str
    assessed_at: str
