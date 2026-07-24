import logging

import requests

from app.core.models import IssueData
from app.core.truncation import truncate_comment

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubSource:
    def __init__(self, token: str):
        self._headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def fetch_new_issues(
        self, repos: list[str], since: str, seen_ids: set[int]
    ) -> list[IssueData]:
        all_issues = []
        for repo in repos:
            issues = self._fetch_repo_issues(repo, since, seen_ids)
            all_issues.extend(issues)
        return all_issues

    def _fetch_repo_issues(
        self, repo: str, since: str, seen_ids: set[int]
    ) -> list[IssueData]:
        url = f"{GITHUB_API}/repos/{repo}/issues"
        params = {
            "since": since,
            "state": "open",
            "sort": "created",
            "direction": "desc",
            "per_page": 100,
        }

        response = requests.get(url, headers=self._headers, params=params)
        if response.status_code != 200:
            logger.error(
                "GitHub API error for %s: %s %s",
                repo,
                response.status_code,
                response.text,
            )
            return []

        issues = []
        for item in response.json():
            if item.get("pull_request"):
                continue
            if item["number"] in seen_ids:
                continue

            comment_count = item.get("comments", 0)
            comments = (
                self._fetch_comments(repo, item["number"]) if comment_count else []
            )

            issues.append(
                IssueData(
                    repo=repo,
                    number=item["number"],
                    title=item["title"],
                    body=item.get("body") or "",
                    labels=[label["name"] for label in item.get("labels", [])],
                    comments=comments,
                    url=item["html_url"],
                    created_at=item["created_at"],
                )
            )

        logger.info("Fetched %d new issues from %s", len(issues), repo)
        return issues

    def _fetch_comments(self, repo: str, issue_number: int) -> list[dict]:
        url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
        params = {"per_page": 5, "direction": "desc"}

        response = requests.get(url, headers=self._headers, params=params)
        if response.status_code != 200:
            logger.warning("Failed to fetch comments for %s#%d", repo, issue_number)
            return []

        return [
            {
                "user": comment.get("user", {}).get("login", "unknown"),
                "body": truncate_comment(comment.get("body")),
            }
            for comment in response.json()
        ]
