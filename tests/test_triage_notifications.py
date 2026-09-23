import logging
from pathlib import Path

from app.core.profiles import load_repo_config
from app.triage import _build_notification_router

PROFILES_DIR = Path(__file__).parent.parent / "profiles"


def _agent_ops_channels():
    repo_config = load_repo_config("openshell", profiles_dir=PROFILES_DIR)
    router = _build_notification_router(repo_config)
    return router.team_configs["agent-ops"].channels


def test_missing_webhook_env_var_skips_channel_and_warns(monkeypatch, caplog):
    monkeypatch.delenv("SLACK_WEBHOOK_AGENT_OPS", raising=False)

    with caplog.at_level(logging.WARNING, logger="app.triage"):
        channels = _agent_ops_channels()

    assert "slack_webhook" not in [c.adapter_type for c in channels]
    assert "log" in [c.adapter_type for c in channels]
    assert any(
        "SLACK_WEBHOOK_AGENT_OPS" in r.getMessage() and r.levelno == logging.WARNING
        for r in caplog.records
    )


def test_webhook_env_var_set_creates_channel_with_real_url(monkeypatch):
    monkeypatch.setenv(
        "SLACK_WEBHOOK_AGENT_OPS", "https://hooks.slack.com/services/T/B/X"
    )

    channels = _agent_ops_channels()

    slack = [c for c in channels if c.adapter_type == "slack_webhook"]
    assert len(slack) == 1
    assert slack[0].config["webhook_url"] == "https://hooks.slack.com/services/T/B/X"
