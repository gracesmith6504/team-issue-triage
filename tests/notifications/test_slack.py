from unittest.mock import MagicMock, patch

from app.core.models import Assessment, DigestEntry, Verdict
from app.notifications.slack import SlackNotifier


def _make_assessment():
    return Assessment(
        repo="NVIDIA/OpenShell",
        issue_number=2401,
        issue_title="protobuf sync failed",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2401",
        relevance=5,
        relevance_reason="Team-owned",
        urgency=5,
        urgency_reason="Blocks releases",
        action_clarity=4,
        action_clarity_reason="Clear fix",
        total=14,
        verdict=Verdict.ESCALATE,
        override_applied=None,
        summary="SDK sync failure",
        recommendation="Re-run sync",
        assessed_at="2026-07-23T14:05:00+00:00",
    )


def _make_digest_entries():
    return [
        DigestEntry(
            issue_number=2399,
            title="Helm values missing tolerations",
            repo="NVIDIA/OpenShell",
            relevance=4,
            urgency=2,
            action_clarity=5,
            verdict="TRACK",
            reason="OpenShift deployment gap",
            url="https://github.com/NVIDIA/OpenShell/issues/2399",
            assessed_at="2026-07-23T13:05:00+00:00",
        ),
        DigestEntry(
            issue_number=2397,
            title="Add NetworkPolicy templates to Helm chart",
            repo="NVIDIA/OpenShell",
            relevance=4,
            urgency=2,
            action_clarity=4,
            verdict="TRACK",
            reason="OpenShift network security enhancement",
            url="https://github.com/NVIDIA/OpenShell/issues/2397",
            assessed_at="2026-07-23T13:10:00+00:00",
        ),
    ]


@patch("app.notifications.slack.requests.post")
def test_slack_escalation(mock_post):
    mock_post.return_value = MagicMock(status_code=200)

    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    notifier.send_escalation(_make_assessment())

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    payload = call_args[1]["json"]

    assert "protobuf sync failed" in payload["text"]


@patch("app.notifications.slack.requests.post")
def test_slack_digest(mock_post):
    mock_post.return_value = MagicMock(status_code=200)

    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    notifier.send_digest(_make_digest_entries())

    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "Helm values" in payload["text"]
    assert "NetworkPolicy" in payload["text"]


@patch("app.notifications.slack.requests.post")
def test_slack_empty_digest(mock_post):
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    notifier.send_digest([])

    mock_post.assert_not_called()


@patch("app.notifications.slack.requests.post")
def test_slack_digest_caps_at_10(mock_post):
    mock_post.return_value = MagicMock(status_code=200)

    entries = [
        DigestEntry(
            issue_number=i,
            title=f"Issue {i}",
            repo="NVIDIA/OpenShell",
            relevance=3,
            urgency=3,
            action_clarity=3,
            verdict="TRACK",
            reason="Test",
            url=f"https://github.com/NVIDIA/OpenShell/issues/{i}",
            assessed_at="2026-07-23T13:00:00+00:00",
        )
        for i in range(15)
    ]

    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    notifier.send_digest(entries)

    payload = mock_post.call_args[1]["json"]
    assert "5 more" in payload["text"] or "omitted" in payload["text"].lower()
