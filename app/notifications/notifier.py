from typing import Protocol

from app.core.models import Assessment, DigestEntry


class Notifier(Protocol):
    def send_escalation(self, assessment: Assessment) -> None: ...
    def send_digest(self, entries: list[DigestEntry]) -> None: ...
