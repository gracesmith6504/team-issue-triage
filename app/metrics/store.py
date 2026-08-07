import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.metrics.models import MetricsSnapshot

logger = logging.getLogger(__name__)


class MetricsStore(Protocol):
    def append(self, snapshot: MetricsSnapshot) -> None: ...

    def read(
        self, *, since: str | None = None, limit: int | None = None
    ) -> list[MetricsSnapshot]: ...


class JsonlMetricsStore:
    def __init__(self, path: Path):
        self._path = path

    def append(self, snapshot: MetricsSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(asdict(snapshot)) + "\n")

    def read(
        self, *, since: str | None = None, limit: int | None = None
    ) -> list[MetricsSnapshot]:
        if not self._path.exists():
            return []

        since_dt = None
        if since:
            since_dt = datetime.fromisoformat(since)

        snapshots: list[MetricsSnapshot] = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping corrupted metrics line")
                    continue

                if since_dt:
                    try:
                        ts = datetime.fromisoformat(record["timestamp"])
                        if ts < since_dt:
                            continue
                    except (KeyError, ValueError):
                        continue

                try:
                    snapshots.append(MetricsSnapshot(**record))
                except (TypeError, KeyError) as exc:
                    logger.warning("Skipping incompatible metrics record: %s", exc)
                    continue

        if limit is not None:
            snapshots = snapshots[-limit:]

        return snapshots
