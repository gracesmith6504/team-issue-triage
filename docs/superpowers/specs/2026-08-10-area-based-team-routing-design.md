# Area-Based Team Routing Design

## Problem

The dashboard currently classifies issues into Red Hat internal team names (agent-ops, acp, ai-safety, kata, agentdev, dashboard). This is useful internally but doesn't map to how NVIDIA organizes their codebase. For Dimitri's upstream pitch to NVIDIA, the dashboard needs to speak NVIDIA's language — their 13 `area:` labels (gateway, sandbox, supervisor, compute, policy, cli, cluster, build, docs, providers, inference, tui, sdk).

At the same time, Dimitri still needs the Red Hat team view — "here are the issues your team should work on" — with issues organized by NVIDIA workstream underneath.

Additionally, 15+ fields from the LLM triage (recommendation, summary, secondary_area, confidence_flag, author info) are computed but never displayed.

## Design

### Architecture: 4 Layers

```
Layer 1: Classify → LLM assigns NVIDIA area label per issue
Layer 2: Map     → Deterministic area → team lookup from YAML config
Layer 3: Synth   → Per-team LLM summary + recommended actions
Layer 4: Render  → Dashboard shows team → area → issues with AI summaries
```

### Layer 1: Area Classification

The LLM prompt is rewritten to classify issues into NVIDIA's 13 area labels instead of Red Hat team names. The LLM no longer needs to know about Red Hat teams — it just identifies the problem domain.

**NVIDIA area taxonomy** (from GitHub `area:` labels):

| Area | Issue Count | Description |
|------|-------------|-------------|
| gateway | 42 | API gateway, proxy, request routing, auth |
| sandbox | 32 | Sandbox isolation, container/VM sandboxes |
| supervisor | 31 | Supervisor process management, middleware |
| compute | 20 | Compute drivers, GPU, resource management |
| policy | 20 | Policy engine, security policies, guardrails |
| cli | 19 | Command-line interface |
| cluster | 14 | Cluster management, Kubernetes, Helm, deployment |
| build | 9 | Build system, CI/CD, packaging |
| docs | 8 | Documentation, examples |
| providers | 8 | LLM provider integrations, routing |
| inference | 5 | Inference engine, model serving |
| tui | 4 | Terminal UI |
| sdk | 3 | SDKs (Python, Go) |

93% of issues have no `area:` label — the LLM fills this gap using title prefix and body content.

**Title prefix → area mapping:** A config table maps title prefixes to NVIDIA areas. Example:
- `certgen`, `network`, `ingress`, `helm`, `openshift`, `kubernetes` → `cluster`
- `gateway-config`, `proxy`, `server`, `auth`, `access-control` → `gateway`
- `vm`, `vm-driver` → `sandbox`
- `l7` → `policy`
- `router` → `providers`
- `python` → `sdk`
- `examples` → `docs`

This table is defined in `profiles/openshell.yaml` as `prefix_to_area` and fed to the LLM as a routing signal.

**LLM output change:**
```json
{
  "reasoning": "...",
  "any_team_cares": true,
  "primary_area": "gateway",
  "primary_confidence": 0.85,
  "secondary_area": "policy",
  "secondary_confidence": 0.4,
  "urgency": "high",
  "urgency_reasoning": "...",
  "summary": "...",
  "recommendation": "..."
}
```

`primary_team` / `secondary_team` are replaced by `primary_area` / `secondary_area` in LLM output.

### Layer 2: Area → Team Mapping

After LLM classification, the triage engine deterministically maps area → team using team profile ownership declarations.

**Team profiles are simplified** to declare ownership of NVIDIA areas:

```yaml
# profiles/teams/agent-ops.yaml
team_id: agent-ops
team_name: "Agent Ops"
description: |
  Core OpenShell integration on Red Hat OpenShift AI...

owned_areas:
  primary: [cli, sdk, sandbox, cluster, docs]
  secondary: [gateway, supervisor, compute]
```

**Resolution rules:**
1. Look up `primary_area` in team profiles — the team that owns it as primary gets `primary_team`
2. If multiple teams have it as secondary, pick the one with highest overlap with the issue's signals
3. If no team owns the area (e.g., `build`, `tui`), `primary_team` = `"none"`
4. `secondary_team` is derived from `secondary_area` the same way

**TriageResult has BOTH area and team fields:**
```python
@dataclass
class TriageResult:
    ...
    primary_area: str           # From LLM (NVIDIA area label)
    primary_confidence: float
    secondary_area: str | None  # From LLM
    secondary_confidence: float | None
    primary_team: str           # Derived from area → team mapping
    secondary_team: str | None  # Derived from area → team mapping
    ...
```

This means:
- Old assessments with `primary_team` but no `primary_area` still load (backward compat)
- New assessments have both
- The team derivation is deterministic and repeatable

### Layer 3: Per-Team LLM Synthesis

A new report generation step after `_compute_team_breakdown()`. For each team with issues:

1. Group the team's issues by area
2. Build a prompt with: team description, issue summaries grouped by area, urgency counts
3. LLM returns:
   - `focus_summary`: 2 sentences describing what's happening in this team's areas
   - `actions`: Top 3 recommended actions (concrete, actionable)

**Model:**
```python
@dataclass
class TeamSynthesis:
    team_id: str
    focus_summary: str
    actions: list[str]
    areas: dict[str, AreaGroup]

@dataclass
class AreaGroup:
    area: str
    total: int
    by_urgency: dict[str, int]
    issues: list[TriageResult]
```

**Storage:** `TeamSynthesis` is added to `BirdsEyeReport` as `team_synthesis: dict[str, TeamSynthesis]`.

### Layer 4: Dashboard Rendering

The team_routing.js component is rewritten:

```
Agent Ops (45 issues)                    [urgency badges]
  ┌──────────────────────────────────────────────────────┐
  │ Focus this week: workspace auth model is blocking    │
  │ 3 PRs in gateway. Kata isolation work needs review.  │
  │                                                      │
  │ → Review gateway auth PRs #2401, #2389, #2356        │
  │ → Triage 5 new sandbox issues from this week         │
  │ → Address critical cluster deployment bug #2445      │
  └──────────────────────────────────────────────────────┘
  
  ▸ gateway (20 issues) — 3 critical, 5 high
  ▸ supervisor (12 issues) — 1 critical, 4 high
  ▸ compute (8 issues) — 2 high
  ▸ sandbox (5 issues) — 1 critical
```

Each area group expands to show issues with enriched data:

```
  ▾ gateway (20 issues)
    🔴 #2401 OIDC token validation fails with Keycloak 25  12d
       → Verify Keycloak version compatibility, test with 24.x fallback
       Author: @external-user (CONTRIBUTOR) | Confidence: 0.92
    🟠 #2389 Gateway returns 502 on large streaming responses  8d
       → Check buffer size config in envoy proxy settings
       ...
```

**New data surfaced per issue:**
- `recommendation` — what the team should do (from LLM triage)
- `author_association` + `author_login` — who filed it and their relationship to the project
- `confidence_flag` — when the routing is uncertain (shown as a badge)
- `summary` — 1-2 sentence issue summary (shown on hover or inline)

**Data flow for rendering:**

`html.py` `_report_to_dict()` is updated to:
1. Build `team_areas` dict: `{team_id: {area: [issues with enriched fields]}}`
2. Include `team_synthesis` data
3. Pass all TriageResult fields through (not just number, title, url, urgency)

### Backward Compatibility

**Assessment loading:** When loading assessments from JSONL:
- If `primary_area` exists → use new pipeline
- If only `primary_team` exists → treat `primary_team` value as `primary_area` if it matches a known area label, otherwise keep as legacy team routing

**Team profiles:** The old `areas.primary`/`areas.secondary` format (with fine-grained prefixes) is replaced by `owned_areas.primary`/`owned_areas.secondary` (with NVIDIA area labels). The `prefix_to_area` mapping in `openshell.yaml` handles the translation from fine-grained prefixes to NVIDIA areas.

### Files Changed

| File | Change |
|------|--------|
| `profiles/openshell.yaml` | Add `area_taxonomy` and `prefix_to_area` config |
| `profiles/teams/*.yaml` | Simplify areas to NVIDIA labels, rename to `owned_areas` |
| `app/core/models.py` | Add `primary_area`, `secondary_area` to TriageResult |
| `app/core/profiles.py` | Add AreaConfig model, area→team resolver, update TeamProfile |
| `app/core/prompt.py` | Rewrite to classify into NVIDIA areas |
| `app/core/triage_engine.py` | Add area→team derivation after LLM classification |
| `app/reports/models.py` | Add TeamSynthesis, AreaGroup models |
| `app/reports/synthesis.py` | New: per-team LLM synthesis engine |
| `app/reports/birds_eye.py` | Add area-based team breakdown, integrate synthesis |
| `app/reports/renderers/html.py` | Restructure team_issues for area grouping + synthesis |
| `app/reports/renderers/templates/components/team_routing.js` | Rewrite for team→area→issues with AI summaries |
| `app/reports/renderers/templates/base.html` | CSS for synthesis cards, area groups, enriched issue rows |
| `tests/` | Update all affected test files |

### What's NOT Changing

- PR Health section (already updated separately)
- KPIs section
- Vouch tracking
- Duplicate detection
- Area heatmap (still uses title prefix extraction)
- The `--mode triage` / `--mode report` pipeline structure
- Assessment JSONL format (additive changes only)
