from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.reports.models import TeamSynthesis

if TYPE_CHECKING:
    from app.core.llm import LLMClientProtocol

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a technical team lead summarizing your team's issue backlog.\n"
    "Given a list of issues grouped by area, write:\n"
    "1. A 2-sentence focus summary - direct, plain language, NO jargon\n"
    "2. Top 3 actions - ONE short sentence each, start with a verb\n\n"
    "IMPORTANT:\n"
    "- Focus summary: 2 simple sentences, 40 words max total\n"
    "- Actions: 15 words max each, imperative mood (Fix X, Review Y, Add Z)\n"
    "- NO parenthetical details, NO em-dashes, NO technical jargon\n\n"
    'Return JSON: {"focus_summary": "...", "actions": ["...", "...", "..."]}'
)


def synthesize_team_summaries(
    teams: dict[str, TeamSynthesis],
    llm_client: LLMClientProtocol,
    model: str,
) -> dict[str, TeamSynthesis]:
    for team_id, synthesis in teams.items():
        if synthesis.total == 0:
            continue

        user_prompt = _build_team_prompt(synthesis)
        response = llm_client.assess(_SYSTEM_PROMPT, user_prompt, model)

        if response and isinstance(response, dict):
            synthesis.focus_summary = response.get("focus_summary", "")
            synthesis.actions = response.get("actions", [])[:3]
        else:
            logger.warning("LLM synthesis failed for team %s", team_id)

    return teams


def _build_team_prompt(synthesis: TeamSynthesis) -> str:
    lines = [
        f"Team: {synthesis.team_name} ({synthesis.total} issues)",
        f"Urgency breakdown: {synthesis.by_urgency}",
        f"Trend: {synthesis.trend}",
        "",
    ]
    for area, group in synthesis.area_groups.items():
        lines.append(f"## {area} ({group.total} issues)")
        for issue in group.issues[:10]:
            urgency = issue.urgency.value
            lines.append(f"- [{urgency}] #{issue.issue_number}: {issue.issue_title}")
            if issue.summary:
                lines.append(f"  Summary: {issue.summary}")
            if issue.recommendation:
                lines.append(f"  Recommendation: {issue.recommendation}")
        if group.total > 10:
            lines.append(f"  ... and {group.total - 10} more")
        lines.append("")

    return "\n".join(lines)
