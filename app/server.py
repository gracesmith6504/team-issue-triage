import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import TriageConfig
from app.core.models import Urgency
from app.sources.enrichment import enrich_issues
from app.state.assessment_log import append_result, read_results_as_triage
from app.state.tracker import StateTracker

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


def _check_auth(config: TriageConfig, authorization: str | None) -> JSONResponse | None:
    if not config.api_token:
        return None
    if not authorization or authorization != f"Bearer {config.api_token}":
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return None


def create_app(config: TriageConfig) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        if not config.worker_mode:
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
    app.state.last_report = None
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
        return {
            "status": "ok" if app.state.last_triage else "starting",
            "last_triage": app.state.last_triage,
            "issue_count": app.state.issue_count,
        }

    @app.post("/api/refresh")
    async def refresh():
        if app.state.last_report:
            last = datetime.fromisoformat(app.state.last_report)
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

    @app.post("/api/backfill")
    async def backfill():
        if not app.state.cycle_lock.acquire(blocking=False):
            return JSONResponse(
                {"error": "Another cycle is already running"}, status_code=409
            )
        app.state.cycle_lock.release()
        thread = threading.Thread(
            target=_run_backfill, args=(app,), daemon=True
        )
        thread.start()
        return JSONResponse({"status": "accepted", "message": "Backfill started"}, status_code=202)

    @app.get("/api/state")
    async def get_state(authorization: str | None = Header(None)):
        auth_err = _check_auth(config, authorization)
        if auth_err:
            return auth_err
        tracker = StateTracker(config.state_path, config.default_lookback_hours)
        state = tracker.load()
        return {
            "last_checked": state["last_checked"],
            "seen_issues": sorted(str(x) for x in state["seen_issues"]),
        }

    @app.post("/api/assessments")
    async def post_assessments(
        request: Request,
        authorization: str | None = Header(None),
    ):
        auth_err = _check_auth(config, authorization)
        if auth_err:
            return auth_err

        body = await request.json()
        results = body.get("results", [])
        if not results:
            return JSONResponse({"error": "No results provided"}, status_code=400)

        from app.core.models import TriageResult

        tracker = StateTracker(config.state_path, config.default_lookback_hours)
        state = tracker.load()

        saved = 0
        for r in results:
            try:
                result = TriageResult(
                    repo=r["repo"],
                    issue_number=r["issue_number"],
                    issue_title=r["issue_title"],
                    issue_url=r["issue_url"],
                    reasoning=r.get("reasoning", ""),
                    any_team_cares=r.get("any_team_cares", True),
                    primary_team=r.get("primary_team", "unknown"),
                    primary_confidence=r.get("primary_confidence", 0.0),
                    secondary_team=r.get("secondary_team"),
                    secondary_confidence=r.get("secondary_confidence"),
                    urgency=Urgency(r["urgency"]),
                    urgency_reasoning=r.get("urgency_reasoning", ""),
                    summary=r.get("summary", ""),
                    recommendation=r.get("recommendation", ""),
                    confidence_flag=r.get("confidence_flag"),
                    assessed_at=r.get("assessed_at", ""),
                    created_at=r.get("created_at", ""),
                    author_association=r.get("author_association", "NONE"),
                    author_login=r.get("author_login", ""),
                    labels=r.get("labels", []),
                    closed=r.get("closed", False),
                )
                append_result(config.assessment_log_path, result)
                seen_key = f"{result.repo}#{result.issue_number}"
                state["seen_issues"].add(seen_key)
                state["seen_timestamps"][seen_key] = datetime.now(
                    timezone.utc
                ).isoformat()
                saved += 1
            except Exception:
                logger.exception(
                    "Failed to save assessment for issue #%s",
                    r.get("issue_number", "?"),
                )

        tracker.save(state)

        app.state.issue_count = len(
            read_results_as_triage(config.assessment_log_path)
        )
        app.state.last_triage = datetime.now(timezone.utc).isoformat()

        return {"saved": saved, "total_submitted": len(results)}

    @app.post("/api/report/trigger")
    async def trigger_report(authorization: str | None = Header(None)):
        auth_err = _check_auth(config, authorization)
        if auth_err:
            return auth_err
        if not app.state.cycle_lock.acquire(blocking=False):
            return JSONResponse(
                {"error": "Another cycle is already running"}, status_code=409
            )
        app.state.cycle_lock.release()
        thread = threading.Thread(
            target=_run_report_cycle, args=(app,), daemon=True
        )
        thread.start()
        return JSONResponse({"status": "accepted"}, status_code=202)

    return app


def _run_backfill(app: FastAPI) -> None:
    """One-time: fetch all open issues, triage unseen ones, then generate report."""
    if not app.state.cycle_lock.acquire(blocking=False):
        logger.info("Backfill skipped — another cycle running")
        return

    try:
        config = app.state.config
        from app.core.llm import build_llm_client, resolve_model
        from app.core.profiles import load_repo_config
        from app.core.prompt import build_system_prompt
        from app.core.triage_engine import triage_issue
        from app.sources.github import GitHubSource
        from app.state.assessment_log import append_result

        existing = read_results_as_triage(config.assessment_log_path)
        seen_numbers = {r.issue_number for r in existing}
        logger.info("Backfill: %d issues already assessed", len(seen_numbers))

        source = GitHubSource(config.github_token)
        all_issues = source.fetch_all_open_issues(config.watch_repos)
        new_issues = [i for i in all_issues if i.number not in seen_numbers]
        logger.info("Backfill: %d open issues fetched, %d new to triage", len(all_issues), len(new_issues))

        repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
        system_prompt = build_system_prompt(repo_config)
        llm_client = build_llm_client(config)
        model = resolve_model(config.llm_provider, config.llm_model)

        triaged = 0
        for issue in new_issues:
            try:
                result = triage_issue(issue, llm_client, model, repo_config, system_prompt)
                if result:
                    append_result(config.assessment_log_path, result)
                    triaged += 1
                    if triaged % 10 == 0:
                        logger.info("Backfill progress: %d/%d triaged", triaged, len(new_issues))
            except Exception:
                logger.exception("Backfill: failed to triage issue #%d", issue.number)

        logger.info("Backfill complete: %d issues triaged", triaged)
    except Exception:
        logger.exception("Backfill failed")
    finally:
        app.state.cycle_lock.release()

    _run_report_cycle(app)


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
        current = [r for r in read_results_as_triage(config.assessment_log_path)
                   if not r.closed]

        # For trend comparison, still need previous period
        # Use last 30 days as the comparison window
        previous_start = now - timedelta(days=60)
        current_start = now - timedelta(days=30)
        previous = [r for r in read_results_as_triage(
            config.assessment_log_path,
            start_date=previous_start.isoformat(),
            end_date=current_start.isoformat(),
        ) if not r.closed]

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
        app.state.last_report = now.isoformat()
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
