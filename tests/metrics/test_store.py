from pathlib import Path

from app.metrics.models import MetricsSnapshot
from app.metrics.store import JsonlMetricsStore


def _make_snapshot(timestamp: str = "2026-08-01T00:00:00+00:00") -> MetricsSnapshot:
    return MetricsSnapshot(
        timestamp=timestamp,
        period_label="Jul 28 – Aug 3, 2026",
        total_issues=10,
        by_urgency={"critical": 1, "high": 3, "medium": 4, "low": 2},
        by_team={"agent-ops": 5, "ai-safety": 3, "none": 2},
        triage_needed=4,
        total_open=10,
        pr_total_open=42,
        pr_awaiting_review=5,
        pr_stale_14d=3,
        merge_velocity=8,
        avg_review_wait_days=4.2,
        vouch_pending=3,
        vouch_responded_7d=1,
        vouch_longest_wait=45,
    )


def test_append_and_read_roundtrip(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    snap = _make_snapshot()
    store.append(snap)
    result = store.read()
    assert len(result) == 1
    assert result[0].timestamp == snap.timestamp
    assert result[0].total_issues == 10
    assert result[0].by_urgency == {"critical": 1, "high": 3, "medium": 4, "low": 2}


def test_read_with_limit(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    for i in range(5):
        store.append(_make_snapshot(f"2026-08-0{i + 1}T00:00:00+00:00"))
    result = store.read(limit=3)
    assert len(result) == 3
    assert result[0].timestamp == "2026-08-03T00:00:00+00:00"


def test_read_with_since(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    store.append(_make_snapshot("2026-07-01T00:00:00+00:00"))
    store.append(_make_snapshot("2026-08-01T00:00:00+00:00"))
    store.append(_make_snapshot("2026-08-05T00:00:00+00:00"))
    result = store.read(since="2026-08-01T00:00:00+00:00")
    assert len(result) == 2
    assert result[0].timestamp == "2026-08-01T00:00:00+00:00"


def test_read_empty_file(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    result = store.read()
    assert result == []


def test_read_missing_file(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "nonexistent" / "metrics.jsonl")
    result = store.read()
    assert result == []


def test_corrupted_line_skipped(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    store = JsonlMetricsStore(path)
    store.append(_make_snapshot("2026-08-01T00:00:00+00:00"))
    with open(path, "a") as f:
        f.write("not valid json\n")
    store.append(_make_snapshot("2026-08-02T00:00:00+00:00"))
    result = store.read()
    assert len(result) == 2
    assert result[0].timestamp == "2026-08-01T00:00:00+00:00"
    assert result[1].timestamp == "2026-08-02T00:00:00+00:00"


def test_extra_fields_skipped(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    store = JsonlMetricsStore(path)
    store.append(_make_snapshot("2026-08-01T00:00:00+00:00"))
    with open(path, "a") as f:
        import json

        record = json.loads(open(path).readline())
        record["new_future_field"] = 42
        f.write(json.dumps(record) + "\n")
    store.append(_make_snapshot("2026-08-03T00:00:00+00:00"))
    result = store.read()
    assert len(result) == 2
    assert result[0].timestamp == "2026-08-01T00:00:00+00:00"
    assert result[1].timestamp == "2026-08-03T00:00:00+00:00"


def test_none_fields_roundtrip(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    snap = MetricsSnapshot(
        timestamp="2026-08-01T00:00:00+00:00",
        period_label="Jul 28 – Aug 3, 2026",
        total_issues=5,
        by_urgency={"medium": 5},
        by_team={"agent-ops": 5},
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
    store.append(snap)
    result = store.read()
    assert result[0].pr_total_open is None
    assert result[0].vouch_pending is None
