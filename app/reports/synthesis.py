from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.reports.models import TeamSynthesis

if TYPE_CHECKING:
    from app.core.llm import LLMClientProtocol

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a technical team lead writing a brief status summary for leadership.
Given issues grouped by area, produce a short analysis.

Return JSON in this exact format:
{
  "claims": [
    {
      "text": "Short sentence with {ref:key} and {area:name} markers.",
      "refs": {
        "key": {"label": "short label", "issues": [1234, 5678]}
      }
    }
  ],
  "actions": [
    {"text": "Verb phrase, max 12 words.", "issues": [1234], "priority": "critical"}
  ]
}

CRITICAL RULES:
- Write exactly 2 claims. Each claim is ONE sentence, MAX 25 words.
- Do NOT describe what each bug does. The {ref:} disclosure shows that.
- BAD: "{ref:exec_hang} where the CLI never exits after a completed command"
- GOOD: "The {area:sandbox} area has {ref:critical_bugs} causing hangs and crashes"
- {ref:key} = expandable group of issues. Label is what the user sees.
- {area:name} = link to an area section. Use area names from the input.
- Ref keys: snake_case. Keep labels under 5 words.
- Write exactly 3 actions. Each starts with a verb, max 12 words.
- Plain language. No jargon. Briefing a VP who has 10 seconds."""


def synthesize_team_summaries(
    teams: dict[str, TeamSynthesis],
    deltas: dict[str, dict],
    llm_client: LLMClientProtocol,
    model: str,
) -> dict[str, TeamSynthesis]:
    now = datetime.now(timezone.utc).isoformat()

    for team_id, synthesis in teams.items():
        if synthesis.total == 0:
            continue

        delta = deltas.get(team_id, {})
        user_prompt = _build_team_prompt(synthesis, delta)
        response = llm_client.assess(_SYSTEM_PROMPT, user_prompt, model)

        if response and isinstance(response, dict):
            _apply_response(synthesis, response)
        else:
            logger.warning("LLM synthesis failed for team %s", team_id)

        synthesis.generated_at = now
        synthesis.covered_issues = synthesis.total
        synthesis.model = model

    return teams


def _apply_response(synthesis: TeamSynthesis, response: dict) -> None:
    claims = response.get("claims")
    actions = response.get("actions")

    if claims and isinstance(claims, list):
        valid_claims = []
        for claim in claims:
            if isinstance(claim, dict) and "text" in claim:
                valid_claims.append({
                    "text": claim["text"],
                    "refs": claim.get("refs", {}),
                })
        synthesis.claims = valid_claims

        # Generate fallback focus_summary by stripping markers
        plain_parts = []
        for claim in valid_claims:
            text = claim["text"]
            text = re.sub(r"\{ref:([^}]+)\}", lambda m: _ref_label(claim, m.group(1)), text)
            text = re.sub(r"\{area:([^}]+)\}", r"\1", text)
            plain_parts.append(text)
        synthesis.focus_summary = " ".join(plain_parts)
    elif "focus_summary" in response:
        synthesis.focus_summary = response["focus_summary"]

    if actions and isinstance(actions, list):
        valid_actions = []
        for action in actions[:3]:
            if isinstance(action, dict) and "text" in action:
                valid_actions.append({
                    "text": action["text"],
                    "issues": action.get("issues", []),
                    "priority": action.get("priority", "medium"),
                })
            elif isinstance(action, str):
                valid_actions.append({"text": action, "issues": [], "priority": "medium"})
        synthesis.structured_actions = valid_actions
        synthesis.actions = [a["text"] for a in valid_actions]
    elif "actions" in response:
        synthesis.actions = response.get("actions", [])[:3]


def _ref_label(claim: dict, key: str) -> str:
    refs = claim.get("refs", {})
    ref = refs.get(key, {})
    return ref.get("label", key.replace("_", " "))


def _count_bugs(synthesis: TeamSynthesis) -> int:
    bug_re = re.compile(r"^(?:bug|fix)[\(:]", re.IGNORECASE)
    count = 0
    for group in synthesis.area_groups.values():
        for issue in group.issues:
            if bug_re.match(issue.issue_title):
                count += 1
    return count


def _build_team_prompt(synthesis: TeamSynthesis, delta: dict) -> str:
    bug_count = _count_bugs(synthesis)
    lines = [
        f"Team: {synthesis.team_name} ({synthesis.total} issues, {bug_count} bugs)",
        f"Urgency breakdown: {synthesis.by_urgency}",
        f"Trend: {synthesis.trend}",
        "",
    ]

    new_issues = delta.get("new", [])
    resolved_issues = delta.get("resolved", [])
    if new_issues or resolved_issues:
        lines.append("CHANGES SINCE LAST PERIOD:")
        if new_issues:
            items = [f"#{i['number']} [{i['urgency']}] {i['title']}" for i in new_issues[:10]]
            suffix = f" (and {len(new_issues) - 10} more)" if len(new_issues) > 10 else ""
            lines.append(f"- {len(new_issues)} new issues: {', '.join(items)}{suffix}")
        else:
            lines.append("- No new issues")
        if resolved_issues:
            items = [f"#{i['number']} [{i['urgency']}] {i['title']}" for i in resolved_issues[:5]]
            suffix = f" (and {len(resolved_issues) - 5} more)" if len(resolved_issues) > 5 else ""
            lines.append(f"- {len(resolved_issues)} resolved: {', '.join(items)}{suffix}")
        lines.append("- Incorporate these changes into your analysis.")
        lines.append("")

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
