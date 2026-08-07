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
