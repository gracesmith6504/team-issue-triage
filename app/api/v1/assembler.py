import copy
from datetime import datetime, timezone

from app.cache.section_cache import SectionCache
from app.cache.sections import Section


def assemble_report(cache: SectionCache) -> dict:
    result = {}

    issues = cache.get(Section.ISSUES)
    if issues:
        result.update(copy.deepcopy(issues.data))

    pr_health = cache.get(Section.PR_HEALTH)
    result["pr_health"] = copy.deepcopy(pr_health.data) if pr_health else None

    vouch = cache.get(Section.VOUCH)
    result["vouch_status"] = copy.deepcopy(vouch.data) if vouch else None

    synthesis = cache.get(Section.SYNTHESIS)
    if synthesis:
        synth_data = synthesis.data
        result["narrative"] = synth_data.get("narrative", "")
        result["team_synthesis"] = synth_data.get("team_synthesis")
        _attach_synthesis_to_breakdown(result)
    else:
        result.setdefault("narrative", "")
        result.setdefault("team_synthesis", None)

    metrics = cache.get(Section.METRICS)
    result["sparklines"] = (
        copy.deepcopy(metrics.data)
        if metrics
        else {"triage": [0] * 7, "prs": [0] * 7, "blocked": [0] * 7, "velocity": [0] * 7}
    )

    result.setdefault("generated_at", datetime.now(timezone.utc).isoformat())

    result["_meta"] = {"sections": cache.all_meta()}

    return result


def _attach_synthesis_to_breakdown(data: dict) -> None:
    team_synthesis = data.get("team_synthesis")
    if not team_synthesis:
        return
    for team_id, team in data.get("team_breakdown", {}).items():
        synth = team_synthesis.get(team_id)
        if synth:
            team["synthesis"] = {
                "focus_summary": synth.get("focus_summary", ""),
                "actions": synth.get("actions", []),
                "claims": synth.get("claims"),
                "structured_actions": synth.get("structured_actions"),
                "generated_at": synth.get("generated_at", ""),
                "covered_issues": synth.get("covered_issues", 0),
                "model": synth.get("model", ""),
            }
