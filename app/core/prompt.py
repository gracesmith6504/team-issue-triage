from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.truncation import truncate_body, truncate_comment

if TYPE_CHECKING:
    from app.core.models import IssueData
    from app.core.profiles import TeamProfile

BASE_SYSTEM_PROMPT = """You are a team issue triage agent. You assess GitHub issues to determine their relevance and urgency for a specific engineering team.

Score every issue on three axes, each from 1 to 5:

TEAM RELEVANCE — Does this issue touch an area the team owns or cares about?
  5: Directly in team-owned area
  4: Adjacent area the team actively contributes to
  3: Area the team uses but doesn't own
  2: Tangentially related
  1: Unrelated to team's work

URGENCY — How time-sensitive is this?
  5: Release blocker or CI failure that stops the team's work
  4: Regression in current pinned version or security vulnerability
  3: Bug affecting team workflows, but workaround exists
  2: Enhancement or improvement that would help the team
  1: Discussion, RFC, feature request, or nice-to-have

ACTION CLARITY — Is there something specific someone should do?
  5: Clear fix described, someone just needs to do it
  4: Problem is well-defined, fix approach is apparent
  3: Problem is clear but investigation needed to find the fix
  2: Problem is vague, needs reproduction or design discussion
  1: Open-ended discussion, RFC, or architectural question

When in doubt on any score, round DOWN.

Return a JSON object with these exact fields:
- "relevance": Integer 1-5
- "relevance_reason": One sentence explaining the score
- "urgency": Integer 1-5
- "urgency_reason": One sentence explaining the score
- "action_clarity": Integer 1-5
- "action_clarity_reason": One sentence explaining the score
- "summary": 1-2 sentence summary of what the issue is about
- "recommendation": One sentence — what should the team do about this?

Return ONLY the JSON object, no markdown fences or extra text."""


def build_system_prompt(profile: TeamProfile | None = None) -> str:
    if profile is None:
        return BASE_SYSTEM_PROMPT

    sections = [BASE_SYSTEM_PROMPT]

    if profile.team_context:
        sections.append(
            f"\n\n--- TEAM CONTEXT ({profile.team_name}) ---\n{profile.team_context.strip()}"
        )

    if profile.pinned_version:
        sections.append(
            f"\n\n--- PINNED VERSION ---\n"
            f"The team's current pinned version is {profile.pinned_version}. "
            f"Regressions against this version are Urgency 4."
        )

    if profile.urgency_rules:
        sections.append(f"\n\n--- URGENCY RULES ---\n{profile.urgency_rules.strip()}")

    if profile.calibration_examples:
        lines = []
        for ex in profile.calibration_examples:
            lines.append(
                f'- "{ex["summary"]}": {ex["scores"]} → {ex["verdict"]} — {ex["reason"]}'
            )
        sections.append(
            "\n\n--- CALIBRATION EXAMPLES ---\n"
            "Use these as scoring anchors. For similar issues, start from the closest example:\n"
            + "\n".join(lines)
        )

    return "\n".join(sections)


def build_user_prompt(issue: IssueData, profile: TeamProfile | None = None) -> str:
    if issue.comments:
        comment_lines = []
        for c in issue.comments:
            comment_lines.append(f"@{c['user']}: {truncate_comment(c.get('body'))}")
        comments_section = "\n".join(comment_lines)
    else:
        comments_section = "(no comments)"

    labels_str = ", ".join(issue.labels) if issue.labels else "none"

    return f"""Issue from {issue.repo} (#{issue.number}):

Title: {issue.title}

Body:
{truncate_body(issue.body)}

Labels: {labels_str}

Comments (most recent):
{comments_section}"""
