import logging

from app.core.models import TriageResult
from app.notifications.adapter import NotificationAdapter, TeamNotificationConfig

logger = logging.getLogger(__name__)

URGENCY_ORDER = ["critical", "high", "medium", "low"]


class NotificationRouter:
    def __init__(
        self,
        team_configs: dict[str, TeamNotificationConfig],
        adapters: dict[str, NotificationAdapter],
    ):
        self.team_configs = team_configs
        self.adapters = adapters

    def route(self, result: TriageResult) -> None:
        if not result.any_team_cares:
            return

        primary_config = self.team_configs.get(result.primary_team)
        if primary_config:
            self._deliver_to_team(result, primary_config)

        if result.secondary_team:
            secondary_config = self.team_configs.get(result.secondary_team)
            if secondary_config and secondary_config.receive_secondary:
                min_urg = secondary_config.secondary_min_urgency or "low"
                if URGENCY_ORDER.index(result.urgency.value) <= URGENCY_ORDER.index(
                    min_urg
                ):
                    self._deliver_to_team(result, secondary_config)

    def send_digest(self, results: list[TriageResult]) -> None:
        grouped: dict[str, list[TriageResult]] = {}
        for r in results:
            if r.any_team_cares:
                grouped.setdefault(r.primary_team, []).append(r)

        for team_id, team_results in grouped.items():
            config = self.team_configs.get(team_id)
            if not config:
                continue
            for channel in config.channels:
                adapter = self.adapters.get(channel.adapter_type)
                if adapter:
                    adapter.deliver_digest(team_results, channel.config)

    def _deliver_to_team(
        self, result: TriageResult, config: TeamNotificationConfig
    ) -> None:
        for channel in config.channels:
            adapter = self.adapters.get(channel.adapter_type)
            if not adapter:
                continue
            if result.urgency.value in channel.immediate_on:
                adapter.deliver_immediate(result, channel.config)
