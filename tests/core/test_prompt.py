from app.core.models import IssueData
from app.core.profiles import TeamProfile
from app.core.prompt import build_system_prompt, build_user_prompt


def _make_profile():
    return TeamProfile(
        name="test",
        repos=["NVIDIA/OpenShell"],
        team_name="Agent Ops",
        team_context="The team works on OpenShift integration.",
        pinned_version="v0.0.85",
        urgency_rules="Release blockers are urgency 5.",
        calibration_examples=[
            {
                "summary": "protobuf sync failed",
                "scores": "Relevance=5 Urgency=5 Action=4",
                "verdict": "ESCALATE",
                "reason": "Release blocker",
            }
        ],
    )


def _make_issue():
    return IssueData(
        repo="NVIDIA/OpenShell",
        number=2401,
        title="protobuf sync failed",
        body="The sync job failed with error code 1.",
        labels=["kind/bug"],
        comments=[{"user": "bot", "body": "Auto-created"}],
        url="https://github.com/NVIDIA/OpenShell/issues/2401",
        created_at="2026-07-23T14:00:00Z",
    )


def test_system_prompt_no_profile():
    prompt = build_system_prompt()
    assert "relevance" in prompt.lower()
    assert "urgency" in prompt.lower()
    assert "action_clarity" in prompt.lower() or "action clarity" in prompt.lower()
    assert "JSON" in prompt


def test_system_prompt_with_profile():
    profile = _make_profile()
    prompt = build_system_prompt(profile)
    assert "Agent Ops" in prompt
    assert "OpenShift integration" in prompt
    assert "v0.0.85" in prompt
    assert "Release blockers are urgency 5" in prompt
    assert "protobuf sync failed" in prompt


def test_user_prompt_includes_issue_data():
    issue = _make_issue()
    prompt = build_user_prompt(issue)
    assert "protobuf sync failed" in prompt
    assert "#2401" in prompt or "2401" in prompt
    assert "NVIDIA/OpenShell" in prompt
    assert "kind/bug" in prompt
    assert "Auto-created" in prompt


def test_user_prompt_no_comments():
    issue = _make_issue()
    issue.comments = []
    prompt = build_user_prompt(issue)
    assert "(no comments)" in prompt


def test_user_prompt_no_labels():
    issue = _make_issue()
    issue.labels = []
    prompt = build_user_prompt(issue)
    assert "none" in prompt.lower()
