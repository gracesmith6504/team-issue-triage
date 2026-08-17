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
        self._timers: dict[str, threading.Timer] = {}

    def start_all(self) -> None:
        self._refresh_issues(run_synthesis_after=True)
        self._refresh_metrics()

        if self._config.pr_health_enabled:
            self._refresh_pr_health()
        if self._config.vouch_tracking_enabled:
            self._refresh_vouch()

        self._schedule_synthesis()

    def _refresh_issues(self, *, run_synthesis_after: bool = False) -> None:
        def run():
            try:
                from app.refresh.issues import refresh_issues

                refresh_issues(self._config, self._cache)
                if run_synthesis_after:
                    self._run_synthesis_once()
            except Exception:
                logger.exception("Issues refresh failed")
            self._schedule("issues", self._refresh_issues, SECTION_TTLS[Section.ISSUES])

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _refresh_pr_health(self) -> None:
        def run():
            try:
                from app.refresh.pr_health import refresh_pr_health

                refresh_pr_health(self._config, self._cache)
            except Exception:
                logger.exception("PR health refresh failed")
            self._schedule(
                "pr_health", self._refresh_pr_health, SECTION_TTLS[Section.PR_HEALTH]
            )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _refresh_vouch(self) -> None:
        def run():
            try:
                from app.refresh.vouch import refresh_vouch

                refresh_vouch(self._config, self._cache)
            except Exception:
                logger.exception("Vouch refresh failed")
            self._schedule("vouch", self._refresh_vouch, SECTION_TTLS[Section.VOUCH])

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _run_synthesis_once(self) -> None:
        try:
            from app.refresh.synthesis import refresh_synthesis

            refresh_synthesis(self._config, self._cache)
        except Exception:
            logger.exception("Synthesis refresh failed")

    def _refresh_synthesis(self) -> None:
        def run():
            self._run_synthesis_once()
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
            self._schedule(
                "metrics", self._refresh_metrics, SECTION_TTLS[Section.METRICS]
            )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _schedule(self, key: str, func, delay_seconds: int) -> None:
        with self._lock:
            old = self._timers.pop(key, None)
            if old:
                old.cancel()
            timer = threading.Timer(delay_seconds, func)
            timer.daemon = True
            timer.start()
            self._timers[key] = timer

    def _schedule_synthesis(self) -> None:
        report_hour = getattr(self._config, "report_schedule_hour", 9)
        now = datetime.now(timezone.utc)
        # Find the next Monday at report_hour UTC
        days_until_monday = (7 - now.weekday()) % 7  # 0 if today is Monday
        target = now.replace(hour=report_hour, minute=0, second=0, microsecond=0)
        target += timedelta(days=days_until_monday)
        if now >= target:
            target += timedelta(weeks=1)
        delay = (target - now).total_seconds()
        logger.info(
            "Scheduling weekly synthesis refresh at %s (in %.1f hours)",
            target.isoformat(),
            delay / 3600,
        )
        self._schedule("synthesis", self._refresh_synthesis, int(delay))

    def refresh_all_now(self) -> None:
        self._run_one_shot("issues", self._do_refresh_issues)
        self._run_one_shot("metrics", self._do_refresh_metrics)
        if self._config.pr_health_enabled:
            self._run_one_shot("pr_health", self._do_refresh_pr_health)
        if self._config.vouch_tracking_enabled:
            self._run_one_shot("vouch", self._do_refresh_vouch)
        self._run_one_shot("synthesis_manual", self._run_synthesis_once)

    def _run_one_shot(self, label: str, func) -> None:
        thread = threading.Thread(target=func, daemon=True, name=f"refresh-{label}")
        thread.start()

    def _do_refresh_issues(self) -> None:
        try:
            from app.refresh.issues import refresh_issues

            refresh_issues(self._config, self._cache)
        except Exception:
            logger.exception("Issues refresh failed (manual)")

    def _do_refresh_pr_health(self) -> None:
        try:
            from app.refresh.pr_health import refresh_pr_health

            refresh_pr_health(self._config, self._cache)
        except Exception:
            logger.exception("PR health refresh failed (manual)")

    def _do_refresh_vouch(self) -> None:
        try:
            from app.refresh.vouch import refresh_vouch

            refresh_vouch(self._config, self._cache)
        except Exception:
            logger.exception("Vouch refresh failed (manual)")

    def _do_refresh_metrics(self) -> None:
        try:
            from app.refresh.metrics import refresh_metrics

            refresh_metrics(self._config, self._cache)
        except Exception:
            logger.exception("Metrics refresh failed (manual)")
