import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import TriageConfig


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
        profiles_dir=Path(__file__).parent.parent / "profiles",
        default_lookback_hours=24,
        report_output_path=None,
    )


@pytest.fixture()
def app(config):
    with patch("app.server._schedule_cycle"):
        from app.server import create_app

        yield create_app(config)


@pytest.fixture()
def client(app):
    return TestClient(app)


def test_health_before_triage(client):
    resp = client.get("/api/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "starting"
    assert data["last_triage"] is None


def test_health_after_triage(app, client):
    app.state.last_triage = "2026-08-04T12:00:00+00:00"
    app.state.issue_count = 5
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["last_triage"] == "2026-08-04T12:00:00+00:00"
    assert data["issue_count"] == 5


def test_dashboard_before_triage(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Triage in progress" in resp.text
    assert 'http-equiv="refresh"' in resp.text


def test_dashboard_serves_cached_html(app, client):
    app.state.cached_html = "<html><body>Dashboard</body></html>"
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


def test_refresh_when_not_running(app, client):
    app.state.last_triage = "2026-08-04T12:00:00+00:00"
    app.state.cycle_lock = threading.Lock()
    with patch("app.server._run_cycle"):
        resp = client.post("/api/refresh")
    assert resp.status_code == 202


def test_refresh_cooldown(app, client):
    app.state.last_triage = "2099-01-01T00:00:00+00:00"
    resp = client.post("/api/refresh")
    assert resp.status_code == 429
