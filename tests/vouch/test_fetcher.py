from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.vouch.fetcher import fetch_vouch_status
from app.vouch.models import VouchFindings

NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

VOUCH_CATEGORY_ID = "DIC_abc123"


def _make_comment(body, association="NONE"):
    return {
        "body": body,
        "author": {"login": "reviewer"},
        "authorAssociation": association,
    }


def _make_discussion(
    number, author="newuser", created_days_ago=5, comments=None, closed=False
):
    created = (NOW - timedelta(days=created_days_ago)).isoformat()
    return {
        "number": number,
        "title": f"Vouch request from {author}",
        "author": {"login": author},
        "createdAt": created,
        "closed": closed,
        "comments": {"nodes": comments or []},
    }


def _categories_response(has_vouch=True):
    cats = [{"id": "DIC_other", "name": "General"}]
    if has_vouch:
        cats.append({"id": VOUCH_CATEGORY_ID, "name": "Vouch Requests"})
    return {"data": {"repository": {"discussionCategories": {"nodes": cats}}}}


def _discussions_response(discussions):
    return {"data": {"repository": {"discussions": {"nodes": discussions}}}}


def _make_response(data):
    resp = MagicMock()
    resp.json.return_value = data
    return resp


def _patch_dt(mock_dt):
    mock_dt.now.return_value = NOW
    mock_dt.fromisoformat = datetime.fromisoformat


@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_fetch_vouch_status_returns_findings(mock_post, mock_dt):
    _patch_dt(mock_dt)
    disc = _make_discussion(1, created_days_ago=10)
    mock_post.side_effect = [
        _make_response(_categories_response()),
        _make_response(_discussions_response([disc])),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert isinstance(result, VouchFindings)
    assert result.total_pending == 1


@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_no_vouch_category_returns_empty(mock_post, mock_dt):
    _patch_dt(mock_dt)
    mock_post.side_effect = [
        _make_response(_categories_response(has_vouch=False)),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert result.total_pending == 0
    assert result.pending_vouches == []


@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_pending_vouch_no_member_comment(mock_post, mock_dt):
    _patch_dt(mock_dt)
    disc = _make_discussion(
        1,
        created_days_ago=10,
        comments=[
            _make_comment("looks good", "NONE"),
        ],
    )
    mock_post.side_effect = [
        _make_response(_categories_response()),
        _make_response(_discussions_response([disc])),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert result.total_pending == 1
    assert result.pending_vouches[0].discussion_number == 1


@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_vouched_by_member(mock_post, mock_dt):
    _patch_dt(mock_dt)
    disc = _make_discussion(
        1,
        created_days_ago=10,
        comments=[
            _make_comment("/vouch", "MEMBER"),
        ],
    )
    mock_post.side_effect = [
        _make_response(_categories_response()),
        _make_response(_discussions_response([disc])),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert result.total_pending == 0


@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_vouch_ignored_from_non_member(mock_post, mock_dt):
    _patch_dt(mock_dt)
    disc = _make_discussion(
        1,
        created_days_ago=10,
        comments=[
            _make_comment("/vouch", "NONE"),
        ],
    )
    mock_post.side_effect = [
        _make_response(_categories_response()),
        _make_response(_discussions_response([disc])),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert result.total_pending == 1


@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_responded_in_7d_counting(mock_post, mock_dt):
    _patch_dt(mock_dt)
    disc = _make_discussion(
        1,
        created_days_ago=3,
        comments=[
            _make_comment("/vouch", "COLLABORATOR"),
        ],
    )
    mock_post.side_effect = [
        _make_response(_categories_response()),
        _make_response(_discussions_response([disc])),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert result.responded_in_7d == 1
    assert result.total_pending == 0


@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_over_30d_count(mock_post, mock_dt):
    _patch_dt(mock_dt)
    discs = [
        _make_discussion(1, created_days_ago=45),
        _make_discussion(2, created_days_ago=35),
        _make_discussion(3, created_days_ago=10),
    ]
    mock_post.side_effect = [
        _make_response(_categories_response()),
        _make_response(_discussions_response(discs)),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert result.over_30d_count == 2
    assert result.longest_wait_days == 45


@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_closed_discussions_skipped(mock_post, mock_dt):
    _patch_dt(mock_dt)
    discs = [
        _make_discussion(1, created_days_ago=10, closed=True),
        _make_discussion(2, created_days_ago=5),
    ]
    mock_post.side_effect = [
        _make_response(_categories_response()),
        _make_response(_discussions_response(discs)),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert result.total_pending == 1
    assert result.pending_vouches[0].discussion_number == 2
