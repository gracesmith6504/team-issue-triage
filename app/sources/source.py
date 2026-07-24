from typing import Protocol

from app.core.models import IssueData


class IssueSource(Protocol):
    def fetch_new_issues(
        self, repos: list[str], since: str, seen_ids: set[int]
    ) -> list[IssueData]: ...
