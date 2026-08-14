import logging

from app.cache.section_cache import SectionCache
from app.cache.sections import SECTION_TTLS, Section
from app.config import TriageConfig

logger = logging.getLogger(__name__)


def refresh_synthesis(config: TriageConfig, cache: SectionCache) -> None:
    from app.core.llm import build_llm_client, resolve_model
    from app.reports.synthesis import synthesize_team_summaries
    from app.reports.models import TeamSynthesis

    issues_entry = cache.get(Section.ISSUES)
    if not issues_entry:
        logger.warning("Cannot refresh synthesis: no issues data in cache")
        return

    team_breakdown = issues_entry.data.get("team_breakdown", {})
    if not team_breakdown:
        logger.warning("Cannot refresh synthesis: empty team_breakdown")
        return

    teams = {}
    deltas = {}
    for team_id, team_data in team_breakdown.items():
        issues = team_data.get("issues", [])
        teams[team_id] = TeamSynthesis(
            focus_summary="",
            actions=[],
            issues=issues,
        )
        deltas[team_id] = {
            "total": team_data.get("total", 0),
            "previous_total": team_data.get("previous_period", 0),
            "by_urgency": team_data.get("by_urgency", {}),
        }

    llm_client = build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)
    synthesize_team_summaries(teams, deltas, llm_client, model)

    narrative = _generate_narrative(config, issues_entry.data, llm_client, model)

    synthesis_data = {
        "narrative": narrative,
        "team_synthesis": {
            tid: {
                "focus_summary": t.focus_summary,
                "actions": t.actions,
                "claims": getattr(t, "claims", None),
                "structured_actions": getattr(t, "structured_actions", None),
                "generated_at": getattr(t, "generated_at", ""),
                "covered_issues": getattr(t, "covered_issues", 0),
                "model": getattr(t, "model", ""),
            }
            for tid, t in teams.items()
        },
    }
    cache.set(Section.SYNTHESIS, synthesis_data, SECTION_TTLS[Section.SYNTHESIS])
    logger.info("Synthesis section refreshed for %d teams", len(teams))


def _generate_narrative(config, issues_data, llm_client, model) -> str:
    summary = issues_data.get("summary", {})
    total = summary.get("total_open", 0)
    by_urgency = summary.get("by_urgency", {})
    critical = by_urgency.get("critical", 0)
    high = by_urgency.get("high", 0)

    prompt = (
        f"Write a 2-3 sentence executive summary of the current issue landscape. "
        f"Total open: {total}. Critical: {critical}. High: {high}. "
        f"Be concise and actionable."
    )
    try:
        return llm_client.assess(prompt, model=model)
    except Exception:
        logger.exception("Narrative generation failed")
        return ""
