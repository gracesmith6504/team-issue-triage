from unittest.mock import MagicMock

from app.core.assessment import assess_issue
from app.core.models import IssueData, Verdict
from app.core.profiles import TeamProfile


def _make_issue():
    return IssueData(
        repo="NVIDIA/OpenShell",
        number=2401,
        title="protobuf sync failed",
        body="The sync job failed.",
        labels=["kind/bug"],
        comments=[],
        url="https://github.com/NVIDIA/OpenShell/issues/2401",
        created_at="2026-07-23T14:00:00Z",
    )


def _make_profile():
    return TeamProfile(
        name="openshell",
        repos=["NVIDIA/OpenShell"],
        team_name="Agent Ops",
        team_context="OpenShift integration team.",
    )


def _mock_llm_response(relevance=5, urgency=5, action_clarity=4):
    return {
        "relevance": relevance,
        "relevance_reason": "Team-owned area",
        "urgency": urgency,
        "urgency_reason": "Blocks releases",
        "action_clarity": action_clarity,
        "action_clarity_reason": "Clear fix needed",
        "summary": "SDK sync failure",
        "recommendation": "Re-run sync",
    }


def test_assess_issue_escalate():
    issue = _make_issue()
    mock_llm = MagicMock()
    mock_llm.assess.return_value = _mock_llm_response(5, 5, 4)

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6", profile=_make_profile())

    assert result is not None
    assert result.verdict == Verdict.ESCALATE
    assert result.total == 14
    assert result.relevance == 5
    assert result.issue_number == 2401
    assert result.override_applied is None


def test_assess_issue_track():
    issue = _make_issue()
    mock_llm = MagicMock()
    mock_llm.assess.return_value = _mock_llm_response(3, 3, 3)

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is not None
    assert result.verdict == Verdict.TRACK
    assert result.total == 9


def test_assess_issue_skip_low_relevance():
    issue = _make_issue()
    mock_llm = MagicMock()
    # Total 9 would be TRACK, but relevance=1 caps verdict at WATCH
    mock_llm.assess.return_value = _mock_llm_response(1, 4, 4)

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is not None
    assert result.verdict == Verdict.WATCH
    assert result.override_applied == "Relevance=1 caps at WATCH"


def test_assess_issue_llm_returns_none():
    issue = _make_issue()
    mock_llm = MagicMock()
    mock_llm.assess.return_value = None

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is None


def test_assess_issue_clamps_scores():
    issue = _make_issue()
    mock_llm = MagicMock()
    response = _mock_llm_response()
    response["relevance"] = 10
    response["urgency"] = 0
    mock_llm.assess.return_value = response

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is not None
    assert result.relevance == 5
    assert result.urgency == 1


def test_assess_issue_override_urgency5_relevance3():
    issue = _make_issue()
    mock_llm = MagicMock()
    mock_llm.assess.return_value = _mock_llm_response(3, 5, 1)

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is not None
    assert result.verdict == Verdict.ESCALATE
    assert result.override_applied == "Urgency=5 + Relevance>=3 forces ESCALATE"
