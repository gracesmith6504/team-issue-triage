import logging

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from app.cache.section_cache import SectionCache
from app.cache.sections import Section
from app.config import TriageConfig

from .assembler import assemble_report

logger = logging.getLogger(__name__)


def _check_auth(config: TriageConfig, authorization: str | None) -> JSONResponse | None:
    if not config.api_token:
        return None
    if not authorization or authorization != f"Bearer {config.api_token}":
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return None


def _section_response(cache: SectionCache, section: str) -> JSONResponse:
    entry = cache.get(section)
    if entry is None:
        return JSONResponse(
            {"error": f"Section '{section}' not yet computed", "section": section},
            status_code=503,
        )
    return JSONResponse({
        "section": section,
        "generated_at": entry.generated_at,
        "ttl_seconds": entry.ttl_seconds,
        "stale": cache.is_stale(section),
        "data": entry.data,
    })


def create_v1_router(cache: SectionCache, config: TriageConfig) -> APIRouter:
    router = APIRouter()

    @router.get("/report")
    async def combined_report():
        report = assemble_report(cache)
        if not report.get("summary"):
            return JSONResponse(
                {"error": "Report not yet generated", "status": "warming_up"},
                status_code=503,
            )
        return JSONResponse(report)

    @router.get("/report/issues")
    async def issues_section():
        return _section_response(cache, Section.ISSUES)

    @router.get("/report/pr-health")
    async def pr_health_section():
        if not config.pr_health_enabled:
            return JSONResponse(
                {"error": "PR health is disabled", "section": "pr_health"},
                status_code=404,
            )
        return _section_response(cache, Section.PR_HEALTH)

    @router.get("/report/vouch")
    async def vouch_section():
        if not config.vouch_tracking_enabled:
            return JSONResponse(
                {"error": "Vouch tracking is disabled", "section": "vouch"},
                status_code=404,
            )
        return _section_response(cache, Section.VOUCH)

    @router.get("/report/synthesis")
    async def synthesis_section():
        return _section_response(cache, Section.SYNTHESIS)

    @router.get("/report/metrics")
    async def metrics_section():
        return _section_response(cache, Section.METRICS)

    @router.get("/report/meta")
    async def report_meta():
        return JSONResponse({"sections": cache.all_meta()})

    return router
