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

    def to_dict(self) -> dict:
        return {
            "issue_number": self.issue_number,
            "title": self.title,
            "repo": self.repo,
            "relevance": self.relevance,
            "urgency": self.urgency,
            "action_clarity": self.action_clarity,
            "verdict": self.verdict,
            "reason": self.reason,
            "url": self.url,
            "assessed_at": self.assessed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DigestEntry":
        return cls(
            issue_number=data["issue_number"],
            title=data["title"],
            repo=data["repo"],
            relevance=data["relevance"],
            urgency=data["urgency"],
            action_clarity=data["action_clarity"],
            verdict=data["verdict"],
            reason=data["reason"],
            url=data["url"],
            assessed_at=data["assessed_at"],
        )


DIGEST_MAX_ITEMS = 10
