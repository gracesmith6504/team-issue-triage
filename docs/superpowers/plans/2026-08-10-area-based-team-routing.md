# Area-Based Team Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rearchitect the dashboard's Team Routing section to classify issues by NVIDIA's 13 `area:` labels, map areas to Red Hat teams via YAML config, add per-team LLM synthesis summaries, and surface hidden triage data (recommendations, confidence, author info).

**Architecture:** 4-layer pipeline: (1) LLM classifies issues into NVIDIA area labels, (2) deterministic area→team mapping from YAML config, (3) per-team LLM synthesis generates summaries and action items, (4) dashboard renders team→area→issues hierarchy with AI summaries. Backward-compatible with existing assessments.

**Tech Stack:** Python 3.12 (dataclasses, yaml), Vertex AI / Claude (LLM), inline JS/CSS in Jinja2 HTML templates (no build toolchain)

## Global Constraints

- NEVER include `Co-Authored-By` lines in commit messages
- No npm/build toolchain — CSS/JS is inline in HTML templates
- One logical change = one commit
- Always run `make lint` before pushing
- Always run `python3 -m pytest tests/ -q` before committing
- Choose architectural fix over easy one (boy scout rule)
- Existing tests must keep passing throughout

---

## File Map

| File | Role | Change |
|------|------|--------|
| `app/core/models.py` | Core data models | Add `primary_area`, `secondary_area` fields to TriageResult |
| `app/core/profiles.py` | Config loader | Add `prefix_to_area` mapping, `resolve_area_to_team()`, update TeamProfile |
| `app/core/prompt.py` | LLM prompt builder | Rewrite to classify into NVIDIA areas instead of Red Hat teams |
| `app/core/triage_engine.py` | Triage pipeline | Add area→team derivation after LLM classification |
| `profiles/openshell.yaml` | Repo config | Add `area_taxonomy`, `prefix_to_area`, `no_team_areas` |
| `profiles/teams/agent-ops.yaml` | Team profile | Change `areas` to `owned_areas` with NVIDIA area labels |
| `profiles/teams/acp.yaml` | Team profile | Same |
| `profiles/teams/ai-safety.yaml` | Team profile | Same |
| `profiles/teams/kata.yaml` | Team profile | Same |
| `profiles/teams/agentdev.yaml` | Team profile | Same |
| `profiles/teams/dashboard.yaml` | Team profile | Same |
| `app/reports/models.py` | Report models | Add `TeamSynthesis`, `AreaGroup` models |
| `app/reports/synthesis.py` | **New**: synthesis engine | Per-team LLM summary generation |
| `app/reports/birds_eye.py` | Report generator | Area-based team breakdown, integrate synthesis |
| `app/reports/renderers/html.py` | HTML renderer | Restructure `team_issues` for area grouping + synthesis |
| `app/reports/renderers/templates/components/team_routing.js` | Dashboard UI | Rewrite for team→area→issues with AI summaries |
| `app/reports/renderers/templates/base.html` | CSS | Styles for synthesis cards, area groups, enriched rows |
| `tests/reports/conftest.py` | Test fixtures | Update `make_result` factory with area fields |
| `tests/core/test_profiles.py` | Profile tests | Tests for area taxonomy loading, area→team resolution |
| `tests/core/test_prompt.py` | Prompt tests | Update for area-based prompt output |
| `tests/core/test_triage_engine.py` | Engine tests | Tests for area→team derivation |
| `tests/reports/test_birds_eye.py` | Report tests | Tests for area-based breakdown |
| `tests/reports/test_synthesis.py` | **New**: synthesis tests | Tests for LLM synthesis |
| `tests/reports/test_html_renderer.py` | Renderer tests | Update for new data structure |

---

### Task 1: Add area fields to TriageResult and update test fixtures

**Files:**
- Modify: `app/core/models.py:27-48` (TriageResult dataclass)
- Modify: `tests/reports/conftest.py:12-39` (make_result factory)

**Interfaces:**
- Produces: `TriageResult.primary_area` (str, default `""`)
- Produces: `TriageResult.secondary_area` (str | None, default `None`)
- Produces: Updated `make_result()` factory with `area` parameter

- [ ] **Step 1: Add `primary_area` and `secondary_area` fields to TriageResult**

In `app/core/models.py`, add two new fields to the `TriageResult` dataclass. Place them after `any_team_cares` and before `primary_team`:

```python
@dataclass
class TriageResult:
    repo: str
    issue_number: int
    issue_title: str
    issue_url: str
    reasoning: str
    any_team_cares: bool
    primary_area: str
    primary_confidence: float
    secondary_area: str | None
    secondary_confidence: float | None
    primary_team: str
    secondary_team: str | None
    urgency: Urgency
    urgency_reasoning: str
    summary: str
    recommendation: str
    confidence_flag: str | None
    assessed_at: str
    created_at: str = ""
    author_association: str = "NONE"
    author_login: str = ""
```

Note: `primary_area` has no default — it's required for new instances. But we'll need backward compat for deserialization (handled in Task 5).

- [ ] **Step 2: Update `make_result` factory in conftest.py**

In `tests/reports/conftest.py`, update the `make_result` function to include the new area fields:

```python
def make_result(
    number=1,
    title="test issue",
    team="agent-ops",
    area="cli",
    urgency=Urgency.MEDIUM,
    secondary_team=None,
    secondary_confidence=None,
    secondary_area=None,
    confidence_flag=None,
):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=number,
        issue_title=title,
        issue_url=f"https://github.com/NVIDIA/OpenShell/issues/{number}",
        reasoning="test",
        any_team_cares=True,
        primary_area=area,
        primary_confidence=0.9,
        secondary_area=secondary_area,
        secondary_confidence=secondary_confidence,
        primary_team=team,
        secondary_team=secondary_team,
        urgency=urgency,
        urgency_reasoning="test",
        summary=f"Summary for #{number}",
        recommendation="test recommendation",
        confidence_flag=confidence_flag,
        assessed_at="2026-07-28T10:00:00+00:00",
        created_at="2026-07-25T10:00:00Z",
    )
```

- [ ] **Step 3: Fix all TriageResult constructions across the test suite**

Search for all places that construct TriageResult directly (not via `make_result`) and add the `primary_area` and `secondary_area` fields. Key files:

- `tests/core/test_triage_engine.py` — the `triage_issue` function constructs TriageResult internally, so it will need updating in the production code (Task 5). No test changes needed here yet.
- `tests/core/test_models.py` — if it constructs TriageResult directly
- Any other test files that build TriageResult directly

Run: `grep -rn "TriageResult(" tests/ --include="*.py" | grep -v conftest | grep -v __pycache__`

For each match, add `primary_area="cli"` and `secondary_area=None` as appropriate.

- [ ] **Step 4: Run full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS (the new fields have defaults where needed, and `make_result` provides them)

- [ ] **Step 5: Run lint**

Run: `make lint`

- [ ] **Step 6: Commit**

```bash
git add app/core/models.py tests/reports/conftest.py tests/
git commit -m "feat: add primary_area and secondary_area fields to TriageResult"
```

---

### Task 2: Add area taxonomy config and area-to-team resolution

**Files:**
- Modify: `profiles/openshell.yaml` — add `area_taxonomy`, `prefix_to_area`, `no_team_areas`
- Modify: `profiles/teams/agent-ops.yaml` — change `areas` to `owned_areas` with NVIDIA area labels
- Modify: `profiles/teams/acp.yaml` — same
- Modify: `profiles/teams/ai-safety.yaml` — same
- Modify: `profiles/teams/kata.yaml` — same
- Modify: `profiles/teams/agentdev.yaml` — same
- Modify: `profiles/teams/dashboard.yaml` — same
- Modify: `app/core/profiles.py` — add `prefix_to_area` loading, `owned_areas` support, `resolve_area_to_team()`
- Test: `tests/core/test_profiles.py`

**Interfaces:**
- Consumes: YAML config files
- Produces: `RepoConfig.area_taxonomy` (list of area label strings)
- Produces: `RepoConfig.prefix_to_area` (dict mapping title prefixes to NVIDIA area labels)
- Produces: `RepoConfig.no_team_areas` (list of area labels with no team owner)
- Produces: `TeamProfile.owned_areas` (dict with `primary` and `secondary` lists of NVIDIA area labels)
- Produces: `resolve_area_to_team(area: str, repo_config: RepoConfig) -> tuple[str, str | None]` — returns `(primary_team, secondary_team)`

- [ ] **Step 1: Write failing tests for area taxonomy loading**

In `tests/core/test_profiles.py`, add tests:

```python
def test_load_repo_config_area_taxonomy(profiles_dir):
    """Repo config should load area_taxonomy list."""
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    assert "cli" in config.area_taxonomy
    assert "gateway" in config.area_taxonomy


def test_load_repo_config_prefix_to_area(profiles_dir):
    """Repo config should load prefix_to_area mapping."""
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    assert config.prefix_to_area["cli"] == "cli"


def test_load_repo_config_no_team_areas(profiles_dir):
    """Repo config should load no_team_areas list."""
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    assert "build" in config.no_team_areas
```

Update the `profiles_dir` fixture to include the new config fields.

- [ ] **Step 2: Write failing tests for owned_areas in team profiles**

```python
def test_team_profile_owned_areas(profiles_dir):
    """Team profiles should have owned_areas with primary/secondary."""
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    team_a = config.team_profiles[0]
    assert "cli" in team_a.owned_areas["primary"]
    assert "gateway" in team_a.owned_areas.get("secondary", [])
```

- [ ] **Step 3: Write failing tests for `resolve_area_to_team`**

```python
from app.core.profiles import resolve_area_to_team


def test_resolve_area_primary_owner(profiles_dir):
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    primary, secondary = resolve_area_to_team("cli", config)
    assert primary == "team-a"
    assert secondary is None


def test_resolve_area_with_secondary(profiles_dir):
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    primary, secondary = resolve_area_to_team("gateway", config)
    assert primary == "team-b"
    assert secondary == "team-a"


def test_resolve_area_no_owner(profiles_dir):
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    primary, secondary = resolve_area_to_team("build", config)
    assert primary == "none"
    assert secondary is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python3 -m pytest tests/core/test_profiles.py -v -k "area"`
Expected: All new tests FAIL

- [ ] **Step 5: Update `profiles/openshell.yaml`**

Add the area taxonomy, prefix-to-area mapping, and no-team areas to the repo config:

```yaml
area_taxonomy:
  - gateway
  - sandbox
  - supervisor
  - compute
  - policy
  - cli
  - cluster
  - build
  - docs
  - providers
  - inference
  - tui
  - sdk

prefix_to_area:
  # Direct matches (prefix = area label)
  gateway: gateway
  sandbox: sandbox
  supervisor: supervisor
  compute: compute
  policy: policy
  cli: cli
  cluster: cluster
  build: build
  docs: docs
  providers: providers
  inference: inference
  tui: tui
  sdk: sdk
  # Aliases (prefix maps to parent area)
  gateway-config: gateway
  proxy: gateway
  server: gateway
  auth: gateway
  access-control: gateway
  supervisor-middleware: supervisor
  vm: sandbox
  vm-driver: sandbox
  driver-podman: compute
  podman: compute
  gpu: compute
  l7: policy
  python: sdk
  examples: docs
  router: providers
  helm: cluster
  openshift: cluster
  kubernetes: cluster
  certgen: cluster
  network: cluster
  ingress: cluster
  e2e: cluster

no_team_areas:
  - build
  - tui
```

Keep the existing `no_team_prefixes` for backward compatibility with the old prompt system until fully migrated.

- [ ] **Step 6: Update all team profile YAMLs**

Each team profile gets an `owned_areas` field alongside the existing `areas` field (keep `areas` for backward compat during transition).

`profiles/teams/agent-ops.yaml` — add:
```yaml
owned_areas:
  primary: [cli, sdk, sandbox, cluster, docs, supervisor, compute]
  secondary: [gateway]
```

`profiles/teams/acp.yaml` — add:
```yaml
owned_areas:
  primary: [gateway]
  secondary: [cluster]
```

`profiles/teams/ai-safety.yaml` — add:
```yaml
owned_areas:
  primary: [policy]
  secondary: [supervisor]
```

`profiles/teams/kata.yaml` — add:
```yaml
owned_areas:
  primary: []
  secondary: [sandbox, compute]
```

`profiles/teams/agentdev.yaml` — add:
```yaml
owned_areas:
  primary: [inference, providers]
  secondary: []
```

`profiles/teams/dashboard.yaml` — add:
```yaml
owned_areas:
  primary: []
  secondary: []
```

- [ ] **Step 7: Update `app/core/profiles.py`**

Add `owned_areas` to `TeamProfile`, add `area_taxonomy`, `prefix_to_area`, `no_team_areas` to `RepoConfig`, add `resolve_area_to_team()`:

```python
@dataclass
class TeamProfile:
    team_id: str
    team_name: str
    description: str
    areas: dict[str, list[str]]
    owned_areas: dict[str, list[str]]
    urgency_overrides: dict[str, list[str]]
    examples: list[dict]
    notifications: dict


@dataclass
class RepoConfig:
    repo: str
    pinned_version: str
    team_profiles: list[TeamProfile]
    no_team_prefixes: list[str]
    none_examples: list[dict]
    confidence_thresholds: dict[str, float]
    reporting: dict
    area_taxonomy: list[str]
    prefix_to_area: dict[str, str]
    no_team_areas: list[str]
    codeowners: list[str] | None = None
```

Update `_load_team_profile` to load `owned_areas`:
```python
def _load_team_profile(path: Path) -> TeamProfile:
    with open(path) as f:
        data = yaml.safe_load(f)
    return TeamProfile(
        team_id=data["team_id"],
        team_name=data["team_name"],
        description=data.get("description", ""),
        areas=data.get("areas", {"primary": [], "secondary": []}),
        owned_areas=data.get("owned_areas", {"primary": [], "secondary": []}),
        urgency_overrides=data.get("urgency_overrides", {}),
        examples=data.get("examples", []),
        notifications=data.get("notifications", {}),
    )
```

Update `load_repo_config` to load the new fields:
```python
    return RepoConfig(
        ...
        area_taxonomy=data.get("area_taxonomy", []),
        prefix_to_area=data.get("prefix_to_area", {}),
        no_team_areas=data.get("no_team_areas", []),
    )
```

Add `resolve_area_to_team`:
```python
def resolve_area_to_team(
    area: str, repo_config: RepoConfig
) -> tuple[str, str | None]:
    primary_team = "none"
    secondary_teams: list[str] = []

    for profile in repo_config.team_profiles:
        owned = profile.owned_areas
        if area in owned.get("primary", []):
            primary_team = profile.team_id
        elif area in owned.get("secondary", []):
            secondary_teams.append(profile.team_id)

    secondary_team = secondary_teams[0] if secondary_teams else None
    return primary_team, secondary_team
```

- [ ] **Step 8: Update `_validate_profiles` for `owned_areas`**

Add validation that each NVIDIA area has at most one primary owner via `owned_areas`:

```python
    primary_area_owners: dict[str, str] = {}
    for profile in profiles:
        for area in profile.owned_areas.get("primary", []):
            if area in primary_area_owners:
                raise ValueError(
                    f"Area '{area}' listed as primary by both "
                    f"'{primary_area_owners[area]}' and '{profile.team_id}'"
                )
            primary_area_owners[area] = profile.team_id
```

- [ ] **Step 9: Update test fixture `profiles_dir` to include new config**

Update the fixture in `tests/core/test_profiles.py` to include `area_taxonomy`, `prefix_to_area`, `no_team_areas` in the repo config YAML, and `owned_areas` in team profile YAMLs.

- [ ] **Step 10: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS

- [ ] **Step 11: Run lint**

Run: `make lint`

- [ ] **Step 12: Commit**

```bash
git add profiles/ app/core/profiles.py tests/core/test_profiles.py
git commit -m "feat: add NVIDIA area taxonomy config and area-to-team resolution"
```

---

### Task 3: Rewrite LLM prompt for area-based classification

**Files:**
- Modify: `app/core/prompt.py` — rewrite classification to target NVIDIA areas
- Test: `tests/core/test_prompt.py`

**Interfaces:**
- Consumes: `RepoConfig.area_taxonomy`, `RepoConfig.prefix_to_area`, `RepoConfig.no_team_areas`
- Consumes: `TeamProfile.owned_areas` (for area descriptions in prompt)
- Produces: LLM system prompt that asks for `primary_area` and `secondary_area` instead of `primary_team` and `secondary_team`

- [ ] **Step 1: Write failing tests for area-based system prompt**

In `tests/core/test_prompt.py`, update or add tests:

```python
def test_system_prompt_contains_area_taxonomy():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "primary_area" in prompt
    assert "secondary_area" in prompt


def test_system_prompt_lists_nvidia_areas():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "gateway" in prompt
    assert "sandbox" in prompt
    assert "supervisor" in prompt


def test_system_prompt_contains_prefix_to_area_hints():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "prefix" in prompt.lower()
```

Update `_make_repo_config` to include the new fields:
```python
def _make_repo_config(teams=None, no_team_prefixes=None, none_examples=None):
    if teams is None:
        teams = [
            _make_team(
                "agent-ops", "Agent Ops", "Core integration",
                primary=["cli", "sdk"], secondary=["gateway"],
                owned_areas={"primary": ["cli", "sdk"], "secondary": ["gateway"]},
            ),
            _make_team(
                "acp", "ACP", "Hosted mode",
                primary=["gateway"], secondary=["cluster"],
                owned_areas={"primary": ["gateway"], "secondary": ["cluster"]},
            ),
        ]
    return RepoConfig(
        repo="NVIDIA/OpenShell",
        pinned_version="v0.0.92",
        team_profiles=teams,
        no_team_prefixes=no_team_prefixes or ["build", "tui"],
        none_examples=none_examples or [...],
        confidence_thresholds={...},
        reporting={},
        area_taxonomy=["cli", "sdk", "gateway", "sandbox", "cluster", "build", "tui"],
        prefix_to_area={"cli": "cli", "sdk": "sdk", "gateway": "gateway",
                        "gateway-config": "gateway", "sandbox": "sandbox"},
        no_team_areas=["build", "tui"],
    )
```

Update `_make_team` to accept `owned_areas`:
```python
def _make_team(team_id, name, description, primary=None, secondary=None,
               examples=None, owned_areas=None):
    return TeamProfile(
        team_id=team_id,
        team_name=name,
        description=description,
        areas={"primary": primary or [], "secondary": secondary or []},
        owned_areas=owned_areas or {"primary": [], "secondary": []},
        urgency_overrides={},
        examples=examples or [],
        notifications={},
    )
```

- [ ] **Step 2: Rewrite `_build_preamble()`**

Change from team-based to area-based classification:

```python
def _build_preamble(repo_config: RepoConfig) -> str:
    areas_str = ", ".join(repo_config.area_taxonomy)
    return (
        "You are an issue triage agent for the OpenShell repository. You assess\n"
        "GitHub issues and classify them by PROBLEM AREA.\n\n"
        "## Your task\n\n"
        "For each issue, answer three questions:\n"
        f"1. Which area does this issue belong to? (pick from: {areas_str})\n"
        "2. Is there a secondary area? (pick from the same list, or null)\n"
        "3. How urgent is it? (critical / high / medium / low)"
    )
```

Update `build_system_prompt` to pass `repo_config` to `_build_preamble`.

- [ ] **Step 3: Replace `_build_teams_section` with `_build_areas_section`**

```python
def _build_areas_section(repo_config: RepoConfig) -> str:
    lines = ["## Areas\n"]
    for area in repo_config.area_taxonomy:
        aliases = [k for k, v in repo_config.prefix_to_area.items() if v == area and k != area]
        alias_note = f" (also: {', '.join(aliases)})" if aliases else ""
        lines.append(f"- **{area}**{alias_note}")
    no_team = ", ".join(repo_config.no_team_areas)
    if no_team:
        lines.append(f"\nAreas with no Red Hat team owner: {no_team}")
    return "\n".join(lines)
```

- [ ] **Step 4: Update `_build_routing_signals`**

Change the routing signals to reference areas instead of teams:

```python
def _build_routing_signals(repo_config: RepoConfig) -> str:
    lines = [
        "## Routing Signals",
        "",
        "SIGNAL 1 — Title prefix: OpenShell uses conventional commit titles like",
        "feat(cli):, bug(supervisor):. The component in parentheses maps to an area.",
        "Check the prefix-to-area table below. But read the body too — the prefix",
        "tells you the CODE area, the body tells you the PROBLEM domain. When they",
        "disagree, the problem domain wins.",
        "",
        "SIGNAL 2 — Issue body: For the 28% of issues with no title prefix, read",
        "the body to identify the area from keywords and problem description.",
        "",
        "SIGNAL 3 — Labels: area: and topic: labels are reliable when present,",
        "but exist on only ~3% of triage-needed issues.",
        "",
    ]
    lines.append(_build_prefix_area_table(repo_config))
    return "\n".join(lines)
```

- [ ] **Step 5: Replace `_build_routing_table` with `_build_prefix_area_table`**

```python
def _build_prefix_area_table(repo_config: RepoConfig) -> str:
    lines = [
        "| Title Prefix | Maps to Area |",
        "|-------------|-------------|",
    ]
    seen = set()
    for prefix, area in sorted(repo_config.prefix_to_area.items()):
        if prefix not in seen:
            seen.add(prefix)
            lines.append(f"| {prefix} | {area} |")
    return "\n".join(lines)
```

- [ ] **Step 6: Update `_build_calibration_examples`**

Change examples to reference areas instead of teams:

```python
def _build_calibration_examples(repo_config: RepoConfig) -> str:
    lines = ["## Calibration Examples", ""]

    for p in repo_config.team_profiles:
        for ex in p.examples:
            lines.append(f'- "{ex["title"]}"')
            owned_primary = p.owned_areas.get("primary", [])
            area = owned_primary[0] if owned_primary else "unknown"
            lines.append(
                f"  → area: {area}, {ex.get('urgency', 'medium')} — {ex.get('reasoning', '')}"
            )

    lines.extend([
        "",
        "Prefix misleads (problem domain overrides code area):",
        "",
        '- "bug(supervisor): SPIFFE-enabled sandboxes crash on restart"',
        "  → area: policy (secondary: supervisor) — prefix says supervisor",
        "  but the problem is SPIFFE identity security (policy area)",
        "",
        '- "feat(cli): import externally issued OIDC tokens non-interactively"',
        "  → area: gateway (secondary: cli) — prefix says cli but the",
        "  problem is OIDC token management (gateway area)",
    ])

    lines.extend(["", "No team areas (still classify the area):"])
    for ex in repo_config.none_examples:
        lines.append(f'\n- "{ex["title"]}"')
        lines.append(f"  → area from prefix, low — {ex.get('reasoning', '')}")

    return "\n".join(lines)
```

- [ ] **Step 7: Update `_build_output_format`**

Change output fields from team to area:

```python
def _build_output_format() -> str:
    return (
        "## Output Format\n\n"
        "Think through the routing signals step by step, THEN give your answer.\n\n"
        "Return ONLY a JSON object with these fields in this exact order:\n"
        "{\n"
        '  "reasoning": "Which signals you found and why they point to this area",\n'
        '  "any_team_cares": true/false,\n'
        '  "primary_area": "area-label",\n'
        '  "primary_confidence": 0.0-1.0,\n'
        '  "secondary_area": "area-label or null",\n'
        '  "secondary_confidence": 0.0-1.0,\n'
        '  "urgency": "critical/high/medium/low",\n'
        '  "urgency_reasoning": "Why this urgency level",\n'
        '  "summary": "1-2 sentence issue summary",\n'
        '  "recommendation": "What should be done about this issue"\n'
        "}\n\n"
        "IMPORTANT:\n"
        '- "reasoning" MUST come first — think before you classify\n'
        "- primary_area must be one of the areas listed above\n"
        "- If two areas are relevant, put the stronger match as primary\n"
        "- When in doubt on urgency, round DOWN\n"
        '- Set any_team_cares to false if the area is in the "no team owner" list'
    )
```

- [ ] **Step 8: Update `build_system_prompt` to use new section builders**

```python
def build_system_prompt(repo_config: RepoConfig) -> str:
    sections = [
        _build_preamble(repo_config),
        _build_areas_section(repo_config),
        _build_routing_signals(repo_config),
        _build_urgency_scale(),
        _build_calibration_examples(repo_config),
        _build_output_format(),
    ]
    return "\n\n".join(sections)
```

- [ ] **Step 9: Update existing tests that check for `primary_team` in prompt**

Update `test_system_prompt_contains_output_format`:
```python
def test_system_prompt_contains_output_format():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "reasoning" in prompt
    assert "any_team_cares" in prompt
    assert "primary_area" in prompt
    assert "primary_confidence" in prompt
```

Update `test_system_prompt_contains_team_descriptions` → rename to `test_system_prompt_contains_area_taxonomy`:
```python
def test_system_prompt_contains_area_taxonomy():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "cli" in prompt
    assert "sdk" in prompt
    assert "gateway" in prompt
```

- [ ] **Step 10: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS

- [ ] **Step 11: Run lint**

Run: `make lint`

- [ ] **Step 12: Commit**

```bash
git add app/core/prompt.py tests/core/test_prompt.py
git commit -m "feat: rewrite LLM prompt to classify into NVIDIA area labels"
```

---

### Task 4: Update triage engine for area-based classification with team derivation

**Files:**
- Modify: `app/core/triage_engine.py:45-113` (triage_issue function)
- Test: `tests/core/test_triage_engine.py`

**Interfaces:**
- Consumes: LLM response with `primary_area` and `secondary_area` fields
- Consumes: `resolve_area_to_team()` from `app/core/profiles`
- Produces: `TriageResult` with both area fields (from LLM) and team fields (derived)

- [ ] **Step 1: Write failing tests for area-based triage**

In `tests/core/test_triage_engine.py`, update the `TestTriageIssue` class:

```python
def test_area_based_triage(self):
    llm = self._mock_llm(
        {
            "reasoning": "CLI feature, cli area",
            "any_team_cares": True,
            "primary_area": "cli",
            "primary_confidence": 0.9,
            "secondary_area": None,
            "secondary_confidence": None,
            "urgency": "medium",
            "urgency_reasoning": "Feature request",
            "summary": "New CLI flag",
            "recommendation": "Review the feature request",
        }
    )
    config = _make_repo_config()
    result = triage_issue(
        _make_issue(title="feat(cli): add flag"),
        llm,
        "claude-sonnet-4-6",
        config,
        "system prompt",
    )
    assert result is not None
    assert result.primary_area == "cli"
    assert result.primary_team == "agent-ops"
    assert result.urgency == Urgency.MEDIUM


def test_area_derives_secondary_team(self):
    llm = self._mock_llm(
        {
            "reasoning": "Gateway auth issue",
            "any_team_cares": True,
            "primary_area": "gateway",
            "primary_confidence": 0.85,
            "secondary_area": "policy",
            "secondary_confidence": 0.4,
            "urgency": "high",
            "urgency_reasoning": "Auth bypass risk",
            "summary": "OIDC validation issue",
            "recommendation": "Investigate auth flow",
        }
    )
    config = _make_repo_config()
    result = triage_issue(
        _make_issue(title="bug(gateway): OIDC fails"),
        llm,
        "claude-sonnet-4-6",
        config,
        "system prompt",
    )
    assert result is not None
    assert result.primary_area == "gateway"
    assert result.primary_team == "acp"
    assert result.secondary_area == "policy"
```

Update `_make_repo_config` to include `area_taxonomy`, `prefix_to_area`, `no_team_areas`, and `owned_areas` in team profiles so `resolve_area_to_team` works.

- [ ] **Step 2: Update `triage_issue` to read area from LLM response and derive team**

```python
from app.core.profiles import resolve_area_to_team

def triage_issue(...) -> TriageResult | None:
    ...
    primary_area = response.get("primary_area", "")
    secondary_area = response.get("secondary_area")

    # Derive team from area
    primary_team, _ = resolve_area_to_team(primary_area, repo_config)
    secondary_team_derived = None
    if secondary_area:
        secondary_team_derived, _ = resolve_area_to_team(secondary_area, repo_config)

    # Fall back to LLM-provided team if area-based resolution gives "none"
    # but LLM says a team cares (backward compat with old prompt format)
    if primary_team == "none" and response.get("primary_team"):
        primary_team = response.get("primary_team", "none")
    if secondary_team_derived is None and response.get("secondary_team"):
        secondary_team_derived = response.get("secondary_team")

    ...

    return TriageResult(
        ...
        primary_area=primary_area,
        secondary_area=secondary_area,
        primary_team=primary_team,
        secondary_team=secondary_team_derived,
        ...
    )
```

- [ ] **Step 3: Update existing tests**

Update the existing `test_successful_triage` to use the new response format (with `primary_area` instead of `primary_team`). Keep a backward-compat test that verifies old-format responses still work.

- [ ] **Step 4: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS

- [ ] **Step 5: Run lint**

Run: `make lint`

- [ ] **Step 6: Commit**

```bash
git add app/core/triage_engine.py tests/core/test_triage_engine.py
git commit -m "feat: derive team from NVIDIA area classification in triage engine"
```

---

### Task 5: Add report models for synthesis and area grouping

**Files:**
- Modify: `app/reports/models.py` — add TeamSynthesis, AreaGroup, update BirdsEyeReport
- Test: `tests/core/test_models.py` (if it exists) or verify with existing tests

**Interfaces:**
- Produces: `AreaGroup(area: str, total: int, by_urgency: dict, issues: list[TriageResult])`
- Produces: `TeamSynthesis(team_id: str, team_name: str, focus_summary: str, actions: list[str], area_groups: dict[str, AreaGroup], total: int, by_urgency: dict, trend: str)`
- Produces: `BirdsEyeReport.team_synthesis: dict[str, TeamSynthesis] | None`

- [ ] **Step 1: Add AreaGroup and TeamSynthesis dataclasses**

In `app/reports/models.py`, add:

```python
@dataclass
class AreaGroup:
    area: str
    total: int
    by_urgency: dict[str, int]
    issues: list[TriageResult]


@dataclass
class TeamSynthesis:
    team_id: str
    team_name: str
    focus_summary: str
    actions: list[str]
    area_groups: dict[str, AreaGroup]
    total: int
    by_urgency: dict[str, int]
    trend: str
```

- [ ] **Step 2: Add `team_synthesis` field to BirdsEyeReport**

```python
@dataclass
class BirdsEyeReport:
    summary: ReportSummary
    critical_list: list[TriageResult]
    team_breakdown: dict[str, TeamSummary]
    area_heatmap: dict[str, AreaTrend]
    duplicate_clusters: list[DuplicateCluster]
    no_team_list: list[TriageResult]
    all_issues: list[TriageResult]
    narrative: str
    generated_at: str
    pr_health: dict | None = None
    vouch_status: dict | None = None
    team_synthesis: dict[str, TeamSynthesis] | None = None
```

- [ ] **Step 3: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS (new field has default None)

- [ ] **Step 4: Run lint**

Run: `make lint`

- [ ] **Step 5: Commit**

```bash
git add app/reports/models.py
git commit -m "feat: add TeamSynthesis and AreaGroup models for area-based routing"
```

---

### Task 6: Update report generator for area-based team breakdown

**Files:**
- Modify: `app/reports/birds_eye.py:102-131` (`_compute_team_breakdown` and new area grouping)
- Test: `tests/reports/test_birds_eye.py`

**Interfaces:**
- Consumes: `TriageResult.primary_area`, `TriageResult.primary_team`
- Consumes: Team profile `owned_areas` for team name lookup
- Produces: `_compute_team_area_breakdown()` returns `dict[str, TeamSynthesis]` (without focus_summary and actions — those come from synthesis in Task 7)

- [ ] **Step 1: Write failing tests for area-based team breakdown**

In `tests/reports/test_birds_eye.py`, add tests:

```python
def test_team_area_breakdown_groups_by_team_and_area():
    """Issues are grouped by primary_team, then by primary_area within each team."""
    from tests.reports.conftest import make_result
    current = [
        make_result(1, "feat(cli): add flag", team="agent-ops", area="cli"),
        make_result(2, "bug(gateway): crash", team="agent-ops", area="gateway"),
        make_result(3, "feat(cli): other", team="agent-ops", area="cli"),
        make_result(4, "bug(policy): bypass", team="ai-safety", area="policy"),
    ]
    # ... construct generator and call method
```

- [ ] **Step 2: Add `_compute_team_area_breakdown` method**

In `app/reports/birds_eye.py`, add a new method to `BirdsEyeReportGenerator`:

```python
def _compute_team_area_breakdown(
    self, team_profiles: list,
) -> dict[str, TeamSynthesis]:
    team_map: dict[str, dict[str, list[TriageResult]]] = {}
    team_name_map: dict[str, str] = {p.team_id: p.team_name for p in team_profiles}

    for r in self._current:
        team = r.primary_team
        area = r.primary_area or ""
        team_map.setdefault(team, {}).setdefault(area, []).append(r)

    previous_teams: dict[str, int] = {}
    for r in self._previous:
        previous_teams[r.primary_team] = previous_teams.get(r.primary_team, 0) + 1

    result: dict[str, TeamSynthesis] = {}
    for team_id, areas in team_map.items():
        total = sum(len(issues) for issues in areas.values())
        by_urgency: dict[str, int] = {}
        area_groups: dict[str, AreaGroup] = {}

        for area, issues in sorted(areas.items(), key=lambda x: -len(x[1])):
            area_urgency: dict[str, int] = {}
            for r in issues:
                u = r.urgency.value
                area_urgency[u] = area_urgency.get(u, 0) + 1
                by_urgency[u] = by_urgency.get(u, 0) + 1
            area_groups[area] = AreaGroup(
                area=area,
                total=len(issues),
                by_urgency=area_urgency,
                issues=sorted(issues, key=lambda r: (
                    {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r.urgency.value, 99),
                    r.issue_number,
                )),
            )

        prev_count = previous_teams.get(team_id, 0)
        delta = total - prev_count

        result[team_id] = TeamSynthesis(
            team_id=team_id,
            team_name=team_name_map.get(team_id, team_id),
            focus_summary="",
            actions=[],
            area_groups=area_groups,
            total=total,
            by_urgency=by_urgency,
            trend=_format_trend(delta),
        )

    return result
```

- [ ] **Step 3: Integrate into `generate()`**

Update the `generate()` method to call `_compute_team_area_breakdown()` and store in the report:

```python
def generate(self, team_profiles=None) -> BirdsEyeReport:
    ...
    team_synthesis = self._compute_team_area_breakdown(team_profiles or [])
    ...
    return BirdsEyeReport(
        ...
        team_synthesis=team_synthesis,
    )
```

- [ ] **Step 4: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS

- [ ] **Step 5: Run lint**

Run: `make lint`

- [ ] **Step 6: Commit**

```bash
git add app/reports/birds_eye.py tests/reports/test_birds_eye.py
git commit -m "feat: add area-based team breakdown grouping to report generator"
```

---

### Task 7: Add per-team LLM synthesis engine

**Files:**
- Create: `app/reports/synthesis.py`
- Modify: `app/reports/birds_eye.py` — integrate synthesis into report generation
- Test: `tests/reports/test_synthesis.py`

**Interfaces:**
- Consumes: `TeamSynthesis` objects (with area_groups populated but focus_summary empty)
- Consumes: `LLMClientProtocol` for LLM calls
- Produces: Updated `TeamSynthesis` objects with `focus_summary` and `actions` populated

- [ ] **Step 1: Write failing tests for synthesis**

Create `tests/reports/test_synthesis.py`:

```python
from unittest.mock import MagicMock

from app.core.models import Urgency
from app.reports.models import AreaGroup, TeamSynthesis
from app.reports.synthesis import synthesize_team_summaries
from tests.reports.conftest import make_result


def _mock_llm(response):
    client = MagicMock()
    client.assess.return_value = response
    return client


def test_synthesis_populates_summary_and_actions():
    llm = _mock_llm({
        "focus_summary": "Gateway auth is blocking PRs. Sandbox needs review.",
        "actions": [
            "Review gateway auth PRs",
            "Triage sandbox issues",
            "Fix cluster bug",
        ],
    })
    teams = {
        "agent-ops": TeamSynthesis(
            team_id="agent-ops",
            team_name="Agent Ops",
            focus_summary="",
            actions=[],
            area_groups={
                "cli": AreaGroup(
                    area="cli", total=3,
                    by_urgency={"medium": 3},
                    issues=[make_result(1, "cli issue", area="cli")],
                ),
            },
            total=3, by_urgency={"medium": 3}, trend="+1",
        ),
    }
    result = synthesize_team_summaries(teams, llm, "claude-sonnet-4-6")
    assert result["agent-ops"].focus_summary != ""
    assert len(result["agent-ops"].actions) == 3


def test_synthesis_skips_empty_teams():
    llm = _mock_llm(None)
    teams = {
        "empty": TeamSynthesis(
            team_id="empty", team_name="Empty",
            focus_summary="", actions=[],
            area_groups={}, total=0,
            by_urgency={}, trend="flat",
        ),
    }
    result = synthesize_team_summaries(teams, llm, "claude-sonnet-4-6")
    assert result["empty"].focus_summary == ""
    assert llm.assess.call_count == 0


def test_synthesis_handles_llm_failure():
    llm = _mock_llm(None)
    teams = {
        "agent-ops": TeamSynthesis(
            team_id="agent-ops", team_name="Agent Ops",
            focus_summary="", actions=[],
            area_groups={
                "cli": AreaGroup(area="cli", total=1, by_urgency={"medium": 1},
                                 issues=[make_result(1, "test", area="cli")]),
            },
            total=1, by_urgency={"medium": 1}, trend="flat",
        ),
    }
    result = synthesize_team_summaries(teams, llm, "claude-sonnet-4-6")
    assert result["agent-ops"].focus_summary == ""
```

- [ ] **Step 2: Implement `app/reports/synthesis.py`**

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.reports.models import TeamSynthesis

if TYPE_CHECKING:
    from app.core.llm import LLMClientProtocol

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a technical team lead summarizing your team's issue backlog.\n"
    "Given a list of issues grouped by area, write:\n"
    "1. A 2-sentence focus summary (what's happening, what's urgent)\n"
    "2. Top 3 concrete recommended actions (specific, actionable)\n\n"
    'Return JSON: {"focus_summary": "...", "actions": ["...", "...", "..."]}'
)


def synthesize_team_summaries(
    teams: dict[str, TeamSynthesis],
    llm_client: LLMClientProtocol,
    model: str,
) -> dict[str, TeamSynthesis]:
    for team_id, synthesis in teams.items():
        if synthesis.total == 0:
            continue

        user_prompt = _build_team_prompt(synthesis)
        response = llm_client.assess(_SYSTEM_PROMPT, user_prompt, model)

        if response and isinstance(response, dict):
            synthesis.focus_summary = response.get("focus_summary", "")
            synthesis.actions = response.get("actions", [])[:3]
        else:
            logger.warning("LLM synthesis failed for team %s", team_id)

    return teams


def _build_team_prompt(synthesis: TeamSynthesis) -> str:
    lines = [
        f"Team: {synthesis.team_name} ({synthesis.total} issues)",
        f"Urgency breakdown: {synthesis.by_urgency}",
        f"Trend: {synthesis.trend}",
        "",
    ]
    for area, group in synthesis.area_groups.items():
        lines.append(f"## {area} ({group.total} issues)")
        for issue in group.issues[:10]:
            urgency = issue.urgency.value
            lines.append(f"- [{urgency}] #{issue.issue_number}: {issue.issue_title}")
            if issue.summary:
                lines.append(f"  Summary: {issue.summary}")
            if issue.recommendation:
                lines.append(f"  Recommendation: {issue.recommendation}")
        if group.total > 10:
            lines.append(f"  ... and {group.total - 10} more")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 3: Integrate synthesis into `BirdsEyeReportGenerator.generate()`**

Update `birds_eye.py` to call synthesis after computing the team area breakdown:

```python
from app.reports.synthesis import synthesize_team_summaries

def generate(self, team_profiles=None) -> BirdsEyeReport:
    ...
    team_synthesis = self._compute_team_area_breakdown(team_profiles or [])
    team_synthesis = synthesize_team_summaries(
        team_synthesis, self._llm_client, self._model,
    )
    ...
```

- [ ] **Step 4: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS

- [ ] **Step 5: Run lint**

Run: `make lint`

- [ ] **Step 6: Commit**

```bash
git add app/reports/synthesis.py tests/reports/test_synthesis.py app/reports/birds_eye.py
git commit -m "feat: add per-team LLM synthesis engine for focus summaries and actions"
```

---

### Task 8: Update HTML renderer for area-based team routing data

**Files:**
- Modify: `app/reports/renderers/html.py:43-111` (`_report_to_dict`)
- Test: `tests/reports/test_html_renderer.py`

**Interfaces:**
- Consumes: `BirdsEyeReport.team_synthesis` (dict of TeamSynthesis)
- Produces: `data["team_synthesis"]` dict for JS template with structure:
  ```
  {team_id: {team_name, focus_summary, actions, total, by_urgency, trend,
             area_groups: {area: {total, by_urgency, issues: [{number, title, url, urgency,
             summary, recommendation, confidence_flag, author_login, author_association,
             days_open, has_linked_pr, area}]}}}}
  ```

- [ ] **Step 1: Write failing tests for new data structure**

In `tests/reports/test_html_renderer.py`, add:

```python
def test_report_to_dict_team_synthesis():
    from app.reports.models import AreaGroup, TeamSynthesis
    synthesis = {
        "agent-ops": TeamSynthesis(
            team_id="agent-ops",
            team_name="Agent Ops",
            focus_summary="Gateway auth is blocking PRs.",
            actions=["Review PRs", "Triage sandbox", "Fix cluster bug"],
            area_groups={
                "cli": AreaGroup(
                    area="cli", total=2, by_urgency={"medium": 2},
                    issues=[make_result(1, "cli issue", area="cli"),
                            make_result(2, "cli other", area="cli")],
                ),
            },
            total=2, by_urgency={"medium": 2}, trend="+1",
        ),
    }
    report = make_report(team_synthesis=synthesis)
    result = _report_to_dict(report)
    ts = result["team_synthesis"]
    assert "agent-ops" in ts
    assert ts["agent-ops"]["focus_summary"] == "Gateway auth is blocking PRs."
    assert len(ts["agent-ops"]["actions"]) == 3
    assert "cli" in ts["agent-ops"]["area_groups"]
    cli_group = ts["agent-ops"]["area_groups"]["cli"]
    assert cli_group["total"] == 2
    assert len(cli_group["issues"]) == 2
    issue = cli_group["issues"][0]
    assert "recommendation" in issue
    assert "summary" in issue
    assert "days_open" in issue
```

- [ ] **Step 2: Update `_report_to_dict` to include team_synthesis**

In `app/reports/renderers/html.py`, add team_synthesis processing after the existing `team_issues` code:

```python
    # Build team_synthesis for the new team routing UI
    team_synthesis_data = {}
    if data.get("team_synthesis"):
        for team_id, ts in data["team_synthesis"].items():
            area_groups_data = {}
            for area, group in ts.get("area_groups", {}).items():
                issues_data = []
                for iss in group.get("issues", []):
                    created_at = iss.get("created_at", "")
                    days_open = 0
                    if created_at:
                        created = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )
                        days_open = (now - created).days

                    enr = enrichment.get(iss["issue_number"]) if enrichment else None
                    issues_data.append({
                        "number": iss["issue_number"],
                        "title": iss["issue_title"],
                        "url": iss["issue_url"],
                        "urgency": iss["urgency"],
                        "area": iss.get("primary_area", ""),
                        "summary": iss.get("summary", ""),
                        "recommendation": iss.get("recommendation", ""),
                        "confidence_flag": iss.get("confidence_flag"),
                        "author_login": iss.get("author_login", ""),
                        "author_association": iss.get("author_association", ""),
                        "days_open": days_open,
                        "has_linked_pr": enr.has_linked_pr if enr else False,
                    })
                area_groups_data[area] = {
                    "area": area,
                    "total": group.get("total", 0),
                    "by_urgency": group.get("by_urgency", {}),
                    "issues": issues_data,
                }
            team_synthesis_data[team_id] = {
                "team_id": team_id,
                "team_name": ts.get("team_name", team_id),
                "focus_summary": ts.get("focus_summary", ""),
                "actions": ts.get("actions", []),
                "total": ts.get("total", 0),
                "by_urgency": ts.get("by_urgency", {}),
                "trend": ts.get("trend", "flat"),
                "area_groups": area_groups_data,
            }
    data["team_synthesis"] = team_synthesis_data
```

- [ ] **Step 3: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS

- [ ] **Step 4: Run lint**

Run: `make lint`

- [ ] **Step 5: Commit**

```bash
git add app/reports/renderers/html.py tests/reports/test_html_renderer.py
git commit -m "feat: include team synthesis and enriched issue data in HTML renderer"
```

---

### Task 9: Rewrite team_routing.js and add CSS for new dashboard UI

**Files:**
- Modify: `app/reports/renderers/templates/components/team_routing.js` — complete rewrite
- Modify: `app/reports/renderers/templates/base.html` — add CSS for synthesis cards, area sub-groups

**Interfaces:**
- Consumes: `d.team_synthesis` dict from rendered data (or falls back to `d.team_breakdown` + `d.team_issues` for backward compat)
- Produces: Visual team→area→issues hierarchy with AI summaries, recommendations, author info

- [ ] **Step 1: Add CSS for synthesis cards and area groups**

In `app/reports/renderers/templates/base.html`, add after the existing `.team-band` styles:

```css
.team-synthesis-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: 8px;
  padding: 14px 18px;
  margin: 10px 0 14px 0;
  font-size: 14px;
  line-height: 1.6;
}
.team-synthesis-summary {
  color: var(--text-primary);
  margin-bottom: 10px;
}
.team-synthesis-actions {
  list-style: none;
  padding: 0;
  margin: 0;
}
.team-synthesis-actions li {
  padding: 4px 0;
  color: var(--text-secondary);
  font-size: 13px;
}
.team-synthesis-actions li::before {
  content: "→ ";
  color: var(--accent);
  font-weight: 600;
}
.area-sub-group {
  margin: 6px 0;
}
.area-sub-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}
.area-sub-header:hover {
  background: var(--hover);
}
.area-sub-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  background: var(--accent-glow);
  color: var(--accent);
}
.area-sub-count {
  color: var(--text-muted);
  font-weight: 400;
}
.area-sub-issues {
  padding: 0 0 0 16px;
}
.enriched-issue-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
}
.enriched-issue-row:last-child {
  border-bottom: none;
}
.enriched-issue-main {
  display: flex;
  align-items: center;
  gap: 6px;
}
.enriched-issue-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-muted);
  padding-left: 26px;
}
.issue-recommendation {
  font-size: 12px;
  color: var(--text-secondary);
  padding-left: 26px;
  font-style: italic;
}
.confidence-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 500;
  background: rgba(212,160,21,0.1);
  color: #9a6700;
}
.author-badge {
  font-size: 11px;
  color: var(--text-muted);
}
.author-badge.external {
  color: var(--accent);
  font-weight: 500;
}
```

- [ ] **Step 2: Rewrite `team_routing.js`**

Replace the entire contents of `app/reports/renderers/templates/components/team_routing.js`:

```javascript
function buildTeamRouting() {
  var section = el("div", "section");
  section.id = "team-routing";

  var ts = d.team_synthesis || {};
  var teamIds = Object.keys(ts);
  if (!teamIds.length) {
    // Fallback to old team_breakdown if no synthesis data
    return buildTeamRoutingLegacy();
  }

  var totalIssues = 0;
  teamIds.forEach(function(tid) { totalIssues += ts[tid].total; });
  section.innerHTML = '<div class="section-header"><div class="section-title">Team Routing <span class="count">(' + totalIssues + ' issues across ' + teamIds.length + ' teams)</span></div></div>';

  // Sort teams by total issues descending
  teamIds.sort(function(a, b) { return ts[b].total - ts[a].total; });

  teamIds.forEach(function(teamId) {
    var team = ts[teamId];
    if (!team || team.total === 0) return;
    var band = el("details", "team-band");
    band.dataset.team = teamId;
    var color = tc(teamId);

    var urgencies = team.by_urgency || {};
    var urgencyBadges = "";
    ["critical","high","medium","low"].forEach(function(u) {
      var count = urgencies[u] || 0;
      if (count > 0) {
        urgencyBadges += ' ' + makeUrgencyBadgeHTML(u) + '<span style="font-size:13px;font-weight:600;color:var(--text-secondary);margin:0 8px 0 4px;">' + count + '</span>';
      }
    });

    var trend = team.trend || "flat";
    var trendClass = trend.charAt(0) === "+" ? "trend-up" : (trend.charAt(0) === "-" ? "trend-down" : "trend-flat");

    var header = el("summary", "team-band-header");
    header.innerHTML =
      '<span class="team-band-badge" style="background:' + color + '20;color:' + color + ';">' + esc(team.team_name || teamId) + '</span>' +
      '<span class="team-band-count">' + team.total + '</span>' +
      (trend !== "flat" && trend !== "0" ? '<span class="team-band-trend ' + trendClass + '">' + esc(trend) + '</span>' : '') +
      '<span style="flex:1;display:flex;align-items:center;margin:0 12px;">' + urgencyBadges + '</span>' +
      '<span class="team-band-chevron">&#9654;</span>';
    band.appendChild(header);

    // Synthesis card
    if (team.focus_summary) {
      var card = el("div", "team-synthesis-card");
      var cardHtml = '<div class="team-synthesis-summary">' + esc(team.focus_summary) + '</div>';
      if (team.actions && team.actions.length) {
        cardHtml += '<ul class="team-synthesis-actions">';
        team.actions.forEach(function(action) {
          cardHtml += '<li>' + esc(action) + '</li>';
        });
        cardHtml += '</ul>';
      }
      card.innerHTML = cardHtml;
      band.appendChild(card);
    }

    // Area sub-groups
    var areaKeys = Object.keys(team.area_groups || {});
    areaKeys.sort(function(a, b) {
      return (team.area_groups[b].total || 0) - (team.area_groups[a].total || 0);
    });

    areaKeys.forEach(function(areaKey) {
      var group = team.area_groups[areaKey];
      if (!group || !group.total) return;

      var areaDetails = el("details", "area-sub-group");
      var areaUrgencies = group.by_urgency || {};
      var areaUrgencyText = "";
      ["critical","high","medium","low"].forEach(function(u) {
        var c = areaUrgencies[u] || 0;
        if (c > 0) {
          areaUrgencyText += (areaUrgencyText ? ", " : "") + c + " " + u;
        }
      });

      var areaSummary = el("summary", "area-sub-header");
      areaSummary.innerHTML =
        '<span class="team-band-chevron" style="font-size:10px;">&#9654;</span>' +
        '<span class="area-sub-badge">' + esc(areaKey || "other") + '</span>' +
        '<span class="area-sub-count">' + group.total + ' issue' + (group.total !== 1 ? 's' : '') + '</span>' +
        (areaUrgencyText ? '<span style="color:var(--text-muted);font-size:12px;margin-left:8px;">— ' + esc(areaUrgencyText) + '</span>' : '');
      areaDetails.appendChild(areaSummary);

      var issuesDiv = el("div", "area-sub-issues");
      (group.issues || []).forEach(function(iss) {
        var row = el("div", "enriched-issue-row");

        // Main row: urgency + number + title + days
        var mainRow = '<div class="enriched-issue-main">';
        mainRow += makeUrgencyBadgeHTML(iss.urgency);
        mainRow += ' <a href="' + esc(iss.url) + '" target="_blank">#' + iss.number + '</a>';
        if (iss.has_linked_pr) {
          mainRow += ' <svg width="14" height="14" viewBox="0 0 16 16" fill="#1A7F37" style="vertical-align:-2px;"><path d="M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"/></svg>';
        }
        if (iss.confidence_flag) {
          mainRow += ' <span class="confidence-badge">' + esc(iss.confidence_flag) + '</span>';
        }
        mainRow += ' <span style="color:var(--text-secondary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(iss.title) + '</span>';
        mainRow += '<span style="color:var(--text-muted);font-size:12px;margin-left:auto;white-space:nowrap;">' + (iss.days_open || 0) + 'd</span>';
        mainRow += '</div>';

        // Recommendation row
        var recRow = '';
        if (iss.recommendation && iss.recommendation !== 'test' && iss.recommendation !== 'test recommendation') {
          recRow = '<div class="issue-recommendation">' + esc(iss.recommendation) + '</div>';
        }

        // Meta row: author + association
        var metaRow = '';
        if (iss.author_login) {
          var assocClass = (iss.author_association === "NONE" || iss.author_association === "CONTRIBUTOR") ? "external" : "";
          metaRow = '<div class="enriched-issue-meta">' +
            '<span class="author-badge ' + assocClass + '">@' + esc(iss.author_login) + '</span>' +
            '<span>' + esc(iss.author_association || "") + '</span>' +
            '</div>';
        }

        row.innerHTML = mainRow + recRow + metaRow;
        issuesDiv.appendChild(row);
      });

      areaDetails.appendChild(issuesDiv);
      band.appendChild(areaDetails);
    });

    band.addEventListener("toggle", function() {
      state.collapsed["team-" + teamId] = band.open;
      saveState(state);
    });
    section.appendChild(band);
  });

  return section;
}

function buildTeamRoutingLegacy() {
  // Keep the old implementation as fallback for reports without synthesis data
  var section = el("div", "section");
  section.id = "team-routing";
  section.innerHTML = '<div class="section-header"><div class="section-title">Team Routing <span class="count">(' + d.all_issues.length + ' issues across ' + Object.keys(d.team_breakdown).length + ' teams)</span></div></div>';

  var teamOrder = Object.keys(d.team_breakdown);
  teamOrder.forEach(function(teamId) {
    var team = d.team_breakdown[teamId];
    if (!team) return;
    var band = el("details", "team-band");
    band.dataset.team = teamId;
    var color = tc(teamId);
    var urgencies = team.by_urgency || {};
    var total = team.total;
    var trend = team.trend || "0";
    var trendClass = trend.charAt(0) === "+" ? "trend-up" : (trend.charAt(0) === "-" ? "trend-down" : "trend-flat");

    var urgencyBadges = "";
    ["critical","high","medium","low"].forEach(function(u) {
      var count = urgencies[u] || 0;
      if (count > 0) {
        urgencyBadges += ' ' + makeUrgencyBadgeHTML(u) + '<span style="font-size:13px;font-weight:600;color:var(--text-secondary);margin:0 8px 0 4px;">' + count + '</span>';
      }
    });

    var header = el("summary", "team-band-header");
    header.innerHTML =
      '<span class="team-band-badge" style="background:' + color + '20;color:' + color + ';">' + esc(teamId === "none" ? "Unassigned" : teamId) + '</span>' +
      '<span class="team-band-count">' + total + '</span>' +
      (trend !== "0" ? '<span class="team-band-trend ' + trendClass + '">' + esc(trend) + '</span>' : '') +
      '<span style="flex:1;display:flex;align-items:center;margin:0 12px;">' + urgencyBadges + '</span>' +
      '<span class="team-band-chevron">&#9654;</span>';
    band.appendChild(header);

    var issues = d.team_issues[teamId] || [];
    if (issues.length) {
      var issuesDiv = el("div", "team-band-issues");
      issues.forEach(function(iss) {
        var row = el("div", "team-issue-row");
        var prInfo = d.all_issues.find(function(ai) { return ai.issue_number === iss.number; });
        var prIcon = (prInfo && prInfo.has_linked_pr) ? ' <svg width="14" height="14" viewBox="0 0 16 16" fill="#1A7F37" style="vertical-align:-2px;"><path d="M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"/></svg>' : '';
        var areaTag = (prInfo && prInfo.area) ? ' <span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;background:var(--accent-glow);color:var(--accent);font-weight:600;">' + esc(prInfo.area) + '</span>' : '';
        var daysTag = (prInfo && prInfo.days_open != null) ? '<span style="color:var(--text-muted);font-size:12px;margin-left:auto;white-space:nowrap;">' + prInfo.days_open + 'd</span>' : '';
        row.style.cssText = 'display:flex;align-items:center;gap:6px;';
        row.innerHTML = makeUrgencyBadgeHTML(iss.urgency) +
          ' <a href="' + esc(iss.url) + '" target="_blank">#' + iss.number + '</a>' + areaTag + prIcon + ' ' +
          '<span style="color:var(--text-secondary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(iss.title) + '</span>' + daysTag;
        issuesDiv.appendChild(row);
      });
      band.appendChild(issuesDiv);
    }
    section.appendChild(band);
  });
  return section;
}
```

- [ ] **Step 3: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS

- [ ] **Step 4: Run lint**

Run: `make lint`

- [ ] **Step 5: Commit**

```bash
git add app/reports/renderers/templates/components/team_routing.js app/reports/renderers/templates/base.html
git commit -m "feat: rewrite team routing dashboard with area hierarchy and AI synthesis"
```

---

### Task 10: Wire up the full pipeline and verify end-to-end

**Files:**
- Modify: `app/reports/birds_eye.py` — pass team_profiles through from caller
- Possibly modify: `app/main.py` or equivalent entry point that calls `generate()`
- Test: Run full test suite + manual verification

**Interfaces:**
- Consumes: All changes from Tasks 1-9
- Produces: Fully integrated pipeline that works end-to-end

- [ ] **Step 1: Find and update the caller of `BirdsEyeReportGenerator.generate()`**

Run: `grep -rn "generate()" app/ --include="*.py" | grep -v __pycache__`

Update the caller to pass `team_profiles` from the loaded `RepoConfig`:
```python
report = generator.generate(team_profiles=repo_config.team_profiles)
```

- [ ] **Step 2: Run the full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS

- [ ] **Step 3: Run lint**

Run: `make lint`

- [ ] **Step 4: Commit**

```bash
git add app/
git commit -m "feat: wire up area-based team routing through full pipeline"
```
