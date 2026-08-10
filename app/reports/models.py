from dataclasses import dataclass

from app.core.models import TriageResult


@dataclass
class ReportSummary:
    new_this_period: int
    by_urgency: dict[str, int]
    period_label: str
    triage_needed: int = 0
    total_open: int = 0


@dataclass
class TeamSummary:
    team_id: str
    total: int
    by_urgency: dict[str, int]
    new_this_period: int
    previous_period: int
    trend: str


@dataclass
class AreaGroup:
    area: str
    total: int
    by_urgency: dict[str, int]
    issues: list[TriageResult]


@dataclass
class TeamSynthesis:
    team_id: str
    team_name: str
    focus_summary: str
    actions: list[str]
    area_groups: dict[str, AreaGroup]
    total: int
    by_urgency: dict[str, int]
    trend: str


@dataclass
class AreaTrend:
    area: str
    current_count: int
    previous_count: int
    delta: int
    trend: str


@dataclass
class DuplicateCluster:
    area: str
    issues: list[TriageResult]
    similarity_reason: str


@dataclass
class BirdsEyeReport:
    summary: ReportSummary
    critical_list: list[TriageResult]
    team_breakdown: dict[str, TeamSummary]
    area_heatmap: dict[str, AreaTrend]
    duplicate_clusters: list[DuplicateCluster]
    no_team_list: list[TriageResult]
    all_issues: list[TriageResult]
    narrative: str
    generated_at: str
    pr_health: dict | None = None
    vouch_status: dict | None = None
    team_synthesis: dict[str, TeamSynthesis] | None = None
