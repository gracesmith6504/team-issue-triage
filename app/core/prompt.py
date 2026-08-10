from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.truncation import truncate_body, truncate_comment

if TYPE_CHECKING:
    from app.core.models import IssueData, IssueSignals
    from app.core.profiles import RepoConfig, TeamProfile


def build_system_prompt(repo_config: RepoConfig) -> str:
    sections = [
        _build_preamble(),
        _build_teams_section(repo_config.team_profiles),
        _build_routing_signals(repo_config),
        _build_urgency_scale(),
        _build_calibration_examples(repo_config),
        _build_output_format(),
    ]
    return "\n\n".join(sections)


def build_user_prompt(issue: IssueData, signals: IssueSignals) -> str:
    parts = [f"Issue from {issue.repo} (#{issue.number}):"]

    parts.append("\nSIGNALS (pre-extracted):")
    parts.append(f"- Title prefix: {signals.title_prefix or '(none)'}")
    parts.append(f"- Area labels: {', '.join(signals.area_labels) or '(none)'}")
    parts.append(f"- Topic labels: {', '.join(signals.topic_labels) or '(none)'}")
    parts.append(f"- State: {signals.state_label or '(none)'}")
    parts.append(f"- Type: {signals.issue_type or '(none)'}")

    parts.append(f"\nTitle: {issue.title}")
    parts.append(f"\nBody:\n{truncate_body(issue.body)}")
    parts.append(f"\nLabels: {', '.join(issue.labels) if issue.labels else '(none)'}")

    if issue.comments:
        parts.append("\nComments (most recent):")
        for c in issue.comments[-5:]:
            parts.append(
                f"  @{c.get('user', 'unknown')}: {truncate_comment(c.get('body', ''))}"
            )

    return "\n".join(parts)


def _build_preamble() -> str:
    return (
        "You are a multi-team issue triage agent. You assess GitHub issues from\n"
        "the OpenShell repository and determine which Red Hat engineering team,\n"
        "if any, should care about each issue.\n\n"
        "## Your task\n\n"
        "For each issue, answer three questions:\n"
        "1. Does any Red Hat team need to care? (yes or no)\n"
        "2. If yes, which team should own it? (pick from the list below)\n"
        "3. How urgent is it? (critical / high / medium / low)"
    )


def _build_teams_section(profiles: list[TeamProfile]) -> str:
    lines = ["## Teams"]
    for p in profiles:
        lines.append(f"\n### {p.team_id} — {p.team_name}")
        lines.append(p.description.strip())
    return "\n".join(lines)


def _build_routing_signals(repo_config: RepoConfig) -> str:
    lines = [
        "## Routing Signals",
        "",
        "IMPORTANT: 97% of state:triage-needed issues have NO area labels.",
        "Area labels get added DURING triage — they are a result of the process,",
        "not an input. Do not expect them. Route primarily from the title prefix",
        "and the issue body.",
        "",
        "SIGNAL 1 — Title prefix component: OpenShell issues use conventional",
        "commit titles like feat(cli):, bug(supervisor):. The component in",
        "parentheses is a strong hint. Check it FIRST. But read the issue body",
        "too — the prefix tells you the CODE area, the body tells you the",
        "PROBLEM domain. When they disagree, the problem domain wins.",
        "",
        'Example: "bug(supervisor): SPIFFE-enabled sandboxes crash" — prefix',
        "says supervisor (agent-ops), but the problem is SPIFFE identity",
        "security (ai-safety). Route to ai-safety.",
        "",
        "SIGNAL 2 — Issue body keywords and problem domain: For the 28% of",
        "issues with no title prefix, and for all issues where the prefix is",
        "ambiguous, read the issue body. Look for team-specific keywords:",
    ]

    for p in repo_config.team_profiles:
        keywords = ", ".join(p.areas.get("primary", [])[:5])
        if keywords:
            lines.append(f"- {keywords} → {p.team_id}")

    lines.extend(
        [
            "",
            "SIGNAL 3 — Labels (when present): Area and topic labels are reliable",
            "when they exist, but are present on only ~3% of triage-needed issues.",
            "",
        ]
    )

    lines.append(_build_routing_table(repo_config))
    return "\n".join(lines)


def _build_routing_table(repo_config: RepoConfig) -> str:
    primary_map: dict[str, str] = {}
    secondary_map: dict[str, list[str]] = {}

    for p in repo_config.team_profiles:
        for prefix in p.areas.get("primary", []):
            primary_map[prefix] = p.team_id
        for prefix in p.areas.get("secondary", []):
            secondary_map.setdefault(prefix, []).append(p.team_id)

    lines = [
        "| Prefix / Area | Primary | Secondary |",
        "|---------------|---------|-----------|",
    ]

    seen = set()
    for p in repo_config.team_profiles:
        for prefix in p.areas.get("primary", []):
            if prefix in seen:
                continue
            seen.add(prefix)
            secondary = ", ".join(secondary_map.get(prefix, [])) or "—"
            lines.append(f"| {prefix} | {p.team_id} | {secondary} |")

    for prefix in repo_config.no_team_prefixes:
        if prefix not in seen:
            seen.add(prefix)
            lines.append(f"| {prefix} | NONE | — |")

    return "\n".join(lines)


def _build_urgency_scale() -> str:
    return (
        "## Urgency Scale\n\n"
        "- critical: Release blocker, CI failure, security vulnerability (CVE),\n"
        "  protobuf sync failure\n"
        "- high: Regression against current version, broken core functionality,\n"
        "  security issue in team-owned area\n"
        "- medium: Reproducible bug with workaround, feature request in owned area\n"
        "- low: RFC, design discussion, feature request outside core scope"
    )


def _build_calibration_examples(repo_config: RepoConfig) -> str:
    lines = ["## Calibration Examples", "", "Standard routing (prefix matches team):"]

    for p in repo_config.team_profiles:
        for ex in p.examples:
            lines.append(f'\n- "{ex["title"]}"')
            lines.append(
                f"  → {p.team_id}, {ex.get('urgency', 'medium')} — {ex.get('reasoning', '')}"
            )

    lines.extend(["", "Prefix misleads (problem domain overrides code area):", ""])
    lines.append('- "bug(supervisor): SPIFFE-enabled sandboxes crash on restart"')
    lines.append("  → ai-safety (secondary: agent-ops), high — prefix says supervisor")
    lines.append(
        "  (agent-ops) but the problem is SPIFFE identity security (ai-safety)"
    )
    lines.append("")
    lines.append(
        '- "feat(cli): import externally issued OIDC tokens non-interactively"'
    )
    lines.append("  → acp (secondary: agent-ops), medium — prefix says cli (agent-ops)")
    lines.append("  but the problem is OIDC token management (acp)")
    lines.append("")
    lines.append(
        '- "docs(access-control): document required Keycloak protocol mappers"'
    )
    lines.append("  → acp, low — prefix says docs (agent-ops) but the content is")
    lines.append("  Keycloak auth infrastructure (acp)")

    lines.extend(["", "No team cares:"])
    for ex in repo_config.none_examples:
        lines.append(f'\n- "{ex["title"]}"')
        lines.append(f"  → NONE — {ex.get('reasoning', '')}")

    return "\n".join(lines)


def _build_output_format() -> str:
    return (
        "## Output Format\n\n"
        "Think through the routing signals step by step, THEN give your answer.\n\n"
        "Return ONLY a JSON object with these fields in this exact order:\n"
        "{\n"
        '  "reasoning": "Which signals you found and why they point to this team",\n'
        '  "any_team_cares": true/false,\n'
        '  "primary_team": "team-id or none",\n'
        '  "primary_confidence": 0.0-1.0,\n'
        '  "secondary_team": "team-id or null",\n'
        '  "secondary_confidence": 0.0-1.0,\n'
        '  "urgency": "critical/high/medium/low",\n'
        '  "urgency_reasoning": "Why this urgency level",\n'
        '  "summary": "1-2 sentence issue summary"\n'
        "}\n\n"
        "IMPORTANT:\n"
        '- "reasoning" MUST come first — think before you classify\n'
        '- Choose "none" when no team clearly owns the area\n'
        "- If two teams are relevant, put the stronger match as primary\n"
        "- When in doubt on urgency, round DOWN"
    )
