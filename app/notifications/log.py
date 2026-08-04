import logging

from app.core.models import TriageResult

logger = logging.getLogger(__name__)

_SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class LogAdapter:
    def deliver_immediate(self, result: TriageResult, channel_config: dict) -> None:
        print(
            f"[IMMEDIATE] #{result.issue_number} → {result.primary_team} "
            f"({result.urgency.value}): {result.issue_title}"
        )
        print(f"  Summary: {result.summary}")
        print(f"  Recommendation: {result.recommendation}")
        if result.secondary_team:
            print(f"  Also relevant to: {result.secondary_team}")

    def deliver_digest(self, results: list[TriageResult], channel_config: dict) -> None:
        if not results:
            print("[DIGEST] 0 issues")
            return
        team = results[0].primary_team
        print(f"[DIGEST] {team}: {len(results)} issues")
        for r in sorted(results, key=lambda x: _SEVERITY.get(x.urgency.value, 99)):
            print(f"  #{r.issue_number} {r.issue_title} — {r.urgency.value}")

    def collect_feedback(self) -> list:
        return []
