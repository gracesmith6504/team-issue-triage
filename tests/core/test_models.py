from app.core.models import (
    Assessment,
    DigestEntry,
    IssueData,
    Verdict,
    DIGEST_MAX_ITEMS,
)


def test_verdict_values():
    assert Verdict.ESCALATE == "ESCALATE"
    assert Verdict.TRACK == "TRACK"
    assert Verdict.WATCH == "WATCH"
    assert Verdict.SKIP == "SKIP"


def test_verdict_ordering():
    ordered = [Verdict.ESCALATE, Verdict.TRACK, Verdict.WATCH, Verdict.SKIP]
    assert len(ordered) == 4


def test_issue_data_creation():
    issue = IssueData(
        repo="NVIDIA/OpenShell",
        number=2401,
        title="protobuf sync failed",
        body="The sync job failed with error...",
        labels=["kind/bug", "priority/critical"],
        comments=[{"user": "bot", "body": "Auto-created by sync action"}],
        url="https://github.com/NVIDIA/OpenShell/issues/2401",
        created_at="2026-07-23T14:00:00Z",
    )
    assert issue.repo == "NVIDIA/OpenShell"
    assert issue.number == 2401
    assert len(issue.labels) == 2
    assert len(issue.comments) == 1


def test_assessment_creation():
    assessment = Assessment(
        repo="NVIDIA/OpenShell",
        issue_number=2401,
        issue_title="protobuf sync failed",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2401",
        relevance=5,
        relevance_reason="Go SDK sync is team-owned",
        urgency=5,
        urgency_reason="Blocks releases",
        action_clarity=4,
        action_clarity_reason="Re-run sync after fixing protos",
        total=14,
        verdict=Verdict.ESCALATE,
        override_applied=None,
        summary="SDK sync failure blocks release",
        recommendation="Fix proto definitions and re-run sync",
        assessed_at="2026-07-23T14:05:00Z",
    )
    assert assessment.verdict == Verdict.ESCALATE
    assert assessment.total == 14
    assert assessment.override_applied is None


def test_digest_entry_creation():
    entry = DigestEntry(
        issue_number=2399,
        title="Helm values missing tolerations",
        repo="NVIDIA/OpenShell",
        relevance=4,
        urgency=2,
        action_clarity=5,
        verdict="TRACK",
        reason="OpenShift deployment gap",
        url="https://github.com/NVIDIA/OpenShell/issues/2399",
        assessed_at="2026-07-23T13:05:00Z",
    )
    assert entry.verdict == "TRACK"
    assert entry.relevance == 4


def test_digest_entry_to_dict():
    entry = DigestEntry(
        issue_number=2399,
        title="Helm values missing tolerations",
        repo="NVIDIA/OpenShell",
        relevance=4,
        urgency=2,
        action_clarity=5,
        verdict="TRACK",
        reason="OpenShift deployment gap",
        url="https://github.com/NVIDIA/OpenShell/issues/2399",
        assessed_at="2026-07-23T13:05:00Z",
    )
    d = entry.to_dict()
    assert d["issue_number"] == 2399
    assert d["verdict"] == "TRACK"
    assert len(d) == 10


def test_digest_entry_from_dict():
    data = {
        "issue_number": 2399,
        "title": "Helm values missing tolerations",
        "repo": "NVIDIA/OpenShell",
        "relevance": 4,
        "urgency": 2,
        "action_clarity": 5,
        "verdict": "TRACK",
        "reason": "OpenShift deployment gap",
        "url": "https://github.com/NVIDIA/OpenShell/issues/2399",
        "assessed_at": "2026-07-23T13:05:00Z",
    }
    entry = DigestEntry.from_dict(data)
    assert entry.issue_number == 2399
    assert entry.verdict == "TRACK"


def test_digest_entry_roundtrip():
    entry = DigestEntry(
        issue_number=100,
        title="Test",
        repo="org/repo",
        relevance=3,
        urgency=3,
        action_clarity=3,
        verdict="WATCH",
        reason="test",
        url="https://example.com/100",
        assessed_at="2026-07-23T12:00:00Z",
    )
    assert DigestEntry.from_dict(entry.to_dict()) == entry


def test_digest_max_items_constant():
    assert DIGEST_MAX_ITEMS == 10
