import json
from unittest.mock import MagicMock, patch

import pytest

from app.config import TriageConfig, load_config
from app.core.models import Verdict
from app.triage import run_digest, run_triage


@pytest.fixture()
def config(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    return TriageConfig(
        watch_repos=["NVIDIA/OpenShell"],
        llm_provider="vertex",
        llm_model=None,
        vertex_project_id="test-project",
        vertex_region="us-east5",
        anthropic_api_key=None,
        github_token="test-github-token",
        slack_webhook_url=None,
        state_path=tmp_path / "state.json",
        profiles_dir=profiles_dir,
        default_lookback_hours=24,
    )


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("WATCH_REPOS", "NVIDIA/OpenShell,opendatahub-io/agent-ops")
    monkeypatch.setenv("LLM_PROVIDER", "vertex")
    monkeypatch.setenv("VERTEX_PROJECT_ID", "my-project")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("STATE_PATH", "/tmp/state.json")

    config = load_config()
    assert config.watch_repos == ["NVIDIA/OpenShell", "opendatahub-io/agent-ops"]
    assert config.llm_provider == "vertex"
    assert config.vertex_project_id == "my-project"
    assert config.github_token == "ghp_test"


def test_load_config_defaults(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("VERTEX_PROJECT_ID", "default-project")  # required for vertex
    config = load_config()
    assert config.llm_provider == "vertex"
    assert config.vertex_region == "us-east5"
    assert config.default_lookback_hours == 24


def test_load_config_vertex_missing_project_id_raises(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("LLM_PROVIDER", "vertex")
    monkeypatch.delenv("VERTEX_PROJECT_ID", raising=False)

    with pytest.raises(ValueError, match="VERTEX_PROJECT_ID"):
        load_config()


def test_load_config_anthropic_missing_api_key_raises(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        load_config()


@patch("app.triage.GitHubSource")
@patch("app.triage.create_llm_client")
def test_run_triage_no_new_issues(mock_create_llm, mock_github_cls, config):
    mock_source = MagicMock()
    mock_source.fetch_new_issues.return_value = []
    mock_github_cls.return_value = mock_source

    mock_llm = MagicMock()
    mock_create_llm.return_value = mock_llm

    run_triage(config)

    mock_source.fetch_new_issues.assert_called_once()
    mock_llm.assess.assert_not_called()


@patch("app.triage.GitHubSource")
@patch("app.triage.create_llm_client")
@patch("app.triage.assess_issue")
def test_run_triage_with_escalation(
    mock_assess, mock_create_llm, mock_github_cls, config
):
    from app.core.models import Assessment, IssueData

    mock_source = MagicMock()
    mock_source.fetch_new_issues.return_value = [
        IssueData(
            repo="NVIDIA/OpenShell",
            number=2401,
            title="protobuf sync failed",
            body="Sync failed.",
            labels=["kind/bug"],
            comments=[],
            url="https://github.com/NVIDIA/OpenShell/issues/2401",
            created_at="2026-07-23T14:00:00Z",
        )
    ]
    mock_github_cls.return_value = mock_source

    mock_assess.return_value = Assessment(
        repo="NVIDIA/OpenShell",
        issue_number=2401,
        issue_title="protobuf sync failed",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2401",
        relevance=5,
        relevance_reason="Team-owned",
        urgency=5,
        urgency_reason="Blocker",
        action_clarity=4,
        action_clarity_reason="Clear fix",
        total=14,
        verdict=Verdict.ESCALATE,
        override_applied=None,
        summary="SDK sync failure",
        recommendation="Re-run sync",
        assessed_at="2026-07-23T14:05:00+00:00",
    )

    run_triage(config)

    mock_assess.assert_called_once()
    state = json.loads(config.state_path.read_text())
    assert 2401 in state["seen_issues"]


@patch("app.triage.GitHubSource")
@patch("app.triage.create_llm_client")
@patch("app.triage.assess_issue")
def test_run_triage_track_goes_to_digest(
    mock_assess, mock_create_llm, mock_github_cls, config
):
    from app.core.models import Assessment, IssueData

    mock_source = MagicMock()
    mock_source.fetch_new_issues.return_value = [
        IssueData(
            repo="NVIDIA/OpenShell",
            number=2399,
            title="Helm values issue",
            body="Missing tolerations.",
            labels=[],
            comments=[],
            url="https://github.com/NVIDIA/OpenShell/issues/2399",
            created_at="2026-07-23T12:00:00Z",
        )
    ]
    mock_github_cls.return_value = mock_source

    mock_assess.return_value = Assessment(
        repo="NVIDIA/OpenShell",
        issue_number=2399,
        issue_title="Helm values issue",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2399",
        relevance=4,
        urgency=2,
        action_clarity=5,
        total=11,
        verdict=Verdict.TRACK,
        override_applied=None,
        summary="Missing tolerations",
        recommendation="Add tolerations passthrough",
        relevance_reason="OpenShift area",
        urgency_reason="Not urgent",
        action_clarity_reason="Clear fix",
        assessed_at="2026-07-23T13:05:00+00:00",
    )

    run_triage(config)

    state = json.loads(config.state_path.read_text())
    assert len(state["digest_buffer"]) == 1
    assert state["digest_buffer"][0]["issue_number"] == 2399


def test_run_digest_flushes_buffer(config):
    state = {
        "last_checked": "2026-07-23T14:00:00+00:00",
        "seen_issues": [2399],
        "digest_buffer": [
            {
                "issue_number": 2399,
                "title": "Helm values issue",
                "repo": "NVIDIA/OpenShell",
                "relevance": 4,
                "urgency": 2,
                "action_clarity": 5,
                "verdict": "TRACK",
                "reason": "OpenShift gap",
                "url": "https://github.com/NVIDIA/OpenShell/issues/2399",
                "assessed_at": "2026-07-23T13:05:00+00:00",
            }
        ],
        "seen_timestamps": {},
    }
    config.state_path.write_text(json.dumps(state))

    run_digest(config)

    updated = json.loads(config.state_path.read_text())
    assert updated["digest_buffer"] == []
