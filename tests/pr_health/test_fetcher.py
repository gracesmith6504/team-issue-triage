from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.pr_health.fetcher import _compute_age_distribution, fetch_pr_health
from app.pr_health.models import PRHealthFindings

NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_pr(
    number,
    title="Test PR",
    created_days_ago=3,
    updated_days_ago=1,
    draft=False,
    labels=None,
    requested_reviewers=None,
    author="testuser",
    merged_at=None,
):
    created = (NOW - timedelta(days=created_days_ago)).isoformat()
    updated = (NOW - timedelta(days=updated_days_ago)).isoformat()
    return {
        "number": number,
        "title": title,
        "html_url": f"https://github.com/test/repo/pull/{number}",
        "user": {"login": author},
        "created_at": created,
        "updated_at": updated,
        "draft": draft,
        "labels": labels or [],
        "requested_reviewers": requested_reviewers or [],
        "merged_at": merged_at,
    }


def _make_response(data):
    resp = MagicMock()
    resp.json.return_value = data
    return resp


def _patch_dt(mock_dt):
    mock_dt.now.return_value = NOW
    mock_dt.fromisoformat = datetime.fromisoformat


# --- Unit tests for pure functions ---


def test_age_distribution_buckets():
    prs = [
        {"created_at": (NOW - timedelta(days=3)).isoformat()},
        {"created_at": (NOW - timedelta(days=10)).isoformat()},
        {"created_at": (NOW - timedelta(days=20)).isoformat()},
        {"created_at": (NOW - timedelta(days=40)).isoformat()},
    ]
    result = _compute_age_distribution(prs, NOW)
    assert result["lt_1w"]["count"] == 1
    assert result["1_2w"]["count"] == 1
    assert result["2_4w"]["count"] == 1
    assert result["gt_1m"]["count"] == 1


def test_age_distribution_all_in_one_bucket():
    prs = [
        {"created_at": (NOW - timedelta(days=1)).isoformat()},
        {"created_at": (NOW - timedelta(days=2)).isoformat()},
    ]
    result = _compute_age_distribution(prs, NOW)
    assert result["lt_1w"]["count"] == 2
    assert result["1_2w"]["count"] == 0


# --- Integration tests through fetch_pr_health ---


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_fetch_pr_health_returns_findings(mock_get, mock_dt):
    _patch_dt(mock_dt)
    prs = [_make_pr(1, created_days_ago=3), _make_pr(2, created_days_ago=5)]
    mock_get.side_effect = [
        _make_response(prs),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert isinstance(result, PRHealthFindings)
    assert result.total_open == 2
    assert result.stuck_prs == []


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_stuck_prs_skips_drafts(mock_get, mock_dt):
    _patch_dt(mock_dt)
    draft_pr = _make_pr(1, created_days_ago=30, draft=True)
    mock_get.side_effect = [
        _make_response([draft_pr]),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert result.stuck_prs == []


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_stuck_prs_filters_codeowners_from_participants(mock_get, mock_dt):
    _patch_dt(mock_dt)
    old_pr = _make_pr(1, created_days_ago=14, author="contributor")
    codeowner_review = {
        "user": {"login": "mrunalp"},
        "submitted_at": (NOW - timedelta(days=2)).isoformat(),
    }
    mock_get.side_effect = [
        _make_response([old_pr]),
        _make_response([codeowner_review]),
        _make_response([]),
        _make_response(
            [
                {
                    "commit": {
                        "author": {"date": (NOW - timedelta(days=5)).isoformat()}
                    },
                    "author": {"login": "contributor"},
                }
            ]
        ),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token", codeowners=["mrunalp"])
    assert len(result.stuck_prs) == 1
    assert "mrunalp" not in result.stuck_prs[0].participants


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_stuck_prs_excludes_bots(mock_get, mock_dt):
    _patch_dt(mock_dt)
    old_pr = _make_pr(1, created_days_ago=14, author="contributor")
    bot_comment = {"user": {"login": "dependabot[bot]"}, "body": "update deps"}
    mock_get.side_effect = [
        _make_response([old_pr]),
        _make_response([]),
        _make_response([bot_comment]),
        _make_response(
            [
                {
                    "commit": {
                        "author": {"date": (NOW - timedelta(days=5)).isoformat()}
                    },
                    "author": {"login": "contributor"},
                }
            ]
        ),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert len(result.stuck_prs) == 1
    assert "dependabot[bot]" not in result.stuck_prs[0].participants


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_merge_velocity_counts_by_week(mock_get, mock_dt):
    _patch_dt(mock_dt)
    closed_prs = [
        _make_pr(10, merged_at=(NOW - timedelta(days=2)).isoformat()),
        _make_pr(11, merged_at=(NOW - timedelta(days=5)).isoformat()),
        _make_pr(12, merged_at=(NOW - timedelta(days=10)).isoformat()),
        _make_pr(13),
    ]
    mock_get.side_effect = [
        _make_response([]),
        _make_response(closed_prs),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert result.merge_velocity == 2
    assert result.merge_velocity_prev == 1


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_pagination_fetches_page_2(mock_get, mock_dt):
    _patch_dt(mock_dt)
    page1 = [_make_pr(i, created_days_ago=1) for i in range(100)]
    page2 = [_make_pr(100, created_days_ago=1)]
    mock_get.side_effect = [
        _make_response(page1),
        _make_response(page2),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert result.total_open == 101
    assert mock_get.call_count == 3


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_api_error_on_velocity_returns_zero(mock_get, mock_dt):
    _patch_dt(mock_dt)
    import requests

    error_resp = MagicMock()
    error_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("403")

    mock_get.side_effect = [
        _make_response([]),
        error_resp,
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert result.merge_velocity == 0
    assert result.merge_velocity_prev == 0


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_last_activity_includes_comment_date(mock_get, mock_dt):
    _patch_dt(mock_dt)
    old_pr = _make_pr(1, created_days_ago=30, author="contributor")
    review = {
        "user": {"login": "reviewer1"},
        "submitted_at": (NOW - timedelta(days=20)).isoformat(),
    }
    comment = {
        "user": {"login": "reviewer2"},
        "body": "Please address the feedback",
        "created_at": (NOW - timedelta(days=3)).isoformat(),
    }
    commit = {
        "commit": {"author": {"date": (NOW - timedelta(days=25)).isoformat()}},
        "author": {"login": "contributor"},
    }
    mock_get.side_effect = [
        _make_response([old_pr]),
        _make_response([review]),
        _make_response([comment]),
        _make_response([commit]),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert len(result.stuck_prs) == 1
    assert "last comment 3d ago" in result.stuck_prs[0].last_activity


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_last_activity_omits_comment_older_than_review(mock_get, mock_dt):
    _patch_dt(mock_dt)
    old_pr = _make_pr(1, created_days_ago=30, author="contributor")
    review = {
        "user": {"login": "reviewer1"},
        "submitted_at": (NOW - timedelta(days=10)).isoformat(),
    }
    comment = {
        "user": {"login": "reviewer2"},
        "body": "Looks interesting",
        "created_at": (NOW - timedelta(days=15)).isoformat(),
    }
    commit = {
        "commit": {"author": {"date": (NOW - timedelta(days=20)).isoformat()}},
        "author": {"login": "contributor"},
    }
    mock_get.side_effect = [
        _make_response([old_pr]),
        _make_response([review]),
        _make_response([comment]),
        _make_response([commit]),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert len(result.stuck_prs) == 1
    assert "last comment" not in result.stuck_prs[0].last_activity
    assert "last review 10d ago" in result.stuck_prs[0].last_activity


@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_last_activity_ignores_bot_comments(mock_get, mock_dt):
    _patch_dt(mock_dt)
    old_pr = _make_pr(1, created_days_ago=30, author="contributor")
    bot_comment = {
        "user": {"login": "github-actions[bot]"},
        "body": "This PR is stale",
        "created_at": (NOW - timedelta(days=1)).isoformat(),
    }
    commit = {
        "commit": {"author": {"date": (NOW - timedelta(days=25)).isoformat()}},
        "author": {"login": "contributor"},
    }
    mock_get.side_effect = [
        _make_response([old_pr]),
        _make_response([]),
        _make_response([bot_comment]),
        _make_response([commit]),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert len(result.stuck_prs) == 1
    assert "last comment" not in result.stuck_prs[0].last_activity
