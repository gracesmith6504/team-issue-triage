import logging
import re
from datetime import datetime, timezone

from app.core.llm import LLMClientProtocol
from app.core.models import TriageResult, Urgency
from app.reports.duplicates import DuplicateDetector
from app.reports.models import (
    AreaGroup,
    AreaTrend,
    BirdsEyeReport,
    ReportSummary,
    TeamSummary,
    TeamSynthesis,
)

logger = logging.getLogger(__name__)

_PREFIX_RE = re.compile(r"^(?:feat|fix|bug|chore|docs|refactor|test|ci)\(([^)]+)\):\s*")

_URGENCY_SORT = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


def _extract_prefix(title: str) -> str | None:
    m = _PREFIX_RE.match(title)
    return m.group(1) if m else None


def _format_trend(delta: int) -> str:
    if delta > 0:
        return f"+{delta}"
    elif delta < 0:
        return str(delta)
    else:
        return "flat"


class BirdsEyeReportGenerator:
    def __init__(
        self,
        current: list[TriageResult],
        previous: list[TriageResult],
        llm_client: LLMClientProtocol,
        model: str,
        period_label: str,
    ):
        self._current = current
        self._previous = previous
        self._llm_client = llm_client
        self._model = model
        self._period_label = period_label

    def generate(self) -> BirdsEyeReport:
        summary = self._compute_summary()
        critical_list = self._extract_critical_list()
        team_breakdown = self._compute_team_breakdown()
        area_heatmap = self._compute_area_heatmap()
        duplicate_clusters = self._detect_duplicates()
        no_team_list = self._extract_no_team_list()
        team_synthesis = self._build_team_synthesis()

        # Generate LLM-based focus summaries and action items
        try:
            from app.reports.synthesis import synthesize_team_summaries
            team_synthesis = synthesize_team_summaries(
                team_synthesis, self._llm_client, self._model
            )
        except Exception:
            logger.exception("Team synthesis generation failed, using empty summaries")

        narrative = self._generate_narrative(
            summary, critical_list, team_breakdown, area_heatmap
        )
        generated_at = datetime.now(timezone.utc).isoformat()

        all_issues = sorted(
            self._current,
            key=lambda r: (_URGENCY_SORT.get(r.urgency.value, 99), r.issue_number),
        )

        return BirdsEyeReport(
            summary=summary,
            critical_list=critical_list,
            team_breakdown=team_breakdown,
            area_heatmap=area_heatmap,
            duplicate_clusters=duplicate_clusters,
            no_team_list=no_team_list,
            all_issues=all_issues,
            narrative=narrative,
            generated_at=generated_at,
            team_synthesis=team_synthesis,
        )

    def _compute_summary(self) -> ReportSummary:
        by_urgency: dict[str, int] = {}
        for r in self._current:
            urgency_str = r.urgency.value
            by_urgency[urgency_str] = by_urgency.get(urgency_str, 0) + 1

        return ReportSummary(
            new_this_period=len(self._current),
            by_urgency=by_urgency,
            period_label=self._period_label,
            total_open=len(self._current),
        )

    def _extract_critical_list(self) -> list[TriageResult]:
        critical = [
            r for r in self._current if r.urgency in (Urgency.CRITICAL, Urgency.HIGH)
        ]
        critical.sort(key=lambda r: (_URGENCY_SORT[r.urgency.value], r.issue_number))
        return critical

    def _compute_team_breakdown(self) -> dict[str, TeamSummary]:
        current_teams: dict[str, list[TriageResult]] = {}
        for r in self._current:
            current_teams.setdefault(r.primary_team, []).append(r)

        previous_teams: dict[str, list[TriageResult]] = {}
        for r in self._previous:
            previous_teams.setdefault(r.primary_team, []).append(r)

        breakdown: dict[str, TeamSummary] = {}
        for team_id, results in current_teams.items():
            by_urgency: dict[str, int] = {}
            for r in results:
                urgency_str = r.urgency.value
                by_urgency[urgency_str] = by_urgency.get(urgency_str, 0) + 1

            current_count = len(results)
            previous_count = len(previous_teams.get(team_id, []))
            delta = current_count - previous_count

            breakdown[team_id] = TeamSummary(
                team_id=team_id,
                total=current_count,
                by_urgency=by_urgency,
                new_this_period=current_count,
                previous_period=previous_count,
                trend=_format_trend(delta),
            )

        return breakdown

    def _compute_area_heatmap(self) -> dict[str, AreaTrend]:
        current_areas: dict[str, int] = {}
        for r in self._current:
            prefix = _extract_prefix(r.issue_title)
            if prefix:
                current_areas[prefix] = current_areas.get(prefix, 0) + 1

        previous_areas: dict[str, int] = {}
        for r in self._previous:
            prefix = _extract_prefix(r.issue_title)
            if prefix:
                previous_areas[prefix] = previous_areas.get(prefix, 0) + 1

        heatmap: dict[str, AreaTrend] = {}
        all_areas = set(current_areas.keys()) | set(previous_areas.keys())
        for area in all_areas:
            current_count = current_areas.get(area, 0)
            previous_count = previous_areas.get(area, 0)
            delta = current_count - previous_count

            heatmap[area] = AreaTrend(
                area=area,
                current_count=current_count,
                previous_count=previous_count,
                delta=delta,
                trend=_format_trend(delta),
            )

        return heatmap

    def _detect_duplicates(self) -> list:
        detector = DuplicateDetector()
        return detector.detect(self._current)

    def _extract_no_team_list(self) -> list[TriageResult]:
        return [r for r in self._current if r.primary_team == "none"]

    def _build_team_synthesis(self) -> dict[str, TeamSynthesis]:
        """Build TeamSynthesis structures with area grouping, without LLM summaries."""
        team_map: dict[str, dict[str, list[TriageResult]]] = {}

        # Group issues by team, then by area (deduplicate by issue number)
        seen_numbers: set[int] = set()
        for r in self._current:
            if r.issue_number in seen_numbers:
                continue
            seen_numbers.add(r.issue_number)

            team = r.primary_team
            # Extract area from title prefix
            prefix = _extract_prefix(r.issue_title)
            area = prefix or "uncategorized"
            team_map.setdefault(team, {}).setdefault(area, []).append(r)

        # Compute previous counts
        previous_teams: dict[str, int] = {}
        for r in self._previous:
            previous_teams[r.primary_team] = previous_teams.get(r.primary_team, 0) + 1

        result: dict[str, TeamSynthesis] = {}
        for team_id, areas in team_map.items():
            total = sum(len(issues) for issues in areas.values())
            by_urgency: dict[str, int] = {}
            area_groups: dict[str, AreaGroup] = {}

            for area, issues in areas.items():
                area_urgency: dict[str, int] = {}
                for r in issues:
                    u = r.urgency.value
                    area_urgency[u] = area_urgency.get(u, 0) + 1
                    by_urgency[u] = by_urgency.get(u, 0) + 1

                # Sort issues by urgency then number
                sorted_issues = sorted(
                    issues,
                    key=lambda r: (
                        _URGENCY_SORT.get(r.urgency.value, 99),
                        r.issue_number,
                    ),
                )

                area_groups[area] = AreaGroup(
                    area=area,
                    total=len(issues),
                    by_urgency=area_urgency,
                    issues=sorted_issues,
                )

            prev_count = previous_teams.get(team_id, 0)
            delta = total - prev_count

            result[team_id] = TeamSynthesis(
                team_id=team_id,
                team_name=team_id,  # Will be enriched later with actual team name
                focus_summary="",  # Will be filled by LLM synthesis
                actions=[],  # Will be filled by LLM synthesis
                area_groups=area_groups,
                total=total,
                by_urgency=by_urgency,
                trend=_format_trend(delta),
            )

        return result

    def _generate_narrative(
        self,
        summary: ReportSummary,
        critical_list: list[TriageResult],
        team_breakdown: dict[str, TeamSummary],
        area_heatmap: dict[str, AreaTrend],
    ) -> str:
        system_prompt = """You are a technical report writer. Given triage data, write a 2-3 sentence narrative summary.
Highlight spikes in specific areas, critical items, and notable trends. Be concise and specific."""

        user_prompt = f"""Report data:
- Total issues: {summary.new_this_period}
- By urgency: {summary.by_urgency}
- Critical/High: {len(critical_list)}
- Teams: {list(team_breakdown.keys())}
- Areas with activity: {list(area_heatmap.keys())}

Write a 2-3 sentence narrative summary. Return JSON: {{"narrative": "..."}}"""

        result = self._llm_client.assess(system_prompt, user_prompt, self._model)
        if result and "narrative" in result:
            return result["narrative"]

        return f"{len(self._current)} issues triaged this period."
