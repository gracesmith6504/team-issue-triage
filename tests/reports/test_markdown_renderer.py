from app.reports.models import BirdsEyeReport, DuplicateCluster, ReportSummary
from app.reports.renderers.markdown import render_markdown
from tests.reports.conftest import make_report, make_result


def test_render_contains_header():
    md = render_markdown(make_report())
    assert "Bird's Eye View" in md
    assert "Jul 28 – Aug 3, 2026" in md


def test_render_contains_summary():
    md = render_markdown(make_report())
    assert "5 new issues" in md
    assert "critical" in md.lower()


def test_render_contains_narrative():
    md = render_markdown(make_report())
    assert "Gateway saw unusual activity" in md


def test_render_contains_critical_list():
    md = render_markdown(make_report())
    assert "critical issue" in md


def test_render_contains_team_breakdown():
    md = render_markdown(make_report())
    assert "agent-ops" in md


def test_render_contains_area_heatmap():
    md = render_markdown(make_report())
    assert "gateway" in md


def test_render_contains_duplicates_when_present():
    cluster = DuplicateCluster(
        area="sandbox",
        issues=[make_result(1, "ns support"), make_result(2, "ns fails")],
        similarity_reason="shared: namespace",
    )
    md = render_markdown(make_report(duplicate_clusters=[cluster]))
    assert "sandbox" in md
    assert "namespace" in md


def test_render_contains_no_team_list():
    no_team = [make_result(10, "build system change", team="none")]
    md = render_markdown(make_report(no_team_list=no_team))
    assert "build system change" in md


def test_render_empty_report():
    report = BirdsEyeReport(
        summary=ReportSummary(new_this_period=0, by_urgency={}, period_label="test"),
        critical_list=[],
        team_breakdown={},
        area_heatmap={},
        duplicate_clusters=[],
        no_team_list=[],
        all_issues=[],
        narrative="No issues.",
        generated_at="2026-08-04T00:00:00+00:00",
    )
    md = render_markdown(report)
    assert "0 new issues" in md
