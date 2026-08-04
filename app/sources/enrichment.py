import logging
from dataclasses import dataclass

import requests

from app.core.models import TriageResult
from app.sources.github import GITHUB_API

logger = logging.getLogger(__name__)


@dataclass
class EnrichedIssue:
    result: TriageResult
    is_open: bool
    comment_count: int
    assignees: list[str]
    has_linked_pr: bool


def enrich_issues(results: list[TriageResult], token: str) -> dict[int, EnrichedIssue]:
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    seen: set[int] = set()
    enriched: dict[int, EnrichedIssue] = {}

    for result in results:
        if result.issue_number in seen:
            continue
        seen.add(result.issue_number)

        issue_data = _fetch_issue(result.repo, result.issue_number, headers)
        has_pr = _check_linked_pr(result.repo, result.issue_number, headers)

        enriched[result.issue_number] = EnrichedIssue(
            result=result,
            is_open=issue_data.get("state", "open") == "open",
            comment_count=issue_data.get("comments", 0),
            assignees=[a.get("login", "") for a in issue_data.get("assignees", [])],
            has_linked_pr=has_pr,
        )

    return enriched


def _fetch_issue(repo: str, number: int, headers: dict) -> dict:
    url = f"{GITHUB_API}/repos/{repo}/issues/{number}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                "Enrichment failed for %s#%d: %s", repo, number, resp.status_code
            )
            return {}
        return resp.json()
    except Exception:
        logger.exception("Enrichment request failed for %s#%d", repo, number)
        return {}


def _check_linked_pr(repo: str, number: int, headers: dict) -> bool:
    url = f"{GITHUB_API}/repos/{repo}/issues/{number}/timeline"
    timeline_headers = {
        **headers,
        "Accept": "application/vnd.github.mockingbird-preview+json",
    }
    try:
        resp = requests.get(url, headers=timeline_headers, timeout=10)
        if resp.status_code != 200:
            return False
        for event in resp.json():
            if event.get("event") == "cross-referenced":
                source_issue = event.get("source", {}).get("issue", {})
                if source_issue.get("pull_request"):
                    return True
        return False
    except Exception:
        logger.exception("Timeline request failed for %s#%d", repo, number)
        return False
