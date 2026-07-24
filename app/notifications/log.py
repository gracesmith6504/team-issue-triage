import logging

from app.core.models import Assessment, DigestEntry
from app.core.scoring import format_scores

logger = logging.getLogger(__name__)

DIGEST_MAX_ITEMS = 10


class LogNotifier:
    def send_escalation(self, assessment: Assessment) -> None:
        scores = format_scores(
            relevance=assessment.relevance,
            urgency=assessment.urgency,
            action_clarity=assessment.action_clarity,
            relevance_reason=assessment.relevance_reason,
            urgency_reason=assessment.urgency_reason,
            action_clarity_reason=assessment.action_clarity_reason,
        )
        print(
            f"[ESCALATE] #{assessment.issue_number}: {assessment.issue_title}\n"
            f"  {assessment.issue_url}\n"
            f"  {assessment.summary}\n"
            f"  {scores}\n"
            f"  Recommendation: {assessment.recommendation}"
        )

    def send_digest(self, entries: list[DigestEntry]) -> None:
        if not entries:
            print("[DIGEST] Empty — no TRACK items to report.")
            return

        sorted_entries = sorted(entries, key=lambda e: e.urgency, reverse=True)
        shown = sorted_entries[:DIGEST_MAX_ITEMS]
        omitted = len(sorted_entries) - len(shown)

        print(f"[DIGEST] {len(sorted_entries)} items:")
        for entry in shown:
            print(
                f"  - #{entry.issue_number}: {entry.title} "
                f"(R={entry.relevance} U={entry.urgency} AC={entry.action_clarity}) "
                f"— {entry.reason}"
            )
        if omitted > 0:
            print(f"  ... and {omitted} more omitted")
