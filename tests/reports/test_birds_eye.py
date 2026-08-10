from unittest.mock import MagicMock

from app.core.models import TriageResult, Urgency
from app.reports.birds_eye import BirdsEyeReportGenerator
from app.reports.models import BirdsEyeReport


def _make_result(
    number=1,
    title="feat(cli): test issue",
    team="agent-ops",
    urgency=Urgency.MEDIUM,
    assessed_at="2026-07-28T10:00:00+00:00",
    any_team_cares=True,
):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=number,
        issue_title=title,
        issue_url=f"https://github.com/NVIDIA/OpenShell/issues/{number}",
        reasoning="test",
        any_team_cares=any_team_cares,
        primary_team=team,
        primary_confidence=0.9,
        secondary_team=None,
        secondary_confidence=None,
        urgency=urgency,
        urgency_reasoning="test",
        summary="test summary",
        recommendation="test recommendation",
        confidence_flag=None,
        assessed_at=assessed_at,
    )


def _mock_llm(narrative="No notable trends this period."):
    client = MagicMock()
    client.assess.return_value = {"narrative": narrative}
    return client


def test_generate_empty_report():
    gen = BirdsEyeReportGenerator(
        [], [], _mock_llm(), "claude-sonnet-4-6", "Jul 28 – Aug 3"
    )
    report = gen.generate()
    assert isinstance(report, BirdsEyeReport)
    assert report.summary.new_this_period == 0
    assert report.critical_list == []
    assert report.team_breakdown == {}
    assert report.duplicate_clusters == []


def test_generate_summary_counts():
    current = [
        _make_result(1, urgency=Urgency.CRITICAL),
        _make_result(2, urgency=Urgency.HIGH),
        _make_result(3, urgency=Urgency.MEDIUM),
        _make_result(4, urgency=Urgency.MEDIUM),
        _make_result(5, urgency=Urgency.LOW),
    ]
    gen = BirdsEyeReportGenerator(current, [], _mock_llm(), "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert report.summary.new_this_period == 5
    assert report.summary.by_urgency == {
        "critical": 1,
        "high": 1,
        "medium": 2,
        "low": 1,
    }


def test_critical_list_sorted():
    current = [
        _make_result(1, urgency=Urgency.MEDIUM),
        _make_result(2, urgency=Urgency.CRITICAL),
        _make_result(3, urgency=Urgency.HIGH),
    ]
    gen = BirdsEyeReportGenerator(current, [], _mock_llm(), "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert len(report.critical_list) == 2
    assert report.critical_list[0].urgency == Urgency.CRITICAL
    assert report.critical_list[1].urgency == Urgency.HIGH


def test_team_breakdown_with_trend():
    current = [
        _make_result(1, team="agent-ops"),
        _make_result(2, team="agent-ops"),
        _make_result(3, team="acp"),
    ]
    previous = [
        _make_result(10, team="agent-ops"),
    ]
    gen = BirdsEyeReportGenerator(
        current, previous, _mock_llm(), "claude-sonnet-4-6", "test"
    )
    report = gen.generate()
    assert "agent-ops" in report.team_breakdown
    assert report.team_breakdown["agent-ops"].total == 2
    assert report.team_breakdown["agent-ops"].previous_period == 1
    assert report.team_breakdown["agent-ops"].trend == "+1"
    assert "acp" in report.team_breakdown
    assert report.team_breakdown["acp"].previous_period == 0
    assert report.team_breakdown["acp"].trend == "+1"


def test_area_heatmap():
    current = [
        _make_result(1, title="feat(gateway): test 1"),
        _make_result(2, title="bug(gateway): test 2"),
        _make_result(3, title="feat(cli): test 3"),
    ]
    previous = [
        _make_result(10, title="feat(gateway): old"),
    ]
    gen = BirdsEyeReportGenerator(
        current, previous, _mock_llm(), "claude-sonnet-4-6", "test"
    )
    report = gen.generate()
    assert "gateway" in report.area_heatmap
    assert report.area_heatmap["gateway"].current_count == 2
    assert report.area_heatmap["gateway"].previous_count == 1
    assert report.area_heatmap["gateway"].delta == 1


def test_no_team_list():
    current = [
        _make_result(1, team="agent-ops"),
        _make_result(2, team="none", any_team_cares=False),
        _make_result(3, team="none", any_team_cares=False),
    ]
    gen = BirdsEyeReportGenerator(current, [], _mock_llm(), "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert len(report.no_team_list) == 2


def test_narrative_from_llm():
    llm = _mock_llm("Gateway saw unusual activity this week.")
    gen = BirdsEyeReportGenerator(
        [_make_result(1)], [], llm, "claude-sonnet-4-6", "test"
    )
    report = gen.generate()
    assert report.narrative == "Gateway saw unusual activity this week."
    # LLM is called twice: once for synthesis, once for narrative
    assert llm.assess.call_count == 2


def test_narrative_fallback_on_llm_failure():
    llm = MagicMock()
    llm.assess.return_value = None
    gen = BirdsEyeReportGenerator(
        [_make_result(1)], [], llm, "claude-sonnet-4-6", "test"
    )
    report = gen.generate()
    assert report.narrative != ""
