from unittest.mock import patch

from app.config import TriageConfig
from app.notifications.log import LogNotifier
from app.notifications.slack import SlackNotifier
from app.triage import _build_llm_client, _build_notifier


def _make_config(tmp_path, **overrides):
    defaults = dict(
        watch_repos=["NVIDIA/OpenShell"],
        llm_provider="vertex",
        llm_model=None,
        vertex_project_id="test-project",
        vertex_region="us-east5",
        anthropic_api_key=None,
        github_token="test-token",
        slack_webhook_url=None,
        state_path=tmp_path / "state.json",
        profiles_dir=tmp_path / "profiles",
        default_lookback_hours=24,
    )
    defaults.update(overrides)
    return TriageConfig(**defaults)


def test_build_notifier_returns_log_when_no_webhook(tmp_path):
    config = _make_config(tmp_path)
    assert isinstance(_build_notifier(config), LogNotifier)


def test_build_notifier_returns_slack_when_webhook_set(tmp_path):
    config = _make_config(tmp_path, slack_webhook_url="https://hooks.slack.com/test")
    assert isinstance(_build_notifier(config), SlackNotifier)


@patch("app.triage.create_llm_client")
def test_build_llm_client_vertex(mock_create, tmp_path):
    config = _make_config(
        tmp_path,
        llm_provider="vertex",
        vertex_project_id="my-proj",
        vertex_region="us-central1",
    )
    _build_llm_client(config)
    mock_create.assert_called_once_with(
        "vertex", project_id="my-proj", region="us-central1"
    )


@patch("app.triage.create_llm_client")
def test_build_llm_client_anthropic(mock_create, tmp_path):
    config = _make_config(
        tmp_path, llm_provider="anthropic", anthropic_api_key="sk-test"
    )
    _build_llm_client(config)
    mock_create.assert_called_once_with("anthropic", api_key="sk-test")
