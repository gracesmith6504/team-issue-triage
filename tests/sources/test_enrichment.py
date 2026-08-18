from unittest.mock import MagicMock, patch

from app.core.models import TriageResult, Urgency
from app.sources.enrichment import enrich_issues


def _make_result(number, repo="NVIDIA/OpenShell"):
    return TriageResult(
        repo=repo,
        issue_number=number,
        issue_title=f"Issue {number}",
        issue_url=f"https://github.com/{repo}/issues/{number}",
        reasoning="test",
        any_team_cares=True,
        primary_team="agent-ops",
        primary_confidence=0.9,
        secondary_team=None,
        secondary_confidence=None,
        urgency=Urgency.MEDIUM,
        urgency_reasoning="test",
        summary="test",
        recommendation="test",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00+00:00",
    )


@patch("app.sources.enrichment.requests.get")
def test_enrich_issues_basic(mock_get):
    timeline_resp = MagicMock()
    timeline_resp.status_code = 200
    timeline_resp.json.return_value = []

    mock_get.return_value = timeline_resp

    results = [_make_result(42)]
    enriched = enrich_issues(results, "ghp_test")

    assert 42 in enriched
    assert enriched[42].has_linked_pr is False
    assert enriched[42].result is results[0]


@patch("app.sources.enrichment.requests.get")
def test_enrich_detects_linked_pr(mock_get):
    timeline_resp = MagicMock()
    timeline_resp.status_code = 200
    timeline_resp.json.return_value = [
        {"event": "commented"},
        {
            "event": "cross-referenced",
            "source": {
                "issue": {
                    "pull_request": {"merged_at": None},
                    "html_url": "https://github.com/NVIDIA/OpenShell/pull/123",
                }
            },
        },
    ]

    pr_resp = MagicMock()
    pr_resp.status_code = 200
    pr_resp.json.return_value = {"draft": False}

    mock_get.side_effect = [timeline_resp, pr_resp]

    enriched = enrich_issues([_make_result(10)], "ghp_test")
    assert enriched[10].has_linked_pr is True


@patch("app.sources.enrichment.requests.get")
def test_enrich_fallback_on_api_error(mock_get):
    error_resp = MagicMock()
    error_resp.status_code = 403
    error_resp.text = "Rate limited"

    mock_get.return_value = error_resp

    enriched = enrich_issues([_make_result(99)], "ghp_test")
    assert 99 in enriched
    assert enriched[99].has_linked_pr is False


@patch("app.sources.enrichment.requests.get")
def test_enrich_deduplicates_by_issue_number(mock_get):
    timeline_resp = MagicMock()
    timeline_resp.status_code = 200
    timeline_resp.json.return_value = []

    mock_get.return_value = timeline_resp

    results = [_make_result(42), _make_result(42)]
    enriched = enrich_issues(results, "ghp_test")

    assert len(enriched) == 1
    assert mock_get.call_count == 1


@patch("app.sources.enrichment.requests.get")
def test_enrich_empty_list(mock_get):
    enriched = enrich_issues([], "ghp_test")
    assert enriched == {}
    mock_get.assert_not_called()


@patch("app.sources.enrichment.requests.get")
def test_enrich_sets_auth_header(mock_get):
    timeline_resp = MagicMock()
    timeline_resp.status_code = 200
    timeline_resp.json.return_value = []

    mock_get.return_value = timeline_resp

    enrich_issues([_make_result(1)], "ghp_secret")

    for call in mock_get.call_args_list:
        headers = call[1].get("headers", {})
        assert headers["Authorization"] == "token ghp_secret"
