from app.reports.models import (
    AreaTrend,
    BirdsEyeReport,
    ReportSummary,
    TeamSummary,
)


def test_report_summary_creation():
    s = ReportSummary(
        new_this_period=12,
        by_urgency={"critical": 2, "high": 7},
        period_label="Jul 28 – Aug 3, 2026",
    )
    assert s.new_this_period == 12
    assert s.by_urgency["critical"] == 2


def test_team_summary_creation():
    ts = TeamSummary(
        team_id="agent-ops",
        total=38,
        by_urgency={"critical": 0, "high": 3},
        new_this_period=5,
        previous_period=3,
        trend="+2",
    )
    assert ts.team_id == "agent-ops"
    assert ts.trend == "+2"


def test_area_trend_creation():
    at = AreaTrend(
        area="gateway", current_count=10, previous_count=2, delta=8, trend="spike"
    )
    assert at.delta == 8
    assert at.trend == "spike"


def test_birds_eye_report_creation():
    summary = ReportSummary(new_this_period=0, by_urgency={}, period_label="test")
    report = BirdsEyeReport(
        summary=summary,
        critical_list=[],
        team_breakdown={},
        area_heatmap={},
        duplicate_clusters=[],
        no_team_list=[],
        narrative="No issues.",
        generated_at="2026-08-04T00:00:00+00:00",
    )
    assert report.narrative == "No issues."
    assert report.generated_at == "2026-08-04T00:00:00+00:00"
