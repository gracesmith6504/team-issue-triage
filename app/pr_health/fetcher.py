import logging
from datetime import datetime, timedelta, timezone

import requests

from app.pr_health.models import OpenPRSummary, PRHealthFindings
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

    all_open_pr_summaries = _build_enriched_summaries(
        repo, open_prs, headers, now,
    )

    avg_review_wait = 0.0

    velocity, velocity_prev, merged_dates = _compute_merge_velocity(
        repo, headers, now
    )

    return PRHealthFindings(
        total_open=total_open,
        awaiting_review=awaiting_review,
        stale_14d=stale_14d,
        gator_coverage_pct=gator_coverage_pct,
        merge_velocity=velocity,
        merge_velocity_prev=velocity_prev,
        avg_review_wait_days=avg_review_wait,
        age_distribution=age_distribution,
        codeowners=codeowners,
        all_open_pr_summaries=all_open_pr_summaries,
        merged_dates=merged_dates,
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


_BOT_LOGINS = {"github-actions", "copy-pr-bot", "gator-agent"}


def _is_bot(login: str) -> bool:
    return login.endswith("[bot]") or login.endswith("-bot") or login in _BOT_LOGINS


def _gh_get_all(url: str, headers: dict) -> list:
    all_items: list = []
    page = 1
    while True:
        batch = _gh_get(url, headers, params={"per_page": 100, "page": page})
        if not isinstance(batch, list):
            return [batch]
        all_items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return all_items


def _build_enriched_summaries(
    repo: str,
    all_prs: list[dict],
    headers: dict,
    now: datetime,
) -> list[OpenPRSummary]:
    summaries: list[OpenPRSummary] = []

    for pr in all_prs:
        num = pr["number"]
        author = pr.get("user", {}).get("login", "")
        author_association = pr.get("author_association", "NONE")
        is_draft = bool(pr.get("draft"))

        review_count = 0
        last_review_at = ""
        last_human_comment_at = ""
        last_author_comment_at = ""
        participants: list[str] = []

        if not is_draft:
            try:
                reviews = _gh_get_all(
                    f"{GITHUB_API}/repos/{repo}/pulls/{num}/reviews", headers,
                )
                comments = _gh_get_all(
                    f"{GITHUB_API}/repos/{repo}/issues/{num}/comments", headers,
                )
            except Exception:
                logger.exception("Failed to enrich PR #%d", num)
                reviews, comments = [], []

            engaged: set[str] = set()
            for r in reviews:
                if r.get("state") == "PENDING":
                    continue
                reviewer = r["user"]["login"]
                if reviewer != author and not _is_bot(reviewer):
                    review_count += 1
                    engaged.add(reviewer)
                    submitted = r.get("submitted_at", "")
                    if submitted > last_review_at:
                        last_review_at = submitted

            for c in comments:
                commenter = c["user"]["login"]
                if _is_bot(commenter):
                    continue
                created = c.get("created_at", "")
                if commenter == author:
                    if created > last_author_comment_at:
                        last_author_comment_at = created
                else:
                    engaged.add(commenter)
                    if created > last_human_comment_at:
                        last_human_comment_at = created

            participants = sorted(engaged)

        summaries.append(OpenPRSummary(
            number=num,
            title=pr.get("title", ""),
            url=pr.get("html_url", ""),
            author=author,
            created_at=pr["created_at"],
            updated_at=pr["updated_at"],
            has_requested_reviewers=bool(pr.get("requested_reviewers")),
            is_draft=is_draft,
            has_gator_label=any(
                lbl["name"].startswith("gator:")
                for lbl in pr.get("labels", [])
            ),
            author_association=author_association,
            review_count=review_count,
            last_review_at=last_review_at,
            last_human_comment_at=last_human_comment_at,
            last_author_comment_at=last_author_comment_at,
            participants=participants,
        ))

    logger.info("Enriched %d/%d PRs (skipped drafts)", len(summaries), len(all_prs))
    return summaries


def _compute_merge_velocity(
    repo: str, headers: dict, now: datetime
) -> tuple[int, int, list[str]]:
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
        return 0, 0, []

    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    this_week = 0
    last_week = 0
    merged_dates: list[str] = []

    for pr in merged_resp:
        if not pr.get("merged_at"):
            continue
        merged_dates.append(pr["merged_at"])
        merged = _parse_dt(pr["merged_at"])
        if merged >= week_ago:
            this_week += 1
        elif merged >= two_weeks_ago:
            last_week += 1

    return this_week, last_week, merged_dates
