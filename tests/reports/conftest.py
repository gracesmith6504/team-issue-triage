# tests/reports/conftest.py
from app.core.models import TriageResult, Urgency
from app.reports.models import (
    AreaTrend,
    BirdsEyeReport,
    DuplicateCluster,
    ReportSummary,
    TeamSummary,
)


def make_result(
    number=1,
    title="test issue",
    team="agent-ops",
    urgency=Urgency.MEDIUM,
    secondary_team=None,
    secondary_confidence=None,
    confidence_flag=None,
):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=number,
        issue_title=title,
        issue_url=f"https://github.com/NVIDIA/OpenShell/issues/{number}",
        reasoning="test",
        any_team_cares=True,
        primary_team=team,
        primary_confidence=0.9,
        secondary_team=secondary_team,
        secondary_confidence=secondary_confidence,
        urgency=urgency,
        urgency_reasoning="test",
        summary=f"Summary for #{number}",
        recommendation="test",
        confidence_flag=confidence_flag,
        assessed_at="2026-07-28T10:00:00+00:00",
        created_at="2026-07-25T10:00:00Z",
    )


def make_report(**overrides):
    defaults = dict(
        summary=ReportSummary(
            new_this_period=5,
            by_urgency={"critical": 1, "high": 2, "medium": 1, "low": 1},
            period_label="Jul 28 – Aug 3, 2026",
            total_open=5,
        ),
        critical_list=[make_result(1, "critical issue", urgency=Urgency.CRITICAL)],
        team_breakdown={
            "agent-ops": TeamSummary(
                team_id="agent-ops",
                total=3,
                by_urgency={"critical": 1, "high": 1, "medium": 1, "low": 0},
                new_this_period=3,
                previous_period=2,
                trend="+1",
            ),
            "ai-safety": TeamSummary(
                team_id="ai-safety",
                total=2,
                by_urgency={"critical": 0, "high": 1, "medium": 1, "low": 0},
                new_this_period=2,
                previous_period=0,
                trend="+2",
            ),
        },
        area_heatmap={
            "gateway": AreaTrend(
                area="gateway", current_count=5, previous_count=2, delta=3, trend="+3"
            )
        },
        duplicate_clusters=[
            DuplicateCluster(
                area="sandbox",
                issues=[make_result(10, "ns support"), make_result(11, "ns fails")],
                similarity_reason="shared: namespace",
            )
        ],
        no_team_list=[make_result(20, "build system change", team="none")],
        all_issues=[make_result(1, "critical issue", urgency=Urgency.CRITICAL)],
        narrative="Gateway saw unusual activity this week.",
        generated_at="2026-08-04T00:00:00+00:00",
    )
    defaults.update(overrides)
    return BirdsEyeReport(**defaults)
