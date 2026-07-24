from app.core.models import Verdict

DEFAULT_THRESHOLDS = {
    "ESCALATE": 12,
    "TRACK": 8,
    "WATCH": 5,
}

AXIS_LABELS = {
    "relevance": "Team Relevance",
    "urgency": "Urgency",
    "action_clarity": "Action Clarity",
}


def clamp_score(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, n))


def compute_verdict(
    relevance: int,
    urgency: int,
    action_clarity: int,
    thresholds: dict[str, int] | None = None,
) -> tuple[Verdict, int, str | None]:
    t = thresholds or DEFAULT_THRESHOLDS
    total = relevance + urgency + action_clarity
    override = None

    verdict = Verdict.SKIP
    for v in (Verdict.ESCALATE, Verdict.TRACK, Verdict.WATCH):
        if total >= t[v.value]:
            verdict = v
            break

    if relevance == 1 and verdict in (Verdict.ESCALATE, Verdict.TRACK):
        verdict = Verdict.WATCH
        override = "Relevance=1 caps at WATCH"
    elif urgency == 5 and relevance >= 3 and verdict != Verdict.ESCALATE:
        verdict = Verdict.ESCALATE
        override = "Urgency=5 + Relevance>=3 forces ESCALATE"

    return verdict, total, override


def format_scores(
    relevance: int,
    urgency: int,
    action_clarity: int,
    relevance_reason: str,
    urgency_reason: str,
    action_clarity_reason: str,
) -> str:
    lines = []
    for axis, score, reason in [
        ("relevance", relevance, relevance_reason),
        ("urgency", urgency, urgency_reason),
        ("action_clarity", action_clarity, action_clarity_reason),
    ]:
        label = AXIS_LABELS[axis]
        sep = f" — {reason}" if reason else ""
        lines.append(f"{label}: {score}/5{sep}")
    return "\n".join(lines)
