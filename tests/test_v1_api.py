from pathlib import Path

from fastapi.testclient import TestClient

from app.cache.sections import SECTION_TTLS, Section
from app.config import TriageConfig


def _make_config(tmp_path):
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
        worker_mode=True,
    )


def _make_app(tmp_path, populate=False):
    config = _make_config(tmp_path)
    from app.server import create_app

    app = create_app(config)
    if populate:
        _populate_cache(app.state.section_cache)
    return app


def _populate_cache(cache):
    cache.set(
        Section.ISSUES,
        {
            "summary": {
                "new_this_period": 10,
                "by_urgency": {"critical": 1, "high": 3, "medium": 4, "low": 2},
                "period_label": "All time",
                "triage_needed": 5,
                "total_open": 50,
            },
            "critical_list": [],
            "team_breakdown": {
                "agent-ops": {
                    "team_id": "agent-ops",
                    "total": 10,
                    "by_urgency": {"critical": 1, "high": 3, "medium": 4, "low": 2},
                    "new_this_period": 10,
                    "previous_period": 8,
                    "trend": "+2",
                },
            },
            "area_heatmap": [],
            "area_unlabeled": 0,
            "duplicate_clusters": [],
            "no_team_list": [],
            "all_issues": [],
            "team_issues": {},
            "generated_at": "2026-08-14T10:00:00+00:00",
        },
        SECTION_TTLS[Section.ISSUES],
    )
    cache.set(
        Section.PR_HEALTH,
        {"total_open": 20, "awaiting_review": 5, "stale_14d": 2},
        SECTION_TTLS[Section.PR_HEALTH],
    )
    cache.set(
        Section.SYNTHESIS,
        {"narrative": "Test narrative.", "team_synthesis": None},
        SECTION_TTLS[Section.SYNTHESIS],
    )
    cache.set(
        Section.METRICS,
        {
            "triage": [1, 2, 3, 4, 5, 6, 7],
            "prs": [0] * 7,
            "blocked": [0] * 7,
            "velocity": [0] * 7,
        },
        SECTION_TTLS[Section.METRICS],
    )
    return cache


def test_report_503_when_empty(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/v1/report")
    assert resp.status_code == 503
    assert resp.json()["status"] == "warming_up"


def test_report_returns_combined(tmp_path):
    app = _make_app(tmp_path, populate=True)
    client = TestClient(app)
    resp = client.get("/api/v1/report")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total_open"] == 50
    assert data["narrative"] == "Test narrative."
    assert data["pr_health"]["total_open"] == 20
    assert data["sparklines"]["triage"] == [1, 2, 3, 4, 5, 6, 7]
    assert "_meta" in data
    assert "sections" in data["_meta"]


def test_issues_section(tmp_path):
    app = _make_app(tmp_path, populate=True)
    client = TestClient(app)
    resp = client.get("/api/v1/report/issues")
    assert resp.status_code == 200
    body = resp.json()
    assert body["section"] == "issues"
    assert body["data"]["summary"]["total_open"] == 50


def test_issues_section_503_when_empty(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/v1/report/issues")
    assert resp.status_code == 503


def test_pr_health_section(tmp_path):
    app = _make_app(tmp_path, populate=True)
    client = TestClient(app)
    resp = client.get("/api/v1/report/pr-health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["section"] == "pr_health"
    assert body["data"]["total_open"] == 20


def test_pr_health_disabled(tmp_path):
    config = _make_config(tmp_path)
    config.pr_health_enabled = False
    from app.server import create_app

    app = create_app(config)
    client = TestClient(app)
    resp = client.get("/api/v1/report/pr-health")
    assert resp.status_code == 404


def test_synthesis_section(tmp_path):
    app = _make_app(tmp_path, populate=True)
    client = TestClient(app)
    resp = client.get("/api/v1/report/synthesis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["narrative"] == "Test narrative."


def test_metrics_section(tmp_path):
    app = _make_app(tmp_path, populate=True)
    client = TestClient(app)
    resp = client.get("/api/v1/report/metrics")
    assert resp.status_code == 200


def test_meta_endpoint(tmp_path):
    app = _make_app(tmp_path, populate=True)
    client = TestClient(app)
    resp = client.get("/api/v1/report/meta")
    assert resp.status_code == 200
    sections = resp.json()["sections"]
    assert "issues" in sections
    assert "pr_health" in sections
    assert "generated_at" in sections["issues"]


def test_old_endpoints_still_work(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    resp = client.get("/")
    assert resp.status_code == 200


def test_dashboard_serves_shell_immediately(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "loadReport" in resp.text
    assert "/api/v1/report" in resp.text
    assert "loading-skeleton" in resp.text


def test_reload_config(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/api/reload-config",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "reloaded"
    assert body["profile"] == "openshell"
    assert body["repo"] == "NVIDIA/OpenShell"
    assert "agent-ops" in body["teams"]


def test_reload_config_requires_auth(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.post("/api/reload-config")
    assert resp.status_code == 401


def test_profile_name_in_config(tmp_path):
    config = _make_config(tmp_path)
    assert config.profile_name == "openshell"


def test_combined_report_excludes_disabled_pr_health(tmp_path):
    config = _make_config(tmp_path)
    config.pr_health_enabled = False
    from app.server import create_app

    app = create_app(config)
    _populate_cache(app.state.section_cache)
    client = TestClient(app)
    resp = client.get("/api/v1/report")
    assert resp.status_code == 200
    assert resp.json()["pr_health"] is None
