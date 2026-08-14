import logging
import threading
from datetime import datetime, timedelta, timezone

from app.cache.section_cache import SectionCache
from app.cache.sections import SECTION_TTLS, Section
from app.config import TriageConfig

logger = logging.getLogger(__name__)


class SectionRefresher:
    def __init__(self, config: TriageConfig, cache: SectionCache):
        self._config = config
        self._cache = cache
        self._lock = threading.Lock()
        self._timers: list[threading.Timer] = []

    def start_all(self) -> None:
        self._refresh_issues()
        self._refresh_metrics()

        if self._config.pr_health_enabled:
            self._refresh_pr_health()
        if self._config.vouch_tracking_enabled:
            self._refresh_vouch()

        self._schedule_synthesis()

    def _refresh_issues(self) -> None:
        def run():
            try:
                from app.refresh.issues import refresh_issues
                refresh_issues(self._config, self._cache)
            except Exception:
                logger.exception("Issues refresh failed")
            self._schedule(self._refresh_issues, SECTION_TTLS[Section.ISSUES])

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _refresh_pr_health(self) -> None:
        def run():
            try:
                from app.refresh.pr_health import refresh_pr_health
                refresh_pr_health(self._config, self._cache)
            except Exception:
                logger.exception("PR health refresh failed")
            self._schedule(self._refresh_pr_health, SECTION_TTLS[Section.PR_HEALTH])

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _refresh_vouch(self) -> None:
        def run():
            try:
                from app.refresh.vouch import refresh_vouch
                refresh_vouch(self._config, self._cache)
            except Exception:
                logger.exception("Vouch refresh failed")
            self._schedule(self._refresh_vouch, SECTION_TTLS[Section.VOUCH])

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _refresh_synthesis(self) -> None:
        def run():
            try:
                from app.refresh.synthesis import refresh_synthesis
                refresh_synthesis(self._config, self._cache)
            except Exception:
                logger.exception("Synthesis refresh failed")
            self._schedule_synthesis()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _refresh_metrics(self) -> None:
        def run():
            try:
                from app.refresh.metrics import refresh_metrics
                refresh_metrics(self._config, self._cache)
            except Exception:
                logger.exception("Metrics refresh failed")
            self._schedule(self._refresh_metrics, SECTION_TTLS[Section.METRICS])

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _schedule(self, func, delay_seconds: int) -> None:
        timer = threading.Timer(delay_seconds, func)
        timer.daemon = True
        timer.start()
        self._timers.append(timer)

    def _schedule_synthesis(self) -> None:
        report_hour = getattr(self._config, "report_schedule_hour", 9)
        now = datetime.now(timezone.utc)
        target = now.replace(hour=report_hour, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        delay = (target - now).total_seconds()
        logger.info(
            "Scheduling synthesis refresh at %s (in %.1f hours)",
            target.isoformat(), delay / 3600,
        )
        self._schedule(self._refresh_synthesis, int(delay))

    def refresh_all_now(self) -> None:
        self._refresh_issues()
        self._refresh_metrics()
        if self._config.pr_health_enabled:
            self._refresh_pr_health()
        if self._config.vouch_tracking_enabled:
            self._refresh_vouch()
        self._refresh_synthesis()
