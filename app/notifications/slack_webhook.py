import logging

import requests

from app.core.models import TriageResult

logger = logging.getLogger(__name__)

URGENCY_EMOJI = {
    "critical": "\U0001f534",
    "high": "\U0001f7e0",
    "medium": "\U0001f7e1",
    "low": "\U0001f535",
}


class SlackWebhookAdapter:
    def deliver_immediate(self, result: TriageResult, channel_config: dict) -> None:
        emoji = URGENCY_EMOJI.get(result.urgency.value, "")
        text = (
            f"{emoji} {result.urgency.value.upper()} — Routed to: {result.primary_team}"
        )
        if result.secondary_team:
            text += f"\nAlso relevant to: {result.secondary_team}"
        text += f"\n\n#{result.issue_number}: {result.issue_title}"
        text += f"\n\nSummary: {result.summary}"
        text += f"\n\nRecommendation: {result.recommendation}"
        text += f"\n\n\U0001f517 {result.issue_url}"

        self._post(channel_config.get("webhook_url", ""), {"text": text})

    def deliver_digest(self, results: list[TriageResult], channel_config: dict) -> None:
        if not results:
            return
        team = results[0].primary_team
        lines = [f"\U0001f4cb Daily Triage Digest — {team} ({len(results)} issues)\n"]
        for r in results:
            lines.append(f"• #{r.issue_number} {r.issue_title} — {r.urgency.value}")
            lines.append(f"  {r.summary}")
        self._post(channel_config.get("webhook_url", ""), {"text": "\n".join(lines)})

    def collect_feedback(self) -> list:
        return []

    def _post(self, webhook_url: str, payload: dict) -> None:
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
        except Exception:
            logger.exception(f"Slack webhook post failed: {webhook_url}")
