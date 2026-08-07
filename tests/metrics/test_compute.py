from datetime import datetime, timezone

from app.metrics.compute import build_sparklines, compute_snapshot
from app.metrics.models import MetricsSnapshot
from tests.reports.conftest import make_report


NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def test_compute_snapshot_basic():
    report = make_report()
    snap = compute_snapshot(report, NOW)
    assert snap.timestamp == NOW.isoformat()
    assert snap.period_label == "Jul 28 – Aug 3, 2026"
    assert snap.total_issues == 5
    assert snap.by_urgency == {"critical": 1, "high": 2, "medium": 1, "low": 1}
    assert snap.total_open == 5
    assert snap.triage_needed == 0


def test_compute_snapshot_team_breakdown():
    report = make_report()
    snap = compute_snapshot(report, NOW)
    assert snap.by_team == {"agent-ops": 3, "ai-safety": 2}


def test_compute_snapshot_with_pr_health():
    pr_data = {
        "total_open": 42,
        "awaiting_review": 5,
        "stale_14d": 3,
        "merge_velocity": 8,
        "merge_velocity_prev": 6,
        "avg_review_wait_days": 4.2,
        "stuck_prs": [],
        "age_distribution": {},
        "gator_coverage_pct": 60,
    }
    report = make_report(pr_health=pr_data)
    snap = compute_snapshot(report, NOW)
    assert snap.pr_total_open == 42
    assert snap.pr_awaiting_review == 5
    assert snap.pr_stale_14d == 3
    assert snap.merge_velocity == 8
    assert snap.avg_review_wait_days == 4.2


def test_compute_snapshot_without_pr_health():
    report = make_report(pr_health=None)
    snap = compute_snapshot(report, NOW)
    assert snap.pr_total_open is None
    assert snap.pr_awaiting_review is None
    assert snap.merge_velocity is None


def test_compute_snapshot_with_vouch_status():
    vouch_data = {
        "total_pending": 3,
        "responded_in_7d": 1,
        "longest_wait_days": 45,
        "over_30d_count": 2,
        "pending_vouches": [],
    }
    report = make_report(vouch_status=vouch_data)
    snap = compute_snapshot(report, NOW)
    assert snap.vouch_pending == 3
    assert snap.vouch_responded_7d == 1
    assert snap.vouch_longest_wait == 45


def test_compute_snapshot_without_vouch():
    report = make_report(vouch_status=None)
    snap = compute_snapshot(report, NOW)
    assert snap.vouch_pending is None
    assert snap.vouch_responded_7d is None


def test_compute_snapshot_empty_team_breakdown():
    report = make_report(team_breakdown={})
    snap = compute_snapshot(report, NOW)
    assert snap.by_team == {}


def test_build_sparklines_basic():
    snaps = [
        MetricsSnapshot(
            timestamp=f"2026-08-0{i}T00:00:00+00:00",
            period_label="test",
            total_issues=10 + i,
            by_urgency={"critical": i},
            by_team={"agent-ops": 5},
            triage_needed=i,
            total_open=10,
            pr_total_open=40 + i,
            pr_awaiting_review=3 + i,
            pr_stale_14d=1,
            merge_velocity=5 + i,
            avg_review_wait_days=2.0,
            vouch_pending=2 + i,
            vouch_responded_7d=1,
            vouch_longest_wait=30,
        )
        for i in range(7)
    ]
    result = build_sparklines(snaps)
    assert result["triage"] == [0, 1, 2, 3, 4, 5, 6]
    assert result["prs"] == [3, 4, 5, 6, 7, 8, 9]
    assert result["blocked"] == [2, 3, 4, 5, 6, 7, 8]
    assert result["velocity"] == [5, 6, 7, 8, 9, 10, 11]


def test_build_sparklines_none_fields_become_zero():
    snap = MetricsSnapshot(
        timestamp="2026-08-01T00:00:00+00:00",
        period_label="test",
        total_issues=5,
        by_urgency={},
        by_team={},
        triage_needed=2,
        total_open=5,
        pr_total_open=None,
        pr_awaiting_review=None,
        pr_stale_14d=None,
        merge_velocity=None,
        avg_review_wait_days=None,
        vouch_pending=None,
        vouch_responded_7d=None,
        vouch_longest_wait=None,
    )
    result = build_sparklines([snap])
    assert result["prs"] == [0]
    assert result["blocked"] == [0]
    assert result["velocity"] == [0]


def test_build_sparklines_empty():
    result = build_sparklines([])
    assert result == {"triage": [], "prs": [], "blocked": [], "velocity": []}
