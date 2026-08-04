import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class StateTracker:
    def __init__(self, state_path: Path, lookback_hours: int = 24):
        self._path = state_path
        self._lookback_hours = lookback_hours

    def load(self) -> dict:
        if not self._path.exists():
            logger.info("No state file found, using defaults")
            return self.default_state(lookback_hours=self._lookback_hours)

        try:
            with open(self._path) as f:
                raw = json.load(f)
            seen_list = raw.get("seen_issues", [])
            raw["seen_issues"] = set(str(x) for x in seen_list)
            return raw
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Corrupted state file, using defaults: {e}")
            return self.default_state()

    def save(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            **state,
            "seen_issues": sorted(str(x) for x in state.get("seen_issues", set())),
        }
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(serializable, f, indent=2)
        os.replace(tmp, self._path)

    @staticmethod
    def default_state(lookback_hours: int = 24) -> dict:
        last_checked = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        return {
            "last_checked": last_checked.isoformat(),
            "seen_issues": set(),
            "digest_buffer": [],
            "seen_timestamps": {},
        }

    @staticmethod
    def prune_seen(state: dict, max_age_days: int = 30) -> dict:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max_age_days)
        timestamps = state.get("seen_timestamps", {})

        kept = set()
        kept_timestamps = {}
        for issue_id in state["seen_issues"]:
            key = str(issue_id)
            ts_str = timestamps.get(key)
            if ts_str:
                ts = datetime.fromisoformat(ts_str)
                if ts > cutoff:
                    kept.add(key)
                    kept_timestamps[key] = ts_str
            else:
                kept.add(key)
                kept_timestamps[key] = now.isoformat()

        pruned_count = len(state["seen_issues"]) - len(kept)
        if pruned_count > 0:
            logger.info(f"Pruned {pruned_count} issues older than {max_age_days} days")

        state["seen_issues"] = kept
        state["seen_timestamps"] = kept_timestamps
        return state
