# Multi-Team Triage Agent Design Spec

Date: 2026-08-04
Author: Grace Smith
Source of truth: `/Users/grasmith/Desktop/verified-team-routing-map.md`

## Overview

Evolve the single-team GitHub issue triage agent into a multi-team triage agent for OpenShell. The current system scores one issue against one team profile (3-axis scoring with ESCALATE/TRACK/WATCH/SKIP verdicts). The new system classifies which of 6 Red Hat teams should own each issue, with confidence scores and urgency levels.

## Approach

Bottom-up layer replacement. Each layer is replaced completely with its tests, working up the dependency graph. Two phases: Phase 1 delivers core classification and notifications; Phase 2 adds the bird's eye view report.

## Phase 1: Core Classification & Notifications

### 1. Data Models (`app/core/models.py`)

**Remove:** `Verdict` enum, `Assessment` dataclass, `DigestEntry` dataclass, `DIGEST_MAX_ITEMS`.

**Keep:** `IssueData` (unchanged).

**Add:**

```python
class Urgency(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class TriageResult:
    repo: str
    issue_number: int
    issue_title: str
    issue_url: str
    reasoning: str
    any_team_cares: bool
    primary_team: str            # team_id or "none"
    primary_confidence: float
    secondary_team: str | None
    secondary_confidence: float | None
    urgency: Urgency
    urgency_reasoning: str
    summary: str
    recommendation: str
    confidence_flag: str | None  # "auto", "multi_team", "uncertain"
    assessed_at: str
```

### 2. Profile System (`app/core/profiles.py`)

**Remove:** Current `TeamProfile` (single-team format), `find_profile_for_repo()`.

**Add:**

```python
@dataclass
class TeamProfile:
    team_id: str                    # kebab-case, e.g. "agent-ops"
    team_name: str
    description: str                # 2-3 sentences for LLM prompt
    areas: dict[str, list[str]]     # {"primary": [...], "secondary": [...]}
    urgency_overrides: dict[str, list[str]]
    examples: list[dict]            # calibration examples
    notifications: dict             # notification routing config

@dataclass
class RepoConfig:
    repo: str
    pinned_version: str
    team_profiles: list[TeamProfile]
    no_team_prefixes: list[str]     # prefixes that map to "no team" (build, tui, rfc, etc.)
    none_examples: list[dict]
    confidence_thresholds: dict[str, float]  # auto_assign, multi_team_gap, uncertain, none_min
    reporting: dict
```

**Add:** `load_repo_config(name: str, profiles_dir: Path | None = None) -> RepoConfig` — loads repo YAML, then loads each referenced team YAML and assembles the full config. Performs validation after loading all profiles:
- **Primary uniqueness:** each prefix/area can appear in at most one team's `areas.primary`. If `gateway` is primary for both ACP and AgentOps, raise `ValueError` at load time with both team IDs and the conflicting prefix. A prefix CAN appear in multiple teams' `areas.secondary` — that's expected.
- **No-team overlap:** prefixes in `no_team_prefixes` must not appear in any team's `areas.primary` or `areas.secondary`. If `build` is in `no_team_prefixes` AND in a team's areas, raise `ValueError`.
- **Team ID uniqueness:** no two team profiles share the same `team_id`.

### 3. Profile Directory Structure

```
profiles/
  openshell.yaml          # repo config (references teams, thresholds, none_examples)
  teams/
    agent-ops.yaml        # primary: cli, sdk, python, sandbox, cluster, docs, examples, helm, openshift, kubernetes, e2e, certgen, network, ingress; secondary: gateway, supervisor, compute, server, etc.
    acp.yaml              # primary: gateway, gateway-config, server, auth, access-control; secondary: cluster, kubernetes, helm, openshift
    ai-safety.yaml        # primary: policy, l7; secondary: supervisor, supervisor-middleware, proxy
    kata.yaml             # primary: vm, vm-driver, gpu; secondary: sandbox, compute
    agentdev.yaml         # primary: inference, providers, router; secondary: (none)
    dashboard.yaml        # narrow scope: upstream API changes affecting UI only, no primary areas
```

Repo config YAML format:

```yaml
repo: "NVIDIA/OpenShell"
pinned_version: "v0.0.92"
team_profiles:
  - teams/agent-ops.yaml
  - teams/acp.yaml
  - teams/ai-safety.yaml
  - teams/kata.yaml
  - teams/agentdev.yaml
  - teams/dashboard.yaml
no_team_prefixes:
  - build
  - ci
  - deps
  - rfc
  - rpm
  - snap
  - tui
  - observability
none_examples:
  - title: "feat(build): evaluate Bazel for unified build"
    reasoning: "Build system internals — no Red Hat team owns upstream CI/CD"
  - title: "feat(observability): OpenTelemetry span emission from supervisor"
    reasoning: "No Red Hat team has observability ownership for OpenShell"
  - title: "fix(tui): terminal corrupts to black screen after exiting shell"
    reasoning: "TUI is not owned by any Red Hat team"
  - title: "feat(rfc): make proposed RFCs discoverable from main"
    reasoning: "Upstream governance process, not team-specific"
confidence_thresholds:
  auto_assign: 0.8
  multi_team_gap: 0.2
  uncertain: 0.5
  none_min: 0.75
reporting:
  period: weekly
  period_start: monday
  timezone: UTC
```

Per-team YAML format:

```yaml
team_id: agent-ops
team_name: "Agent Ops"
description: |
  Core OpenShell integration on Red Hat OpenShift AI. Owns Helm deployment,
  SCCs, RBAC, Routes, Go SDK sync, sandbox operator design, and midstream
  pipeline. Does NOT own: TUI, Docker driver, MicroVM, macOS.
areas:
  primary:
    - cli
    - sdk
    - python
    - sandbox
    - cluster
    - docs
    - examples
    - helm
    - openshift
    - kubernetes
    - e2e
    - certgen
    - network
    - ingress
  secondary:
    - gateway
    - gateway-config
    - supervisor
    - supervisor-middleware
    - proxy
    - compute
    - driver-podman
    - podman
    - server
urgency_overrides:
  critical:
    - "Go SDK protobuf sync failures"
    - "CI pipeline failures blocking midstream"
  high:
    - "Regressions in Helm/SCC/RBAC deployment"
    - "CVEs in sandbox or supervisor"
examples:
  - title: "Go SDK protobuf sync failed for v0.4.2"
    urgency: critical
    reasoning: "SDK sync errors block the Agent Ops release pipeline"
  - title: "Helm chart fails when SCC restricts runAsUser"
    urgency: high
    reasoning: "OpenShift deployment is Agent Ops's primary focus"
notifications:
  receive_secondary: true
  secondary_min_urgency: high
  channels:
    - adapter: slack_webhook
      config:
        webhook_url: "${SLACK_WEBHOOK_AGENT_OPS}"
      immediate_on: [critical, high]
    - adapter: log
      config:
        level: info
      immediate_on: [critical, high, medium, low]
```

### 4. Signal Extraction & Prompt (`app/core/prompt.py`, `app/core/triage_engine.py`)

**Signal extraction** (in `triage_engine.py`):

```python
@dataclass
class IssueSignals:
    title_prefix: str | None
    area_labels: list[str]
    topic_labels: list[str]
    state_label: str | None
    issue_type: str | None

def extract_signals(issue: IssueData) -> IssueSignals:
    # Regex on title for conventional commit prefix
    # Filter labels by prefix: area:*, topic:*, state:*
    # Detect issue type from labels
```

**Prompt rewrite** (`app/core/prompt.py`):

Remove `BASE_SYSTEM_PROMPT` and current functions. Replace with:

- `build_system_prompt(repo_config: RepoConfig) -> str` — auto-generates all sections of the system prompt. ~2000 tokens, cached across all issues in a run. Required sections in order:
  1. **Team descriptions** — auto-generated from each `TeamProfile.description`
  2. **Routing signals** — three-signal hierarchy with explicit "problem domain overrides prefix" guidance. SIGNAL 1: title prefix (check first, but the prefix tells you the CODE area while the body tells you the PROBLEM domain — when they disagree, the problem domain wins). SIGNAL 2: issue body keywords. SIGNAL 3: labels (when present, only ~3% of triage-needed issues).
  3. **Routing table** — auto-generated from all teams' `areas.primary` and `areas.secondary` fields, plus explicit NONE rows from `RepoConfig.no_team_prefixes`. Each prefix appears at most once as primary (validated at load time).
  4. **Urgency scale** — critical/high/medium/low definitions
  5. **Calibration examples** — three structured categories: (a) standard routing (prefix matches team), (b) prefix misleads (problem domain overrides code area — e.g. `feat(cli): import OIDC tokens` → ACP not AgentOps), (c) no team cares. This three-category structure is required — it teaches the LLM the 12% of cases where naive prefix routing fails.
  6. **JSON output format** — reasoning-first schema
- `build_user_prompt(issue: IssueData, signals: IssueSignals) -> str` — formats issue with pre-extracted SIGNALS section above raw content.

The routing table is auto-generated from team profiles' `areas` fields plus `RepoConfig.no_team_prefixes` for NONE rows. Validation at load time: each prefix can appear in at most one team's `areas.primary` (duplicates fail loud). A prefix CAN appear in multiple teams' `areas.secondary` — that's expected (e.g. AgentOps is secondary for many areas).

### 5. Confidence Rules (`app/core/scoring.py`)

**Remove:** `clamp_score()`, `compute_verdict()`, `format_scores()`, `DEFAULT_THRESHOLDS`, `AXIS_LABELS`.

**Replace with:**

```python
def apply_confidence_rules(
    primary_confidence: float,
    secondary_confidence: float | None,
    any_team_cares: bool,
    thresholds: dict[str, float],
) -> str | None:
    # Checks in order (first match wins):
    # "forced_none" — LLM picked a team but confidence < none_min (0.75).
    #   Suspect forced classification — override to any_team_cares=False.
    #   This prevents the #1 failure mode: LLM always picks a team on weak signals.
    # "auto" — highly confident single-team (primary > 0.8 AND gap > 0.2)
    # "multi_team" — two teams close (gap < 0.2, any confidence)
    # "uncertain" — low confidence (primary < 0.5, gap >= 0.2)
    # None — normal assignment (primary 0.5-0.8, gap >= 0.2)
    #
    # Note: "forced_none" only fires when the LLM said any_team_cares=True
    # but confidence is below none_min. If the LLM already said
    # any_team_cares=False, no override is needed.
```

### 6. Triage Engine (`app/core/triage_engine.py`, replaces `app/core/assessment.py`)

**Delete:** `assessment.py`.

**Create:** `triage_engine.py` with:

```python
def triage_issue(
    issue: IssueData,
    llm_client: LLMClientProtocol,
    model: str,
    repo_config: RepoConfig,
    system_prompt: str,
) -> TriageResult | None:
    # 1. extract_signals(issue)
    # 2. build_user_prompt(issue, signals)
    # 3. llm_client.assess(system_prompt, user_prompt, model)
    # 4. Parse JSON response, validate fields
    # 5. apply_confidence_rules() to set confidence_flag
    # 6. Return TriageResult
```

Takes `system_prompt` as parameter (built once per run, not per issue). Takes `RepoConfig` for confidence thresholds.

### 7. State Fix (`app/state/tracker.py`)

Namespace `seen_issues` keys from bare `int` to `"repo#number"` strings.

- `load()`: detect and migrate legacy bare-int keys on load
- `save()`: store namespaced string keys
- `prune_seen()`: same logic, string keys
- `default_state()`: `seen_issues` becomes `set[str]`
- Callers use `f"{repo}#{number}"` format

### 8. Notification Architecture

#### `app/notifications/adapter.py` (new)

```python
class NotificationAdapter(Protocol):
    def deliver_immediate(self, result: TriageResult, channel_config: dict) -> None: ...
    def deliver_digest(self, results: list[TriageResult], channel_config: dict) -> None: ...
    def collect_feedback(self) -> list[FeedbackEvent]: ...

@dataclass
class FeedbackEvent:
    issue_number: int
    team_id: str
    feedback_type: str
    feedback_by: str
    feedback_at: str
    original_confidence: float

@dataclass
class ChannelConfig:
    adapter_type: str
    config: dict
    immediate_on: list[str]

@dataclass
class TeamNotificationConfig:
    team_id: str
    receive_secondary: bool
    secondary_min_urgency: str | None
    channels: list[ChannelConfig]
```

#### `app/notifications/router.py` (new)

```python
class NotificationRouter:
    def __init__(self, team_configs, adapters):
        self.team_configs = team_configs
        self.adapters = adapters

    def route(self, result: TriageResult) -> None:
        # Skip if not any_team_cares
        # Only deliver immediate notifications (urgency in channel's immediate_on list)
        # Medium/low results are silently skipped — they go to the daily digest via run_digest()
        # If secondary_team, check config and deliver FYI (same urgency filter)

    def send_digest(self, results: list[TriageResult]) -> None:
        # Called by run_digest() with pre-filtered medium/low results from the JSONL log
        # Groups by primary_team, sends one digest message per team via adapter.deliver_digest()
```

#### `app/notifications/slack_webhook.py` (new, replaces `slack.py`)

`SlackWebhookAdapter` with Block Kit formatting. Three message formats:
- Immediate alert (critical/high): emoji + team + issue + summary + recommendation + link
- Daily digest (medium/low): team header + bullet list
- Secondary team FYI: "Also routed to you" format

`collect_feedback()` returns `[]`.

#### `app/notifications/log.py` (update)

`LogAdapter` wrapping existing stdout logging to implement the new protocol.

#### Delete

- `app/notifications/slack.py` (old `SlackNotifier`)
- `app/notifications/notifier.py` (old `Notifier` protocol)

### 9. Orchestrator Rewrite (`app/triage.py`)

`run_triage(config)`:
1. Load state (StateTracker)
2. Load repo config (all 6 team profiles)
3. Build system prompt once from repo config
4. Build notification router (team configs from profiles, adapters from config)
5. Fetch new issues from GitHub
6. For each new issue: triage_issue() → TriageResult → log to JSONL → router.route()
   - router.route() only sends immediate notifications (critical/high)
   - medium/low results are logged to JSONL but NOT sent — they wait for the daily digest
7. Update seen_issues (namespaced keys), save state

`run_review(config)`: Same concept, updated for TriageResult field names.

`run_digest(config)`: Reads the JSONL assessment log for all results since last digest run. Filters for medium/low urgency, groups by primary_team, sends one digest per team via the configured adapter. Tracks "last digest timestamp" in state to avoid re-sending. The daily digest CronJob (`k8s/cronjob-digest.yaml`, 08:30 UTC) stays — it calls `--mode digest`.

### 10. Config Updates (`app/config.py`)

Add to `TriageConfig`:
- Per-team webhook URL env vars referenced from team YAML `${SLACK_WEBHOOK_*}` placeholders
- Env var interpolation when loading team notification configs

---

## Phase 2: Bird's Eye View & Duplicate Detection

### 11. Extend Assessment Log (`app/state/assessment_log.py`, update)

Phase 1 already built JSONL persistence with `append_result()`, `read_results()` (with `since_hours`, `team_filter`, `urgency_filter`), `result_to_record()`, `record_to_result()`, and `format_review()`. No separate `TriageResultStore` needed.

**Add:**
- `start_date` / `end_date` (ISO string) parameters to `read_results()` for period-based queries
- Convenience wrapper `read_results_as_triage(...)` that returns `list[TriageResult]` instead of `list[dict]`

### 12. Duplicate Detection (`app/reports/duplicates.py`, new)

Layer 1: Group by area label or title prefix. Flag issues within 7-day window.
Layer 2: Title token overlap within clusters. 2+ shared meaningful tokens threshold.

```python
@dataclass
class DuplicateCluster:
    area: str
    issues: list[TriageResult]
    similarity_reason: str

class DuplicateDetector:
    def detect(self, results: list[TriageResult]) -> list[DuplicateCluster]: ...
```

### 13. Report Data Models (`app/reports/models.py`, new)

```python
@dataclass
class ReportSummary:
    total_open: int
    new_this_period: int
    closed_this_period: int
    by_urgency: dict[str, int]
    untriaged_count: int

@dataclass
class TeamSummary:
    team_id: str
    total: int
    by_urgency: dict[str, int]
    new_this_period: int
    previous_period: int
    trend: str
    uncertain: list[TriageResult]

@dataclass
class AreaTrend:
    area: str
    current_count: int
    previous_count: int
    delta: int
    trend: str

@dataclass
class BirdsEyeReport:
    summary: ReportSummary
    critical_list: list[TriageResult]
    team_breakdown: dict[str, TeamSummary]
    area_heatmap: dict[str, AreaTrend]
    duplicate_clusters: list[DuplicateCluster]
    no_team_list: list[TriageResult]
    narrative: str
    generated_at: str
```

### 14. Report Generator (`app/reports/birds_eye.py`, new)

```python
class BirdsEyeReportGenerator:
    def __init__(self, current, previous, llm_client, model): ...
    def generate(self) -> BirdsEyeReport: ...
```

Computes all sections from TriageResult lists. One Sonnet call for the narrative summary.

### 15. Markdown Renderer (`app/reports/renderers/markdown.py`, new)

`MarkdownRenderer.render(report: BirdsEyeReport) -> str` — formats the report as readable markdown matching the format shown in the design doc (section 6). Outputs to stdout or file.

Google Doc renderer deferred — markdown output can be pasted manually for now.

### 16. CLI & Wiring

Add `--mode report` to `__main__.py`. `run_report()` in `triage.py` loads assessment log, computes current + previous period results, generates report, renders to markdown, prints to stdout. Optional `--output` flag writes to file. On-demand via `python -m app --mode report`.

---

## File Change Summary

### Phase 1

| File | Action |
|------|--------|
| `app/core/models.py` | Replace Assessment/Verdict/DigestEntry with TriageResult/Urgency |
| `app/core/profiles.py` | Replace TeamProfile, add RepoConfig, new loader |
| `app/core/prompt.py` | Complete rewrite — multi-team system prompt |
| `app/core/scoring.py` | Replace 3-axis scoring with confidence rules |
| `app/core/assessment.py` | Delete |
| `app/core/triage_engine.py` | New — signal extraction, triage orchestration |
| `app/state/tracker.py` | Namespace seen_ids by repo |
| `app/notifications/adapter.py` | New — protocol, FeedbackEvent, config dataclasses |
| `app/notifications/router.py` | New — NotificationRouter |
| `app/notifications/slack_webhook.py` | New — SlackWebhookAdapter |
| `app/notifications/log.py` | Update — implement new protocol |
| `app/notifications/notifier.py` | Delete |
| `app/notifications/slack.py` | Delete |
| `app/triage.py` | Rewrite orchestration |
| `app/state/assessment_log.py` | Update `assessment_to_record()` and `format_review()` for TriageResult fields |
| `app/config.py` | Add per-team webhook config |
| `app/__main__.py` | Minor updates |
| `profiles/openshell.yaml` | Rewrite to repo config format |
| `profiles/teams/*.yaml` | New — 6 team profile files |

### Phase 2

| File | Action |
|------|--------|
| `app/state/assessment_log.py` | Extend with period-based queries |
| `app/reports/__init__.py` | New |
| `app/reports/models.py` | New |
| `app/reports/duplicates.py` | New |
| `app/reports/birds_eye.py` | New |
| `app/reports/renderers/__init__.py` | New |
| `app/reports/renderers/markdown.py` | New |
| `app/triage.py` | Wire in report generation |
| `app/__main__.py` | Add --mode report |
| `app/config.py` | Add report config |

### What stays unchanged

- `app/core/llm.py` — LLM client abstraction
- `app/core/truncation.py` — text truncation utilities
- `app/sources/github.py` — GitHub issue fetcher
- `app/sources/source.py` — IssueSource protocol
- `Dockerfile`, `Makefile`, `requirements.txt`
- `k8s/cronjob-triage.yaml` — hourly schedule stays, args unchanged
- `k8s/cronjob-digest.yaml` — daily schedule stays, args unchanged (still `--mode digest`)
- `k8s/configmap.yaml` — add new env vars for per-team webhook URLs and triage store path
- `k8s/pvc.yaml`, `k8s/kustomization.yaml` — unchanged

## Commit Plan

### Phase 1 (8 commits)

1. Replace data models (TriageResult, Urgency) + update model tests
2. Rewrite profile system (TeamProfile, RepoConfig, loader) + create 6 team YAMLs + rewrite openshell.yaml + update profile tests
3. Rewrite prompt construction (multi-team system prompt, signal-aware user prompt) + update prompt tests
4. Replace scoring with confidence rules + update scoring tests
5. Create triage engine (signal extraction, issue triage) + delete assessment.py + update engine tests
6. Fix state tracker (namespace seen_ids) + update tracker tests
7. Build notification architecture (adapter protocol, router, webhook adapter, update log adapter) + delete old notifier/slack + add notification tests
8. Rewrite orchestrator (triage.py, config.py, __main__.py) + update integration tests

### Phase 2 (5 commits)

9. Extend assessment_log with period queries + add report data models + tests
10. Add duplicate detector + tests
11. Build bird's eye report generator + tests
12. Build markdown renderer + tests
13. Wire reports into main flow (triage.py, __main__.py, config.py) + integration tests
