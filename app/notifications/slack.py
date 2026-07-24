import logging

import requests

from app.core.models import Assessment, DigestEntry, DIGEST_MAX_ITEMS

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    def send_escalation(self, assessment: Assessment) -> None:
        override_note = ""
        if assessment.override_applied:
            override_note = f"\n_Override: {assessment.override_applied}_"

        text = (
            f":rotating_light: *ESCALATE* — <{assessment.issue_url}|#{assessment.issue_number}: "
            f"{assessment.issue_title}>\n"
            f"{assessment.summary}{override_note}"
        )

        payload = {"text": text}
        self._post(payload)

    def send_digest(self, entries: list[DigestEntry]) -> None:
        if not entries:
            return

        sorted_entries = sorted(entries, key=lambda e: e.urgency, reverse=True)
        shown = sorted_entries[:DIGEST_MAX_ITEMS]
        omitted = len(sorted_entries) - len(shown)

        lines = [f":clipboard: *Daily Issue Digest* — {len(sorted_entries)} items\n"]
        for entry in shown:
            lines.append(
                f"• <{entry.url}|#{entry.issue_number}: {entry.title}> "
                f"(R={entry.relevance} U={entry.urgency} AC={entry.action_clarity}) "
                f"— {entry.reason}"
            )
        if omitted > 0:
            lines.append(f"\n_{omitted} more omitted_")

        payload = {"text": "\n".join(lines)}
        self._post(payload)

    def _post(self, payload: dict) -> None:
        try:
            response = requests.post(self._webhook_url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.error(
                    f"Slack webhook failed: {response.status_code} {response.text}"
                )
        except requests.RequestException as e:
            logger.error(f"Slack webhook error: {e}")
