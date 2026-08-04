from unittest.mock import MagicMock

from app.core.models import TriageResult, Urgency
from app.notifications.adapter import ChannelConfig, TeamNotificationConfig
from app.notifications.router import NotificationRouter


def _make_result(
    primary_team="agent-ops",
    secondary_team=None,
    urgency=Urgency.HIGH,
    any_team_cares=True,
):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=2571,
        issue_title="test issue",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2571",
        reasoning="test",
        any_team_cares=any_team_cares,
        primary_team=primary_team,
        primary_confidence=0.9,
        secondary_team=secondary_team,
        secondary_confidence=0.7 if secondary_team else None,
        urgency=urgency,
        urgency_reasoning="test",
        summary="test",
        recommendation="test",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00Z",
    )


def _make_team_config(
    team_id, immediate_on=None, receive_secondary=True, secondary_min_urgency="high"
):
    return TeamNotificationConfig(
        team_id=team_id,
        receive_secondary=receive_secondary,
        secondary_min_urgency=secondary_min_urgency,
        channels=[
            ChannelConfig(
                adapter_type="mock",
                config={},
                immediate_on=immediate_on or ["critical", "high"],
            ),
        ],
    )


def test_route_delivers_immediate_for_high():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={"agent-ops": _make_team_config("agent-ops")},
        adapters={"mock": adapter},
    )
    result = _make_result(urgency=Urgency.HIGH)
    router.route(result)
    adapter.deliver_immediate.assert_called_once()


def test_route_skips_medium_urgency():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={"agent-ops": _make_team_config("agent-ops")},
        adapters={"mock": adapter},
    )
    result = _make_result(urgency=Urgency.MEDIUM)
    router.route(result)
    adapter.deliver_immediate.assert_not_called()


def test_route_skips_when_no_team_cares():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={"agent-ops": _make_team_config("agent-ops")},
        adapters={"mock": adapter},
    )
    result = _make_result(any_team_cares=False)
    router.route(result)
    adapter.deliver_immediate.assert_not_called()


def test_route_delivers_to_secondary_team():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={
            "ai-safety": _make_team_config("ai-safety"),
            "agent-ops": _make_team_config(
                "agent-ops", receive_secondary=True, secondary_min_urgency="high"
            ),
        },
        adapters={"mock": adapter},
    )
    result = _make_result(
        primary_team="ai-safety", secondary_team="agent-ops", urgency=Urgency.HIGH
    )
    router.route(result)
    assert adapter.deliver_immediate.call_count == 2


def test_route_skips_secondary_when_not_configured():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={
            "ai-safety": _make_team_config("ai-safety"),
            "agentdev": _make_team_config("agentdev", receive_secondary=False),
        },
        adapters={"mock": adapter},
    )
    result = _make_result(
        primary_team="ai-safety", secondary_team="agentdev", urgency=Urgency.HIGH
    )
    router.route(result)
    assert adapter.deliver_immediate.call_count == 1


def test_route_skips_secondary_below_min_urgency():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={
            "ai-safety": _make_team_config("ai-safety"),
            "agent-ops": _make_team_config(
                "agent-ops", secondary_min_urgency="critical"
            ),
        },
        adapters={"mock": adapter},
    )
    result = _make_result(
        primary_team="ai-safety", secondary_team="agent-ops", urgency=Urgency.HIGH
    )
    router.route(result)
    assert adapter.deliver_immediate.call_count == 1


def test_send_digest_groups_by_team():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={
            "agent-ops": _make_team_config("agent-ops"),
            "acp": _make_team_config("acp"),
        },
        adapters={"mock": adapter},
    )
    results = [
        _make_result(primary_team="agent-ops", urgency=Urgency.MEDIUM),
        _make_result(primary_team="agent-ops", urgency=Urgency.LOW),
        _make_result(primary_team="acp", urgency=Urgency.MEDIUM),
    ]
    router.send_digest(results)
    assert adapter.deliver_digest.call_count == 2
