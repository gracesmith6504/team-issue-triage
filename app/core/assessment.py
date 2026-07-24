from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.core.prompt import build_system_prompt, build_user_prompt
from app.core.scoring import clamp_score, compute_verdict

if TYPE_CHECKING:
    from app.core.llm import LLMClientProtocol
    from app.core.models import IssueData
    from app.core.profiles import TeamProfile

from app.core.models import Assessment

logger = logging.getLogger(__name__)


def assess_issue(
    issue: IssueData,
    llm_client: LLMClientProtocol,
    model: str,
    profile: TeamProfile | None = None,
) -> Assessment | None:
    system_prompt = build_system_prompt(profile)
    user_prompt = build_user_prompt(issue, profile=profile)
    analysis = llm_client.assess(system_prompt, user_prompt, model)
    if not analysis:
        return None

    relevance = clamp_score(analysis.get("relevance"))
    urgency = clamp_score(analysis.get("urgency"))
    action_clarity = clamp_score(analysis.get("action_clarity"))

    thresholds = profile.verdict_thresholds if profile else None
    verdict, total, override = compute_verdict(
        relevance, urgency, action_clarity, thresholds=thresholds
    )

    logger.info(
        f"[{issue.repo} #{issue.number}] "
        f"R={relevance} U={urgency} AC={action_clarity} Total={total} -> {verdict.value}"
    )

    return Assessment(
        repo=issue.repo,
        issue_number=issue.number,
        issue_title=issue.title,
        issue_url=issue.url,
        relevance=relevance,
        relevance_reason=analysis.get("relevance_reason", ""),
        urgency=urgency,
        urgency_reason=analysis.get("urgency_reason", ""),
        action_clarity=action_clarity,
        action_clarity_reason=analysis.get("action_clarity_reason", ""),
        total=total,
        verdict=verdict,
        override_applied=override,
        summary=analysis.get("summary", ""),
        recommendation=analysis.get("recommendation", ""),
        assessed_at=datetime.now(timezone.utc).isoformat(),
    )
