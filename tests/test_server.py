import json
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
        api_token="test-token",
    )


@pytest.fixture()
def app(config):
    with patch("app.refresh.scheduler.SectionRefresher"):
        from app.server import create_app

        yield create_app(config)


@pytest.fixture()
def client(app):
    return TestClient(app)


def test_health_before_triage(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
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
    assert "<!DOCTYPE html>" in resp.text
    assert "loadReport" in resp.text


def test_dashboard_serves_cached_html(app, client):
    app.state.cached_html = "<html><body>Dashboard</body></html>"
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


def test_refresh_when_not_running(app, client):
    app.state.last_triage = "2026-08-04T12:00:00+00:00"
    app.state.cycle_lock = threading.Lock()
    resp = client.post("/api/refresh")
    assert resp.status_code == 202


def test_refresh_cooldown(app, client):
    app.state.last_report = "2099-01-01T00:00:00+00:00"
    resp = client.post("/api/refresh")
    assert resp.status_code == 429


def test_get_state_unauthenticated(client):
    resp = client.get("/api/state")
    assert resp.status_code == 200


def test_get_state_with_auth(client):
    resp = client.get("/api/state", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert "last_checked" in data
    assert "seen_issues" in data


def test_post_assessments_unauthorized(client):
    resp = client.post("/api/assessments", json={"results": []})
    assert resp.status_code == 401


def test_post_assessments_empty(client):
    resp = client.post(
        "/api/assessments",
        json={"results": []},
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 400


def test_post_assessments_saves(app, client):
    result = {
        "repo": "NVIDIA/OpenShell",
        "issue_number": 123,
        "issue_title": "Test issue",
        "issue_url": "https://github.com/NVIDIA/OpenShell/issues/123",
        "reasoning": "test",
        "any_team_cares": True,
        "primary_team": "agent-ops",
        "primary_confidence": 0.9,
        "secondary_team": None,
        "secondary_confidence": None,
        "urgency": "medium",
        "urgency_reasoning": "not urgent",
        "summary": "A test issue",
        "recommendation": "investigate",
        "confidence_flag": None,
        "assessed_at": "2026-08-13T12:00:00+00:00",
        "created_at": "2026-08-13T10:00:00+00:00",
        "author_association": "NONE",
        "author_login": "testuser",
        "labels": ["bug"],
        "closed": False,
    }
    resp = client.post(
        "/api/assessments",
        json={"results": [result]},
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["saved"] == 1
    assert data["total_submitted"] == 1

    config = app.state.config
    assert config.assessment_log_path.exists()
    with open(config.assessment_log_path) as f:
        saved = json.loads(f.readline())
    assert saved["issue_number"] == 123
    assert saved["primary_team"] == "agent-ops"


def test_trigger_report_unauthorized(client):
    resp = client.post("/api/report/trigger")
    assert resp.status_code == 401
