# tests/core/test_prompt.py
from app.core.models import IssueData, IssueSignals
from app.core.profiles import RepoConfig, TeamProfile
from app.core.prompt import build_system_prompt, build_user_prompt


def _make_team(team_id, name, description, primary=None, secondary=None, examples=None):
    return TeamProfile(
        team_id=team_id,
        team_name=name,
        description=description,
        areas={"primary": primary or [], "secondary": secondary or []},
        urgency_overrides={},
        examples=examples or [],
        notifications={},
    )


def _make_repo_config(teams=None, no_team_prefixes=None, none_examples=None):
    if teams is None:
        teams = [
            _make_team(
                "agent-ops", "Agent Ops", "Core integration", primary=["cli", "sdk"]
            ),
            _make_team(
                "acp", "ACP", "Hosted mode", primary=["gateway"], secondary=["cluster"]
            ),
        ]
    return RepoConfig(
        repo="NVIDIA/OpenShell",
        pinned_version="v0.0.92",
        team_profiles=teams,
        no_team_prefixes=no_team_prefixes or ["build", "tui"],
        none_examples=none_examples
        or [{"title": "feat(build): Bazel", "reasoning": "No team"}],
        confidence_thresholds={
            "auto_assign": 0.8,
            "multi_team_gap": 0.2,
            "uncertain": 0.5,
            "none_min": 0.75,
        },
        reporting={},
    )


def _make_issue():
    return IssueData(
        repo="NVIDIA/OpenShell",
        number=2571,
        title="bug(supervisor): SPIFFE crash",
        body="SPIFFE sandboxes crash on restart",
        labels=["area:supervisor", "topic:security", "Bug"],
        comments=[{"user": "dev", "body": "Investigating"}],
        url="https://github.com/NVIDIA/OpenShell/issues/2571",
        created_at="2026-08-01T00:00:00Z",
    )


def _make_signals():
    return IssueSignals(
        title_prefix="supervisor",
        area_labels=["area:supervisor"],
        topic_labels=["topic:security"],
        state_label=None,
        issue_type="Bug",
    )


def test_system_prompt_contains_team_descriptions():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "agent-ops" in prompt
    assert "Agent Ops" in prompt
    assert "Core integration" in prompt
    assert "acp" in prompt
    assert "ACP" in prompt
    assert "Hosted mode" in prompt


def test_system_prompt_contains_routing_table():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "cli" in prompt
    assert "sdk" in prompt
    assert "gateway" in prompt


def test_system_prompt_contains_none_rows():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "build" in prompt
    assert "tui" in prompt
    assert "NONE" in prompt


def test_system_prompt_contains_prefix_misleads_guidance():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "problem domain" in prompt.lower() or "PROBLEM domain" in prompt
    assert "prefix" in prompt.lower()


def test_system_prompt_contains_urgency_scale():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "critical" in prompt.lower()
    assert "high" in prompt.lower()
    assert "medium" in prompt.lower()
    assert "low" in prompt.lower()


def test_system_prompt_contains_output_format():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "reasoning" in prompt
    assert "any_team_cares" in prompt
    assert "primary_team" in prompt
    assert "primary_confidence" in prompt


def test_system_prompt_contains_calibration_examples():
    teams = [
        _make_team(
            "agent-ops",
            "Agent Ops",
            "Core",
            primary=["cli"],
            examples=[
                {
                    "title": "SDK sync failed",
                    "urgency": "critical",
                    "reasoning": "Blocks release",
                }
            ],
        ),
    ]
    config = _make_repo_config(teams=teams)
    prompt = build_system_prompt(config)
    assert "SDK sync failed" in prompt


def test_system_prompt_contains_none_examples():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "feat(build): Bazel" in prompt


def test_user_prompt_contains_signals():
    issue = _make_issue()
    signals = _make_signals()
    prompt = build_user_prompt(issue, signals)
    assert "supervisor" in prompt
    assert "area:supervisor" in prompt
    assert "topic:security" in prompt
    assert "Bug" in prompt


def test_user_prompt_contains_issue_data():
    issue = _make_issue()
    signals = _make_signals()
    prompt = build_user_prompt(issue, signals)
    assert "bug(supervisor): SPIFFE crash" in prompt
    assert "SPIFFE sandboxes crash on restart" in prompt
    assert "#2571" in prompt or "2571" in prompt


def test_user_prompt_no_signals():
    issue = _make_issue()
    signals = IssueSignals(
        title_prefix=None,
        area_labels=[],
        topic_labels=[],
        state_label=None,
        issue_type=None,
    )
    prompt = build_user_prompt(issue, signals)
    assert "bug(supervisor): SPIFFE crash" in prompt
    assert "(none)" in prompt.lower() or "None" in prompt
