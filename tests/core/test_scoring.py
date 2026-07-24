from app.core.models import Verdict
from app.core.scoring import clamp_score, compute_verdict, format_scores


class TestClampScore:
    def test_valid_int(self):
        assert clamp_score(3) == 3

    def test_string_int(self):
        assert clamp_score("4") == 4

    def test_below_min(self):
        assert clamp_score(0) == 1

    def test_above_max(self):
        assert clamp_score(10) == 5

    def test_none(self):
        assert clamp_score(None) == 3

    def test_invalid_string(self):
        assert clamp_score("abc") == 3

    def test_boundary_1(self):
        assert clamp_score(1) == 1

    def test_boundary_5(self):
        assert clamp_score(5) == 5


class TestComputeVerdict:
    def test_escalate(self):
        verdict, total, override = compute_verdict(5, 5, 4)
        assert verdict == Verdict.ESCALATE
        assert total == 14
        assert override is None

    def test_track(self):
        verdict, total, override = compute_verdict(3, 3, 3)
        assert verdict == Verdict.TRACK
        assert total == 9

    def test_watch(self):
        verdict, total, override = compute_verdict(2, 2, 2)
        assert verdict == Verdict.WATCH
        assert total == 6

    def test_skip(self):
        verdict, total, override = compute_verdict(1, 1, 1)
        assert verdict == Verdict.SKIP
        assert total == 3

    def test_escalate_threshold_boundary(self):
        verdict, _, _ = compute_verdict(4, 4, 4)
        assert verdict == Verdict.ESCALATE

    def test_track_threshold_boundary(self):
        verdict, _, _ = compute_verdict(3, 3, 2)
        assert verdict == Verdict.TRACK

    def test_watch_threshold_boundary(self):
        verdict, _, _ = compute_verdict(2, 2, 1)
        assert verdict == Verdict.WATCH

    def test_override_urgency5_relevance3_forces_escalate(self):
        verdict, total, override = compute_verdict(3, 5, 1)
        assert verdict == Verdict.ESCALATE
        assert total == 9
        assert override == "Urgency=5 + Relevance>=3 forces ESCALATE"

    def test_override_urgency5_relevance2_no_force(self):
        verdict, _, override = compute_verdict(2, 5, 1)
        assert verdict == Verdict.TRACK
        assert override is None

    def test_override_relevance1_caps_at_watch(self):
        verdict, total, override = compute_verdict(1, 5, 5)
        assert verdict == Verdict.WATCH
        assert total == 11
        assert override == "Relevance=1 caps at WATCH"

    def test_override_relevance1_already_skip(self):
        verdict, _, override = compute_verdict(1, 1, 1)
        assert verdict == Verdict.SKIP
        assert override is None

    def test_custom_thresholds(self):
        custom = {"ESCALATE": 14, "TRACK": 10, "WATCH": 6}
        verdict, _, _ = compute_verdict(4, 4, 4, thresholds=custom)
        assert verdict == Verdict.TRACK

    def test_override_precedence_relevance1_over_urgency5(self):
        verdict, _, override = compute_verdict(1, 5, 5)
        assert verdict == Verdict.WATCH
        assert "Relevance=1" in override


class TestFormatScores:
    def test_format_with_reasons(self):
        result = format_scores(
            relevance=5,
            urgency=4,
            action_clarity=3,
            relevance_reason="Team-owned area",
            urgency_reason="Regression",
            action_clarity_reason="Needs investigation",
        )
        assert "Team Relevance: 5/5" in result
        assert "Urgency: 4/5" in result
        assert "Action Clarity: 3/5" in result
        assert "Team-owned area" in result

    def test_format_empty_reasons(self):
        result = format_scores(
            relevance=3,
            urgency=2,
            action_clarity=1,
            relevance_reason="",
            urgency_reason="",
            action_clarity_reason="",
        )
        assert "Team Relevance: 3/5" in result
        assert " — " not in result
