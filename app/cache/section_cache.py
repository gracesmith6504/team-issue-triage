import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CachedSection:
    data: dict
    generated_at: str
    ttl_seconds: int


class SectionCache:
    def __init__(self, persist_dir: Path | None = None):
        self._store: dict[str, CachedSection] = {}
        self._lock = threading.Lock()
        self._persist_dir = persist_dir
        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)

    def get(self, section: str) -> CachedSection | None:
        with self._lock:
            return self._store.get(section)

    def set(self, section: str, data: dict, ttl_seconds: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        entry = CachedSection(data=data, generated_at=now, ttl_seconds=ttl_seconds)
        with self._lock:
            self._store[section] = entry
            if self._persist_dir:
                self._persist(section, entry)

    def is_stale(self, section: str) -> bool:
        entry = self.get(section)
        if entry is None:
            return True
        return self._entry_is_stale(entry)

    def invalidate(self, section: str) -> None:
        with self._lock:
            self._store.pop(section, None)
            if self._persist_dir:
                path = self._persist_dir / f"{self._section_filename(section)}.json"
                path.unlink(missing_ok=True)

    def all_meta(self) -> dict[str, dict]:
        with self._lock:
            return {
                name: {
                    "generated_at": entry.generated_at,
                    "ttl_seconds": entry.ttl_seconds,
                    "stale": self._entry_is_stale(entry),
                }
                for name, entry in self._store.items()
            }

    @staticmethod
    def _entry_is_stale(entry: CachedSection) -> bool:
        generated = datetime.fromisoformat(entry.generated_at)
        elapsed = (datetime.now(timezone.utc) - generated).total_seconds()
        return elapsed > entry.ttl_seconds

    @staticmethod
    def _section_filename(section: str) -> str:
        return getattr(section, "value", section)

    def _persist(self, section: str, entry: CachedSection) -> None:
        path = self._persist_dir / f"{self._section_filename(section)}.json"
        try:
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(asdict(entry), f)
            os.replace(tmp, path)
        except Exception:
            logger.exception("Failed to persist cache section %s", section)

    def load_persisted(self) -> None:
        if not self._persist_dir or not self._persist_dir.exists():
            return
        for path in self._persist_dir.glob("*.json"):
            section = path.stem
            try:
                with open(path) as f:
                    raw = json.load(f)
                self._store[section] = CachedSection(
                    data=raw["data"],
                    generated_at=raw["generated_at"],
                    ttl_seconds=raw["ttl_seconds"],
                )
                logger.info("Loaded cached section %s from disk", section)
            except Exception:
                logger.exception("Failed to load cached section %s", section)
