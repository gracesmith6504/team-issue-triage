from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.core.models import IssueSignals, TriageResult, Urgency
from app.core.prompt import build_user_prompt
from app.core.scoring import apply_confidence_rules

if TYPE_CHECKING:
    from app.core.llm import LLMClientProtocol
    from app.core.models import IssueData
    from app.core.profiles import RepoConfig

logger = logging.getLogger(__name__)

_PREFIX_RE = re.compile(
    r"^(?:feat|fix|bug|docs|chore|refactor|test|perf|ci)\(([^)]+)\):"
)
_TYPE_LABELS = {"Bug", "Improvement", "feature request"}


def extract_signals(issue: IssueData) -> IssueSignals:
    match = _PREFIX_RE.match(issue.title)
    title_prefix = match.group(1) if match else None

    area_labels = [lbl for lbl in issue.labels if lbl.startswith("area:")]
    topic_labels = [lbl for lbl in issue.labels if lbl.startswith("topic:")]
    state_labels = [lbl for lbl in issue.labels if lbl.startswith("state:")]
    state_label = state_labels[0] if state_labels else None
    type_labels = [lbl for lbl in issue.labels if lbl in _TYPE_LABELS]
    issue_type = type_labels[0] if type_labels else None

    return IssueSignals(
        title_prefix=title_prefix,
        area_labels=area_labels,
        topic_labels=topic_labels,
        state_label=state_label,
        issue_type=issue_type,
    )


def triage_issue(
    issue: IssueData,
    llm_client: LLMClientProtocol,
    model: str,
    repo_config: RepoConfig,
    system_prompt: str,
) -> TriageResult | None:
    signals = extract_signals(issue)
    user_prompt = build_user_prompt(issue, signals)

    response = llm_client.assess(system_prompt, user_prompt, model)
    if response is None:
        logger.warning(f"LLM returned None for #{issue.number}")
        return None

    try:
        urgency = Urgency(response["urgency"])
    except (KeyError, ValueError):
        logger.warning(
            f"Invalid urgency in response for #{issue.number}: {response.get('urgency')}"
        )
        urgency = Urgency.LOW

    any_team_cares = response.get("any_team_cares", False)
    primary_confidence = float(response.get("primary_confidence", 0.0))
    secondary_confidence_raw = response.get("secondary_confidence")
    secondary_confidence = (
        float(secondary_confidence_raw)
        if secondary_confidence_raw is not None
        else None
    )

    confidence_flag = apply_confidence_rules(
        primary_confidence,
        secondary_confidence,
        any_team_cares,
        repo_config.confidence_thresholds,
    )

    primary_team = response.get("primary_team", "none")
    secondary_team = response.get("secondary_team")

    if confidence_flag == "forced_none":
        any_team_cares = False
        primary_team = "none"
        secondary_team = None
        secondary_confidence = None

    return TriageResult(
        repo=issue.repo,
        issue_number=issue.number,
        issue_title=issue.title,
        issue_url=issue.url,
        reasoning=response.get("reasoning", ""),
        any_team_cares=any_team_cares,
        primary_team=primary_team,
        primary_confidence=primary_confidence,
        secondary_team=secondary_team,
        secondary_confidence=secondary_confidence,
        urgency=urgency,
        urgency_reasoning=response.get("urgency_reasoning", ""),
        summary=response.get("summary", ""),
        recommendation=response.get("recommendation", ""),
        confidence_flag=confidence_flag,
        assessed_at=datetime.now(timezone.utc).isoformat(),
        created_at=issue.created_at,
        author_association=issue.author_association,
        author_login=issue.author_login,
    )
