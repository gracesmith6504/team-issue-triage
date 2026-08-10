import dataclasses
import logging

import requests

from app.sources.github import GITHUB_API

logger = logging.getLogger(__name__)


def _count_issues(repo: str, token: str, label: str | None = None) -> int:
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    total = 0
    page = 1
    while page <= 5:
        params: dict = {"state": "open", "per_page": 100, "page": page}
        if label:
            params["labels"] = label
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/issues",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        items = [i for i in data if not i.get("pull_request")]
        total += len(items)
        if len(data) < 100:
            break
        page += 1
    return total


def _enrich_issue_counts(report, config, repo_config):
    repo = repo_config.repo
    token = config.github_token
    report.summary.total_open = _count_issues(repo, token)
    report.summary.triage_needed = _count_issues(
        repo, token, label="state:triage-needed"
    )


def enrich_report(report, config, repo_config):
    try:
        _enrich_issue_counts(report, config, repo_config)
    except Exception:
        logger.exception("Issue count enrichment failed")

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

    _cross_reference_blocked_prs(report)


def _cross_reference_blocked_prs(report):
    if not report.pr_health or not report.vouch_status:
        return

    pending_by_author = {}
    for v in report.vouch_status.get("pending_vouches", []):
        pending_by_author[v["author"]] = v

    blocked = []
    for pr in report.pr_health.get("stuck_prs", []):
        vouch = pending_by_author.get(pr["author"])
        if vouch:
            blocked.append(
                {
                    "pr_number": pr["number"],
                    "pr_title": pr["title"],
                    "pr_url": pr["url"],
                    "author": pr["author"],
                    "vouch_discussion": vouch["discussion_number"],
                    "vouch_url": vouch["url"],
                    "vouch_wait_days": vouch["wait_days"],
                }
            )

    report.vouch_status["blocked_prs"] = blocked
