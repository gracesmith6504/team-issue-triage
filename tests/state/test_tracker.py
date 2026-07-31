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


def test_default_state(tracker):
    state = tracker.default_state()
    assert "last_checked" in state
    assert isinstance(state["seen_issues"], set)
    assert len(state["seen_issues"]) == 0
    assert state["digest_buffer"] == []


def test_default_state_lookback(tracker):
    state = tracker.default_state(lookback_hours=48)
    last_checked = datetime.fromisoformat(state["last_checked"])
    now = datetime.now(timezone.utc)
    diff = now - last_checked
    assert 47 < diff.total_seconds() / 3600 < 49


def test_load_missing_file(tracker):
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)
    assert state["digest_buffer"] == []


def test_save_and_load(tracker, state_path):
    state = {
        "last_checked": "2026-07-23T14:00:00+00:00",
        "seen_issues": {"NVIDIA/OpenShell#2401", "NVIDIA/OpenShell#2399"},
        "digest_buffer": [
            {
                "issue_number": 2399,
                "title": "Helm values missing tolerations",
                "repo": "NVIDIA/OpenShell",
                "relevance": 4,
                "urgency": 2,
                "action_clarity": 5,
                "verdict": "TRACK",
                "reason": "Clear fix, not urgent",
                "url": "https://github.com/NVIDIA/OpenShell/issues/2399",
                "assessed_at": "2026-07-23T13:05:00+00:00",
            }
        ],
    }
    tracker.save(state)

    loaded = tracker.load()
    assert loaded["last_checked"] == "2026-07-23T14:00:00+00:00"
    assert loaded["seen_issues"] == {"NVIDIA/OpenShell#2401", "NVIDIA/OpenShell#2399"}
    assert len(loaded["digest_buffer"]) == 1
    assert loaded["digest_buffer"][0]["issue_number"] == 2399


def test_load_corrupted_file(tracker, state_path):
    state_path.write_text("not valid json {{{")
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)


def test_prune_old_issues(tracker):
    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(days=31)).isoformat()
    recent_time = (now - timedelta(days=1)).isoformat()

    state = {
        "last_checked": recent_time,
        "seen_issues": {"NVIDIA/OpenShell#100", "NVIDIA/OpenShell#200", "NVIDIA/OpenShell#300"},
        "digest_buffer": [],
        "seen_timestamps": {
            "NVIDIA/OpenShell#100": old_time,
            "NVIDIA/OpenShell#200": old_time,
            "NVIDIA/OpenShell#300": recent_time,
        },
    }
    tracker.save(state)

    loaded = tracker.load()
    pruned = tracker.prune_seen(loaded, max_age_days=30)
    assert "NVIDIA/OpenShell#300" in pruned["seen_issues"]
    assert "NVIDIA/OpenShell#100" not in pruned["seen_issues"]
    assert "NVIDIA/OpenShell#200" not in pruned["seen_issues"]


def test_save_creates_parent_dirs(tmp_path):
    nested_path = tmp_path / "deep" / "nested" / "state.json"
    tracker = StateTracker(nested_path)
    state = tracker.default_state()
    tracker.save(state)
    assert nested_path.exists()


def test_seen_issues_serialized_as_list(tracker, state_path):
    state = {
        "last_checked": "2026-07-23T14:00:00+00:00",
        "seen_issues": {"repo/a#1", "repo/a#2", "repo/a#3"},
        "digest_buffer": [],
    }
    tracker.save(state)

    raw = json.loads(state_path.read_text())
    assert isinstance(raw["seen_issues"], list)
