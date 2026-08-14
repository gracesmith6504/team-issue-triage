import logging

from app.cache.section_cache import SectionCache
from app.cache.sections import SECTION_TTLS, Section
from app.config import TriageConfig

logger = logging.getLogger(__name__)

_DEFAULT_SPARKLINES = {
    "triage": [0, 0, 0, 0, 0, 0, 0],
    "prs": [0, 0, 0, 0, 0, 0, 0],
    "blocked": [0, 0, 0, 0, 0, 0, 0],
    "velocity": [0, 0, 0, 0, 0, 0, 0],
}


def refresh_metrics(config: TriageConfig, cache: SectionCache) -> None:
    from app.metrics.compute import build_sparklines
    from app.metrics.store import JsonlMetricsStore

    store = JsonlMetricsStore(config.metrics_path)
    recent = store.read(limit=7)
    sparklines = build_sparklines(recent) if recent else _DEFAULT_SPARKLINES
    cache.set(Section.METRICS, sparklines, SECTION_TTLS[Section.METRICS])
    logger.info("Metrics section refreshed")
