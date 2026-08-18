import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.v1.router import create_v1_router
from app.cache.section_cache import SectionCache
from app.cache.sections import Section
from app.config import TriageConfig
from app.core.models import Urgency
from app.state.assessment_log import append_result, read_results_as_triage
from app.state.tracker import StateTracker

logger = logging.getLogger(__name__)

_REFRESH_COOLDOWN_SECONDS = 300


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
            from app.refresh.scheduler import SectionRefresher

            refresher = SectionRefresher(config, app.state.section_cache)
            app.state.refresher = refresher
            refresher.start_all()

            if config.auto_backfill and not config.assessment_log_path.exists():
                logger.info(
                    "AUTO_BACKFILL=true and no assessment log found — running backfill on startup"
                )
                thread = threading.Thread(
                    target=_run_backfill, args=(app,), daemon=True, name="auto-backfill"
                )
                thread.start()
        yield

    app = FastAPI(
        title="OpenShell Triage Dashboard",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    cache_dir = (
        config.state_path.parent / "cache" / config.profile_name
        if config.state_path
        else None
    )
    section_cache = SectionCache(persist_dir=cache_dir)
    section_cache.load_persisted()

    from app.reports.renderers.html import render_shell

    app.state.config = config
    app.state.cached_html = render_shell()
    app.state.last_triage = None
    app.state.last_report = None
    app.state.issue_count = 0
    app.state.cycle_lock = threading.Lock()
    app.state.section_cache = section_cache

    v1_router = create_v1_router(section_cache, config)
    app.include_router(v1_router, prefix="/api/v1")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
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

        refresher = getattr(app.state, "refresher", None)
        if refresher:
            refresher.refresh_all_now()
        app.state.last_report = datetime.now(timezone.utc).isoformat()
        return JSONResponse({"status": "accepted"}, status_code=202)

    @app.post("/api/backfill")
    async def backfill():
        if not app.state.cycle_lock.acquire(blocking=False):
            return JSONResponse(
                {"error": "Another cycle is already running"}, status_code=409
            )
        app.state.cycle_lock.release()
        thread = threading.Thread(target=_run_backfill, args=(app,), daemon=True)
        thread.start()
        return JSONResponse(
            {"status": "accepted", "message": "Backfill started"}, status_code=202
        )

    @app.get("/api/state")
    async def get_state():
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

        app.state.issue_count = len(read_results_as_triage(config.assessment_log_path))
        app.state.last_triage = datetime.now(timezone.utc).isoformat()

        if saved > 0:
            refresher = getattr(app.state, "refresher", None)
            if refresher:
                refresher.refresh_issues_now()
            else:
                section_cache.invalidate(Section.ISSUES)

        return {"saved": saved, "total_submitted": len(results)}

    @app.post("/api/reload-config")
    async def reload_config(authorization: str | None = Header(None)):
        auth_err = _check_auth(config, authorization)
        if auth_err:
            return auth_err
        from app.core.profiles import load_repo_config

        try:
            repo_config = load_repo_config(
                config.profile_name, profiles_dir=config.profiles_dir
            )
            logger.info(
                "Config reloaded: profile=%s, repo=%s, teams=%d",
                config.profile_name,
                repo_config.repo,
                len(repo_config.team_profiles),
            )
            for s in Section:
                section_cache.invalidate(s)
            refresher = getattr(app.state, "refresher", None)
            if refresher:
                refresher.refresh_all_now()
            return {
                "status": "reloaded",
                "profile": config.profile_name,
                "repo": repo_config.repo,
                "teams": [t.team_id for t in repo_config.team_profiles],
            }
        except Exception as e:
            logger.exception("Config reload failed")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/report/trigger")
    async def trigger_report(authorization: str | None = Header(None)):
        auth_err = _check_auth(config, authorization)
        if auth_err:
            return auth_err
        refresher = getattr(app.state, "refresher", None)
        if refresher:
            refresher.refresh_all_now()
        return JSONResponse({"status": "accepted"}, status_code=202)

    return app


def _run_backfill(app: FastAPI) -> None:
    """One-time: fetch all open issues, triage unseen ones, then refresh cache."""
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
        logger.info(
            "Backfill: %d open issues fetched, %d new to triage",
            len(all_issues),
            len(new_issues),
        )

        repo_config = load_repo_config(
            config.profile_name, profiles_dir=config.profiles_dir
        )
        system_prompt = build_system_prompt(repo_config)
        llm_client = build_llm_client(config)
        model = resolve_model(config.llm_provider, config.llm_model)

        triaged = 0
        for issue in new_issues:
            try:
                result = triage_issue(
                    issue, llm_client, model, repo_config, system_prompt
                )
                if result:
                    append_result(config.assessment_log_path, result)
                    triaged += 1
                    if triaged % 10 == 0:
                        logger.info(
                            "Backfill progress: %d/%d triaged", triaged, len(new_issues)
                        )
            except Exception:
                logger.exception("Backfill: failed to triage issue #%d", issue.number)

        logger.info("Backfill complete: %d issues triaged", triaged)
    except Exception:
        logger.exception("Backfill failed")
    finally:
        app.state.cycle_lock.release()

    refresher = getattr(app.state, "refresher", None)
    if refresher:
        refresher.refresh_all_now()


def start_server(config: TriageConfig) -> None:
    app = create_app(config)
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
