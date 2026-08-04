from app.core.models import TriageResult, Urgency
from app.notifications.log import LogAdapter


def _make_result(urgency=Urgency.HIGH, primary_team="agent-ops"):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=2571,
        issue_title="bug(supervisor): SPIFFE crash",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2571",
        reasoning="Security issue",
        any_team_cares=True,
        primary_team=primary_team,
        primary_confidence=0.85,
        secondary_team=None,
        secondary_confidence=None,
        urgency=urgency,
        urgency_reasoning="Regression",
        summary="SPIFFE sandboxes crash",
        recommendation="Investigate",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00Z",
    )


def test_log_adapter_immediate(capsys):
    adapter = LogAdapter()
    adapter.deliver_immediate(_make_result(), {})
    captured = capsys.readouterr()
    assert "agent-ops" in captured.out
    assert "2571" in captured.out


def test_log_adapter_digest(capsys):
    adapter = LogAdapter()
    results = [_make_result(urgency=Urgency.MEDIUM), _make_result(urgency=Urgency.LOW)]
    adapter.deliver_digest(results, {})
    captured = capsys.readouterr()
    assert "2571" in captured.out


def test_log_adapter_empty_digest(capsys):
    adapter = LogAdapter()
    adapter.deliver_digest([], {})
    captured = capsys.readouterr()
    assert "0 issues" in captured.out or captured.out == ""


def test_log_adapter_digest_severity_order(capsys):
    """Digest should sort by severity: critical > high > medium > low."""
    adapter = LogAdapter()
    results = [
        _make_result(urgency=Urgency.LOW, primary_team="agent-ops"),
        _make_result(urgency=Urgency.CRITICAL, primary_team="agent-ops"),
        _make_result(urgency=Urgency.MEDIUM, primary_team="agent-ops"),
        _make_result(urgency=Urgency.HIGH, primary_team="agent-ops"),
    ]
    adapter.deliver_digest(results, {})
    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.strip().split("\n") if line.strip()]
    # First line is the header, remaining are issue lines
    issue_lines = lines[1:]
    urgencies = []
    for line in issue_lines:
        for level in ("critical", "high", "medium", "low"):
            if level in line:
                urgencies.append(level)
                break
    assert urgencies == ["critical", "high", "medium", "low"]


def test_log_adapter_collect_feedback():
    adapter = LogAdapter()
    assert adapter.collect_feedback() == []
