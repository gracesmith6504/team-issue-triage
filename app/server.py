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
    app.state.enrichment = {}
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
                    {
                        "error": "Refresh cooldown active",
                        "retry_after_seconds": int(_REFRESH_COOLDOWN_SECONDS - elapsed),
                    },
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

        app.state.enrichment = enrichment

        from app.core.llm import build_llm_client, resolve_model
        from app.core.profiles import load_repo_config
        from app.reports.birds_eye import BirdsEyeReportGenerator
        from app.reports.enrich import enrich_report
        from app.reports.periods import compute_period

        repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)

        now = datetime.now(timezone.utc)
        current_start, previous_start, period_label = compute_period(
            repo_config.reporting, now
        )

        current = read_results_as_triage(
            config.assessment_log_path,
            start_date=current_start.isoformat(),
        )
        previous = read_results_as_triage(
            config.assessment_log_path,
            start_date=previous_start.isoformat(),
            end_date=current_start.isoformat(),
        )

        llm_client = build_llm_client(config)
        model = resolve_model(config.llm_provider, config.llm_model)

        generator = BirdsEyeReportGenerator(
            current, previous, llm_client, model, period_label
        )
        report = generator.generate()

        enrich_report(report, config, repo_config)

        sparklines = None
        try:
            from app.metrics.compute import build_sparklines, compute_snapshot
            from app.metrics.store import JsonlMetricsStore

            store = JsonlMetricsStore(config.metrics_path)
            snapshot = compute_snapshot(report, now)
            store.append(snapshot)
            recent = store.read(limit=7)
            sparklines = build_sparklines(recent)
        except Exception:
            logger.exception("Metrics collection failed")

        from app.reports.renderers.html import render_html

        app.state.cached_html = render_html(
            report, enrichment=enrichment, sparklines=sparklines
        )
        app.state.last_triage = now.isoformat()
        app.state.issue_count = len(current)

        logger.info("Triage cycle complete: %d issues", len(current))
    except Exception:
        logger.exception("Triage cycle failed")
    finally:
        app.state.cycle_lock.release()
        _schedule_next(app)


def _schedule_next(app: FastAPI) -> None:
    timer = threading.Timer(3600, _run_cycle, args=(app,))
    timer.daemon = True
    timer.start()


def start_server(config: TriageConfig) -> None:
    app = create_app(config)
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
