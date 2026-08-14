import dataclasses
import logging

from app.cache.section_cache import SectionCache
from app.cache.sections import SECTION_TTLS, Section
from app.config import TriageConfig

logger = logging.getLogger(__name__)


def refresh_pr_health(config: TriageConfig, cache: SectionCache) -> None:
    from app.core.profiles import load_repo_config
    from app.pr_health.fetcher import fetch_pr_health

    repo_config = load_repo_config(config.profile_name, profiles_dir=config.profiles_dir)
    codeowners = repo_config.codeowners or []
    findings = fetch_pr_health(repo_config.repo, config.github_token, codeowners)
    cache.set(Section.PR_HEALTH, dataclasses.asdict(findings), SECTION_TTLS[Section.PR_HEALTH])
    logger.info("PR health section refreshed")

    from app.refresh.vouch import update_blocked_prs
    update_blocked_prs(cache)
