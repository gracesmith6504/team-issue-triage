def apply_confidence_rules(
    primary_confidence: float,
    secondary_confidence: float | None,
    any_team_cares: bool,
    thresholds: dict[str, float],
) -> str | None:
    if not any_team_cares:
        return None

    auto_assign = thresholds.get("auto_assign", 0.8)
    multi_team_gap = thresholds.get("multi_team_gap", 0.2)
    uncertain = thresholds.get("uncertain", 0.5)
    none_min = thresholds.get("none_min", 0.75)

    gap = primary_confidence - (secondary_confidence or 0.0)

    if primary_confidence > auto_assign and gap > multi_team_gap:
        return "auto"

    if secondary_confidence is not None and gap < multi_team_gap:
        return "multi_team"

    if primary_confidence < uncertain:
        return "uncertain"

    if primary_confidence < none_min:
        return "forced_none"

    return None
