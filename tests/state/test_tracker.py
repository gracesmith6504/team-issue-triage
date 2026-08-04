# tests/state/test_tracker.py
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.state.tracker import StateTracker


@pytest.fixture()
def state_path(tmp_path):
    return tmp_path / "state.json"


@pytest.fixture()
def tracker(state_path):
    return StateTracker(state_path)


def test_default_state():
    state = StateTracker.default_state()
    assert isinstance(state["seen_issues"], set)
    assert len(state["seen_issues"]) == 0
    assert "last_checked" in state
    assert "digest_buffer" in state
    assert "seen_timestamps" in state


def test_default_state_lookback():
    state = StateTracker.default_state(lookback_hours=48)
    checked = datetime.fromisoformat(state["last_checked"])
    now = datetime.now(timezone.utc)
    assert (now - checked).total_seconds() >= 47 * 3600


def test_load_missing_file(tracker):
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)
    assert len(state["seen_issues"]) == 0


def test_save_and_load_namespaced(tracker):
    state = StateTracker.default_state()
    state["seen_issues"] = {"NVIDIA/OpenShell#2571", "NVIDIA/OpenShell#2588"}
    state["seen_timestamps"] = {
        "NVIDIA/OpenShell#2571": "2026-08-01T00:00:00Z",
        "NVIDIA/OpenShell#2588": "2026-08-01T01:00:00Z",
    }
    tracker.save(state)
    loaded = tracker.load()
    assert loaded["seen_issues"] == {"NVIDIA/OpenShell#2571", "NVIDIA/OpenShell#2588"}
    assert "NVIDIA/OpenShell#2571" in loaded["seen_timestamps"]


def test_load_corrupted_file(state_path, tracker):
    state_path.write_text("not json")
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)
    assert len(state["seen_issues"]) == 0


def test_prune_old_issues():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=60)).isoformat()
    recent = (now - timedelta(days=5)).isoformat()

    state = {
        "seen_issues": {"NVIDIA/OpenShell#100", "NVIDIA/OpenShell#200"},
        "seen_timestamps": {
            "NVIDIA/OpenShell#100": old,
            "NVIDIA/OpenShell#200": recent,
        },
    }
    pruned = StateTracker.prune_seen(state)
    assert "NVIDIA/OpenShell#100" not in pruned["seen_issues"]
    assert "NVIDIA/OpenShell#200" in pruned["seen_issues"]


def test_save_creates_parent_dirs(tmp_path):
    deep_path = tmp_path / "a" / "b" / "state.json"
    tracker = StateTracker(deep_path)
    state = StateTracker.default_state()
    tracker.save(state)
    assert deep_path.exists()


def test_seen_issues_serialized_as_list(state_path, tracker):
    state = StateTracker.default_state()
    state["seen_issues"] = {"NVIDIA/OpenShell#1", "NVIDIA/OpenShell#2"}
    tracker.save(state)
    raw = json.loads(state_path.read_text())
    assert isinstance(raw["seen_issues"], list)
    assert sorted(raw["seen_issues"]) == ["NVIDIA/OpenShell#1", "NVIDIA/OpenShell#2"]


def test_migrate_legacy_int_keys(state_path, tracker):
    """Legacy state files used bare int keys. They should be loaded and preserved as-is."""
    legacy = {
        "last_checked": "2026-08-01T00:00:00Z",
        "seen_issues": [100, 200, 300],
        "digest_buffer": [],
        "seen_timestamps": {"100": "2026-08-01T00:00:00Z"},
    }
    state_path.write_text(json.dumps(legacy))
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)
    assert all(isinstance(x, (int, str)) for x in state["seen_issues"])
