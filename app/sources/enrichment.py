import logging
from dataclasses import dataclass

import requests

from app.core.models import TriageResult
from app.sources.github import GITHUB_API

logger = logging.getLogger(__name__)


@dataclass
class EnrichedIssue:
    result: TriageResult
    has_linked_pr: bool
    linked_pr_url: str | None = None
    linked_pr_draft: bool = False


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

        pr_data = _check_linked_pr(result.repo, result.issue_number, headers)

        enriched[result.issue_number] = EnrichedIssue(
            result=result,
            has_linked_pr=pr_data["has_pr"],
            linked_pr_url=pr_data.get("url"),
            linked_pr_draft=pr_data.get("draft", False),
        )

    return enriched


def _check_linked_pr(repo: str, number: int, headers: dict) -> dict:
    """Check for linked PR and return details (URL, draft status).

    Returns most recent linked PR if multiple exist.
    """
    url = f"{GITHUB_API}/repos/{repo}/issues/{number}/timeline"
    timeline_headers = {
        **headers,
        "Accept": "application/vnd.github.mockingbird-preview+json",
    }
    try:
        resp = requests.get(url, headers=timeline_headers, timeout=10)
        if resp.status_code != 200:
            return {"has_pr": False}

        # Track most recent PR (timeline is chronological, so last one wins)
        pr_url = None
        for event in resp.json():
            if event.get("event") == "cross-referenced":
                source_issue = event.get("source", {}).get("issue", {})
                if source_issue.get("pull_request"):
                    pr_url = source_issue.get("html_url")

        if not pr_url:
            return {"has_pr": False}

        # Extract PR number from URL and fetch draft status
        # URL format: https://github.com/NVIDIA/OpenShell/pull/2638
        pr_number = pr_url.split("/")[-1]
        pr_api_url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}"

        pr_resp = requests.get(pr_api_url, headers=headers, timeout=10)
        if pr_resp.status_code == 200:
            pr_data = pr_resp.json()
            return {
                "has_pr": True,
                "url": pr_url,
                "draft": pr_data.get("draft", False),
            }

        # Fallback if PR fetch fails
        return {"has_pr": True, "url": pr_url, "draft": False}

    except Exception:
        logger.exception("Timeline request failed for %s#%d", repo, number)
        return {"has_pr": False}
