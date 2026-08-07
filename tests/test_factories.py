from pathlib import Path
from unittest.mock import patch

from app.config import TriageConfig
from app.core.llm import build_llm_client


def _make_config(tmp_path, **overrides):
    defaults = {
        "watch_repos": ["NVIDIA/OpenShell"],
        "llm_provider": "vertex",
        "llm_model": None,
        "vertex_project_id": "test-project",
        "vertex_region": "us-east5",
        "anthropic_api_key": None,
        "github_token": "ghp_test",
        "slack_webhook_url": None,
        "state_path": tmp_path / "state.json",
        "assessment_log_path": tmp_path / "assessments.jsonl",
        "profiles_dir": Path(__file__).parent.parent / "profiles",
        "default_lookback_hours": 24,
        "report_output_path": None,
    }
    defaults.update(overrides)
    return TriageConfig(**defaults)


def test_build_llm_client_vertex(tmp_path):
    config = _make_config(tmp_path, llm_provider="vertex")
    with patch("app.core.llm.create_llm_client") as mock_create:
        build_llm_client(config)
        mock_create.assert_called_once_with(
            "vertex", project_id="test-project", region="us-east5"
        )


def test_build_llm_client_anthropic(tmp_path):
    config = _make_config(
        tmp_path, llm_provider="anthropic", anthropic_api_key="sk-test"
    )
    with patch("app.core.llm.create_llm_client") as mock_create:
        build_llm_client(config)
        mock_create.assert_called_once_with("anthropic", api_key="sk-test")
