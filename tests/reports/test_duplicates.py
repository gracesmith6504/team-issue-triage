from app.core.models import TriageResult, Urgency
from app.reports.duplicates import DuplicateDetector


def _make_result(number, title, assessed_at="2026-07-28T10:00:00+00:00"):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=number,
        issue_title=title,
        issue_url=f"https://github.com/NVIDIA/OpenShell/issues/{number}",
        reasoning="test",
        any_team_cares=True,
        primary_team="agent-ops",
        primary_confidence=0.9,
        secondary_team=None,
        secondary_confidence=None,
        urgency=Urgency.MEDIUM,
        urgency_reasoning="test",
        summary="test",
        recommendation="test",
        confidence_flag=None,
        assessed_at=assessed_at,
    )


def test_detect_duplicates_by_shared_tokens():
    results = [
        _make_result(1, "feat(sandbox): add user namespace support"),
        _make_result(
            2, "bug(sandbox): enableUserNamespaces fails on namespace creation"
        ),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 1
    assert clusters[0].area == "sandbox"
    assert len(clusters[0].issues) == 2
    assert "namespace" in clusters[0].similarity_reason.lower()


def test_no_duplicates_different_areas():
    results = [
        _make_result(1, "feat(cli): add sandbox prune command"),
        _make_result(2, "feat(gateway): connection pool timeout"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 0


def test_no_duplicates_outside_time_window():
    results = [
        _make_result(
            1, "feat(sandbox): add user namespace support", "2026-07-01T10:00:00+00:00"
        ),
        _make_result(
            2, "bug(sandbox): user namespace fails", "2026-07-20T10:00:00+00:00"
        ),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 0


def test_stopwords_excluded():
    results = [
        _make_result(1, "fix(cli): add support for new flag"),
        _make_result(2, "feat(cli): update support for old flag"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 1
    reason = clusters[0].similarity_reason.lower()
    assert "flag" in reason


def test_single_issue_no_cluster():
    results = [_make_result(1, "feat(sandbox): add namespace support")]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 0


def test_cluster_merges_transitive():
    results = [
        _make_result(1, "feat(sandbox): user namespace creation"),
        _make_result(2, "bug(sandbox): namespace creation fails"),
        _make_result(3, "fix(sandbox): creation timeout on namespace"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 1
    assert len(clusters[0].issues) == 3


def test_no_prefix_issues_grouped_by_body_tokens():
    results = [
        _make_result(1, "VM sandbox SSH disconnects randomly"),
        _make_result(2, "VM sandbox SSH connection drops"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 1
