from unittest.mock import MagicMock, patch

import pytest

from app.sources.github import GitHubSource


@pytest.fixture()
def github_source():
    return GitHubSource(token="test-token")


@pytest.fixture()
def mock_issues_response():
    return [
        {
            "number": 2401,
            "title": "protobuf sync failed for v0.4.2",
            "body": "The sync job failed with error code 1.",
            "labels": [{"name": "kind/bug"}, {"name": "priority/critical"}],
            "html_url": "https://github.com/NVIDIA/OpenShell/issues/2401",
            "created_at": "2026-07-23T14:00:00Z",
            "pull_request": None,
            "author_association": "NONE",
            "user": {"login": "community-user"},
            "assignees": [],
        },
        {
            "number": 2400,
            "title": "Fix typo in README",
            "body": "Small typo fix.",
            "labels": [{"name": "docs"}],
            "html_url": "https://github.com/NVIDIA/OpenShell/issues/2400",
            "created_at": "2026-07-23T13:00:00Z",
            "author_association": "CONTRIBUTOR",
            "user": {"login": "contributor-user"},
            "assignees": [{"login": "alice"}],
        },
    ]


@patch("app.sources.github.requests.get")
def test_fetch_new_issues(mock_get, github_source, mock_issues_response):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_issues_response
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert len(issues) == 2
    assert issues[0].number == 2401
    assert issues[0].repo == "NVIDIA/OpenShell"
    assert issues[0].labels == ["kind/bug", "priority/critical"]


@patch("app.sources.github.requests.get")
def test_fetch_extracts_author_association(mock_get, github_source, mock_issues_response):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_issues_response
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert issues[0].author_association == "NONE"
    assert issues[0].author_login == "community-user"
    assert issues[0].assignees == []
    assert issues[1].author_association == "CONTRIBUTOR"
    assert issues[1].author_login == "contributor-user"
    assert issues[1].assignees == ["alice"]


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_filters_seen(mock_get, github_source, mock_issues_response):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_issues_response
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids={"NVIDIA/OpenShell#2401"},
    )

    assert len(issues) == 1
    assert issues[0].number == 2400


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_skips_pull_requests(mock_get, github_source):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "number": 100,
            "title": "PR: Fix something",
            "body": "A pull request.",
            "labels": [],
            "html_url": "https://github.com/NVIDIA/OpenShell/pull/100",
            "created_at": "2026-07-23T14:00:00Z",
            "pull_request": {"url": "https://api.github.com/..."},
        },
    ]
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert len(issues) == 0


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_skips_old_updated_issues(mock_get, github_source):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "number": 500,
            "title": "Old issue with new comment",
            "body": "Created a week ago.",
            "labels": [],
            "html_url": "https://github.com/NVIDIA/OpenShell/issues/500",
            "created_at": "2026-07-16T10:00:00Z",
        },
        {
            "number": 501,
            "title": "Brand new issue",
            "body": "Just filed.",
            "labels": [],
            "html_url": "https://github.com/NVIDIA/OpenShell/issues/501",
            "created_at": "2026-07-23T15:00:00Z",
        },
    ]
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert len(issues) == 1
    assert issues[0].number == 501


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_api_error(mock_get, github_source):
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "Rate limited"
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert issues == []


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_multiple_repos(mock_get, github_source):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "number": 1,
            "title": "Issue in repo",
            "body": "Test.",
            "labels": [],
            "html_url": "https://github.com/org/repo/issues/1",
            "created_at": "2026-07-23T14:00:00Z",
        },
    ]
    mock_get.return_value = mock_response

    github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell", "opendatahub-io/agent-ops"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert mock_get.call_count == 2


@patch("app.sources.github.requests.get")
def test_fetch_filters_correctly_when_since_has_microseconds(mock_get, github_source):
    """Regression: string comparison fails when since has microsecond precision."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "number": 600,
            "title": "Issue created before since",
            "body": "Should be filtered out.",
            "labels": [],
            "html_url": "https://github.com/NVIDIA/OpenShell/issues/600",
            "created_at": "2026-07-23T12:00:00Z",
        },
    ]
    mock_get.return_value = mock_response

    # since has microseconds (realistic output of datetime.isoformat())
    # 12:00:00.500000 is AFTER 12:00:00, so issue 600 was created BEFORE since
    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00.500000+00:00",
        seen_ids=set(),
    )

    assert len(issues) == 0  # issue should be filtered — it was created before since


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_same_number_different_repos_no_collision(
    mock_get, github_source
):
    """Issue #1 seen in repo A should not filter issue #1 from repo B."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "number": 1,
            "title": "Issue in this repo",
            "body": "Test.",
            "labels": [],
            "html_url": "https://github.com/other/repo/issues/1",
            "created_at": "2026-07-23T14:00:00Z",
        },
    ]
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["other/repo"],
        since="2026-07-23T12:00:00Z",
        seen_ids={"NVIDIA/OpenShell#1"},
    )

    assert len(issues) == 1
