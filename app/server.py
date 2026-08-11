import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

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
    @asynccontextmanager
    async def lifespan(app):
        _schedule_cycle(app)
        yield

    app = FastAPI(
        title="OpenShell Triage Dashboard",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.state.config = config
    app.state.cached_html = None
    app.state.last_triage = None
    app.state.issue_count = 0
    app.state.enrichment = {}
    app.state.cycle_lock = threading.Lock()

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

        # Manual refresh triggers both triage and report (for testing)
        thread = threading.Thread(target=_run_report_cycle, args=(app,), daemon=True)
        thread.start()
        return JSONResponse({"status": "accepted"}, status_code=202)

    return app


def _schedule_cycle(app: FastAPI) -> None:
    # Start both triage (hourly) and report (daily) cycles
    triage_thread = threading.Thread(target=_run_triage_cycle, args=(app,), daemon=True)
    triage_thread.start()
    _schedule_daily_report(app)


def _run_triage_cycle(app: FastAPI) -> None:
    """Hourly: triage new issues and send notifications (no synthesis)."""
    if not app.state.cycle_lock.acquire(blocking=False):
        logger.info("Triage cycle already running, skipping")
        return

    try:
        config = app.state.config
        logger.info("Starting hourly triage cycle")

        from app.triage import check_closed_issues, run_triage

        try:
            run_triage(config)
        except Exception:
            logger.exception("Triage failed")

        # Check for closed issues hourly
        try:
            check_closed_issues(config)
        except Exception:
            logger.exception("Closed-issue check failed")

        # Enrich issues to update linked PR status
        results = read_results_as_triage(config.assessment_log_path)

        try:
            from app.sources.enrichment import enrich_issues
            enrichment = enrich_issues(results, config.github_token)
            app.state.enrichment = enrichment
            logger.info("Enrichment complete: %d issues checked", len(enrichment))
        except Exception:
            logger.exception("Enrichment failed")

        app.state.issue_count = len(results)
        app.state.last_triage = datetime.now(timezone.utc).isoformat()

        logger.info("Triage cycle complete: %d issues total", len(results))
    except Exception:
        logger.exception("Triage cycle failed")
    finally:
        app.state.cycle_lock.release()
        _schedule_triage_next(app)


def _run_report_cycle(app: FastAPI) -> None:
    """Daily: generate team synthesis and full dashboard."""
    if not app.state.cycle_lock.acquire(blocking=False):
        logger.info("Report cycle already running, skipping")
        return

    try:
        config = app.state.config
        logger.info("Starting daily report generation")

        results = read_results_as_triage(config.assessment_log_path)

        # Reuse cached enrichment from hourly cycle
        # (Enrichment was already updated within the last hour)
        enrichment = app.state.enrichment

        from app.core.llm import build_llm_client, resolve_model
        from app.core.profiles import load_repo_config
        from app.reports.birds_eye import BirdsEyeReportGenerator
        from app.reports.enrich import enrich_report
        from app.reports.periods import compute_period

        repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)

        now = datetime.now(timezone.utc)

        # Load ALL issues (no date filter) for client-side time filtering
        current = read_results_as_triage(config.assessment_log_path)

        # For trend comparison, still need previous period
        # Use last 30 days as the comparison window
        previous_start = now - timedelta(days=60)
        current_start = now - timedelta(days=30)
        previous = read_results_as_triage(
            config.assessment_log_path,
            start_date=previous_start.isoformat(),
            end_date=current_start.isoformat(),
        )

        llm_client = build_llm_client(config)
        model = resolve_model(config.llm_provider, config.llm_model)

        # Period label is "All time" since we're loading everything
        # Client-side filtering will handle the actual time windows
        period_label = "All time"

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

        logger.info("Report generation complete: %d issues", len(current))
    except Exception:
        logger.exception("Report generation failed")
    finally:
        app.state.cycle_lock.release()
        _schedule_daily_report(app)


def _schedule_triage_next(app: FastAPI) -> None:
    """Schedule next hourly triage cycle."""
    timer = threading.Timer(3600, _run_triage_cycle, args=(app,))
    timer.daemon = True
    timer.start()


def _schedule_daily_report(app: FastAPI) -> None:
    """Schedule next daily report generation at 9am UTC."""
    config = app.state.config
    report_hour = getattr(config, "report_schedule_hour", 9)  # Default 9am UTC

    now = datetime.now(timezone.utc)
    target = now.replace(hour=report_hour, minute=0, second=0, microsecond=0)

    # If we've passed today's target time, schedule for tomorrow
    if now >= target:
        target += timedelta(days=1)

    delay = (target - now).total_seconds()
    logger.info(
        "Scheduling next report generation at %s (in %.1f hours)",
        target.isoformat(),
        delay / 3600,
    )

    timer = threading.Timer(delay, _run_report_cycle, args=(app,))
    timer.daemon = True
    timer.start()


def start_server(config: TriageConfig) -> None:
    app = create_app(config)
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
