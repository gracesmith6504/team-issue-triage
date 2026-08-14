import dataclasses
import logging

from app.cache.section_cache import SectionCache
from app.cache.sections import SECTION_TTLS, Section
from app.config import TriageConfig

logger = logging.getLogger(__name__)


def refresh_vouch(config: TriageConfig, cache: SectionCache) -> None:
    from app.core.profiles import load_repo_config
    from app.vouch.fetcher import fetch_vouch_status

    repo_config = load_repo_config(config.profile_name, profiles_dir=config.profiles_dir)
    findings = fetch_vouch_status(repo_config.repo, config.github_token)
    data = dataclasses.asdict(findings)

    data["blocked_prs"] = _compute_blocked_prs(data, cache)

    cache.set(Section.VOUCH, data, SECTION_TTLS[Section.VOUCH])
    logger.info("Vouch section refreshed")


def _compute_blocked_prs(vouch_data: dict, cache: SectionCache) -> list[dict]:
    pr_entry = cache.get(Section.PR_HEALTH)
    if not pr_entry or not pr_entry.data:
        return []

    pending_by_author = {}
    for v in vouch_data.get("pending_vouches", []):
        pending_by_author[v["author"]] = v

    blocked = []
    for pr in pr_entry.data.get("all_open_pr_summaries", []):
        vouch = pending_by_author.get(pr["author"])
        if vouch:
            blocked.append({
                "pr_number": pr["number"],
                "pr_title": pr["title"],
                "pr_url": pr["url"],
                "author": pr["author"],
                "vouch_discussion": vouch["discussion_number"],
                "vouch_url": vouch["url"],
                "vouch_wait_days": vouch["wait_days"],
            })
    return blocked


def update_blocked_prs(cache: SectionCache) -> None:
    vouch_entry = cache.get(Section.VOUCH)
    if not vouch_entry:
        return
    vouch_data = vouch_entry.data
    vouch_data["blocked_prs"] = _compute_blocked_prs(vouch_data, cache)
    cache.set(Section.VOUCH, vouch_data, SECTION_TTLS[Section.VOUCH])
