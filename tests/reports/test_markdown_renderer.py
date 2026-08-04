from app.core.models import TriageResult, Urgency
from app.reports.models import (
    AreaTrend,
    BirdsEyeReport,
    DuplicateCluster,
    ReportSummary,
    TeamSummary,
)
from app.reports.renderers.markdown import render_markdown


def _make_result(
    number=1, title="test issue", team="agent-ops", urgency=Urgency.MEDIUM
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
        secondary_team=None,
        secondary_confidence=None,
        urgency=urgency,
        urgency_reasoning="test",
        summary="test",
        recommendation="test",
        confidence_flag=None,
        assessed_at="2026-07-28T10:00:00+00:00",
    )


def _make_report(**overrides):
    defaults = dict(
        summary=ReportSummary(
            new_this_period=5,
            by_urgency={"critical": 1, "high": 2, "medium": 1, "low": 1},
            period_label="Jul 28 – Aug 3, 2026",
        ),
        critical_list=[_make_result(1, "critical issue", urgency=Urgency.CRITICAL)],
        team_breakdown={
            "agent-ops": TeamSummary(
                team_id="agent-ops",
                total=3,
                by_urgency={"critical": 1, "high": 1, "medium": 1, "low": 0},
                new_this_period=3,
                previous_period=2,
                trend="+1",
            )
        },
        area_heatmap={
            "gateway": AreaTrend(
                area="gateway", current_count=5, previous_count=2, delta=3, trend="+3"
            )
        },
        duplicate_clusters=[],
        no_team_list=[],
        narrative="Gateway saw unusual activity this week.",
        generated_at="2026-08-04T00:00:00+00:00",
    )
    defaults.update(overrides)
    return BirdsEyeReport(**defaults)


def test_render_contains_header():
    md = render_markdown(_make_report())
    assert "Bird's Eye View" in md
    assert "Jul 28 – Aug 3, 2026" in md


def test_render_contains_summary():
    md = render_markdown(_make_report())
    assert "5 new issues" in md
    assert "critical" in md.lower()


def test_render_contains_narrative():
    md = render_markdown(_make_report())
    assert "Gateway saw unusual activity" in md


def test_render_contains_critical_list():
    md = render_markdown(_make_report())
    assert "critical issue" in md


def test_render_contains_team_breakdown():
    md = render_markdown(_make_report())
    assert "agent-ops" in md


def test_render_contains_area_heatmap():
    md = render_markdown(_make_report())
    assert "gateway" in md


def test_render_contains_duplicates_when_present():
    cluster = DuplicateCluster(
        area="sandbox",
        issues=[_make_result(1, "ns support"), _make_result(2, "ns fails")],
        similarity_reason="shared: namespace",
    )
    md = render_markdown(_make_report(duplicate_clusters=[cluster]))
    assert "sandbox" in md
    assert "namespace" in md


def test_render_contains_no_team_list():
    no_team = [_make_result(10, "build system change", team="none")]
    md = render_markdown(_make_report(no_team_list=no_team))
    assert "build system change" in md


def test_render_empty_report():
    report = BirdsEyeReport(
        summary=ReportSummary(new_this_period=0, by_urgency={}, period_label="test"),
        critical_list=[],
        team_breakdown={},
        area_heatmap={},
        duplicate_clusters=[],
        no_team_list=[],
        narrative="No issues.",
        generated_at="2026-08-04T00:00:00+00:00",
    )
    md = render_markdown(report)
    assert "0 new issues" in md
