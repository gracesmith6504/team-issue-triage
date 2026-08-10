from dataclasses import dataclass
from unittest.mock import patch

from tests.reports.conftest import make_report


@dataclass
class _FakeConfig:
    pr_health_enabled: bool = True
    vouch_tracking_enabled: bool = True
    github_token: str = "ghp_test"


@dataclass
class _FakeRepoConfig:
    repo: str = "NVIDIA/OpenShell"
    codeowners: list[str] | None = None


def test_enrich_pr_health_enabled():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig(pr_health_enabled=True)
    repo_config = _FakeRepoConfig(codeowners=["mrunalp"])

    with patch("app.pr_health.fetcher.fetch_pr_health") as mock_fetch:
        mock_fetch.return_value = _stub_pr_health()
        enrich_report(report, config, repo_config)

    mock_fetch.assert_called_once_with("NVIDIA/OpenShell", "ghp_test", ["mrunalp"])
    assert report.pr_health is not None


def test_enrich_pr_health_disabled():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig(pr_health_enabled=False)

    with patch("app.pr_health.fetcher.fetch_pr_health") as mock_fetch:
        enrich_report(report, config, _FakeRepoConfig())

    mock_fetch.assert_not_called()
    assert report.pr_health is None


def test_enrich_pr_health_fails_gracefully():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig(pr_health_enabled=True)

    with patch(
        "app.pr_health.fetcher.fetch_pr_health", side_effect=RuntimeError("boom")
    ):
        enrich_report(report, config, _FakeRepoConfig())

    assert report.pr_health is None


def test_enrich_vouch_enabled():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig(vouch_tracking_enabled=True)

    with patch("app.vouch.fetcher.fetch_vouch_status") as mock_fetch:
        mock_fetch.return_value = _stub_vouch()
        enrich_report(report, config, _FakeRepoConfig())

    mock_fetch.assert_called_once_with("NVIDIA/OpenShell", "ghp_test")
    assert report.vouch_status is not None


def test_enrich_vouch_disabled():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig(vouch_tracking_enabled=False)

    with patch("app.vouch.fetcher.fetch_vouch_status") as mock_fetch:
        enrich_report(report, config, _FakeRepoConfig())

    mock_fetch.assert_not_called()
    assert report.vouch_status is None


def test_enrich_vouch_fails_gracefully():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig(vouch_tracking_enabled=True)

    with patch(
        "app.vouch.fetcher.fetch_vouch_status", side_effect=RuntimeError("boom")
    ):
        enrich_report(report, config, _FakeRepoConfig())

    assert report.vouch_status is None


def _stub_pr_health():
    from app.pr_health.models import PRHealthFindings

    return PRHealthFindings(
        total_open=10,
        awaiting_review=5,
        stale_14d=1,
        gator_coverage_pct=80,
        merge_velocity=2,
        merge_velocity_prev=1,
        avg_review_wait_days=3.5,
        stuck_prs=[],
        age_distribution={},
    )


def _stub_vouch():
    from app.vouch.models import VouchFindings

    return VouchFindings(
        total_pending=3,
        responded_in_7d=2,
        longest_wait_days=15,
        over_30d_count=0,
        pending_vouches=[],
    )


def test_enrich_cross_references_blocked_prs():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig()
    repo_config = _FakeRepoConfig()

    with (
        patch("app.reports.enrich._enrich_issue_counts"),
        patch("app.pr_health.fetcher.fetch_pr_health") as mock_pr,
        patch("app.vouch.fetcher.fetch_vouch_status") as mock_vouch,
    ):
        mock_pr.return_value = _stub_pr_health_with_prs()
        mock_vouch.return_value = _stub_vouch_with_pending()
        enrich_report(report, config, repo_config)

    assert report.vouch_status is not None
    blocked = report.vouch_status["blocked_prs"]
    assert len(blocked) == 1
    assert blocked[0]["author"] == "newcontrib"
    assert blocked[0]["pr_number"] == 42
    assert blocked[0]["vouch_discussion"] == 100
    assert blocked[0]["vouch_url"] == "https://github.com/test/repo/discussions/100"


def test_enrich_blocked_prs_empty_when_no_overlap():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig()
    repo_config = _FakeRepoConfig()

    with (
        patch("app.reports.enrich._enrich_issue_counts"),
        patch("app.pr_health.fetcher.fetch_pr_health") as mock_pr,
        patch("app.vouch.fetcher.fetch_vouch_status") as mock_vouch,
    ):
        mock_pr.return_value = _stub_pr_health()
        mock_vouch.return_value = _stub_vouch()
        enrich_report(report, config, repo_config)

    assert report.vouch_status is not None
    assert report.vouch_status["blocked_prs"] == []


def _stub_pr_health_with_prs():
    from app.pr_health.models import PRHealthFindings, PRStatus

    return PRHealthFindings(
        total_open=2,
        awaiting_review=1,
        stale_14d=0,
        gator_coverage_pct=50,
        merge_velocity=5,
        merge_velocity_prev=3,
        avg_review_wait_days=2.0,
        stuck_prs=[
            PRStatus(
                number=42,
                title="feat: add widget",
                url="https://github.com/test/repo/pull/42",
                author="newcontrib",
                days_open=10,
                days_since_author_push=5,
                days_since_last_review=10,
                review_count=0,
                participants=[],
                last_activity="Author pushed 5d ago, no reviews",
                is_draft=False,
            ),
        ],
        age_distribution={},
    )


def _stub_vouch_with_pending():
    from app.vouch.models import PendingVouch, VouchFindings

    return VouchFindings(
        total_pending=1,
        responded_in_7d=0,
        longest_wait_days=12,
        over_30d_count=0,
        pending_vouches=[
            PendingVouch(
                author="newcontrib",
                discussion_number=100,
                url="https://github.com/test/repo/discussions/100",
                wait_days=12,
                created_at="2026-07-20T00:00:00Z",
            ),
        ],
    )
