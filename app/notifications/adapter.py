from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.models import TriageResult


class NotificationAdapter(Protocol):
    def deliver_immediate(self, result: TriageResult, channel_config: dict) -> None: ...
    def deliver_digest(
        self, results: list[TriageResult], channel_config: dict
    ) -> None: ...
    def collect_feedback(self) -> list[FeedbackEvent]: ...


@dataclass
class FeedbackEvent:
    issue_number: int
    team_id: str
    feedback_type: str
    feedback_by: str
    feedback_at: str
    original_confidence: float


@dataclass
class ChannelConfig:
    adapter_type: str
    config: dict
    immediate_on: list[str]


@dataclass
class TeamNotificationConfig:
    team_id: str
    receive_secondary: bool
    secondary_min_urgency: str | None
    channels: list[ChannelConfig]
