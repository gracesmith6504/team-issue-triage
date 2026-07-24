from app.core.models import Assessment, DigestEntry, Verdict
from app.notifications.log import LogNotifier


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
            reason="OpenShift gap",
            url="https://github.com/NVIDIA/OpenShell/issues/2399",
            assessed_at="2026-07-23T13:05:00+00:00",
        ),
    ]


def test_log_notifier_escalation(capsys):
    notifier = LogNotifier()
    notifier.send_escalation(_make_assessment())

    captured = capsys.readouterr()
    assert "ESCALATE" in captured.out
    assert "protobuf sync failed" in captured.out
    assert "#2401" in captured.out


def test_log_notifier_digest(capsys):
    notifier = LogNotifier()
    notifier.send_digest(_make_digest_entries())

    captured = capsys.readouterr()
    assert "DIGEST" in captured.out or "digest" in captured.out.lower()
    assert "Helm values" in captured.out


def test_log_notifier_empty_digest(capsys):
    notifier = LogNotifier()
    notifier.send_digest([])

    captured = capsys.readouterr()
    assert "empty" in captured.out.lower() or captured.out.strip() == ""
