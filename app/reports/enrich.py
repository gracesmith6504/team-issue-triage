import dataclasses
import logging

logger = logging.getLogger(__name__)


def enrich_report(report, config, repo_config):
    if config.pr_health_enabled:
        try:
            from app.pr_health.fetcher import fetch_pr_health

            codeowners = repo_config.codeowners or []
            pr_health = fetch_pr_health(
                repo_config.repo, config.github_token, codeowners
            )
            report.pr_health = dataclasses.asdict(pr_health)
        except Exception:
            logger.exception("PR health fetch failed")

    if config.vouch_tracking_enabled:
        try:
            from app.vouch.fetcher import fetch_vouch_status

            vouch = fetch_vouch_status(repo_config.repo, config.github_token)
            report.vouch_status = dataclasses.asdict(vouch)
        except Exception:
            logger.exception("Vouch status fetch failed")
