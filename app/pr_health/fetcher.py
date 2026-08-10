import logging
from datetime import datetime, timedelta, timezone

import requests

from app.pr_health.models import PRHealthFindings, PRStatus
from app.sources.github import GITHUB_API

logger = logging.getLogger(__name__)


def _gh_get(url: str, headers: dict, **kwargs) -> list | dict:
    resp = requests.get(url, headers=headers, timeout=15, **kwargs)
    resp.raise_for_status()
    return resp.json()


def _parse_dt(iso_str: str) -> datetime:
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def fetch_pr_health(
    repo: str,
    token: str,
    codeowners: list[str] | None = None,
) -> PRHealthFindings:
    if codeowners is None:
        codeowners = []
    codeowners_set = set(codeowners)
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    now = datetime.now(timezone.utc)

    open_prs = _fetch_open_prs(repo, headers)
    total_open = len(open_prs)

    awaiting_review = sum(1 for p in open_prs if p.get("requested_reviewers"))
    stale_14d = sum(
        1 for p in open_prs if (now - _parse_dt(p["updated_at"])).days >= 14
    )
    gator_count = sum(
        1
        for p in open_prs
        if any(lbl["name"].startswith("gator:") for lbl in p.get("labels", []))
    )
    gator_coverage_pct = round(gator_count / max(1, total_open) * 100)

    age_distribution = _compute_age_distribution(open_prs, now)

    stuck_prs = _find_stuck_prs(repo, open_prs, headers, codeowners_set, now)

    avg_review_wait = 0.0
    if stuck_prs:
        avg_review_wait = round(
            sum(p.days_since_last_review for p in stuck_prs) / len(stuck_prs),
            1,
        )

    velocity, velocity_prev = _compute_merge_velocity(repo, headers, now)

    return PRHealthFindings(
        total_open=total_open,
        awaiting_review=awaiting_review,
        stale_14d=stale_14d,
        gator_coverage_pct=gator_coverage_pct,
        merge_velocity=velocity,
        merge_velocity_prev=velocity_prev,
        avg_review_wait_days=avg_review_wait,
        stuck_prs=stuck_prs[:6],
        age_distribution=age_distribution,
        codeowners=codeowners,
    )


def _fetch_open_prs(repo: str, headers: dict) -> list[dict]:
    prs = _gh_get(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers,
        params={
            "state": "open",
            "sort": "updated",
            "direction": "desc",
            "per_page": 100,
        },
    )
    if len(prs) == 100:
        page2 = _gh_get(
            f"{GITHUB_API}/repos/{repo}/pulls",
            headers,
            params={
                "state": "open",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "page": 2,
            },
        )
        prs.extend(page2)
    return prs


def _compute_age_distribution(prs: list[dict], now: datetime) -> dict[str, dict]:
    buckets = {
        "lt_1w": {"count": 0, "label": "< 1 week"},
        "1_2w": {"count": 0, "label": "1-2 weeks"},
        "2_4w": {"count": 0, "label": "2-4 weeks"},
        "gt_1m": {"count": 0, "label": "> 1 month"},
    }
    for pr in prs:
        age = (now - _parse_dt(pr["created_at"])).days
        if age < 7:
            buckets["lt_1w"]["count"] += 1
        elif age < 14:
            buckets["1_2w"]["count"] += 1
        elif age < 28:
            buckets["2_4w"]["count"] += 1
        else:
            buckets["gt_1m"]["count"] += 1
    return buckets


def _find_stuck_prs(
    repo: str,
    all_prs: list[dict],
    headers: dict,
    codeowners: set[str],
    now: datetime,
) -> list[PRStatus]:
    oldest = sorted(all_prs, key=lambda p: p["created_at"])
    results: list[PRStatus] = []

    for pr in oldest[:20]:
        num = pr["number"]
        if pr.get("draft"):
            continue
        created = _parse_dt(pr["created_at"])
        age = (now - created).days
        if age < 7:
            continue

        try:
            reviews = _gh_get(f"{GITHUB_API}/repos/{repo}/pulls/{num}/reviews", headers)
            comments = _gh_get(
                f"{GITHUB_API}/repos/{repo}/issues/{num}/comments", headers
            )
            commits = _gh_get(f"{GITHUB_API}/repos/{repo}/pulls/{num}/commits", headers)
        except Exception:
            logger.exception("Failed to fetch details for PR #%d", num)
            continue

        author = pr["user"]["login"]
        actual_reviewers: set[str] = set()
        last_review_date = None
        review_count = 0

        for r in reviews:
            reviewer = r["user"]["login"]
            if (
                reviewer not in codeowners
                and reviewer != author
                and not reviewer.endswith("[bot]")
            ):
                actual_reviewers.add(reviewer)
            if reviewer != author:
                review_count += 1
                rd = _parse_dt(r["submitted_at"])
                if last_review_date is None or rd > last_review_date:
                    last_review_date = rd

        participants: set[str] = set()
        last_comment_date = None
        for c in comments:
            commenter = c["user"]["login"]
            if commenter != author and not commenter.endswith("[bot]"):
                participants.add(commenter)
                cd = _parse_dt(c["created_at"])
                if last_comment_date is None or cd > last_comment_date:
                    last_comment_date = cd

        last_author_commit = None
        for c in reversed(commits):
            if c.get("author") and c["author"].get("login") == author:
                last_author_commit = _parse_dt(c["commit"]["author"]["date"])
                break
        if not last_author_commit:
            last_author_commit = created

        days_since_author = (now - last_author_commit).days
        days_since_review = (now - last_review_date).days if last_review_date else age
        days_since_comment = (
            (now - last_comment_date).days if last_comment_date else None
        )

        gator = None
        for label in pr.get("labels", []):
            if label["name"].startswith("gator:"):
                gator = label["name"]
                break

        requested = [
            r["login"]
            for r in pr.get("requested_reviewers", [])
            if r["login"] not in codeowners
        ]
        auto_assigned = [
            r["login"]
            for r in pr.get("requested_reviewers", [])
            if r["login"] in codeowners
        ]

        all_engaged = actual_reviewers | participants
        activity_parts = [f"Author pushed {days_since_author}d ago"]
        if last_review_date:
            activity_parts.append(f"last review {days_since_review}d ago")
        else:
            activity_parts.append("no reviews")
        if days_since_comment is not None:
            activity_parts.append(f"last comment {days_since_comment}d ago")

        results.append(
            PRStatus(
                number=num,
                title=pr["title"],
                url=pr["html_url"],
                author=author,
                days_open=age,
                days_since_author_push=days_since_author,
                days_since_last_review=days_since_review,
                review_count=review_count,
                participants=sorted(all_engaged),
                last_activity=", ".join(activity_parts),
                is_draft=False,
                gator_label=gator,
                actual_reviewers=sorted(actual_reviewers),
                requested_non_codeowners=sorted(requested),
                auto_assigned=sorted(auto_assigned),
            )
        )

    results.sort(key=lambda p: p.days_since_last_review, reverse=True)
    return results


def _compute_merge_velocity(repo: str, headers: dict, now: datetime) -> tuple[int, int]:
    try:
        merged_resp = _gh_get(
            f"{GITHUB_API}/repos/{repo}/pulls",
            headers,
            params={
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
            },
        )
    except Exception:
        logger.exception("Failed to fetch merged PRs")
        return 0, 0

    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    this_week = 0
    last_week = 0

    for pr in merged_resp:
        if not pr.get("merged_at"):
            continue
        merged = _parse_dt(pr["merged_at"])
        if merged >= week_ago:
            this_week += 1
        elif merged >= two_weeks_ago:
            last_week += 1

    return this_week, last_week
