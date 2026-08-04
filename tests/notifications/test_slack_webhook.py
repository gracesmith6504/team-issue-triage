from unittest.mock import patch

from app.core.models import TriageResult, Urgency
from app.notifications.slack_webhook import SlackWebhookAdapter


def _make_result(urgency=Urgency.HIGH, secondary_team=None):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=2571,
        issue_title="bug(supervisor): SPIFFE crash",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2571",
        reasoning="Security issue",
        any_team_cares=True,
        primary_team="ai-safety",
        primary_confidence=0.85,
        secondary_team=secondary_team,
        secondary_confidence=0.7 if secondary_team else None,
        urgency=urgency,
        urgency_reasoning="Regression",
        summary="SPIFFE sandboxes crash on restart",
        recommendation="Investigate SPIFFE lifecycle",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00Z",
    )


@patch("app.notifications.slack_webhook.requests")
def test_deliver_immediate(mock_requests):
    adapter = SlackWebhookAdapter()
    config = {"webhook_url": "https://hooks.slack.com/test"}
    adapter.deliver_immediate(_make_result(), config)
    mock_requests.post.assert_called_once()
    payload = mock_requests.post.call_args[1]["json"]
    assert "SPIFFE" in payload["text"] or any(
        "SPIFFE" in str(b) for b in payload.get("blocks", [])
    )


@patch("app.notifications.slack_webhook.requests")
def test_deliver_digest(mock_requests):
    adapter = SlackWebhookAdapter()
    config = {"webhook_url": "https://hooks.slack.com/test"}
    results = [_make_result(urgency=Urgency.MEDIUM), _make_result(urgency=Urgency.LOW)]
    adapter.deliver_digest(results, config)
    mock_requests.post.assert_called_once()


@patch("app.notifications.slack_webhook.requests")
def test_deliver_immediate_with_secondary(mock_requests):
    adapter = SlackWebhookAdapter()
    config = {"webhook_url": "https://hooks.slack.com/test"}
    adapter.deliver_immediate(_make_result(secondary_team="agent-ops"), config)
    mock_requests.post.assert_called_once()
    payload = mock_requests.post.call_args[1]["json"]
    text = str(payload)
    assert "agent-ops" in text.lower() or "Agent Ops" in text


def test_collect_feedback_returns_empty():
    adapter = SlackWebhookAdapter()
    assert adapter.collect_feedback() == []
