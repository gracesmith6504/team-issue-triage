import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.assessment import assess_issue
from app.core.models import IssueData

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def _fixture_to_issue_data(data: dict) -> IssueData:
    return IssueData(
        repo="NVIDIA/OpenShell",
        number=data["number"],
        title=data["title"],
        body=data["body"],
        labels=data["labels"],
        comments=data.get("comments", []),
        url=data["url"],
        created_at=data["created_at"],
    )


@pytest.fixture(
    params=[
        "protobuf_sync_failure.json",
        "helm_chart_regression.json",
        "tui_styling_issue.json",
        "openshift_scc_bug.json",
    ]
)
def fixture_issue(request):
    data = _load_fixture(request.param)
    return _fixture_to_issue_data(data)


def test_fixture_creates_valid_issue_data(fixture_issue):
    assert fixture_issue.repo == "NVIDIA/OpenShell"
    assert isinstance(fixture_issue.number, int)
    assert len(fixture_issue.title) > 0
    assert isinstance(fixture_issue.labels, list)


def test_fixture_issue_through_mock_assessment(fixture_issue):
    mock_llm = MagicMock()
    mock_llm.assess.return_value = {
        "relevance": 4,
        "relevance_reason": "Relevant to team",
        "urgency": 3,
        "urgency_reason": "Moderate",
        "action_clarity": 3,
        "action_clarity_reason": "Possible fix",
        "summary": "Test assessment",
        "recommendation": "Investigate",
    }

    result = assess_issue(fixture_issue, mock_llm, "claude-sonnet-4-6")

    assert result is not None
    assert result.issue_number == fixture_issue.number
    assert result.total == 10
    mock_llm.assess.assert_called_once()
