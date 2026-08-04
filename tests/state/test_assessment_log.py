import json
from datetime import datetime, timedelta, timezone

from app.core.models import TriageResult, Urgency
from app.state.assessment_log import (
    append_result,
    format_review,
    read_results,
    read_results_as_triage,
    record_to_result,
    result_to_record,
)


def _make_result(**overrides) -> TriageResult:
    defaults = {
        "repo": "NVIDIA/OpenShell",
        "issue_number": 2571,
        "issue_title": "bug(supervisor): SPIFFE crash",
        "issue_url": "https://github.com/NVIDIA/OpenShell/issues/2571",
        "reasoning": "Security issue",
        "any_team_cares": True,
        "primary_team": "ai-safety",
        "primary_confidence": 0.85,
        "secondary_team": "agent-ops",
        "secondary_confidence": 0.65,
        "urgency": Urgency.HIGH,
        "urgency_reasoning": "Regression",
        "summary": "SPIFFE crash",
        "recommendation": "Investigate",
        "confidence_flag": None,
        "assessed_at": datetime.now(timezone.utc).isoformat(),
    }
    defaults.update(overrides)
    return TriageResult(**defaults)


def test_result_to_record():
    result = _make_result()
    record = result_to_record(result)
    assert record["primary_team"] == "ai-safety"
    assert record["urgency"] == "high"
    assert record["secondary_team"] == "agent-ops"


def test_append_result_creates_file(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result())
    assert log.exists()
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["issue_number"] == 2571


def test_append_result_appends(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result(issue_number=1))
    append_result(log, _make_result(issue_number=2))
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 2


def test_read_results_no_file(tmp_path):
    assert read_results(tmp_path / "missing.jsonl") == []


def test_read_results_all(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result(issue_number=1))
    append_result(log, _make_result(issue_number=2))
    records = read_results(log)
    assert len(records) == 2


def test_read_results_team_filter(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result(primary_team="ai-safety"))
    append_result(log, _make_result(primary_team="agent-ops"))
    records = read_results(log, team_filter="ai-safety")
    assert len(records) == 1
    assert records[0]["primary_team"] == "ai-safety"


def test_read_results_urgency_filter(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result(urgency=Urgency.HIGH))
    append_result(log, _make_result(urgency=Urgency.LOW))
    records = read_results(log, urgency_filter="high")
    assert len(records) == 1


def test_read_results_since_filter(tmp_path):
    log = tmp_path / "results.jsonl"
    old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    append_result(log, _make_result(assessed_at=old_time))
    append_result(log, _make_result())
    records = read_results(log, since_hours=24)
    assert len(records) == 1


def test_record_to_result_roundtrip():
    """result_to_record and record_to_result should be inverses."""
    original = _make_result()
    record = result_to_record(original)
    restored = record_to_result(record)
    assert restored.repo == original.repo
    assert restored.issue_number == original.issue_number
    assert restored.issue_title == original.issue_title
    assert restored.issue_url == original.issue_url
    assert restored.reasoning == original.reasoning
    assert restored.any_team_cares == original.any_team_cares
    assert restored.primary_team == original.primary_team
    assert restored.primary_confidence == original.primary_confidence
    assert restored.secondary_team == original.secondary_team
    assert restored.secondary_confidence == original.secondary_confidence
    assert restored.urgency == original.urgency
    assert restored.urgency_reasoning == original.urgency_reasoning
    assert restored.summary == original.summary
    assert restored.recommendation == original.recommendation
    assert restored.confidence_flag == original.confidence_flag
    assert restored.assessed_at == original.assessed_at


def test_record_to_result_minimal():
    """record_to_result handles missing optional fields gracefully."""
    record = {
        "repo": "NVIDIA/OpenShell",
        "issue_number": 100,
        "issue_title": "Test",
        "issue_url": "https://github.com/NVIDIA/OpenShell/issues/100",
        "urgency": "low",
    }
    result = record_to_result(record)
    assert result.primary_team == "unknown"
    assert result.primary_confidence == 0.0
    assert result.secondary_team is None
    assert result.reasoning == ""
    assert result.urgency == Urgency.LOW


def test_format_review_empty():
    assert "No results" in format_review([])


def test_format_review_groups_by_team():
    records = [
        result_to_record(_make_result(primary_team="ai-safety")),
        result_to_record(_make_result(primary_team="agent-ops")),
    ]
    output = format_review(records)
    assert "ai-safety" in output
    assert "agent-ops" in output


def test_read_results_start_date_filters(tmp_path):
    log_path = tmp_path / "log.jsonl"
    old_result = _make_result(assessed_at="2026-07-01T10:00:00+00:00", issue_number=1)
    new_result = _make_result(assessed_at="2026-07-28T10:00:00+00:00", issue_number=2)
    append_result(log_path, old_result)
    append_result(log_path, new_result)

    records = read_results(log_path, start_date="2026-07-20T00:00:00+00:00")
    assert len(records) == 1
    assert records[0]["issue_number"] == 2


def test_read_results_end_date_filters(tmp_path):
    log_path = tmp_path / "log.jsonl"
    old_result = _make_result(assessed_at="2026-07-01T10:00:00+00:00", issue_number=1)
    new_result = _make_result(assessed_at="2026-07-28T10:00:00+00:00", issue_number=2)
    append_result(log_path, old_result)
    append_result(log_path, new_result)

    records = read_results(log_path, end_date="2026-07-15T00:00:00+00:00")
    assert len(records) == 1
    assert records[0]["issue_number"] == 1


def test_read_results_date_range(tmp_path):
    log_path = tmp_path / "log.jsonl"
    for i, date in enumerate(
        [
            "2026-07-01T10:00:00+00:00",
            "2026-07-15T10:00:00+00:00",
            "2026-07-28T10:00:00+00:00",
        ]
    ):
        append_result(log_path, _make_result(assessed_at=date, issue_number=i + 1))

    records = read_results(
        log_path,
        start_date="2026-07-10T00:00:00+00:00",
        end_date="2026-07-20T00:00:00+00:00",
    )
    assert len(records) == 1
    assert records[0]["issue_number"] == 2


def test_read_results_as_triage(tmp_path):
    log_path = tmp_path / "log.jsonl"
    result = _make_result()
    append_result(log_path, result)

    triage_results = read_results_as_triage(log_path)
    assert len(triage_results) == 1
    assert isinstance(triage_results[0], TriageResult)
    assert triage_results[0].issue_number == result.issue_number
