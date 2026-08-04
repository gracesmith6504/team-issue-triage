# Multi-Team Triage Agent — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-team 3-axis scoring (ESCALATE/TRACK/WATCH/SKIP) with multi-class team classification (6 teams, confidence scores, urgency levels) for OpenShell issue triage.

**Architecture:** Bottom-up layer replacement through the dependency graph. Each task replaces one layer completely — models, profiles, prompt, scoring, engine, state, notifications, orchestrator. Tests are rewritten alongside each layer.

**Tech Stack:** Python 3.12, pytest, ruff, anthropic[vertex] SDK, requests, PyYAML

## Global Constraints

- Source of truth: `/Users/grasmith/Desktop/verified-team-routing-map.md`
- Run `make lint` before pushing
- Never include `Co-Authored-By` lines in commits
- One logical change per commit, squash before review
- `IssueData` dataclass and `app/core/llm.py` are unchanged
- `app/sources/` and `app/core/truncation.py` are unchanged
- All tests must pass after each task: `python3 -m pytest tests/ -v`

---

### Task 1: Data Models

**Files:**
- Modify: `app/core/models.py`
- Rewrite: `tests/core/test_models.py`

**Interfaces:**
- Consumes: nothing (foundation layer)
- Produces:
  - `Urgency(str, Enum)` with members `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`
  - `TriageResult` dataclass with fields: `repo: str`, `issue_number: int`, `issue_title: str`, `issue_url: str`, `reasoning: str`, `any_team_cares: bool`, `primary_team: str`, `primary_confidence: float`, `secondary_team: str | None`, `secondary_confidence: float | None`, `urgency: Urgency`, `urgency_reasoning: str`, `summary: str`, `recommendation: str`, `confidence_flag: str | None`, `assessed_at: str`
  - `IssueSignals` dataclass with fields: `title_prefix: str | None`, `area_labels: list[str]`, `topic_labels: list[str]`, `state_label: str | None`, `issue_type: str | None`
  - `IssueData` (unchanged, already exists)

- [ ] **Step 1: Write the new test file**

```python
# tests/core/test_models.py
from app.core.models import IssueData, IssueSignals, TriageResult, Urgency


def test_urgency_values():
    assert Urgency.CRITICAL == "critical"
    assert Urgency.HIGH == "high"
    assert Urgency.MEDIUM == "medium"
    assert Urgency.LOW == "low"


def test_urgency_ordering():
    ordered = [Urgency.CRITICAL, Urgency.HIGH, Urgency.MEDIUM, Urgency.LOW]
    assert [u.value for u in ordered] == ["critical", "high", "medium", "low"]


def test_issue_data_creation():
    issue = IssueData(
        repo="NVIDIA/OpenShell",
        number=2571,
        title="bug(supervisor): SPIFFE crash",
        body="SPIFFE sandboxes crash on restart",
        labels=["area:supervisor", "topic:security"],
        comments=[],
        url="https://github.com/NVIDIA/OpenShell/issues/2571",
        created_at="2026-08-01T00:00:00Z",
    )
    assert issue.number == 2571
    assert issue.repo == "NVIDIA/OpenShell"


def test_triage_result_creation():
    result = TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=2571,
        issue_title="bug(supervisor): SPIFFE crash",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2571",
        reasoning="SPIFFE in title indicates security",
        any_team_cares=True,
        primary_team="ai-safety",
        primary_confidence=0.85,
        secondary_team="agent-ops",
        secondary_confidence=0.65,
        urgency=Urgency.HIGH,
        urgency_reasoning="Security crash is a regression",
        summary="SPIFFE sandboxes crash on restart",
        recommendation="Investigate SPIFFE lifecycle",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00Z",
    )
    assert result.primary_team == "ai-safety"
    assert result.urgency == Urgency.HIGH
    assert result.urgency.value == "high"
    assert result.secondary_team == "agent-ops"


def test_triage_result_no_team():
    result = TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=2491,
        issue_title="feat(build): evaluate Bazel",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2491",
        reasoning="Build system, no Red Hat team",
        any_team_cares=False,
        primary_team="none",
        primary_confidence=0.9,
        secondary_team=None,
        secondary_confidence=None,
        urgency=Urgency.LOW,
        urgency_reasoning="Design discussion",
        summary="Evaluate Bazel for builds",
        recommendation="No action needed",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00Z",
    )
    assert result.any_team_cares is False
    assert result.primary_team == "none"
    assert result.secondary_team is None
    assert result.secondary_confidence is None


def test_issue_signals_creation():
    signals = IssueSignals(
        title_prefix="supervisor",
        area_labels=["area:supervisor"],
        topic_labels=["topic:security"],
        state_label="state:triage-needed",
        issue_type="Bug",
    )
    assert signals.title_prefix == "supervisor"
    assert signals.area_labels == ["area:supervisor"]


def test_issue_signals_no_prefix():
    signals = IssueSignals(
        title_prefix=None,
        area_labels=[],
        topic_labels=[],
        state_label=None,
        issue_type=None,
    )
    assert signals.title_prefix is None
    assert signals.area_labels == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/core/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Urgency'`

- [ ] **Step 3: Replace models.py**

Replace the entire contents of `app/core/models.py` with:

```python
from dataclasses import dataclass
from enum import Enum


class Urgency(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class IssueData:
    repo: str
    number: int
    title: str
    body: str
    labels: list[str]
    comments: list[dict]
    url: str
    created_at: str


@dataclass
class TriageResult:
    repo: str
    issue_number: int
    issue_title: str
    issue_url: str
    reasoning: str
    any_team_cares: bool
    primary_team: str
    primary_confidence: float
    secondary_team: str | None
    secondary_confidence: float | None
    urgency: Urgency
    urgency_reasoning: str
    summary: str
    recommendation: str
    confidence_flag: str | None
    assessed_at: str


@dataclass
class IssueSignals:
    title_prefix: str | None
    area_labels: list[str]
    topic_labels: list[str]
    state_label: str | None
    issue_type: str | None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/core/test_models.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/models.py tests/core/test_models.py
git commit -m "feat: replace Assessment/Verdict with TriageResult/Urgency data models"
```

---

### Task 2: Profile System + Team YAMLs

**Files:**
- Modify: `app/core/profiles.py`
- Rewrite: `profiles/openshell.yaml`
- Create: `profiles/teams/agent-ops.yaml`
- Create: `profiles/teams/acp.yaml`
- Create: `profiles/teams/ai-safety.yaml`
- Create: `profiles/teams/kata.yaml`
- Create: `profiles/teams/agentdev.yaml`
- Create: `profiles/teams/dashboard.yaml`
- Rewrite: `tests/core/test_profiles.py`

**Interfaces:**
- Consumes: nothing (reads YAML files only)
- Produces:
  - `TeamProfile` dataclass with fields: `team_id: str`, `team_name: str`, `description: str`, `areas: dict[str, list[str]]`, `urgency_overrides: dict[str, list[str]]`, `examples: list[dict]`, `notifications: dict`
  - `RepoConfig` dataclass with fields: `repo: str`, `pinned_version: str`, `team_profiles: list[TeamProfile]`, `no_team_prefixes: list[str]`, `none_examples: list[dict]`, `confidence_thresholds: dict[str, float]`, `reporting: dict`
  - `load_repo_config(name: str, profiles_dir: Path | None = None) -> RepoConfig`
  - Constant: `PROFILES_DIR`

- [ ] **Step 1: Write the tests**

```python
# tests/core/test_profiles.py
import pytest
import yaml
from pathlib import Path

from app.core.profiles import load_repo_config, PROFILES_DIR


@pytest.fixture()
def profiles_dir(tmp_path):
    teams_dir = tmp_path / "teams"
    teams_dir.mkdir()

    team_a = {
        "team_id": "team-a",
        "team_name": "Team A",
        "description": "Team A does stuff",
        "areas": {"primary": ["cli", "sdk"], "secondary": ["gateway"]},
        "urgency_overrides": {"critical": ["SDK sync failures"]},
        "examples": [{"title": "SDK sync failed", "urgency": "critical", "reasoning": "Blocks release"}],
        "notifications": {
            "receive_secondary": True,
            "secondary_min_urgency": "high",
            "channels": [],
        },
    }
    team_b = {
        "team_id": "team-b",
        "team_name": "Team B",
        "description": "Team B does other stuff",
        "areas": {"primary": ["gateway"], "secondary": []},
        "urgency_overrides": {},
        "examples": [],
        "notifications": {"receive_secondary": False, "channels": []},
    }

    (teams_dir / "team-a.yaml").write_text(yaml.dump(team_a))
    (teams_dir / "team-b.yaml").write_text(yaml.dump(team_b))

    repo_config = {
        "repo": "NVIDIA/OpenShell",
        "pinned_version": "v0.0.92",
        "team_profiles": ["teams/team-a.yaml", "teams/team-b.yaml"],
        "no_team_prefixes": ["build", "tui"],
        "none_examples": [
            {"title": "feat(build): evaluate Bazel", "reasoning": "No team owns builds"},
        ],
        "confidence_thresholds": {
            "auto_assign": 0.8,
            "multi_team_gap": 0.2,
            "uncertain": 0.5,
            "none_min": 0.75,
        },
        "reporting": {"period": "weekly", "period_start": "monday", "timezone": "UTC"},
    }
    (tmp_path / "test-repo.yaml").write_text(yaml.dump(repo_config))
    return tmp_path


def test_load_repo_config(profiles_dir):
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    assert config.repo == "NVIDIA/OpenShell"
    assert config.pinned_version == "v0.0.92"
    assert len(config.team_profiles) == 2
    assert config.team_profiles[0].team_id == "team-a"
    assert config.team_profiles[1].team_id == "team-b"
    assert config.no_team_prefixes == ["build", "tui"]
    assert config.confidence_thresholds["none_min"] == 0.75
    assert len(config.none_examples) == 1


def test_load_repo_config_team_fields(profiles_dir):
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    team_a = config.team_profiles[0]
    assert team_a.team_name == "Team A"
    assert team_a.description == "Team A does stuff"
    assert team_a.areas["primary"] == ["cli", "sdk"]
    assert team_a.areas["secondary"] == ["gateway"]
    assert len(team_a.examples) == 1
    assert team_a.notifications["receive_secondary"] is True


def test_load_repo_config_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_repo_config("nonexistent", profiles_dir=tmp_path)


def test_load_repo_config_missing_team_file(profiles_dir):
    repo_yaml = profiles_dir / "test-repo.yaml"
    data = yaml.safe_load(repo_yaml.read_text())
    data["team_profiles"].append("teams/missing.yaml")
    repo_yaml.write_text(yaml.dump(data))
    with pytest.raises(FileNotFoundError):
        load_repo_config("test-repo", profiles_dir=profiles_dir)


def test_validation_primary_uniqueness(profiles_dir):
    team_b_path = profiles_dir / "teams" / "team-b.yaml"
    team_b = yaml.safe_load(team_b_path.read_text())
    team_b["areas"]["primary"] = ["cli"]  # conflict: team-a also has cli as primary
    team_b_path.write_text(yaml.dump(team_b))
    with pytest.raises(ValueError, match="cli.*primary"):
        load_repo_config("test-repo", profiles_dir=profiles_dir)


def test_validation_no_team_overlap(profiles_dir):
    team_a_path = profiles_dir / "teams" / "team-a.yaml"
    team_a = yaml.safe_load(team_a_path.read_text())
    team_a["areas"]["primary"].append("build")  # conflict: build is in no_team_prefixes
    team_a_path.write_text(yaml.dump(team_a))
    with pytest.raises(ValueError, match="build.*no_team_prefixes"):
        load_repo_config("test-repo", profiles_dir=profiles_dir)


def test_validation_team_id_uniqueness(profiles_dir):
    team_b_path = profiles_dir / "teams" / "team-b.yaml"
    team_b = yaml.safe_load(team_b_path.read_text())
    team_b["team_id"] = "team-a"  # duplicate
    team_b_path.write_text(yaml.dump(team_b))
    with pytest.raises(ValueError, match="team-a.*duplicate"):
        load_repo_config("test-repo", profiles_dir=profiles_dir)


def test_secondary_can_overlap(profiles_dir):
    """Multiple teams listing the same prefix as secondary is allowed."""
    team_b_path = profiles_dir / "teams" / "team-b.yaml"
    team_b = yaml.safe_load(team_b_path.read_text())
    team_b["areas"]["secondary"] = ["cli"]  # team-a has cli as primary, team-b as secondary — OK
    team_b_path.write_text(yaml.dump(team_b))
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    assert len(config.team_profiles) == 2


def test_load_real_profiles():
    """Smoke test: the actual profiles/ directory loads without errors."""
    config = load_repo_config("openshell")
    assert config.repo == "NVIDIA/OpenShell"
    assert len(config.team_profiles) == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/core/test_profiles.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_repo_config'`

- [ ] **Step 3: Write profiles.py**

Replace the entire contents of `app/core/profiles.py` with:

```python
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).parent.parent.parent / "profiles"


@dataclass
class TeamProfile:
    team_id: str
    team_name: str
    description: str
    areas: dict[str, list[str]]
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


def _load_team_profile(path: Path) -> TeamProfile:
    with open(path) as f:
        data = yaml.safe_load(f)
    return TeamProfile(
        team_id=data["team_id"],
        team_name=data["team_name"],
        description=data.get("description", ""),
        areas=data.get("areas", {"primary": [], "secondary": []}),
        urgency_overrides=data.get("urgency_overrides", {}),
        examples=data.get("examples", []),
        notifications=data.get("notifications", {}),
    )


def _validate_profiles(profiles: list[TeamProfile], no_team_prefixes: list[str]) -> None:
    team_ids = [p.team_id for p in profiles]
    duplicates = [tid for tid in team_ids if team_ids.count(tid) > 1]
    if duplicates:
        raise ValueError(f"Duplicate team_id: {duplicates[0]} — each team must have a unique team_id")

    primary_owners: dict[str, str] = {}
    for profile in profiles:
        for prefix in profile.areas.get("primary", []):
            if prefix in primary_owners:
                raise ValueError(
                    f"Prefix '{prefix}' listed as primary by both "
                    f"'{primary_owners[prefix]}' and '{profile.team_id}'"
                )
            primary_owners[prefix] = profile.team_id

    no_team_set = set(no_team_prefixes)
    for profile in profiles:
        for prefix in profile.areas.get("primary", []) + profile.areas.get("secondary", []):
            if prefix in no_team_set:
                raise ValueError(
                    f"Prefix '{prefix}' is in no_team_prefixes but also "
                    f"appears in '{profile.team_id}' areas"
                )


def load_repo_config(name: str, profiles_dir: Path | None = None) -> RepoConfig:
    base = profiles_dir or PROFILES_DIR
    config_path = base / f"{name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Repo config not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    profiles = []
    for team_path_str in data["team_profiles"]:
        team_path = base / team_path_str
        if not team_path.exists():
            raise FileNotFoundError(f"Team profile not found: {team_path}")
        profiles.append(_load_team_profile(team_path))

    no_team_prefixes = data.get("no_team_prefixes", [])
    _validate_profiles(profiles, no_team_prefixes)

    return RepoConfig(
        repo=data["repo"],
        pinned_version=data.get("pinned_version", ""),
        team_profiles=profiles,
        no_team_prefixes=no_team_prefixes,
        none_examples=data.get("none_examples", []),
        confidence_thresholds=data.get("confidence_thresholds", {}),
        reporting=data.get("reporting", {}),
    )
```

- [ ] **Step 4: Create the 6 team YAML files and rewrite openshell.yaml**

Create `profiles/teams/` directory, then create each file. The content for each team comes from the design doc (verified-team-routing-map.md). Here are all 7 YAML files:

**`profiles/openshell.yaml`** — replace the entire file:

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

**`profiles/teams/agent-ops.yaml`:**

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

**`profiles/teams/acp.yaml`:**

```yaml
team_id: acp
team_name: "ACP / OpenShell as Service"

description: |
  Hosted OpenShell on ROSA. Owns gateway RBAC, OIDC, multi-tenancy,
  namespace mapping, hosted-mode e2e testing.

areas:
  primary:
    - gateway
    - gateway-config
    - server
    - auth
    - access-control
  secondary:
    - cluster
    - kubernetes
    - helm
    - openshift

urgency_overrides:
  critical:
    - "Gateway RBAC bypass"
    - "OIDC token validation failure"
  high:
    - "Multi-tenancy namespace isolation breach"
    - "Hosted mode e2e test failures"

examples:
  - title: "feat(gateway): make Postgres connection pool configurable"
    urgency: medium
    reasoning: "Gateway config, ACP runs gateway at scale"
  - title: "feat(server): implement grpc.health.v1.Health/Watch"
    urgency: medium
    reasoning: "Server HA, ACP cares for hosted mode"

notifications:
  receive_secondary: true
  secondary_min_urgency: high
  channels:
    - adapter: slack_webhook
      config:
        webhook_url: "${SLACK_WEBHOOK_ACP}"
      immediate_on: [critical, high]
    - adapter: log
      config:
        level: info
      immediate_on: [critical, high, medium, low]
```

**`profiles/teams/ai-safety.yaml`:**

```yaml
team_id: ai-safety
team_name: "AI Safety"

description: |
  Red teaming OpenShell, guardrails, policy engine, OLS guardrails,
  injection detection, L7 inspection.

areas:
  primary:
    - policy
    - l7
  secondary:
    - supervisor
    - supervisor-middleware
    - proxy

urgency_overrides:
  critical:
    - "Policy bypass vulnerability"
    - "Guardrails injection detection failure"
  high:
    - "Policy engine regression"
    - "SPIFFE identity security issues"

examples:
  - title: "feat(policy): distinguish single- and multi-segment path wildcards"
    urgency: medium
    reasoning: "Policy engine, AI Safety's area"
  - title: "bug(supervisor): SPIFFE-enabled sandboxes crash on restart"
    urgency: high
    reasoning: "SPIFFE identity security, even though prefix says supervisor"

notifications:
  receive_secondary: true
  secondary_min_urgency: medium
  channels:
    - adapter: slack_webhook
      config:
        webhook_url: "${SLACK_WEBHOOK_AI_SAFETY}"
      immediate_on: [critical, high]
    - adapter: log
      config:
        level: info
      immediate_on: [critical, high, medium, low]
```

**`profiles/teams/kata.yaml`:**

```yaml
team_id: kata
team_name: "Kata / Agent Sandbox"

description: |
  VM isolation, Kata containers, agent-sandbox operator, OpenShift
  Sandboxed Containers integration.

areas:
  primary:
    - vm
    - vm-driver
    - gpu
  secondary:
    - sandbox
    - compute

urgency_overrides:
  critical:
    - "VM escape vulnerability"
  high:
    - "Kata container startup failure"
    - "GPU passthrough regression"

examples:
  - title: "VM sandbox SSH session disconnects with broken pipe"
    urgency: high
    reasoning: "VM-based sandbox isolation issue"
  - title: "Mount shared folder from host into VM based sandbox"
    urgency: medium
    reasoning: "VM sandbox feature request"

notifications:
  receive_secondary: true
  secondary_min_urgency: high
  channels:
    - adapter: slack_webhook
      config:
        webhook_url: "${SLACK_WEBHOOK_KATA}"
      immediate_on: [critical, high]
    - adapter: log
      config:
        level: info
      immediate_on: [critical, high, medium, low]
```

**`profiles/teams/agentdev.yaml`:**

```yaml
team_id: agentdev
team_name: "AgentDev"

description: |
  Harness validation (Codex, OpenCode, etc.), MLflow tracing, coding
  agent integration, provider compatibility.

areas:
  primary:
    - inference
    - providers
    - router
  secondary: []

urgency_overrides:
  critical:
    - "Harness compatibility break blocking release"
  high:
    - "Integration test failures with supported harnesses"
    - "Provider routing regression"

examples:
  - title: "bug: integration test fails with Codex harness on v0.0.90"
    urgency: high
    reasoning: "Harness compatibility regression"
  - title: "feat(inference): add streaming support for tool-use responses"
    urgency: medium
    reasoning: "Inference feature in AgentDev's area"

notifications:
  receive_secondary: false
  channels:
    - adapter: slack_webhook
      config:
        webhook_url: "${SLACK_WEBHOOK_AGENTDEV}"
      immediate_on: [critical, high]
    - adapter: log
      config:
        level: info
      immediate_on: [critical, high, medium, low]
```

**`profiles/teams/dashboard.yaml`:**

```yaml
team_id: dashboard
team_name: "AI Core Dashboard"

description: |
  Agent dashboard UI, deploy wizard, admin console. Only cares about
  upstream API changes that affect their UI — NOT CLI bugs, policy
  fixes, or compute driver internals.

areas:
  primary: []
  secondary: []

urgency_overrides:
  high:
    - "Breaking API change affecting workspace CRUD"
    - "Breaking API change affecting sandbox management endpoints"

examples:
  - title: "Stabilize public API, SDK, and extension contracts for beta"
    urgency: medium
    reasoning: "API stability affects dashboard integration"

notifications:
  receive_secondary: true
  secondary_min_urgency: high
  channels:
    - adapter: log
      config:
        level: info
      immediate_on: [critical, high, medium, low]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/core/test_profiles.py -v`
Expected: all 10 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/profiles.py profiles/ tests/core/test_profiles.py
git commit -m "feat: rewrite profile system with multi-team RepoConfig and 6 team YAMLs"
```

---

### Task 3: Prompt Construction

**Files:**
- Modify: `app/core/prompt.py`
- Rewrite: `tests/core/test_prompt.py`

**Interfaces:**
- Consumes: `RepoConfig`, `TeamProfile` from `app.core.profiles`; `IssueData`, `IssueSignals` from `app.core.models`; `truncate_body`, `truncate_comment` from `app.core.truncation`
- Produces:
  - `build_system_prompt(repo_config: RepoConfig) -> str`
  - `build_user_prompt(issue: IssueData, signals: IssueSignals) -> str`

- [ ] **Step 1: Write the tests**

```python
# tests/core/test_prompt.py
from app.core.models import IssueData, IssueSignals
from app.core.profiles import RepoConfig, TeamProfile
from app.core.prompt import build_system_prompt, build_user_prompt


def _make_team(team_id, name, description, primary=None, secondary=None, examples=None):
    return TeamProfile(
        team_id=team_id,
        team_name=name,
        description=description,
        areas={"primary": primary or [], "secondary": secondary or []},
        urgency_overrides={},
        examples=examples or [],
        notifications={},
    )


def _make_repo_config(teams=None, no_team_prefixes=None, none_examples=None):
    if teams is None:
        teams = [
            _make_team("agent-ops", "Agent Ops", "Core integration", primary=["cli", "sdk"]),
            _make_team("acp", "ACP", "Hosted mode", primary=["gateway"], secondary=["cluster"]),
        ]
    return RepoConfig(
        repo="NVIDIA/OpenShell",
        pinned_version="v0.0.92",
        team_profiles=teams,
        no_team_prefixes=no_team_prefixes or ["build", "tui"],
        none_examples=none_examples or [{"title": "feat(build): Bazel", "reasoning": "No team"}],
        confidence_thresholds={"auto_assign": 0.8, "multi_team_gap": 0.2, "uncertain": 0.5, "none_min": 0.75},
        reporting={},
    )


def _make_issue():
    return IssueData(
        repo="NVIDIA/OpenShell",
        number=2571,
        title="bug(supervisor): SPIFFE crash",
        body="SPIFFE sandboxes crash on restart",
        labels=["area:supervisor", "topic:security", "Bug"],
        comments=[{"user": "dev", "body": "Investigating"}],
        url="https://github.com/NVIDIA/OpenShell/issues/2571",
        created_at="2026-08-01T00:00:00Z",
    )


def _make_signals():
    return IssueSignals(
        title_prefix="supervisor",
        area_labels=["area:supervisor"],
        topic_labels=["topic:security"],
        state_label=None,
        issue_type="Bug",
    )


def test_system_prompt_contains_team_descriptions():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "agent-ops" in prompt
    assert "Agent Ops" in prompt
    assert "Core integration" in prompt
    assert "acp" in prompt
    assert "ACP" in prompt
    assert "Hosted mode" in prompt


def test_system_prompt_contains_routing_table():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "cli" in prompt
    assert "sdk" in prompt
    assert "gateway" in prompt


def test_system_prompt_contains_none_rows():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "build" in prompt
    assert "tui" in prompt
    assert "NONE" in prompt


def test_system_prompt_contains_prefix_misleads_guidance():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "problem domain" in prompt.lower() or "PROBLEM domain" in prompt
    assert "prefix" in prompt.lower()


def test_system_prompt_contains_urgency_scale():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "critical" in prompt.lower()
    assert "high" in prompt.lower()
    assert "medium" in prompt.lower()
    assert "low" in prompt.lower()


def test_system_prompt_contains_output_format():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "reasoning" in prompt
    assert "any_team_cares" in prompt
    assert "primary_team" in prompt
    assert "primary_confidence" in prompt


def test_system_prompt_contains_calibration_examples():
    teams = [
        _make_team(
            "agent-ops", "Agent Ops", "Core",
            primary=["cli"],
            examples=[{"title": "SDK sync failed", "urgency": "critical", "reasoning": "Blocks release"}],
        ),
    ]
    config = _make_repo_config(teams=teams)
    prompt = build_system_prompt(config)
    assert "SDK sync failed" in prompt


def test_system_prompt_contains_none_examples():
    config = _make_repo_config()
    prompt = build_system_prompt(config)
    assert "feat(build): Bazel" in prompt


def test_user_prompt_contains_signals():
    issue = _make_issue()
    signals = _make_signals()
    prompt = build_user_prompt(issue, signals)
    assert "supervisor" in prompt
    assert "area:supervisor" in prompt
    assert "topic:security" in prompt
    assert "Bug" in prompt


def test_user_prompt_contains_issue_data():
    issue = _make_issue()
    signals = _make_signals()
    prompt = build_user_prompt(issue, signals)
    assert "bug(supervisor): SPIFFE crash" in prompt
    assert "SPIFFE sandboxes crash on restart" in prompt
    assert "#2571" in prompt or "2571" in prompt


def test_user_prompt_no_signals():
    issue = _make_issue()
    signals = IssueSignals(
        title_prefix=None,
        area_labels=[],
        topic_labels=[],
        state_label=None,
        issue_type=None,
    )
    prompt = build_user_prompt(issue, signals)
    assert "bug(supervisor): SPIFFE crash" in prompt
    assert "(none)" in prompt.lower() or "None" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/core/test_prompt.py -v`
Expected: FAIL — old `build_system_prompt` signature doesn't match

- [ ] **Step 3: Write prompt.py**

Replace the entire contents of `app/core/prompt.py` with:

```python
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
            parts.append(f"  @{c.get('user', 'unknown')}: {truncate_comment(c.get('body', ''))}")

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
        "Example: \"bug(supervisor): SPIFFE-enabled sandboxes crash\" — prefix",
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

    lines.extend([
        "",
        "SIGNAL 3 — Labels (when present): Area and topic labels are reliable",
        "when they exist, but are present on only ~3% of triage-needed issues.",
        "",
    ])

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

    lines = ["| Prefix / Area | Primary | Secondary |", "|---------------|---------|-----------|"]

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
            lines.append(f"\n- \"{ex['title']}\"")
            lines.append(f"  → {p.team_id}, {ex.get('urgency', 'medium')} — {ex.get('reasoning', '')}")

    lines.extend(["", "Prefix misleads (problem domain overrides code area):", ""])
    lines.append("- \"bug(supervisor): SPIFFE-enabled sandboxes crash on restart\"")
    lines.append("  → ai-safety (secondary: agent-ops), high — prefix says supervisor")
    lines.append("  (agent-ops) but the problem is SPIFFE identity security (ai-safety)")
    lines.append("")
    lines.append("- \"feat(cli): import externally issued OIDC tokens non-interactively\"")
    lines.append("  → acp (secondary: agent-ops), medium — prefix says cli (agent-ops)")
    lines.append("  but the problem is OIDC token management (acp)")
    lines.append("")
    lines.append("- \"docs(access-control): document required Keycloak protocol mappers\"")
    lines.append("  → acp, low — prefix says docs (agent-ops) but the content is")
    lines.append("  Keycloak auth infrastructure (acp)")

    lines.extend(["", "No team cares:"])
    for ex in repo_config.none_examples:
        lines.append(f"\n- \"{ex['title']}\"")
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
        '  "summary": "1-2 sentence issue summary",\n'
        '  "recommendation": "What the primary team should do"\n'
        "}\n\n"
        "IMPORTANT:\n"
        "- \"reasoning\" MUST come first — think before you classify\n"
        "- Choose \"none\" when no team clearly owns the area\n"
        "- If two teams are relevant, put the stronger match as primary\n"
        "- When in doubt on urgency, round DOWN"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/core/test_prompt.py -v`
Expected: all 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/prompt.py tests/core/test_prompt.py
git commit -m "feat: rewrite prompt construction for multi-team classification"
```

---

### Task 4: Confidence Rules

**Files:**
- Modify: `app/core/scoring.py`
- Rewrite: `tests/core/test_scoring.py`

**Interfaces:**
- Consumes: nothing (pure function with primitive inputs)
- Produces:
  - `apply_confidence_rules(primary_confidence: float, secondary_confidence: float | None, any_team_cares: bool, thresholds: dict[str, float]) -> str | None`

- [ ] **Step 1: Write the tests**

```python
# tests/core/test_scoring.py
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
        result = apply_confidence_rules(0.7, 0.3, True, THRESHOLDS)
        assert result is None

    def test_normal_no_secondary(self):
        result = apply_confidence_rules(0.7, None, True, THRESHOLDS)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/core/test_scoring.py -v`
Expected: FAIL — `ImportError: cannot import name 'apply_confidence_rules'`

- [ ] **Step 3: Write scoring.py**

Replace the entire contents of `app/core/scoring.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/core/test_scoring.py -v`
Expected: all 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/scoring.py tests/core/test_scoring.py
git commit -m "feat: replace 3-axis scoring with confidence rules"
```

---

### Task 5: Triage Engine

**Files:**
- Create: `app/core/triage_engine.py`
- Create: `tests/core/test_triage_engine.py`
- Delete: `app/core/assessment.py`
- Delete: `tests/core/test_assessment.py`

**Interfaces:**
- Consumes: `IssueData`, `IssueSignals`, `TriageResult`, `Urgency` from `app.core.models`; `RepoConfig` from `app.core.profiles`; `build_user_prompt` from `app.core.prompt`; `apply_confidence_rules` from `app.core.scoring`; `LLMClientProtocol` from `app.core.llm`
- Produces:
  - `extract_signals(issue: IssueData) -> IssueSignals`
  - `triage_issue(issue: IssueData, llm_client: LLMClientProtocol, model: str, repo_config: RepoConfig, system_prompt: str) -> TriageResult | None`

- [ ] **Step 1: Write the tests**

```python
# tests/core/test_triage_engine.py
import re
from unittest.mock import MagicMock

from app.core.models import IssueData, IssueSignals, Urgency
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
        llm = self._mock_llm({
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
        })
        result = triage_issue(
            _make_issue(title="feat(cli): add flag"),
            llm, "claude-sonnet-4-6", _make_repo_config(), "system prompt",
        )
        assert result is not None
        assert result.primary_team == "agent-ops"
        assert result.urgency == Urgency.MEDIUM
        assert result.any_team_cares is True

    def test_no_team_cares(self):
        llm = self._mock_llm({
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
        })
        result = triage_issue(
            _make_issue(title="feat(build): Bazel"),
            llm, "claude-sonnet-4-6", _make_repo_config(), "system prompt",
        )
        assert result is not None
        assert result.any_team_cares is False
        assert result.primary_team == "none"

    def test_llm_returns_none(self):
        llm = self._mock_llm(None)
        result = triage_issue(
            _make_issue(), llm, "claude-sonnet-4-6", _make_repo_config(), "system prompt",
        )
        assert result is None

    def test_multi_team_confidence_flag(self):
        llm = self._mock_llm({
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
        })
        result = triage_issue(
            _make_issue(), llm, "claude-sonnet-4-6", _make_repo_config(), "system prompt",
        )
        assert result is not None
        assert result.confidence_flag == "multi_team"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/core/test_triage_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.triage_engine'`

- [ ] **Step 3: Write triage_engine.py**

Create `app/core/triage_engine.py`:

```python
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.core.models import IssueSignals, TriageResult, Urgency
from app.core.prompt import build_user_prompt
from app.core.scoring import apply_confidence_rules

if TYPE_CHECKING:
    from app.core.llm import LLMClientProtocol
    from app.core.models import IssueData
    from app.core.profiles import RepoConfig

logger = logging.getLogger(__name__)

_PREFIX_RE = re.compile(r"^(?:feat|fix|bug|docs|chore|refactor|test|perf|ci)\(([^)]+)\):")
_TYPE_LABELS = {"Bug", "Improvement", "feature request"}


def extract_signals(issue: IssueData) -> IssueSignals:
    match = _PREFIX_RE.match(issue.title)
    title_prefix = match.group(1) if match else None

    area_labels = [l for l in issue.labels if l.startswith("area:")]
    topic_labels = [l for l in issue.labels if l.startswith("topic:")]
    state_labels = [l for l in issue.labels if l.startswith("state:")]
    state_label = state_labels[0] if state_labels else None
    type_labels = [l for l in issue.labels if l in _TYPE_LABELS]
    issue_type = type_labels[0] if type_labels else None

    return IssueSignals(
        title_prefix=title_prefix,
        area_labels=area_labels,
        topic_labels=topic_labels,
        state_label=state_label,
        issue_type=issue_type,
    )


def triage_issue(
    issue: IssueData,
    llm_client: LLMClientProtocol,
    model: str,
    repo_config: RepoConfig,
    system_prompt: str,
) -> TriageResult | None:
    signals = extract_signals(issue)
    user_prompt = build_user_prompt(issue, signals)

    response = llm_client.assess(system_prompt, user_prompt, model)
    if response is None:
        logger.warning(f"LLM returned None for #{issue.number}")
        return None

    try:
        urgency = Urgency(response["urgency"])
    except (KeyError, ValueError):
        logger.warning(f"Invalid urgency in response for #{issue.number}: {response.get('urgency')}")
        urgency = Urgency.LOW

    any_team_cares = response.get("any_team_cares", False)
    primary_confidence = float(response.get("primary_confidence", 0.0))
    secondary_confidence_raw = response.get("secondary_confidence")
    secondary_confidence = float(secondary_confidence_raw) if secondary_confidence_raw is not None else None

    confidence_flag = apply_confidence_rules(
        primary_confidence,
        secondary_confidence,
        any_team_cares,
        repo_config.confidence_thresholds,
    )

    if confidence_flag == "forced_none":
        any_team_cares = False

    return TriageResult(
        repo=issue.repo,
        issue_number=issue.number,
        issue_title=issue.title,
        issue_url=issue.url,
        reasoning=response.get("reasoning", ""),
        any_team_cares=any_team_cares,
        primary_team=response.get("primary_team", "none"),
        primary_confidence=primary_confidence,
        secondary_team=response.get("secondary_team"),
        secondary_confidence=secondary_confidence,
        urgency=urgency,
        urgency_reasoning=response.get("urgency_reasoning", ""),
        summary=response.get("summary", ""),
        recommendation=response.get("recommendation", ""),
        confidence_flag=confidence_flag,
        assessed_at=datetime.now(timezone.utc).isoformat(),
    )
```

- [ ] **Step 4: Delete old assessment files**

```bash
rm app/core/assessment.py tests/core/test_assessment.py
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/core/test_triage_engine.py -v`
Expected: all 15 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/triage_engine.py tests/core/test_triage_engine.py
git rm app/core/assessment.py tests/core/test_assessment.py
git commit -m "feat: create triage engine with signal extraction, replacing assessment module"
```

---

### Task 6: State Fix

**Files:**
- Modify: `app/state/tracker.py`
- Rewrite: `tests/state/test_tracker.py`

**Interfaces:**
- Consumes: nothing
- Produces: Same `StateTracker` API but with `seen_issues: set[str]` (namespaced `"repo#number"` keys) instead of `set[int]`

- [ ] **Step 1: Write the tests**

```python
# tests/state/test_tracker.py
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.state.tracker import StateTracker


@pytest.fixture()
def state_path(tmp_path):
    return tmp_path / "state.json"


@pytest.fixture()
def tracker(state_path):
    return StateTracker(state_path)


def test_default_state():
    state = StateTracker.default_state()
    assert isinstance(state["seen_issues"], set)
    assert len(state["seen_issues"]) == 0
    assert "last_checked" in state
    assert "digest_buffer" in state
    assert "seen_timestamps" in state


def test_default_state_lookback():
    state = StateTracker.default_state(lookback_hours=48)
    checked = datetime.fromisoformat(state["last_checked"])
    now = datetime.now(timezone.utc)
    assert (now - checked).total_seconds() >= 47 * 3600


def test_load_missing_file(tracker):
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)
    assert len(state["seen_issues"]) == 0


def test_save_and_load_namespaced(tracker):
    state = StateTracker.default_state()
    state["seen_issues"] = {"NVIDIA/OpenShell#2571", "NVIDIA/OpenShell#2588"}
    state["seen_timestamps"] = {
        "NVIDIA/OpenShell#2571": "2026-08-01T00:00:00Z",
        "NVIDIA/OpenShell#2588": "2026-08-01T01:00:00Z",
    }
    tracker.save(state)
    loaded = tracker.load()
    assert loaded["seen_issues"] == {"NVIDIA/OpenShell#2571", "NVIDIA/OpenShell#2588"}
    assert "NVIDIA/OpenShell#2571" in loaded["seen_timestamps"]


def test_load_corrupted_file(state_path, tracker):
    state_path.write_text("not json")
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)
    assert len(state["seen_issues"]) == 0


def test_prune_old_issues():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=60)).isoformat()
    recent = (now - timedelta(days=5)).isoformat()

    state = {
        "seen_issues": {"NVIDIA/OpenShell#100", "NVIDIA/OpenShell#200"},
        "seen_timestamps": {
            "NVIDIA/OpenShell#100": old,
            "NVIDIA/OpenShell#200": recent,
        },
    }
    pruned = StateTracker.prune_seen(state)
    assert "NVIDIA/OpenShell#100" not in pruned["seen_issues"]
    assert "NVIDIA/OpenShell#200" in pruned["seen_issues"]


def test_save_creates_parent_dirs(tmp_path):
    deep_path = tmp_path / "a" / "b" / "state.json"
    tracker = StateTracker(deep_path)
    state = StateTracker.default_state()
    tracker.save(state)
    assert deep_path.exists()


def test_seen_issues_serialized_as_list(state_path, tracker):
    state = StateTracker.default_state()
    state["seen_issues"] = {"NVIDIA/OpenShell#1", "NVIDIA/OpenShell#2"}
    tracker.save(state)
    raw = json.loads(state_path.read_text())
    assert isinstance(raw["seen_issues"], list)
    assert sorted(raw["seen_issues"]) == ["NVIDIA/OpenShell#1", "NVIDIA/OpenShell#2"]


def test_migrate_legacy_int_keys(state_path, tracker):
    """Legacy state files used bare int keys. They should be loaded and preserved as-is."""
    legacy = {
        "last_checked": "2026-08-01T00:00:00Z",
        "seen_issues": [100, 200, 300],
        "digest_buffer": [],
        "seen_timestamps": {"100": "2026-08-01T00:00:00Z"},
    }
    state_path.write_text(json.dumps(legacy))
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)
    assert all(isinstance(x, (int, str)) for x in state["seen_issues"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/state/test_tracker.py -v`
Expected: some tests FAIL due to new namespaced key expectations

- [ ] **Step 3: Update tracker.py**

The existing `tracker.py` works with `set[int]`. The changes are minimal — the `load()` and `save()` methods need to handle string keys, and `prune_seen()` needs to work with string keys. The core logic is the same.

Replace the entire contents of `app/state/tracker.py` with:

```python
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class StateTracker:
    def __init__(self, state_path: Path, lookback_hours: int = 24):
        self._path = state_path
        self._lookback_hours = lookback_hours

    def load(self) -> dict:
        if not self._path.exists():
            logger.info("No state file found, using defaults")
            return self.default_state(lookback_hours=self._lookback_hours)

        try:
            with open(self._path) as f:
                raw = json.load(f)
            seen_list = raw.get("seen_issues", [])
            raw["seen_issues"] = set(str(x) for x in seen_list)
            return raw
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Corrupted state file, using defaults: {e}")
            return self.default_state()

    def save(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            **state,
            "seen_issues": sorted(str(x) for x in state.get("seen_issues", set())),
        }
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(serializable, f, indent=2)
        os.replace(tmp, self._path)

    @staticmethod
    def default_state(lookback_hours: int = 24) -> dict:
        last_checked = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        return {
            "last_checked": last_checked.isoformat(),
            "seen_issues": set(),
            "digest_buffer": [],
            "seen_timestamps": {},
        }

    @staticmethod
    def prune_seen(state: dict, max_age_days: int = 30) -> dict:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max_age_days)
        timestamps = state.get("seen_timestamps", {})

        kept = set()
        kept_timestamps = {}
        for issue_id in state["seen_issues"]:
            key = str(issue_id)
            ts_str = timestamps.get(key)
            if ts_str:
                ts = datetime.fromisoformat(ts_str)
                if ts > cutoff:
                    kept.add(key)
                    kept_timestamps[key] = ts_str
            else:
                kept.add(key)
                kept_timestamps[key] = now.isoformat()

        pruned_count = len(state["seen_issues"]) - len(kept)
        if pruned_count > 0:
            logger.info(f"Pruned {pruned_count} issues older than {max_age_days} days")

        state["seen_issues"] = kept
        state["seen_timestamps"] = kept_timestamps
        return state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/state/test_tracker.py -v`
Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/state/tracker.py tests/state/test_tracker.py
git commit -m "fix: namespace seen_issues keys as repo#number to prevent multi-repo collisions"
```

---

### Task 7: Notification Architecture

**Files:**
- Create: `app/notifications/adapter.py`
- Create: `app/notifications/router.py`
- Create: `app/notifications/slack_webhook.py`
- Modify: `app/notifications/log.py`
- Delete: `app/notifications/notifier.py`
- Delete: `app/notifications/slack.py`
- Create: `tests/notifications/test_router.py`
- Create: `tests/notifications/test_slack_webhook.py`
- Rewrite: `tests/notifications/test_log.py`
- Delete: `tests/notifications/test_slack.py`

**Interfaces:**
- Consumes: `TriageResult`, `Urgency` from `app.core.models`
- Produces:
  - `NotificationAdapter(Protocol)` with methods `deliver_immediate(result, channel_config)`, `deliver_digest(results, channel_config)`, `collect_feedback()`
  - `FeedbackEvent` dataclass
  - `ChannelConfig` dataclass
  - `TeamNotificationConfig` dataclass
  - `NotificationRouter` class with `route(result)` and `send_digest(results)`
  - `SlackWebhookAdapter` class
  - `LogAdapter` class

- [ ] **Step 1: Write adapter.py**

Create `app/notifications/adapter.py`:

```python
from dataclasses import dataclass
from typing import Protocol

from app.core.models import TriageResult


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

- [ ] **Step 2: Write router.py and its tests**

Create `tests/notifications/test_router.py`:

```python
from unittest.mock import MagicMock

from app.core.models import TriageResult, Urgency
from app.notifications.adapter import ChannelConfig, TeamNotificationConfig
from app.notifications.router import NotificationRouter


def _make_result(primary_team="agent-ops", secondary_team=None, urgency=Urgency.HIGH, any_team_cares=True):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=2571,
        issue_title="test issue",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2571",
        reasoning="test",
        any_team_cares=any_team_cares,
        primary_team=primary_team,
        primary_confidence=0.9,
        secondary_team=secondary_team,
        secondary_confidence=0.7 if secondary_team else None,
        urgency=urgency,
        urgency_reasoning="test",
        summary="test",
        recommendation="test",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00Z",
    )


def _make_team_config(team_id, immediate_on=None, receive_secondary=True, secondary_min_urgency="high"):
    return TeamNotificationConfig(
        team_id=team_id,
        receive_secondary=receive_secondary,
        secondary_min_urgency=secondary_min_urgency,
        channels=[
            ChannelConfig(adapter_type="mock", config={}, immediate_on=immediate_on or ["critical", "high"]),
        ],
    )


def test_route_delivers_immediate_for_high():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={"agent-ops": _make_team_config("agent-ops")},
        adapters={"mock": adapter},
    )
    result = _make_result(urgency=Urgency.HIGH)
    router.route(result)
    adapter.deliver_immediate.assert_called_once()


def test_route_skips_medium_urgency():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={"agent-ops": _make_team_config("agent-ops")},
        adapters={"mock": adapter},
    )
    result = _make_result(urgency=Urgency.MEDIUM)
    router.route(result)
    adapter.deliver_immediate.assert_not_called()


def test_route_skips_when_no_team_cares():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={"agent-ops": _make_team_config("agent-ops")},
        adapters={"mock": adapter},
    )
    result = _make_result(any_team_cares=False)
    router.route(result)
    adapter.deliver_immediate.assert_not_called()


def test_route_delivers_to_secondary_team():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={
            "ai-safety": _make_team_config("ai-safety"),
            "agent-ops": _make_team_config("agent-ops", receive_secondary=True, secondary_min_urgency="high"),
        },
        adapters={"mock": adapter},
    )
    result = _make_result(primary_team="ai-safety", secondary_team="agent-ops", urgency=Urgency.HIGH)
    router.route(result)
    assert adapter.deliver_immediate.call_count == 2


def test_route_skips_secondary_when_not_configured():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={
            "ai-safety": _make_team_config("ai-safety"),
            "agentdev": _make_team_config("agentdev", receive_secondary=False),
        },
        adapters={"mock": adapter},
    )
    result = _make_result(primary_team="ai-safety", secondary_team="agentdev", urgency=Urgency.HIGH)
    router.route(result)
    assert adapter.deliver_immediate.call_count == 1


def test_route_skips_secondary_below_min_urgency():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={
            "ai-safety": _make_team_config("ai-safety"),
            "agent-ops": _make_team_config("agent-ops", secondary_min_urgency="critical"),
        },
        adapters={"mock": adapter},
    )
    result = _make_result(primary_team="ai-safety", secondary_team="agent-ops", urgency=Urgency.HIGH)
    router.route(result)
    assert adapter.deliver_immediate.call_count == 1


def test_send_digest_groups_by_team():
    adapter = MagicMock()
    router = NotificationRouter(
        team_configs={
            "agent-ops": _make_team_config("agent-ops"),
            "acp": _make_team_config("acp"),
        },
        adapters={"mock": adapter},
    )
    results = [
        _make_result(primary_team="agent-ops", urgency=Urgency.MEDIUM),
        _make_result(primary_team="agent-ops", urgency=Urgency.LOW),
        _make_result(primary_team="acp", urgency=Urgency.MEDIUM),
    ]
    router.send_digest(results)
    assert adapter.deliver_digest.call_count == 2
```

Create `app/notifications/router.py`:

```python
import logging

from app.core.models import TriageResult
from app.notifications.adapter import NotificationAdapter, TeamNotificationConfig

logger = logging.getLogger(__name__)

URGENCY_ORDER = ["critical", "high", "medium", "low"]


class NotificationRouter:
    def __init__(
        self,
        team_configs: dict[str, TeamNotificationConfig],
        adapters: dict[str, NotificationAdapter],
    ):
        self.team_configs = team_configs
        self.adapters = adapters

    def route(self, result: TriageResult) -> None:
        if not result.any_team_cares:
            return

        primary_config = self.team_configs.get(result.primary_team)
        if primary_config:
            self._deliver_to_team(result, primary_config)

        if result.secondary_team:
            secondary_config = self.team_configs.get(result.secondary_team)
            if secondary_config and secondary_config.receive_secondary:
                min_urg = secondary_config.secondary_min_urgency or "low"
                if URGENCY_ORDER.index(result.urgency.value) <= URGENCY_ORDER.index(min_urg):
                    self._deliver_to_team(result, secondary_config)

    def send_digest(self, results: list[TriageResult]) -> None:
        grouped: dict[str, list[TriageResult]] = {}
        for r in results:
            if r.any_team_cares:
                grouped.setdefault(r.primary_team, []).append(r)

        for team_id, team_results in grouped.items():
            config = self.team_configs.get(team_id)
            if not config:
                continue
            for channel in config.channels:
                adapter = self.adapters.get(channel.adapter_type)
                if adapter:
                    adapter.deliver_digest(team_results, channel.config)

    def _deliver_to_team(self, result: TriageResult, config: TeamNotificationConfig) -> None:
        for channel in config.channels:
            adapter = self.adapters.get(channel.adapter_type)
            if not adapter:
                continue
            if result.urgency.value in channel.immediate_on:
                adapter.deliver_immediate(result, channel.config)
```

- [ ] **Step 3: Write slack_webhook.py and its tests**

Create `tests/notifications/test_slack_webhook.py`:

```python
from unittest.mock import MagicMock, patch

from app.core.models import TriageResult, Urgency
from app.notifications.slack_webhook import SlackWebhookAdapter


def _make_result(urgency=Urgency.HIGH, secondary_team=None):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=2571,
        issue_title="bug(supervisor): SPIFFE crash",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2571",
        reasoning="Security issue",
        any_team_cares=True,
        primary_team="ai-safety",
        primary_confidence=0.85,
        secondary_team=secondary_team,
        secondary_confidence=0.7 if secondary_team else None,
        urgency=urgency,
        urgency_reasoning="Regression",
        summary="SPIFFE sandboxes crash on restart",
        recommendation="Investigate SPIFFE lifecycle",
        confidence_flag=None,
        assessed_at="2026-08-01T00:00:00Z",
    )


@patch("app.notifications.slack_webhook.requests")
def test_deliver_immediate(mock_requests):
    adapter = SlackWebhookAdapter()
    config = {"webhook_url": "https://hooks.slack.com/test"}
    adapter.deliver_immediate(_make_result(), config)
    mock_requests.post.assert_called_once()
    payload = mock_requests.post.call_args[1]["json"]
    assert "SPIFFE" in payload["text"] or any("SPIFFE" in str(b) for b in payload.get("blocks", []))


@patch("app.notifications.slack_webhook.requests")
def test_deliver_digest(mock_requests):
    adapter = SlackWebhookAdapter()
    config = {"webhook_url": "https://hooks.slack.com/test"}
    results = [_make_result(urgency=Urgency.MEDIUM), _make_result(urgency=Urgency.LOW)]
    adapter.deliver_digest(results, config)
    mock_requests.post.assert_called_once()


@patch("app.notifications.slack_webhook.requests")
def test_deliver_immediate_with_secondary(mock_requests):
    adapter = SlackWebhookAdapter()
    config = {"webhook_url": "https://hooks.slack.com/test"}
    adapter.deliver_immediate(_make_result(secondary_team="agent-ops"), config)
    mock_requests.post.assert_called_once()
    payload = mock_requests.post.call_args[1]["json"]
    text = str(payload)
    assert "agent-ops" in text.lower() or "Agent Ops" in text


def test_collect_feedback_returns_empty():
    adapter = SlackWebhookAdapter()
    assert adapter.collect_feedback() == []
```

Create `app/notifications/slack_webhook.py`:

```python
import logging

import requests

from app.core.models import TriageResult

logger = logging.getLogger(__name__)

URGENCY_EMOJI = {
    "critical": "\U0001f534",
    "high": "\U0001f7e0",
    "medium": "\U0001f7e1",
    "low": "\U0001f535",
}


class SlackWebhookAdapter:
    def deliver_immediate(self, result: TriageResult, channel_config: dict) -> None:
        emoji = URGENCY_EMOJI.get(result.urgency.value, "")
        text = f"{emoji} {result.urgency.value.upper()} — Routed to: {result.primary_team}"
        if result.secondary_team:
            text += f"\nAlso relevant to: {result.secondary_team}"
        text += f"\n\n#{result.issue_number}: {result.issue_title}"
        text += f"\n\nSummary: {result.summary}"
        text += f"\n\nRecommendation: {result.recommendation}"
        text += f"\n\n\U0001f517 {result.issue_url}"

        self._post(channel_config.get("webhook_url", ""), {"text": text})

    def deliver_digest(self, results: list[TriageResult], channel_config: dict) -> None:
        if not results:
            return
        team = results[0].primary_team
        lines = [f"\U0001f4cb Daily Triage Digest — {team} ({len(results)} issues)\n"]
        for r in results:
            lines.append(f"• #{r.issue_number} {r.issue_title} — {r.urgency.value}")
            lines.append(f"  {r.summary}")
        self._post(channel_config.get("webhook_url", ""), {"text": "\n".join(lines)})

    def collect_feedback(self) -> list:
        return []

    def _post(self, webhook_url: str, payload: dict) -> None:
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
        except Exception:
            logger.exception(f"Slack webhook post failed: {webhook_url}")
```

- [ ] **Step 4: Rewrite log.py and its tests**

Rewrite `tests/notifications/test_log.py`:

```python
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


def test_log_adapter_collect_feedback():
    adapter = LogAdapter()
    assert adapter.collect_feedback() == []
```

Replace the entire contents of `app/notifications/log.py` with:

```python
import logging

from app.core.models import TriageResult

logger = logging.getLogger(__name__)


class LogAdapter:
    def deliver_immediate(self, result: TriageResult, channel_config: dict) -> None:
        print(
            f"[IMMEDIATE] #{result.issue_number} → {result.primary_team} "
            f"({result.urgency.value}): {result.issue_title}"
        )
        print(f"  Summary: {result.summary}")
        print(f"  Recommendation: {result.recommendation}")
        if result.secondary_team:
            print(f"  Also relevant to: {result.secondary_team}")

    def deliver_digest(self, results: list[TriageResult], channel_config: dict) -> None:
        if not results:
            print("[DIGEST] 0 issues")
            return
        team = results[0].primary_team
        print(f"[DIGEST] {team}: {len(results)} issues")
        for r in sorted(results, key=lambda x: x.urgency.value):
            print(f"  #{r.issue_number} {r.issue_title} — {r.urgency.value}")

    def collect_feedback(self) -> list:
        return []
```

- [ ] **Step 5: Delete old notification files**

```bash
rm app/notifications/notifier.py app/notifications/slack.py tests/notifications/test_slack.py
```

- [ ] **Step 6: Run all notification tests**

Run: `python3 -m pytest tests/notifications/ -v`
Expected: all tests PASS across test_router.py, test_slack_webhook.py, test_log.py

- [ ] **Step 7: Commit**

```bash
git add app/notifications/ tests/notifications/
git rm app/notifications/notifier.py app/notifications/slack.py tests/notifications/test_slack.py
git commit -m "feat: build notification architecture with adapter protocol, router, and webhook adapter"
```

---

### Task 8: Orchestrator Rewrite

**Files:**
- Modify: `app/triage.py`
- Modify: `app/config.py`
- Modify: `app/__main__.py`
- Modify: `app/state/assessment_log.py`
- Rewrite: `tests/integration/test_triage.py`
- Rewrite: `tests/test_main.py`
- Rewrite: `tests/test_factories.py`
- Rewrite: `tests/test_fixtures.py`

**Interfaces:**
- Consumes: everything from Tasks 1-7
- Produces:
  - `run_triage(config: TriageConfig) -> None`
  - `run_review(config: TriageConfig, *, since_hours, verdict_filter) -> None`
  - `run_digest(config: TriageConfig) -> None`
  - Updated `TriageConfig` with `profiles_dir` (already exists) and env var interpolation
  - Updated `assessment_log` functions for TriageResult

- [ ] **Step 1: Update assessment_log.py for TriageResult**

Replace the entire contents of `app/state/assessment_log.py` with:

```python
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.models import TriageResult, Urgency

logger = logging.getLogger(__name__)


def result_to_record(result: TriageResult) -> dict:
    return {
        "repo": result.repo,
        "issue_number": result.issue_number,
        "issue_title": result.issue_title,
        "issue_url": result.issue_url,
        "reasoning": result.reasoning,
        "any_team_cares": result.any_team_cares,
        "primary_team": result.primary_team,
        "primary_confidence": result.primary_confidence,
        "secondary_team": result.secondary_team,
        "secondary_confidence": result.secondary_confidence,
        "urgency": result.urgency.value,
        "urgency_reasoning": result.urgency_reasoning,
        "summary": result.summary,
        "recommendation": result.recommendation,
        "confidence_flag": result.confidence_flag,
        "assessed_at": result.assessed_at,
    }


def append_result(log_path: Path, result: TriageResult) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = result_to_record(result)
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def read_results(
    log_path: Path,
    *,
    since_hours: int | None = None,
    team_filter: str | None = None,
    urgency_filter: str | None = None,
) -> list[dict]:
    if not log_path.exists():
        return []

    cutoff = None
    if since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    records = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if cutoff:
                try:
                    assessed = datetime.fromisoformat(record["assessed_at"])
                    if assessed < cutoff:
                        continue
                except (KeyError, ValueError):
                    continue

            if team_filter and record.get("primary_team") != team_filter:
                continue
            if urgency_filter and record.get("urgency") != urgency_filter:
                continue

            records.append(record)
    return records


def format_review(records: list[dict]) -> str:
    if not records:
        return "No results found."

    lines = [f"Triage Review — {len(records)} results\n"]

    grouped: dict[str, list[dict]] = {}
    for r in records:
        team = r.get("primary_team", "unknown")
        grouped.setdefault(team, []).append(r)

    for team, team_records in sorted(grouped.items()):
        lines.append(f"\n--- {team} ({len(team_records)} issues) ---")
        for r in team_records:
            urgency = r.get("urgency", "?")
            lines.append(
                f"  #{r.get('issue_number', '?')} [{urgency}] {r.get('issue_title', '?')}"
            )
            lines.append(f"    {r.get('summary', '')}")
            if r.get("recommendation"):
                lines.append(f"    → {r['recommendation']}")

    return "\n".join(lines)
```

- [ ] **Step 2: Write tests for assessment_log**

Replace `tests/state/test_assessment_log.py`:

```python
import json
from datetime import datetime, timedelta, timezone

from app.core.models import TriageResult, Urgency
from app.state.assessment_log import append_result, format_review, read_results, result_to_record


def _make_result(**overrides) -> TriageResult:
    defaults = {
        "repo": "NVIDIA/OpenShell",
        "issue_number": 2571,
        "issue_title": "bug(supervisor): SPIFFE crash",
        "issue_url": "https://github.com/NVIDIA/OpenShell/issues/2571",
        "reasoning": "Security issue",
        "any_team_cares": True,
        "primary_team": "ai-safety",
        "primary_confidence": 0.85,
        "secondary_team": "agent-ops",
        "secondary_confidence": 0.65,
        "urgency": Urgency.HIGH,
        "urgency_reasoning": "Regression",
        "summary": "SPIFFE crash",
        "recommendation": "Investigate",
        "confidence_flag": None,
        "assessed_at": datetime.now(timezone.utc).isoformat(),
    }
    defaults.update(overrides)
    return TriageResult(**defaults)


def test_result_to_record():
    result = _make_result()
    record = result_to_record(result)
    assert record["primary_team"] == "ai-safety"
    assert record["urgency"] == "high"
    assert record["secondary_team"] == "agent-ops"


def test_append_result_creates_file(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result())
    assert log.exists()
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["issue_number"] == 2571


def test_append_result_appends(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result(issue_number=1))
    append_result(log, _make_result(issue_number=2))
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 2


def test_read_results_no_file(tmp_path):
    assert read_results(tmp_path / "missing.jsonl") == []


def test_read_results_all(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result(issue_number=1))
    append_result(log, _make_result(issue_number=2))
    records = read_results(log)
    assert len(records) == 2


def test_read_results_team_filter(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result(primary_team="ai-safety"))
    append_result(log, _make_result(primary_team="agent-ops"))
    records = read_results(log, team_filter="ai-safety")
    assert len(records) == 1
    assert records[0]["primary_team"] == "ai-safety"


def test_read_results_urgency_filter(tmp_path):
    log = tmp_path / "results.jsonl"
    append_result(log, _make_result(urgency=Urgency.HIGH))
    append_result(log, _make_result(urgency=Urgency.LOW))
    records = read_results(log, urgency_filter="high")
    assert len(records) == 1


def test_read_results_since_filter(tmp_path):
    log = tmp_path / "results.jsonl"
    old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    append_result(log, _make_result(assessed_at=old_time))
    append_result(log, _make_result())
    records = read_results(log, since_hours=24)
    assert len(records) == 1


def test_format_review_empty():
    assert "No results" in format_review([])


def test_format_review_groups_by_team():
    records = [
        result_to_record(_make_result(primary_team="ai-safety")),
        result_to_record(_make_result(primary_team="agent-ops")),
    ]
    output = format_review(records)
    assert "ai-safety" in output
    assert "agent-ops" in output
```

- [ ] **Step 3: Rewrite triage.py**

Replace the entire contents of `app/triage.py`:

```python
import logging
import os
import re
from datetime import datetime, timezone

from app.config import TriageConfig
from app.core.llm import create_llm_client, resolve_model
from app.core.profiles import load_repo_config
from app.core.prompt import build_system_prompt
from app.core.triage_engine import triage_issue
from app.notifications.adapter import ChannelConfig, TeamNotificationConfig
from app.notifications.log import LogAdapter
from app.notifications.router import NotificationRouter
from app.notifications.slack_webhook import SlackWebhookAdapter
from app.sources.github import GitHubSource
from app.state.assessment_log import append_result, format_review, read_results
from app.state.tracker import StateTracker

logger = logging.getLogger(__name__)


def _build_llm_client(config: TriageConfig):
    if config.llm_provider == "anthropic":
        return create_llm_client("anthropic", api_key=config.anthropic_api_key)
    return create_llm_client(
        "vertex",
        project_id=config.vertex_project_id,
        region=config.vertex_region,
    )


def _resolve_env_vars(value: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), value)


def _build_notification_router(repo_config) -> NotificationRouter:
    adapters = {"slack_webhook": SlackWebhookAdapter(), "log": LogAdapter()}
    team_configs = {}

    for profile in repo_config.team_profiles:
        notif = profile.notifications
        channels = []
        for ch in notif.get("channels", []):
            ch_config = {k: _resolve_env_vars(v) if isinstance(v, str) else v for k, v in ch.get("config", {}).items()}
            channels.append(ChannelConfig(
                adapter_type=ch["adapter"],
                config=ch_config,
                immediate_on=ch.get("immediate_on", []),
            ))
        team_configs[profile.team_id] = TeamNotificationConfig(
            team_id=profile.team_id,
            receive_secondary=notif.get("receive_secondary", False),
            secondary_min_urgency=notif.get("secondary_min_urgency"),
            channels=channels,
        )

    return NotificationRouter(team_configs=team_configs, adapters=adapters)


def run_triage(config: TriageConfig) -> None:
    tracker = StateTracker(config.state_path, config.default_lookback_hours)
    state = tracker.load()

    repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
    system_prompt = build_system_prompt(repo_config)
    router = _build_notification_router(repo_config)

    llm_client = _build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)

    source = GitHubSource(config.github_token)
    new_issues = source.fetch_new_issues(
        config.watch_repos,
        state["last_checked"],
        state["seen_issues"],
    )

    logger.info(f"Found {len(new_issues)} new issues")

    for issue in new_issues:
        result = triage_issue(issue, llm_client, model, repo_config, system_prompt)
        if result is None:
            continue

        append_result(config.assessment_log_path, result)
        router.route(result)

        seen_key = f"{issue.repo}#{issue.number}"
        state["seen_issues"].add(seen_key)
        state["seen_timestamps"][seen_key] = datetime.now(timezone.utc).isoformat()

    state["last_checked"] = datetime.now(timezone.utc).isoformat()
    StateTracker.prune_seen(state)
    tracker.save(state)


def run_review(
    config: TriageConfig,
    *,
    since_hours: int | None = None,
    team_filter: str | None = None,
) -> None:
    records = read_results(
        config.assessment_log_path,
        since_hours=since_hours,
        team_filter=team_filter,
    )
    print(format_review(records))


def run_digest(config: TriageConfig) -> None:
    tracker = StateTracker(config.state_path)
    state = tracker.load()

    last_digest = state.get("last_digest")
    since_hours = 24
    if last_digest:
        try:
            last_dt = datetime.fromisoformat(last_digest)
            delta = datetime.now(timezone.utc) - last_dt
            since_hours = max(1, int(delta.total_seconds() / 3600))
        except ValueError:
            pass

    records = read_results(config.assessment_log_path, since_hours=since_hours)
    medium_low = [r for r in records if r.get("urgency") in ("medium", "low")]

    if medium_low:
        from app.core.models import TriageResult, Urgency
        results = []
        for r in medium_low:
            results.append(TriageResult(
                repo=r["repo"],
                issue_number=r["issue_number"],
                issue_title=r["issue_title"],
                issue_url=r["issue_url"],
                reasoning=r.get("reasoning", ""),
                any_team_cares=r.get("any_team_cares", True),
                primary_team=r.get("primary_team", "unknown"),
                primary_confidence=r.get("primary_confidence", 0.0),
                secondary_team=r.get("secondary_team"),
                secondary_confidence=r.get("secondary_confidence"),
                urgency=Urgency(r["urgency"]),
                urgency_reasoning=r.get("urgency_reasoning", ""),
                summary=r.get("summary", ""),
                recommendation=r.get("recommendation", ""),
                confidence_flag=r.get("confidence_flag"),
                assessed_at=r.get("assessed_at", ""),
            ))

        repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
        router = _build_notification_router(repo_config)
        router.send_digest(results)

    state["last_digest"] = datetime.now(timezone.utc).isoformat()
    tracker.save(state)
```

- [ ] **Step 4: Update __main__.py**

Replace the entire contents of `app/__main__.py`:

```python
import argparse
import logging

from app.config import load_config
from app.triage import run_digest, run_review, run_triage


def main():
    parser = argparse.ArgumentParser(description="Team issue triage agent")
    parser.add_argument(
        "--mode",
        choices=["triage", "digest", "review"],
        default="triage",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--since", type=int, default=None)
    parser.add_argument("--team", type=str, default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    config = load_config()

    if args.mode == "review":
        run_review(config, since_hours=args.since, team_filter=args.team)
    elif args.mode == "digest":
        run_digest(config)
    else:
        run_triage(config)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Write integration tests**

Replace `tests/integration/test_triage.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import TriageConfig, load_config
from app.triage import run_triage


@pytest.fixture()
def config(tmp_path):
    return TriageConfig(
        watch_repos=["NVIDIA/OpenShell"],
        llm_provider="vertex",
        llm_model=None,
        vertex_project_id="test-project",
        vertex_region="us-east5",
        anthropic_api_key=None,
        github_token="ghp_test",
        slack_webhook_url=None,
        state_path=tmp_path / "state.json",
        assessment_log_path=tmp_path / "assessments.jsonl",
        profiles_dir=Path(__file__).parent.parent.parent / "profiles",
        default_lookback_hours=24,
    )


def test_load_config_from_env():
    env = {
        "GITHUB_TOKEN": "ghp_test",
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-test",
        "STATE_PATH": "/tmp/state.json",
    }
    with patch.dict("os.environ", env, clear=False):
        config = load_config()
    assert config.github_token == "ghp_test"
    assert config.llm_provider == "anthropic"


def test_run_triage_no_new_issues(config):
    with (
        patch("app.triage.GitHubSource") as mock_source_cls,
        patch("app.triage.create_llm_client") as mock_llm_factory,
    ):
        mock_source = MagicMock()
        mock_source.fetch_new_issues.return_value = []
        mock_source_cls.return_value = mock_source
        mock_llm_factory.return_value = MagicMock()

        run_triage(config)

        mock_source.fetch_new_issues.assert_called_once()
        assert config.state_path.exists()


def test_run_triage_with_classification(config):
    from app.core.models import IssueData

    mock_issue = IssueData(
        repo="NVIDIA/OpenShell",
        number=2571,
        title="bug(supervisor): SPIFFE crash",
        body="SPIFFE sandboxes crash on restart",
        labels=["Bug"],
        comments=[],
        url="https://github.com/NVIDIA/OpenShell/issues/2571",
        created_at="2026-08-01T00:00:00Z",
    )

    with (
        patch("app.triage.GitHubSource") as mock_source_cls,
        patch("app.triage.create_llm_client") as mock_llm_factory,
    ):
        mock_source = MagicMock()
        mock_source.fetch_new_issues.return_value = [mock_issue]
        mock_source_cls.return_value = mock_source

        mock_llm = MagicMock()
        mock_llm.assess.return_value = {
            "reasoning": "SPIFFE is security",
            "any_team_cares": True,
            "primary_team": "ai-safety",
            "primary_confidence": 0.85,
            "secondary_team": "agent-ops",
            "secondary_confidence": 0.65,
            "urgency": "high",
            "urgency_reasoning": "Security crash",
            "summary": "SPIFFE crash",
            "recommendation": "Investigate",
        }
        mock_llm_factory.return_value = mock_llm

        run_triage(config)

        assert config.assessment_log_path.exists()
        records = json.loads(config.assessment_log_path.read_text().strip())
        assert records["primary_team"] == "ai-safety"

        state = json.loads(config.state_path.read_text())
        assert "NVIDIA/OpenShell#2571" in state["seen_issues"]
```

- [ ] **Step 6: Write test_main.py**

Replace `tests/test_main.py`:

```python
from unittest.mock import MagicMock, patch


@patch("app.__main__.run_triage")
@patch("app.__main__.load_config")
def test_main_default_mode(mock_config, mock_triage):
    mock_config.return_value = MagicMock()
    from app.__main__ import main
    with patch("sys.argv", ["app"]):
        main()
    mock_triage.assert_called_once()


@patch("app.__main__.run_review")
@patch("app.__main__.load_config")
def test_main_review_mode(mock_config, mock_review):
    mock_config.return_value = MagicMock()
    from app.__main__ import main
    with patch("sys.argv", ["app", "--mode", "review"]):
        main()
    mock_review.assert_called_once()


@patch("app.__main__.run_digest")
@patch("app.__main__.load_config")
def test_main_digest_mode(mock_config, mock_digest):
    mock_config.return_value = MagicMock()
    from app.__main__ import main
    with patch("sys.argv", ["app", "--mode", "digest"]):
        main()
    mock_digest.assert_called_once()


@patch("app.__main__.run_review")
@patch("app.__main__.load_config")
def test_main_review_with_filters(mock_config, mock_review):
    mock_config.return_value = MagicMock()
    from app.__main__ import main
    with patch("sys.argv", ["app", "--mode", "review", "--since", "48", "--team", "agent-ops"]):
        main()
    mock_review.assert_called_once_with(
        mock_config.return_value,
        since_hours=48,
        team_filter="agent-ops",
    )
```

- [ ] **Step 7: Write test_factories.py**

Replace `tests/test_factories.py`:

```python
from pathlib import Path
from unittest.mock import patch

from app.config import TriageConfig
from app.triage import _build_llm_client


def _make_config(tmp_path, **overrides):
    defaults = {
        "watch_repos": ["NVIDIA/OpenShell"],
        "llm_provider": "vertex",
        "llm_model": None,
        "vertex_project_id": "test-project",
        "vertex_region": "us-east5",
        "anthropic_api_key": None,
        "github_token": "ghp_test",
        "slack_webhook_url": None,
        "state_path": tmp_path / "state.json",
        "assessment_log_path": tmp_path / "assessments.jsonl",
        "profiles_dir": Path(__file__).parent.parent / "profiles",
        "default_lookback_hours": 24,
    }
    defaults.update(overrides)
    return TriageConfig(**defaults)


def test_build_llm_client_vertex(tmp_path):
    config = _make_config(tmp_path, llm_provider="vertex")
    with patch("app.triage.create_llm_client") as mock_create:
        _build_llm_client(config)
        mock_create.assert_called_once_with("vertex", project_id="test-project", region="us-east5")


def test_build_llm_client_anthropic(tmp_path):
    config = _make_config(tmp_path, llm_provider="anthropic", anthropic_api_key="sk-test")
    with patch("app.triage.create_llm_client") as mock_create:
        _build_llm_client(config)
        mock_create.assert_called_once_with("anthropic", api_key="sk-test")
```

- [ ] **Step 8: Write test_fixtures.py**

Replace `tests/test_fixtures.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock

from app.core.models import IssueData
from app.core.triage_engine import extract_signals

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def _fixture_to_issue_data(data: dict) -> IssueData:
    return IssueData(
        repo="NVIDIA/OpenShell",
        number=data["number"],
        title=data["title"],
        body=data["body"],
        labels=data.get("labels", []),
        comments=data.get("comments", []),
        url=data["url"],
        created_at=data["created_at"],
    )


def test_fixture_creates_valid_issue_data():
    data = _load_fixture("protobuf_sync_failure.json")
    issue = _fixture_to_issue_data(data)
    assert issue.number == 2401
    assert "protobuf" in issue.title.lower()


def test_protobuf_fixture_signals():
    data = _load_fixture("protobuf_sync_failure.json")
    issue = _fixture_to_issue_data(data)
    signals = extract_signals(issue)
    assert signals.title_prefix is None  # no conventional commit prefix
    assert "area/sdk" not in signals.area_labels  # area/sdk, not area:sdk


def test_helm_fixture_signals():
    data = _load_fixture("helm_chart_regression.json")
    issue = _fixture_to_issue_data(data)
    signals = extract_signals(issue)
    assert signals.title_prefix is None


def test_tui_fixture_signals():
    data = _load_fixture("tui_styling_issue.json")
    issue = _fixture_to_issue_data(data)
    signals = extract_signals(issue)
    assert signals.title_prefix is None


def test_scc_fixture_signals():
    data = _load_fixture("openshift_scc_bug.json")
    issue = _fixture_to_issue_data(data)
    signals = extract_signals(issue)
    assert signals.title_prefix is None
```

- [ ] **Step 9: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: ALL tests pass

- [ ] **Step 10: Run lint**

Run: `make lint`
Expected: no errors

- [ ] **Step 11: Commit**

```bash
git add app/triage.py app/config.py app/__main__.py app/state/assessment_log.py
git add tests/integration/test_triage.py tests/test_main.py tests/test_factories.py tests/test_fixtures.py
git add tests/state/test_assessment_log.py
git commit -m "feat: rewrite orchestrator for multi-team triage with notification routing"
```
