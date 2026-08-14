import logging
from datetime import datetime, timezone

import requests

from app.vouch.models import CompletedVouch, PendingVouch, VouchFindings

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
            createdAt
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
    completed: list[CompletedVouch] = []

    for disc in discussions:
        author = disc["author"]["login"] if disc.get("author") else "unknown"
        created = datetime.fromisoformat(disc["createdAt"].replace("Z", "+00:00"))
        wait_days = (now - created).days
        disc_url = f"https://github.com/{owner}/{name}/discussions/{disc['number']}"

        vouched_at = _check_vouched(disc)

        if vouched_at:
            completed.append(
                CompletedVouch(
                    author=author,
                    discussion_number=disc["number"],
                    url=disc_url,
                    vouched_at=vouched_at,
                )
            )

        if disc.get("closed"):
            continue

        if not vouched_at:
            pending.append(
                PendingVouch(
                    author=author,
                    discussion_number=disc["number"],
                    url=disc_url,
                    wait_days=wait_days,
                    created_at=disc["createdAt"],
                )
            )

    pending.sort(key=lambda v: v.wait_days, reverse=True)
    longest = pending[0].wait_days if pending else 0
    over_30d = sum(1 for v in pending if v.wait_days > 30)

    responded_count = sum(
        1
        for c in completed
        if (now - datetime.fromisoformat(c.vouched_at.replace("Z", "+00:00"))).days <= 7
    )

    return VouchFindings(
        total_pending=len(pending),
        responded_in_7d=responded_count,
        longest_wait_days=longest,
        over_30d_count=over_30d,
        pending_vouches=pending,
        completed_vouches=completed,
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


def _check_vouched(discussion: dict) -> str | None:
    """Return the timestamp of the first /vouch comment, or None."""
    for comment in discussion.get("comments", {}).get("nodes", []):
        body = (comment.get("body") or "").strip().lower()
        assoc = comment.get("authorAssociation", "")
        if "/vouch" in body and assoc in VOUCH_ASSOCIATIONS:
            return comment.get("createdAt", "")
    return None
