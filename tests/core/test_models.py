# tests/core/test_models.py
from app.core.models import IssueData, IssueSignals, TriageResult, Urgency


def test_urgency_values():
    assert Urgency.CRITICAL == "critical"
    assert Urgency.HIGH == "high"
    assert Urgency.MEDIUM == "medium"
    assert Urgency.LOW == "low"


def test_urgency_ordering():
    ordered = [Urgency.CRITICAL, Urgency.HIGH, Urgency.MEDIUM, Urgency.LOW]
    assert [u.value for u in ordered] == ["critical", "high", "medium", "low"]


def test_issue_data_creation():
    issue = IssueData(
        repo="NVIDIA/OpenShell",
        number=2571,
        title="bug(supervisor): SPIFFE crash",
        body="SPIFFE sandboxes crash on restart",
        labels=["area:supervisor", "topic:security"],
        comments=[],
        url="https://github.com/NVIDIA/OpenShell/issues/2571",
        created_at="2026-08-01T00:00:00Z",
    )
    assert issue.number == 2571
    assert issue.repo == "NVIDIA/OpenShell"


def test_triage_result_creation():
    result = TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=2571,
        issue_title="bug(supervisor): SPIFFE crash",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2571",
        reasoning="SPIFFE in title indicates security",
        any_team_cares=True,
        primary_team="ai-safety",
        primary_confidence=0.85,
        secondary_team="agent-ops",
        secondary_confidence=0.65,
        urgency=Urgency.HIGH,
        urgency_reasoning="Security crash is a regression",
        summary="SPIFFE sandboxes crash on restart",
        recommendation="Investigate SPIFFE lifecycle",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00Z",
    )
    assert result.primary_team == "ai-safety"
    assert result.urgency == Urgency.HIGH
    assert result.urgency.value == "high"
    assert result.secondary_team == "agent-ops"


def test_triage_result_no_team():
    result = TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=2491,
        issue_title="feat(build): evaluate Bazel",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2491",
        reasoning="Build system, no Red Hat team",
        any_team_cares=False,
        primary_team="none",
        primary_confidence=0.9,
        secondary_team=None,
        secondary_confidence=None,
        urgency=Urgency.LOW,
        urgency_reasoning="Design discussion",
        summary="Evaluate Bazel for builds",
        recommendation="No action needed",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00Z",
    )
    assert result.any_team_cares is False
    assert result.primary_team == "none"
    assert result.secondary_team is None
    assert result.secondary_confidence is None


def test_issue_signals_creation():
    signals = IssueSignals(
        title_prefix="supervisor",
        area_labels=["area:supervisor"],
        topic_labels=["topic:security"],
        state_label="state:triage-needed",
        issue_type="Bug",
    )
    assert signals.title_prefix == "supervisor"
    assert signals.area_labels == ["area:supervisor"]


def test_issue_signals_no_prefix():
    signals = IssueSignals(
        title_prefix=None,
        area_labels=[],
        topic_labels=[],
        state_label=None,
        issue_type=None,
    )
    assert signals.title_prefix is None
    assert signals.area_labels == []
