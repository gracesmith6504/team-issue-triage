import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import TriageConfig, load_config
from app.triage import run_triage


@pytest.fixture()
def config(tmp_path):
    return TriageConfig(
        watch_repos=["NVIDIA/OpenShell"],
        llm_provider="vertex",
        llm_model=None,
        vertex_project_id="test-project",
        vertex_region="us-east5",
        anthropic_api_key=None,
        github_token="ghp_test",
        slack_webhook_url=None,
        state_path=tmp_path / "state.json",
        assessment_log_path=tmp_path / "assessments.jsonl",
        profiles_dir=Path(__file__).parent.parent.parent / "profiles",
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
    monkeypatch.setenv("VERTEX_PROJECT_ID", "default-project")
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


def test_load_config_invalid_provider_raises(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        load_config()


def test_load_config_missing_github_token_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "vertex")
    monkeypatch.setenv("VERTEX_PROJECT_ID", "test-project")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        load_config()


def test_load_config_from_env_anthropic():
    env = {
        "GITHUB_TOKEN": "ghp_test",
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-test",
        "STATE_PATH": "/tmp/state.json",
    }
    with patch.dict("os.environ", env, clear=False):
        config = load_config()
    assert config.github_token == "ghp_test"
    assert config.llm_provider == "anthropic"


def test_run_triage_no_new_issues(config):
    with (
        patch("app.triage.GitHubSource") as mock_source_cls,
        patch("app.triage.create_llm_client") as mock_llm_factory,
    ):
        mock_source = MagicMock()
        mock_source.fetch_new_issues.return_value = []
        mock_source_cls.return_value = mock_source
        mock_llm_factory.return_value = MagicMock()

        run_triage(config)

        mock_source.fetch_new_issues.assert_called_once()
        assert config.state_path.exists()


def test_run_triage_with_classification(config):
    from app.core.models import IssueData

    mock_issue = IssueData(
        repo="NVIDIA/OpenShell",
        number=2571,
        title="bug(supervisor): SPIFFE crash",
        body="SPIFFE sandboxes crash on restart",
        labels=["Bug"],
        comments=[],
        url="https://github.com/NVIDIA/OpenShell/issues/2571",
        created_at="2026-08-01T00:00:00Z",
    )

    with (
        patch("app.triage.GitHubSource") as mock_source_cls,
        patch("app.triage.create_llm_client") as mock_llm_factory,
    ):
        mock_source = MagicMock()
        mock_source.fetch_new_issues.return_value = [mock_issue]
        mock_source_cls.return_value = mock_source

        mock_llm = MagicMock()
        mock_llm.assess.return_value = {
            "reasoning": "SPIFFE is security",
            "any_team_cares": True,
            "primary_team": "ai-safety",
            "primary_confidence": 0.85,
            "secondary_team": "agent-ops",
            "secondary_confidence": 0.65,
            "urgency": "high",
            "urgency_reasoning": "Security crash",
            "summary": "SPIFFE crash",
            "recommendation": "Investigate",
        }
        mock_llm_factory.return_value = mock_llm

        run_triage(config)

        assert config.assessment_log_path.exists()
        records = json.loads(config.assessment_log_path.read_text().strip())
        assert records["primary_team"] == "ai-safety"

        state = json.loads(config.state_path.read_text())
        assert "NVIDIA/OpenShell#2571" in state["seen_issues"]


def test_run_triage_dedup_across_runs(config):
    """Second run should not re-process issues seen in the first run."""
    from app.core.models import IssueData

    mock_issue = IssueData(
        repo="NVIDIA/OpenShell",
        number=2571,
        title="bug(supervisor): SPIFFE crash",
        body="SPIFFE sandboxes crash on restart",
        labels=["Bug"],
        comments=[],
        url="https://github.com/NVIDIA/OpenShell/issues/2571",
        created_at="2026-08-01T00:00:00Z",
    )

    llm_response = {
        "reasoning": "SPIFFE is security",
        "any_team_cares": True,
        "primary_team": "ai-safety",
        "primary_confidence": 0.85,
        "secondary_team": None,
        "secondary_confidence": None,
        "urgency": "high",
        "urgency_reasoning": "Security crash",
        "summary": "SPIFFE crash",
        "recommendation": "Investigate",
    }

    with (
        patch("app.triage.GitHubSource") as mock_source_cls,
        patch("app.triage.create_llm_client") as mock_llm_factory,
    ):
        mock_source = MagicMock()
        mock_source.fetch_new_issues.return_value = [mock_issue]
        mock_source_cls.return_value = mock_source

        mock_llm = MagicMock()
        mock_llm.assess.return_value = llm_response
        mock_llm_factory.return_value = mock_llm

        # First run: issue is processed
        run_triage(config)
        assert mock_llm.assess.call_count == 1

        # Second run: same issue should be deduped via seen_numbers
        mock_llm.assess.reset_mock()
        mock_source.fetch_new_issues.reset_mock()
        mock_source.fetch_new_issues.return_value = [mock_issue]

        run_triage(config)

        # Verify that seen_numbers (with int 2571) was passed, not the
        # namespaced string set
        call_args = mock_source.fetch_new_issues.call_args
        seen_arg = call_args[0][2]
        assert 2571 in seen_arg
        assert isinstance(seen_arg, set)
        for item in seen_arg:
            assert isinstance(item, int)
