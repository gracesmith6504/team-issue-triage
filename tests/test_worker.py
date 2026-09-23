from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import TriageConfig


@pytest.fixture()
def config(tmp_path):
    return TriageConfig(
        watch_repos=["o/r"],
        llm_provider="vertex",
        llm_model=None,
        vertex_project_id="test-project",
        vertex_region="us-east5",
        anthropic_api_key=None,
        github_token="ghp_test",
        slack_webhook_url=None,
        state_path=tmp_path / "state.json",
        assessment_log_path=tmp_path / "assessments.jsonl",
        profiles_dir=Path(__file__).parent.parent / "profiles",
        default_lookback_hours=24,
        report_output_path=None,
        worker_mode=True,
    )


def test_worker_skips_seen_issue_and_advances_last_checked(config, monkeypatch):
    monkeypatch.setenv("DASHBOARD_URL", "http://dashboard.test")

    github_resp = MagicMock()
    github_resp.status_code = 200
    github_resp.json.return_value = [
        {
            "number": 5,
            "title": "Already triaged",
            "body": "",
            "state": "open",
            "labels": [],
            "comments": 0,
            "html_url": "https://github.com/o/r/issues/5",
            "created_at": "2026-09-23T09:00:00Z",
            "author_association": "NONE",
            "user": {"login": "someone"},
            "assignees": [],
        }
    ]

    with (
        patch("app.worker.DashboardClient") as mock_client_cls,
        patch("app.sources.github.requests.get", return_value=github_resp),
        patch("app.worker.triage_issue") as mock_triage,
    ):
        mock_client = mock_client_cls.return_value
        mock_client.get_state.return_value = {
            "last_checked": "2026-09-23T00:00:00+00:00",
            "seen_issues": ["o/r#5"],
        }

        from app.worker import worker_triage

        worker_triage(config)

    mock_triage.assert_not_called()
    mock_client.post_assessments.assert_called_once()
    assert mock_client.post_assessments.call_args.kwargs["last_checked"] is not None
