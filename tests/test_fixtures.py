import json
from pathlib import Path

from app.core.models import IssueData
from app.core.triage_engine import extract_signals

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
        labels=data.get("labels", []),
        comments=data.get("comments", []),
        url=data["url"],
        created_at=data["created_at"],
    )


def test_fixture_creates_valid_issue_data():
    data = _load_fixture("protobuf_sync_failure.json")
    issue = _fixture_to_issue_data(data)
    assert issue.number == 2401
    assert "protobuf" in issue.title.lower()


def test_protobuf_fixture_signals():
    data = _load_fixture("protobuf_sync_failure.json")
    issue = _fixture_to_issue_data(data)
    signals = extract_signals(issue)
    assert signals.title_prefix is None  # no conventional commit prefix
    assert "area/sdk" not in signals.area_labels  # area/sdk, not area:sdk


def test_helm_fixture_signals():
    data = _load_fixture("helm_chart_regression.json")
    issue = _fixture_to_issue_data(data)
    signals = extract_signals(issue)
    assert signals.title_prefix is None


def test_tui_fixture_signals():
    data = _load_fixture("tui_styling_issue.json")
    issue = _fixture_to_issue_data(data)
    signals = extract_signals(issue)
    assert signals.title_prefix is None


def test_scc_fixture_signals():
    data = _load_fixture("openshift_scc_bug.json")
    issue = _fixture_to_issue_data(data)
    signals = extract_signals(issue)
    assert signals.title_prefix is None
