import logging
from datetime import datetime, timezone

import requests

from app.vouch.models import PendingVouch, VouchFindings

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.github.com/graphql"

CATEGORIES_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussionCategories(first: 20) {
      nodes { id name }
    }
  }
}
"""

DISCUSSIONS_QUERY = """
query($owner: String!, $name: String!, $catId: ID!) {
  repository(owner: $owner, name: $name) {
    discussions(categoryId: $catId, first: 50, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        number
        title
        author { login }
        createdAt
        closed
        comments(first: 30) {
          nodes {
            body
            author { login }
            authorAssociation
          }
        }
      }
    }
  }
}
"""

VOUCH_ASSOCIATIONS = {"MEMBER", "COLLABORATOR", "OWNER"}


def fetch_vouch_status(repo: str, token: str) -> VouchFindings:
    owner, name = repo.split("/")
    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
    }

    vouch_cat_id = _find_vouch_category(owner, name, headers)
    if not vouch_cat_id:
        logger.warning("No vouch request category found for %s", repo)
        return VouchFindings(
            total_pending=0,
            responded_in_7d=0,
            longest_wait_days=0,
            over_30d_count=0,
            pending_vouches=[],
        )

    discussions = _fetch_discussions(owner, name, vouch_cat_id, headers)
    now = datetime.now(timezone.utc)

    pending: list[PendingVouch] = []
    responded_count = 0

    for disc in discussions:
        author = disc["author"]["login"] if disc.get("author") else "unknown"
        created = datetime.fromisoformat(disc["createdAt"].replace("Z", "+00:00"))
        wait_days = (now - created).days

        has_vouch = _check_vouched(disc)

        if has_vouch and wait_days <= 7:
            responded_count += 1

        if disc.get("closed"):
            continue

        if not has_vouch:
            pending.append(
                PendingVouch(
                    author=author,
                    discussion_number=disc["number"],
                    url=f"https://github.com/{owner}/{name}/discussions/{disc['number']}",
                    wait_days=wait_days,
                    created_at=disc["createdAt"],
                )
            )

    pending.sort(key=lambda v: v.wait_days, reverse=True)
    longest = pending[0].wait_days if pending else 0
    over_30d = sum(1 for v in pending if v.wait_days > 30)

    return VouchFindings(
        total_pending=len(pending),
        responded_in_7d=responded_count,
        longest_wait_days=longest,
        over_30d_count=over_30d,
        pending_vouches=pending,
    )


def _find_vouch_category(owner: str, name: str, headers: dict) -> str | None:
    resp = requests.post(
        GRAPHQL_URL,
        json={
            "query": CATEGORIES_QUERY,
            "variables": {"owner": owner, "name": name},
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    categories = (
        data.get("data", {})
        .get("repository", {})
        .get("discussionCategories", {})
        .get("nodes", [])
    )
    for cat in categories:
        if "vouch" in cat["name"].lower():
            return cat["id"]
    return None


def _fetch_discussions(owner: str, name: str, cat_id: str, headers: dict) -> list[dict]:
    resp = requests.post(
        GRAPHQL_URL,
        json={
            "query": DISCUSSIONS_QUERY,
            "variables": {"owner": owner, "name": name, "catId": cat_id},
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return (
        data.get("data", {})
        .get("repository", {})
        .get("discussions", {})
        .get("nodes", [])
    )


def _check_vouched(discussion: dict) -> bool:
    for comment in discussion.get("comments", {}).get("nodes", []):
        body = (comment.get("body") or "").strip().lower()
        assoc = comment.get("authorAssociation", "")
        if "/vouch" in body and assoc in VOUCH_ASSOCIATIONS:
            return True
    return False
