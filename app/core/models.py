from dataclasses import dataclass, field
from enum import Enum


class Urgency(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


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
    author_association: str = "NONE"
    author_login: str = ""
    assignees: list[str] = field(default_factory=list)


@dataclass
class TriageResult:
    repo: str
    issue_number: int
    issue_title: str
    issue_url: str
    reasoning: str
    any_team_cares: bool
    primary_team: str
    primary_confidence: float
    secondary_team: str | None
    secondary_confidence: float | None
    urgency: Urgency
    urgency_reasoning: str
    summary: str
    recommendation: str
    confidence_flag: str | None
    assessed_at: str
    created_at: str = ""
    author_association: str = "NONE"
    author_login: str = ""
    labels: list[str] = field(default_factory=list)


@dataclass
class IssueSignals:
    title_prefix: str | None
    area_labels: list[str]
    topic_labels: list[str]
    state_label: str | None
    issue_type: str | None
