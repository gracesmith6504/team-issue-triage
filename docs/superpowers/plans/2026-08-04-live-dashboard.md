# Live Dashboard with Status Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the triage dashboard as a live web page from an OpenShift cluster, with real-time GitHub status enrichment (open/closed, comments, linked PRs) so the data is never stale.

**Architecture:** A single FastAPI Deployment replaces CronJobs for the dashboard use case. It runs triage on a background schedule, enriches issues with current GitHub state, generates the HTML report, and caches it in memory. `GET /` serves the cached HTML instantly. The existing CronJob YAMLs remain as an alternative batch-only deployment mode.

**Tech Stack:** FastAPI 0.115+, Uvicorn 0.30+, GitHub REST API, OpenShift Route (edge TLS), threading.Timer for scheduling, Chart.js 4.5.1 (existing).

## Global Constraints

- Python 3.12+. No new dependencies beyond `fastapi` and `uvicorn`.
- All tests must pass: `python3 -m pytest tests/ -v`
- All lint must pass: `make lint` (ruff check + ruff format)
- Never include `Co-Authored-By` in commit messages.
- Non-root container: UID 1001, `runAsNonRoot: true`, `allowPrivilegeEscalation: false`.
- Existing `--mode report` (CLI) must continue to work unchanged — enrichment is optional.
- Port 8080 for the web server (OpenShift non-root convention).
- All GitHub API calls must handle errors gracefully — never crash the dashboard.
- Follow existing patterns: `@patch` for mocking, `MagicMock` for fakes, `pytest` fixtures with `tmp_path`.

---

### Task 1: Status enrichment module

Build the `enrich_issues()` function that calls the GitHub API to get each issue's current state (open/closed, comment count, assignees, linked PRs). This is the data layer that makes the dashboard show live information.

**Files:**
- Create: `app/sources/enrichment.py`
- Create: `tests/sources/test_enrichment.py`

**Interfaces:**
- Consumes: `TriageResult` from `app/core/models.py` (fields: `repo`, `issue_number`, `issue_url`)
- Consumes: `GITHUB_API` constant from `app/sources/github.py` (value: `"https://api.github.com"`)
- Produces: `EnrichedIssue` dataclass — used by Task 3 (`render_html`) and Task 2 (`app/server.py`)
- Produces: `enrich_issues(results: list[TriageResult], token: str) -> dict[int, EnrichedIssue]` — returns dict keyed by issue_number

- [ ] **Step 1: Write the tests**

Add to `tests/sources/test_enrichment.py`:

```python
from unittest.mock import MagicMock, patch

from app.core.models import TriageResult, Urgency
from app.sources.enrichment import EnrichedIssue, enrich_issues


def _make_result(number, repo="NVIDIA/OpenShell"):
    return TriageResult(
        repo=repo,
        issue_number=number,
        issue_title=f"Issue {number}",
        issue_url=f"https://github.com/{repo}/issues/{number}",
        reasoning="test",
        any_team_cares=True,
        primary_team="agent-ops",
        primary_confidence=0.9,
        secondary_team=None,
        secondary_confidence=None,
        urgency=Urgency.MEDIUM,
        urgency_reasoning="test",
        summary="test",
        recommendation="test",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00+00:00",
    )


@patch("app.sources.enrichment.requests.get")
def test_enrich_issues_basic(mock_get):
    issue_resp = MagicMock()
    issue_resp.status_code = 200
    issue_resp.json.return_value = {
        "state": "open",
        "comments": 5,
        "assignees": [{"login": "alice"}],
    }

    timeline_resp = MagicMock()
    timeline_resp.status_code = 200
    timeline_resp.json.return_value = []

    mock_get.side_effect = [issue_resp, timeline_resp]

    results = [_make_result(42)]
    enriched = enrich_issues(results, "ghp_test")

    assert 42 in enriched
    assert enriched[42].is_open is True
    assert enriched[42].comment_count == 5
    assert enriched[42].assignees == ["alice"]
    assert enriched[42].has_linked_pr is False
    assert enriched[42].result is results[0]


@patch("app.sources.enrichment.requests.get")
def test_enrich_detects_linked_pr(mock_get):
    issue_resp = MagicMock()
    issue_resp.status_code = 200
    issue_resp.json.return_value = {
        "state": "open",
        "comments": 1,
        "assignees": [],
    }

    timeline_resp = MagicMock()
    timeline_resp.status_code = 200
    timeline_resp.json.return_value = [
        {"event": "commented"},
        {
            "event": "cross-referenced",
            "source": {"issue": {"pull_request": {"url": "https://..."}}},
        },
    ]

    mock_get.side_effect = [issue_resp, timeline_resp]

    enriched = enrich_issues([_make_result(10)], "ghp_test")
    assert enriched[10].has_linked_pr is True


@patch("app.sources.enrichment.requests.get")
def test_enrich_closed_issue(mock_get):
    issue_resp = MagicMock()
    issue_resp.status_code = 200
    issue_resp.json.return_value = {
        "state": "closed",
        "comments": 3,
        "assignees": [],
    }

    timeline_resp = MagicMock()
    timeline_resp.status_code = 200
    timeline_resp.json.return_value = []

    mock_get.side_effect = [issue_resp, timeline_resp]

    enriched = enrich_issues([_make_result(7)], "ghp_test")
    assert enriched[7].is_open is False


@patch("app.sources.enrichment.requests.get")
def test_enrich_fallback_on_api_error(mock_get):
    error_resp = MagicMock()
    error_resp.status_code = 403
    error_resp.text = "Rate limited"

    mock_get.return_value = error_resp

    enriched = enrich_issues([_make_result(99)], "ghp_test")
    assert 99 in enriched
    assert enriched[99].is_open is True
    assert enriched[99].comment_count == 0
    assert enriched[99].assignees == []
    assert enriched[99].has_linked_pr is False


@patch("app.sources.enrichment.requests.get")
def test_enrich_deduplicates_by_issue_number(mock_get):
    issue_resp = MagicMock()
    issue_resp.status_code = 200
    issue_resp.json.return_value = {
        "state": "open",
        "comments": 2,
        "assignees": [],
    }

    timeline_resp = MagicMock()
    timeline_resp.status_code = 200
    timeline_resp.json.return_value = []

    mock_get.side_effect = [issue_resp, timeline_resp]

    results = [_make_result(42), _make_result(42)]
    enriched = enrich_issues(results, "ghp_test")

    assert len(enriched) == 1
    assert mock_get.call_count == 2  # one issue call + one timeline call


@patch("app.sources.enrichment.requests.get")
def test_enrich_empty_list(mock_get):
    enriched = enrich_issues([], "ghp_test")
    assert enriched == {}
    mock_get.assert_not_called()


@patch("app.sources.enrichment.requests.get")
def test_enrich_sets_auth_header(mock_get):
    issue_resp = MagicMock()
    issue_resp.status_code = 200
    issue_resp.json.return_value = {
        "state": "open",
        "comments": 0,
        "assignees": [],
    }

    timeline_resp = MagicMock()
    timeline_resp.status_code = 200
    timeline_resp.json.return_value = []

    mock_get.side_effect = [issue_resp, timeline_resp]

    enrich_issues([_make_result(1)], "ghp_secret")

    for call in mock_get.call_args_list:
        headers = call[1].get("headers", {})
        assert headers["Authorization"] == "token ghp_secret"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/sources/test_enrichment.py -v`
Expected: FAIL with ImportError (`cannot import name 'EnrichedIssue' from 'app.sources.enrichment'`)

- [ ] **Step 3: Implement the enrichment module**

Create `app/sources/enrichment.py`:

```python
import logging
from dataclasses import dataclass

import requests

from app.core.models import TriageResult
from app.sources.github import GITHUB_API

logger = logging.getLogger(__name__)


@dataclass
class EnrichedIssue:
    result: TriageResult
    is_open: bool
    comment_count: int
    assignees: list[str]
    has_linked_pr: bool


def enrich_issues(
    results: list[TriageResult], token: str
) -> dict[int, EnrichedIssue]:
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    seen: set[int] = set()
    enriched: dict[int, EnrichedIssue] = {}

    for result in results:
        if result.issue_number in seen:
            continue
        seen.add(result.issue_number)

        issue_data = _fetch_issue(result.repo, result.issue_number, headers)
        has_pr = _check_linked_pr(result.repo, result.issue_number, headers)

        enriched[result.issue_number] = EnrichedIssue(
            result=result,
            is_open=issue_data.get("state", "open") == "open",
            comment_count=issue_data.get("comments", 0),
            assignees=[
                a.get("login", "") for a in issue_data.get("assignees", [])
            ],
            has_linked_pr=has_pr,
        )

    return enriched


def _fetch_issue(repo: str, number: int, headers: dict) -> dict:
    url = f"{GITHUB_API}/repos/{repo}/issues/{number}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                "Enrichment failed for %s#%d: %s", repo, number, resp.status_code
            )
            return {}
        return resp.json()
    except Exception:
        logger.exception("Enrichment request failed for %s#%d", repo, number)
        return {}


def _check_linked_pr(repo: str, number: int, headers: dict) -> bool:
    url = f"{GITHUB_API}/repos/{repo}/issues/{number}/timeline"
    timeline_headers = {
        **headers,
        "Accept": "application/vnd.github.mockingbird-preview+json",
    }
    try:
        resp = requests.get(url, headers=timeline_headers, timeout=10)
        if resp.status_code != 200:
            return False
        for event in resp.json():
            if event.get("event") == "cross-referenced":
                source_issue = event.get("source", {}).get("issue", {})
                if source_issue.get("pull_request"):
                    return True
        return False
    except Exception:
        logger.exception("Timeline request failed for %s#%d", repo, number)
        return False
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/sources/test_enrichment.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Run linter**

Run: `make lint`
Expected: PASS. If format fails, run `python3 -m ruff format app/ tests/` then re-check.

- [ ] **Step 6: Commit**

```bash
git add app/sources/enrichment.py tests/sources/test_enrichment.py
git commit -m "feat: add status enrichment module for live GitHub issue state"
```

---

### Task 2: FastAPI web server with background scheduler

Build the FastAPI application that serves the cached dashboard HTML and runs triage on a background schedule.

**Files:**
- Create: `app/server.py`
- Create: `tests/test_server.py`
- Modify: `app/__main__.py:11-15` (add `"serve"` to mode choices)
- Modify: `app/__main__.py:35-42` (add `elif args.mode == "serve"` branch)
- Modify: `requirements.txt` (add fastapi, uvicorn)

**Interfaces:**
- Consumes: `load_config() -> TriageConfig` from `app/config.py`
- Consumes: `run_triage(config: TriageConfig) -> None` from `app/triage.py`
- Consumes: `run_report(config: TriageConfig, *, output_path, fmt) -> None` from `app/triage.py`
- Consumes: `enrich_issues(results: list[TriageResult], token: str) -> dict[int, EnrichedIssue]` from Task 1
- Consumes: `read_results_as_triage(log_path: Path, **kwargs) -> list[TriageResult]` from `app/state/assessment_log.py`
- Consumes: `render_html(report: BirdsEyeReport, enrichment: dict[int, EnrichedIssue] | None) -> str` from Task 3
- Produces: `start_server(config: TriageConfig) -> None` — called from `__main__.py`
- Produces: `create_app(config: TriageConfig) -> FastAPI` — for TestClient in tests

- [ ] **Step 1: Add dependencies**

Modify `requirements.txt` — append these two lines after the existing entries:

```
fastapi>=0.115.0
uvicorn>=0.30.0
```

- [ ] **Step 2: Write the tests**

Create `tests/test_server.py`:

```python
import threading
from unittest.mock import MagicMock, patch
from pathlib import Path

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

        return create_app(config)


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


def test_refresh_when_running(app, client):
    app.state.last_triage = "2026-08-04T12:00:00+00:00"
    lock = threading.Lock()
    lock.acquire()
    app.state.cycle_lock = lock
    resp = client.post("/api/refresh")
    assert resp.status_code == 409
    lock.release()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_server.py -v`
Expected: FAIL with ImportError (`No module named 'app.server'`)

- [ ] **Step 4: Implement the server**

Create `app/server.py`:

```python
import logging
import threading
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import TriageConfig
from app.sources.enrichment import enrich_issues
from app.state.assessment_log import read_results_as_triage

logger = logging.getLogger(__name__)

_REFRESH_COOLDOWN_SECONDS = 300

_LOADING_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="30">
<title>OpenShell Triage Dashboard</title>
<style>
  body { font-family: 'Inter', sans-serif; background: #0F172A; color: #F1F5F9;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; }
  .msg { text-align: center; }
  .msg h1 { font-size: 24px; margin-bottom: 8px; }
  .msg p { color: #94A3B8; }
</style>
</head>
<body>
<div class="msg">
  <h1>Triage in progress</h1>
  <p>The first triage cycle is running. This page will refresh automatically.</p>
</div>
</body>
</html>
"""


def create_app(config: TriageConfig) -> FastAPI:
    app = FastAPI(title="OpenShell Triage Dashboard", docs_url=None, redoc_url=None)

    app.state.config = config
    app.state.cached_html = None
    app.state.last_triage = None
    app.state.issue_count = 0
    app.state.cycle_lock = threading.Lock()

    @app.on_event("startup")
    async def on_startup():
        _schedule_cycle(app)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        if app.state.cached_html is None:
            return HTMLResponse(_LOADING_HTML)
        return HTMLResponse(app.state.cached_html)

    @app.get("/api/health")
    async def health():
        if app.state.last_triage is None:
            return JSONResponse(
                {"status": "starting", "last_triage": None, "issue_count": 0},
                status_code=503,
            )
        return {
            "status": "ok",
            "last_triage": app.state.last_triage,
            "issue_count": app.state.issue_count,
        }

    @app.post("/api/refresh")
    async def refresh():
        if app.state.last_triage:
            last = datetime.fromisoformat(app.state.last_triage)
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < _REFRESH_COOLDOWN_SECONDS:
                return JSONResponse(
                    {"error": "Refresh cooldown active", "retry_after_seconds": int(_REFRESH_COOLDOWN_SECONDS - elapsed)},
                    status_code=429,
                )

        if not app.state.cycle_lock.acquire(blocking=False):
            return JSONResponse(
                {"error": "Triage cycle already running"},
                status_code=409,
            )
        app.state.cycle_lock.release()

        thread = threading.Thread(target=_run_cycle, args=(app,), daemon=True)
        thread.start()
        return JSONResponse({"status": "accepted"}, status_code=202)

    return app


def _schedule_cycle(app: FastAPI) -> None:
    thread = threading.Thread(target=_run_cycle, args=(app,), daemon=True)
    thread.start()


def _run_cycle(app: FastAPI) -> None:
    if not app.state.cycle_lock.acquire(blocking=False):
        logger.info("Cycle already running, skipping")
        return

    try:
        config = app.state.config
        logger.info("Starting triage cycle")

        from app.triage import run_triage

        try:
            run_triage(config)
        except Exception:
            logger.exception("Triage failed, will serve stale data")

        results = read_results_as_triage(config.assessment_log_path)

        enrichment = {}
        try:
            enrichment = enrich_issues(results, config.github_token)
        except Exception:
            logger.exception("Enrichment failed, rendering without enrichment")

        from app.reports.birds_eye import BirdsEyeReportGenerator
        from app.core.llm import create_llm_client, resolve_model
        from app.core.profiles import load_repo_config
        from datetime import timedelta

        repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
        reporting = repo_config.reporting

        now = datetime.now(timezone.utc)
        period_days = 7 if reporting.get("period") == "weekly" else 1

        weekday_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        target_weekday = weekday_map.get(
            reporting.get("period_start", "monday"), 0
        )
        days_since = (now.weekday() - target_weekday) % 7
        current_start = (now - timedelta(days=days_since)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        previous_start = current_start - timedelta(days=period_days)

        current = read_results_as_triage(
            config.assessment_log_path,
            start_date=current_start.isoformat(),
        )
        previous = read_results_as_triage(
            config.assessment_log_path,
            start_date=previous_start.isoformat(),
            end_date=current_start.isoformat(),
        )

        period_label = (
            f"{current_start.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"
        )

        llm_client = _build_llm_client(config)
        model = resolve_model(config.llm_provider, config.llm_model)

        generator = BirdsEyeReportGenerator(
            current, previous, llm_client, model, period_label
        )
        report = generator.generate()

        from app.reports.renderers.html import render_html

        app.state.cached_html = render_html(report, enrichment=enrichment)
        app.state.last_triage = now.isoformat()
        app.state.issue_count = len(current)

        logger.info("Triage cycle complete: %d issues", len(current))
    except Exception:
        logger.exception("Triage cycle failed")
    finally:
        app.state.cycle_lock.release()
        _schedule_next(app)


def _build_llm_client(config: TriageConfig):
    from app.core.llm import create_llm_client

    if config.llm_provider == "anthropic":
        return create_llm_client("anthropic", api_key=config.anthropic_api_key)
    return create_llm_client(
        "vertex",
        project_id=config.vertex_project_id,
        region=config.vertex_region,
    )


def _schedule_next(app: FastAPI) -> None:
    timer = threading.Timer(3600, _run_cycle, args=(app,))
    timer.daemon = True
    timer.start()


def start_server(config: TriageConfig) -> None:
    app = create_app(config)
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
```

- [ ] **Step 5: Update `__main__.py`**

In `app/__main__.py`, change the mode choices on line 14 from:

```python
        choices=["triage", "digest", "review", "report"],
```

to:

```python
        choices=["triage", "digest", "review", "report", "serve"],
```

And add the serve branch after the report branch (after line 40):

```python
    elif args.mode == "serve":
        from app.server import start_server

        start_server(config)
```

- [ ] **Step 6: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS (existing tests + 7 new server tests)

- [ ] **Step 7: Run linter**

Run: `make lint`
Expected: PASS. If format fails, run `python3 -m ruff format app/ tests/` then re-check.

- [ ] **Step 8: Commit**

```bash
git add app/server.py tests/test_server.py app/__main__.py requirements.txt
git commit -m "feat: add FastAPI dashboard server with background triage scheduler"
```

---

### Task 3: Integrate enrichment data into the HTML renderer

Update `render_html()` to accept optional enrichment data and display live issue status in the dashboard — closed badges, comment counts, linked PR indicators.

**Files:**
- Modify: `app/reports/renderers/html.py:25-36` (`render_html` signature and `_report_to_dict` call)
- Modify: `app/reports/renderers/html.py:39-1085` (CSS additions and JS rendering updates in `_HTML_TEMPLATE`)
- Modify: `tests/reports/test_html_renderer.py` (add enrichment tests)

**Interfaces:**
- Consumes: `EnrichedIssue` from `app/sources/enrichment.py` (Task 1) — fields: `is_open`, `comment_count`, `assignees`, `has_linked_pr`
- Consumes: existing `_report_to_dict(report) -> dict` and `render_html(report) -> str`
- Produces: `render_html(report: BirdsEyeReport, enrichment: dict[int, EnrichedIssue] | None = None) -> str` — updated signature, backward compatible

- [ ] **Step 1: Write the tests**

Add to the end of `tests/reports/test_html_renderer.py`:

```python
from app.sources.enrichment import EnrichedIssue


def _make_enrichment(number, is_open=True, comment_count=0, assignees=None, has_linked_pr=False):
    result = make_result(number, f"issue {number}")
    return EnrichedIssue(
        result=result,
        is_open=is_open,
        comment_count=comment_count,
        assignees=assignees or [],
        has_linked_pr=has_linked_pr,
    )


def test_render_html_without_enrichment_unchanged():
    html = render_html(make_report())
    assert "<!DOCTYPE html>" in html
    assert "REPORT_DATA" in html


def test_render_html_with_enrichment_adds_fields():
    enrichment = {1: _make_enrichment(1, comment_count=5, has_linked_pr=True)}
    report = make_report(
        all_issues=[make_result(1, "test issue", urgency=Urgency.CRITICAL)]
    )
    html = render_html(report, enrichment=enrichment)
    assert '"is_open": true' in html
    assert '"comment_count": 5' in html
    assert '"has_linked_pr": true' in html


def test_render_html_closed_issue_badge():
    enrichment = {1: _make_enrichment(1, is_open=False)}
    report = make_report(
        all_issues=[make_result(1, "closed issue", urgency=Urgency.CRITICAL)]
    )
    html = render_html(report, enrichment=enrichment)
    assert "closed-badge" in html


def test_render_html_pr_badge():
    enrichment = {1: _make_enrichment(1, has_linked_pr=True)}
    report = make_report(
        all_issues=[make_result(1, "issue with pr", urgency=Urgency.CRITICAL)]
    )
    html = render_html(report, enrichment=enrichment)
    assert "pr-badge" in html


def test_render_html_comment_count_display():
    enrichment = {1: _make_enrichment(1, comment_count=12)}
    report = make_report(
        all_issues=[make_result(1, "discussed issue", urgency=Urgency.CRITICAL)]
    )
    html = render_html(report, enrichment=enrichment)
    assert "comment-count" in html
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 -m pytest tests/reports/test_html_renderer.py::test_render_html_with_enrichment_adds_fields -v`
Expected: FAIL (render_html doesn't accept enrichment parameter yet)

- [ ] **Step 3: Update `render_html` signature and `_report_to_dict`**

In `app/reports/renderers/html.py`, replace the `render_html` function (lines 25-36):

```python
def render_html(
    report: BirdsEyeReport,
    enrichment: dict | None = None,
) -> str:
    data = _report_to_dict(report)
    if enrichment:
        _apply_enrichment(data, enrichment)
    labels = {}
    if data.get("critical_list"):
        labels["critical"] = "Action Required"
    if data.get("no_team_list"):
        labels["no_team"] = "Needs Triage"
    if data.get("duplicate_clusters"):
        labels["duplicates"] = "Potential Duplicates"
    data["_labels"] = labels
    report_json = json.dumps(data, indent=2).replace("<", "\\u003c")
    return _HTML_TEMPLATE.replace("__REPORT_JSON__", report_json)


def _apply_enrichment(data: dict, enrichment: dict) -> None:
    for issue_list_key in ("critical_list", "no_team_list", "all_issues"):
        for issue in data.get(issue_list_key, []):
            enr = enrichment.get(issue["issue_number"])
            if enr:
                issue["is_open"] = enr.is_open
                issue["comment_count"] = enr.comment_count
                issue["assignees"] = enr.assignees
                issue["has_linked_pr"] = enr.has_linked_pr

    for cluster in data.get("duplicate_clusters", []):
        for issue in cluster.get("issues", []):
            enr = enrichment.get(issue["issue_number"])
            if enr:
                issue["is_open"] = enr.is_open
                issue["comment_count"] = enr.comment_count
                issue["assignees"] = enr.assignees
                issue["has_linked_pr"] = enr.has_linked_pr
```

- [ ] **Step 4: Add CSS for enrichment badges**

In the `<style>` section of `_HTML_TEMPLATE`, add these CSS classes after the `.flag-badge` block (after line 520):

```css
.closed-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: rgba(100, 116, 139, 0.2);
  color: #64748B;
}

.pr-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
  background: rgba(34, 197, 94, 0.15);
  color: #22C55E;
}

.comment-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.issue-card.closed {
  opacity: 0.6;
}

.table-row.closed {
  opacity: 0.5;
}
```

- [ ] **Step 5: Update JavaScript rendering to show enrichment data**

In the `_HTML_TEMPLATE` JavaScript section, add a helper function after `makeUrgencyBadge` (after line 701):

```javascript
  function makeEnrichmentBadges(issue) {
    var container = makeEl("span");
    container.style.display = "inline-flex";
    container.style.gap = "6px";
    container.style.alignItems = "center";
    if (issue.is_open === false) {
      container.appendChild(makeEl("span", "closed-badge", "Closed"));
    }
    if (issue.has_linked_pr) {
      container.appendChild(makeEl("span", "pr-badge", "PR"));
    }
    if (issue.comment_count > 0) {
      container.appendChild(makeEl("span", "comment-count",
        "\u{1F4AC} " + issue.comment_count));
    }
    return container;
  }
```

In the **critical/high issues** card rendering (around line 776, after the meta div is appended), add enrichment badges:

```javascript
        var enrichBadges = makeEnrichmentBadges(issue);
        if (enrichBadges.childNodes.length > 0) {
          var enrichRow = makeEl("div", "issue-meta");
          enrichRow.appendChild(enrichBadges);
          link.appendChild(enrichRow);
        }

        if (issue.is_open === false) {
          link.classList.add("closed");
        }
```

In the **All Issues table** row rendering (around line 1033, before `table.appendChild(row)`), add:

```javascript
      if (issue.is_open === false) {
        row.classList.add("closed");
      }
```

Widen the table to add a status column. Change the grid-template-columns in both `.table-header` and `.table-row` from:

```css
grid-template-columns: 64px 70px 1fr 120px 90px 100px;
```

to:

```css
grid-template-columns: 64px 70px 1fr 120px 90px 80px 100px;
```

Add a "Status" header column in the table header (line 1001, after the Flag span):

```javascript
      '<span class="hide-mobile">Status</span>';
```

Add a status cell in each table row (after the flag cell, before `table.appendChild(row)`):

```javascript
      var statusCell = makeEl("span", "hide-mobile");
      statusCell.appendChild(makeEnrichmentBadges(issue));
      row.appendChild(statusCell);
```

Update the responsive grid at 768px to match (add one more column):

```css
    grid-template-columns: 50px 60px 1fr 90px 70px 60px 80px;
```

- [ ] **Step 6: Run all tests**

Run: `python3 -m pytest tests/reports/test_html_renderer.py -v`
Expected: All tests PASS (existing 26 + 5 new enrichment tests)

- [ ] **Step 7: Run full test suite and linter**

Run: `python3 -m pytest tests/ -v && make lint`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add app/reports/renderers/html.py tests/reports/test_html_renderer.py
git commit -m "feat: display live issue status in dashboard (closed, PR, comments)"
```

---

### Task 4: Kubernetes manifests and Dockerfile update

Add the Deployment, Service, and Route manifests for serving the dashboard on OpenShift, and update the Dockerfile.

**Files:**
- Create: `k8s/deployment.yaml`
- Create: `k8s/service.yaml`
- Create: `k8s/route.yaml`
- Modify: `k8s/kustomization.yaml:6-10` (add new resources)
- Modify: `Dockerfile:9` (add EXPOSE 8080)

**Interfaces:**
- Consumes: container image `quay.io/gracesmith6504/team-issue-triage:latest` (built from Dockerfile)
- Consumes: `--mode serve` CLI flag from Task 2
- Consumes: `triage-config` ConfigMap and `triage-secrets` Secret (existing)
- Consumes: `triage-state` PVC (existing)

- [ ] **Step 1: Create the Deployment manifest**

Create `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: triage-dashboard
spec:
  replicas: 1
  selector:
    matchLabels:
      app: triage-dashboard
  template:
    metadata:
      labels:
        app: triage-dashboard
    spec:
      containers:
        - name: dashboard
          image: quay.io/gracesmith6504/team-issue-triage:latest
          args: ["--mode", "serve"]
          ports:
            - containerPort: 8080
              name: http
          envFrom:
            - configMapRef:
                name: triage-config
            - secretRef:
                name: triage-secrets
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 200m
              memory: 256Mi
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
          livenessProbe:
            httpGet:
              path: /api/health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /api/health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          volumeMounts:
            - name: state
              mountPath: /data
      volumes:
        - name: state
          persistentVolumeClaim:
            claimName: triage-state
```

- [ ] **Step 2: Create the Service manifest**

Create `k8s/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: triage-dashboard
spec:
  type: ClusterIP
  selector:
    app: triage-dashboard
  ports:
    - port: 8080
      targetPort: http
      protocol: TCP
```

- [ ] **Step 3: Create the Route manifest**

Create `k8s/route.yaml`:

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: triage-dashboard
spec:
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: triage-dashboard
    weight: 100
  port:
    targetPort: http
```

- [ ] **Step 4: Update kustomization.yaml**

Replace the contents of `k8s/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: team-issue-triage

resources:
  - pvc.yaml
  - configmap.yaml
  # Batch mode (CronJobs) — comment out when using dashboard mode
  # - cronjob-triage.yaml
  # - cronjob-digest.yaml
  # Dashboard mode (Deployment) — comment out when using batch mode
  - deployment.yaml
  - service.yaml
  - route.yaml
```

- [ ] **Step 5: Update Dockerfile**

In `Dockerfile`, add `EXPOSE 8080` after the `USER 1001` line. The full file should be:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY profiles/ profiles/

USER 1001

EXPOSE 8080

ENTRYPOINT ["python", "-m", "app"]
```

- [ ] **Step 6: Run linter**

Run: `make lint`
Expected: PASS (no Python changes in this task, but verify nothing broke)

- [ ] **Step 7: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add k8s/deployment.yaml k8s/service.yaml k8s/route.yaml k8s/kustomization.yaml Dockerfile
git commit -m "feat: add k8s Deployment, Service, and Route for live dashboard"
```

---

## Self-Review

**Spec coverage check:**
- [x] Status enrichment module with `EnrichedIssue` dataclass — Task 1
- [x] `enrich_issues()` function with per-issue API calls — Task 1
- [x] Error fallback to defaults on API failure — Task 1
- [x] Deduplication by issue number — Task 1
- [x] FastAPI web server with `GET /`, `GET /api/health`, `POST /api/refresh` — Task 2
- [x] Background scheduler with threading.Timer — Task 2
- [x] Loading page with auto-refresh during cold start — Task 2
- [x] Refresh cooldown (5 minutes) — Task 2
- [x] Concurrent triage prevention via threading.Lock — Task 2
- [x] Error resilience (serve stale data on failure) — Task 2
- [x] `--mode serve` CLI integration — Task 2
- [x] `render_html()` accepts optional enrichment parameter — Task 3
- [x] Closed badge, PR badge, comment count display — Task 3
- [x] Greyed-out styling for closed issues — Task 3
- [x] Backward compatible with `--mode report` (enrichment=None) — Task 3
- [x] Deployment YAML with probes, security context, resources — Task 4
- [x] Service YAML (ClusterIP) — Task 4
- [x] Route YAML (edge TLS) — Task 4
- [x] Kustomization updated — Task 4
- [x] Dockerfile EXPOSE 8080 — Task 4
- [x] FastAPI + Uvicorn dependencies — Task 2
- [x] Port 8080 throughout — Tasks 2, 4

**Placeholder scan:** No TBDs, TODOs, or vague instructions found. All code blocks are complete.

**Type consistency:**
- `EnrichedIssue` defined in Task 1, consumed in Tasks 2 and 3 — consistent.
- `enrich_issues(results: list[TriageResult], token: str) -> dict[int, EnrichedIssue]` — consistent across Task 1 definition, Task 2 consumption, Task 3 consumption.
- `render_html(report: BirdsEyeReport, enrichment: dict | None = None) -> str` — Task 3 defines it, Task 2 calls it with `enrichment=enrichment`. The type annotation uses `dict | None` in the function signature for brevity; the actual dict type is `dict[int, EnrichedIssue]` but Python doesn't enforce this at runtime.
- `create_app(config: TriageConfig) -> FastAPI` — Task 2 defines it, tests use it consistently.
- `start_server(config: TriageConfig) -> None` — Task 2 defines it, `__main__.py` calls it.
