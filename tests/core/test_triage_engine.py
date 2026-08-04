# tests/core/test_triage_engine.py
from unittest.mock import MagicMock

from app.core.models import IssueData, Urgency
from app.core.profiles import RepoConfig, TeamProfile
from app.core.triage_engine import extract_signals, triage_issue


def _make_issue(title="bug(supervisor): SPIFFE crash", labels=None, body="body text"):
    return IssueData(
        repo="NVIDIA/OpenShell",
        number=2571,
        title=title,
        body=body,
        labels=labels or [],
        comments=[],
        url="https://github.com/NVIDIA/OpenShell/issues/2571",
        created_at="2026-08-01T00:00:00Z",
    )


def _make_repo_config():
    team = TeamProfile(
        team_id="agent-ops",
        team_name="Agent Ops",
        description="Core integration",
        areas={"primary": ["cli", "sdk"], "secondary": []},
        urgency_overrides={},
        examples=[],
        notifications={},
    )
    return RepoConfig(
        repo="NVIDIA/OpenShell",
        pinned_version="v0.0.92",
        team_profiles=[team],
        no_team_prefixes=["build"],
        none_examples=[],
        confidence_thresholds={
            "auto_assign": 0.8,
            "multi_team_gap": 0.2,
            "uncertain": 0.5,
            "none_min": 0.75,
        },
        reporting={},
    )


class TestExtractSignals:
    def test_conventional_commit_prefix(self):
        issue = _make_issue(title="bug(supervisor): SPIFFE crash")
        signals = extract_signals(issue)
        assert signals.title_prefix == "supervisor"

    def test_feat_prefix(self):
        issue = _make_issue(title="feat(cli): add new flag")
        signals = extract_signals(issue)
        assert signals.title_prefix == "cli"

    def test_nested_prefix(self):
        issue = _make_issue(title="feat(driver-podman): user namespace support")
        signals = extract_signals(issue)
        assert signals.title_prefix == "driver-podman"

    def test_no_prefix(self):
        issue = _make_issue(title="VM sandbox SSH disconnects with broken pipe")
        signals = extract_signals(issue)
        assert signals.title_prefix is None

    def test_area_labels(self):
        issue = _make_issue(labels=["area:supervisor", "area:sandbox", "kind/bug"])
        signals = extract_signals(issue)
        assert signals.area_labels == ["area:supervisor", "area:sandbox"]

    def test_topic_labels(self):
        issue = _make_issue(labels=["topic:security", "topic:compatibility"])
        signals = extract_signals(issue)
        assert signals.topic_labels == ["topic:security", "topic:compatibility"]

    def test_state_label(self):
        issue = _make_issue(labels=["state:triage-needed", "area:cli"])
        signals = extract_signals(issue)
        assert signals.state_label == "state:triage-needed"

    def test_issue_type_bug(self):
        issue = _make_issue(labels=["Bug", "area:cli"])
        signals = extract_signals(issue)
        assert signals.issue_type == "Bug"

    def test_issue_type_feature_request(self):
        issue = _make_issue(labels=["feature request"])
        signals = extract_signals(issue)
        assert signals.issue_type == "feature request"

    def test_issue_type_improvement(self):
        issue = _make_issue(labels=["Improvement"])
        signals = extract_signals(issue)
        assert signals.issue_type == "Improvement"

    def test_no_labels(self):
        issue = _make_issue(labels=[])
        signals = extract_signals(issue)
        assert signals.area_labels == []
        assert signals.topic_labels == []
        assert signals.state_label is None
        assert signals.issue_type is None


class TestTriageIssue:
    def _mock_llm(self, response):
        client = MagicMock()
        client.assess.return_value = response
        return client

    def test_successful_triage(self):
        llm = self._mock_llm(
            {
                "reasoning": "CLI feature, agent-ops primary area",
                "any_team_cares": True,
                "primary_team": "agent-ops",
                "primary_confidence": 0.9,
                "secondary_team": None,
                "secondary_confidence": None,
                "urgency": "medium",
                "urgency_reasoning": "Feature request",
                "summary": "New CLI flag",
                "recommendation": "Review the feature request",
            }
        )
        result = triage_issue(
            _make_issue(title="feat(cli): add flag"),
            llm,
            "claude-sonnet-4-6",
            _make_repo_config(),
            "system prompt",
        )
        assert result is not None
        assert result.primary_team == "agent-ops"
        assert result.urgency == Urgency.MEDIUM
        assert result.any_team_cares is True

    def test_no_team_cares(self):
        llm = self._mock_llm(
            {
                "reasoning": "Build system, no team",
                "any_team_cares": False,
                "primary_team": "none",
                "primary_confidence": 0.95,
                "secondary_team": None,
                "secondary_confidence": None,
                "urgency": "low",
                "urgency_reasoning": "Design discussion",
                "summary": "Bazel evaluation",
                "recommendation": "No action",
            }
        )
        result = triage_issue(
            _make_issue(title="feat(build): Bazel"),
            llm,
            "claude-sonnet-4-6",
            _make_repo_config(),
            "system prompt",
        )
        assert result is not None
        assert result.any_team_cares is False
        assert result.primary_team == "none"

    def test_llm_returns_none(self):
        llm = self._mock_llm(None)
        result = triage_issue(
            _make_issue(),
            llm,
            "claude-sonnet-4-6",
            _make_repo_config(),
            "system prompt",
        )
        assert result is None

    def test_forced_none_clears_team(self):
        """When confidence_flag is forced_none, primary_team should be 'none'
        and secondary fields should be cleared."""
        llm = self._mock_llm(
            {
                "reasoning": "Maybe agent-ops but unsure",
                "any_team_cares": True,
                "primary_team": "agent-ops",
                "primary_confidence": 0.6,
                "secondary_team": "ai-safety",
                "secondary_confidence": 0.3,
                "urgency": "low",
                "urgency_reasoning": "Low confidence",
                "summary": "Unclear ownership",
                "recommendation": "Review manually",
            }
        )
        result = triage_issue(
            _make_issue(title="Something ambiguous"),
            llm,
            "claude-sonnet-4-6",
            _make_repo_config(),
            "system prompt",
        )
        assert result is not None
        assert result.confidence_flag == "forced_none"
        assert result.any_team_cares is False
        assert result.primary_team == "none"
        assert result.secondary_team is None
        assert result.secondary_confidence is None

    def test_multi_team_confidence_flag(self):
        llm = self._mock_llm(
            {
                "reasoning": "Supervisor but SPIFFE",
                "any_team_cares": True,
                "primary_team": "ai-safety",
                "primary_confidence": 0.85,
                "secondary_team": "agent-ops",
                "secondary_confidence": 0.75,
                "urgency": "high",
                "urgency_reasoning": "Security crash",
                "summary": "SPIFFE crash",
                "recommendation": "Investigate",
            }
        )
        result = triage_issue(
            _make_issue(),
            llm,
            "claude-sonnet-4-6",
            _make_repo_config(),
            "system prompt",
        )
        assert result is not None
        assert result.confidence_flag == "multi_team"
