from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import TriageConfig
from app.triage import run_report


def _make_config(tmp_path):
    log_path = tmp_path / "assessments.jsonl"
    log_path.touch()
    return TriageConfig(
        watch_repos=["NVIDIA/OpenShell"],
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        vertex_project_id=None,
        vertex_region="us-east5",
        anthropic_api_key="test-key",
        github_token="test-token",
        slack_webhook_url=None,
        state_path=tmp_path / "state.json",
        assessment_log_path=log_path,
        profiles_dir=Path("profiles"),
        default_lookback_hours=24,
        report_output_path=None,
    )


@patch("app.core.llm.build_llm_client")
def test_run_report_empty_log(mock_llm, tmp_path, capsys):
    config = _make_config(tmp_path)
    llm = MagicMock()
    llm.assess.return_value = {"narrative": "No issues."}
    mock_llm.return_value = llm

    run_report(config)
    output = capsys.readouterr().out
    assert "Bird's Eye View" in output


@patch("app.core.llm.build_llm_client")
def test_run_report_writes_to_file(mock_llm, tmp_path):
    config = _make_config(tmp_path)
    output_path = tmp_path / "report.md"
    config.report_output_path = output_path
    llm = MagicMock()
    llm.assess.return_value = {"narrative": "Test narrative."}
    mock_llm.return_value = llm

    run_report(config, output_path=output_path)
    assert output_path.exists()
    content = output_path.read_text()
    assert "Bird's Eye View" in content
