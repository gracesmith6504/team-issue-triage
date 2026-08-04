from app.core.scoring import apply_confidence_rules

THRESHOLDS = {
    "auto_assign": 0.8,
    "multi_team_gap": 0.2,
    "uncertain": 0.5,
    "none_min": 0.75,
}


class TestApplyConfidenceRules:
    def test_auto_assign(self):
        result = apply_confidence_rules(0.9, 0.5, True, THRESHOLDS)
        assert result == "auto"

    def test_auto_assign_boundary(self):
        result = apply_confidence_rules(0.81, 0.5, True, THRESHOLDS)
        assert result == "auto"

    def test_multi_team_small_gap(self):
        result = apply_confidence_rules(0.85, 0.75, True, THRESHOLDS)
        assert result == "multi_team"

    def test_multi_team_equal_confidence(self):
        result = apply_confidence_rules(0.8, 0.8, True, THRESHOLDS)
        assert result == "multi_team"

    def test_uncertain_low_confidence(self):
        result = apply_confidence_rules(0.4, None, True, THRESHOLDS)
        assert result == "uncertain"

    def test_uncertain_boundary(self):
        result = apply_confidence_rules(0.49, None, True, THRESHOLDS)
        assert result == "uncertain"

    def test_normal_assignment(self):
        result = apply_confidence_rules(0.76, 0.3, True, THRESHOLDS)
        assert result is None

    def test_normal_no_secondary(self):
        result = apply_confidence_rules(0.76, None, True, THRESHOLDS)
        assert result is None

    def test_forced_none_low_confidence_team_picked(self):
        result = apply_confidence_rules(0.6, None, True, THRESHOLDS)
        assert result == "forced_none"

    def test_forced_none_boundary(self):
        result = apply_confidence_rules(0.74, None, True, THRESHOLDS)
        assert result == "forced_none"

    def test_forced_none_not_when_already_none(self):
        result = apply_confidence_rules(0.6, None, False, THRESHOLDS)
        assert result is None

    def test_forced_none_not_when_above_threshold(self):
        result = apply_confidence_rules(0.76, None, True, THRESHOLDS)
        assert result is None

    def test_no_team_cares_always_none(self):
        result = apply_confidence_rules(0.9, None, False, THRESHOLDS)
        assert result is None

    def test_multi_team_takes_priority_over_forced_none(self):
        result = apply_confidence_rules(0.7, 0.6, True, THRESHOLDS)
        assert result == "multi_team"
