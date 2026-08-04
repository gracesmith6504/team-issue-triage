from dataclasses import dataclass

from app.core.models import TriageResult


@dataclass
class ReportSummary:
    new_this_period: int
    by_urgency: dict[str, int]
    period_label: str


@dataclass
class TeamSummary:
    team_id: str
    total: int
    by_urgency: dict[str, int]
    new_this_period: int
    previous_period: int
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
    narrative: str
    generated_at: str
