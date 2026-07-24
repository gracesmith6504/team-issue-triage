# Team Issue Triage Agent — Design Spec

**Goal:** An automated agent that monitors NVIDIA/OpenShell GitHub issues and surfaces the ones that matter to the Agent Ops team — release blockers, OpenShift-related bugs, regressions in team-owned areas — while filtering out the noise.

**Non-goals:** This is not a newcomer issue finder (that's github-issue-monitor). It does not create Jira tickets, assign work, or take action on issues. It informs humans.

---

## Architecture Principles

These guide every decision below. When in doubt, refer back.

1. **Configuration over code.** When the team's focus shifts (like Kagenti to OpenShell), updating a YAML profile should be enough. No code changes for scope adjustments.

2. **Pluggable notification backends.** Slack today, but the notification layer is an interface. Adding Jira, email, a dashboard, or a weekly report means implementing one class, not refactoring the pipeline.

3. **Assessment history is a first-class artifact.** Every assessment is persisted with full reasoning. When someone asks "why did this get escalated?" or "why did we miss that issue?", the answer is in the logs. This is also how you tune the profile — review past assessments and add calibration examples.

4. **Stateless execution, persistent state file.** The CronJob itself is stateless — it reads a state file at start, writes it at end. The state file tracks: last poll timestamp, set of already-assessed issue IDs, and the current digest buffer. If the state file is lost, the agent re-assesses the last N hours of issues (safe because assessments are idempotent).

5. **Test without external dependencies.** Every component is testable with fixtures and mocks. No test requires a live GitHub API, LLM call, or Slack webhook.

---

## Component Architecture

```
team-issue-triage/
├── app/
│   ├── core/                    # Engine — no I/O side effects
│   │   ├── assessment.py        # Orchestrates: issue → LLM → scored result
│   │   ├── llm.py               # LLM provider abstraction (from github-issue-monitor)
│   │   ├── prompt.py            # System prompt builder (profile-aware)
│   │   ├── scoring.py           # Verdict computation from axis scores
│   │   └── models.py            # Data classes: Assessment, Verdict, IssueData
│   │
│   ├── sources/                 # Where issues come from
│   │   ├── github.py            # GitHub API client — fetch issues, comments, labels
│   │   └── source.py            # Protocol: any issue source implements this
│   │
│   ├── notifications/           # Where results go
│   │   ├── notifier.py          # Protocol: send_escalation(), send_digest()
│   │   ├── slack.py             # Slack webhook implementation
│   │   ├── digest.py            # Digest buffer — accumulates TRACK items
│   │   └── log.py               # Stdout/file logger (for testing and audit)
│   │
│   ├── state/                   # Persistence between runs
│   │   └── tracker.py           # Read/write state: last_checked, seen_issues, digest_buffer
│   │
│   ├── config.py                # Load config from env vars + YAML
│   └── triage.py                # Main orchestrator — wires everything together
│
├── profiles/
│   └── openshell.yaml           # OpenShell team relevance profile
│
├── k8s/
│   ├── cronjob-triage.yaml      # Hourly triage run
│   ├── cronjob-digest.yaml      # Daily digest flush
│   ├── configmap.yaml           # Non-secret configuration
│   ├── pvc.yaml                 # Persistent volume for state file
│   └── kustomization.yaml       # Kustomize overlay for the agent-ops cluster
│
├── tests/
│   ├── core/                    # Unit tests for assessment, scoring, prompt
│   ├── sources/                 # Tests with fixture issues
│   ├── notifications/           # Tests for formatting, digest accumulation
│   ├── state/                   # State read/write tests
│   ├── integration/             # End-to-end with mocked LLM
│   └── fixtures/                # Real OpenShell issues saved as JSON
│       ├── protobuf_sync_failure.json
│       ├── openshift_scc_bug.json
│       ├── tui_styling_issue.json    # Should be SKIP
│       └── helm_chart_regression.json
│
├── Dockerfile
├── Makefile                     # lint, test, build, deploy targets
├── requirements.txt
├── requirements-dev.txt
├── conftest.py
└── README.md
```

### Why this structure

**`core/` has no I/O side effects.** It takes data in, returns data out. No GitHub calls, no Slack posts, no file writes. This means every piece of assessment logic is testable with plain function calls and fixture data.

**`sources/` and `notifications/` are symmetric boundaries.** Issues come in through a source protocol; results go out through a notifier protocol. The triage orchestrator (`triage.py`) wires them together. To add a new source (e.g., Jira issues, GitLab), implement the source protocol. To add a new notification channel, implement the notifier protocol.

**`state/` is deliberately simple.** A JSON file on a PersistentVolume. Not a database. The state is small (a timestamp, a set of integers, and a list of digest entries). If it gets corrupted, the worst case is re-assessing some issues — which is safe because assessments are idempotent and the agent never takes action, only notifies.

**`profiles/` is separate from `app/`.** Profiles are configuration, not code. A team member who doesn't write Python can update the profile YAML to adjust what the agent watches for.

---

## Scoring System

### Three Axes (1-5 each)

**Team Relevance** — Does this issue touch an area the Agent Ops team owns or cares about?

| Score | Meaning |
|-------|---------|
| 5 | Directly in team-owned area (OpenShift deployment, sandbox operator, inference routing, agent identity) |
| 4 | Adjacent area the team actively contributes to (CLI commands the team has PRs against, mTLS setup) |
| 3 | Area the team uses but doesn't own (core gateway, policy engine) |
| 2 | Tangentially related (general Rust tooling, build system) |
| 1 | Unrelated to team's work (TUI styling, Docker-only driver, macOS-specific) |

**Urgency** — How time-sensitive is this?

| Score | Meaning |
|-------|---------|
| 5 | Release blocker or CI failure that stops the team's work |
| 4 | Regression in current pinned version (v0.0.85) or security vulnerability |
| 3 | Bug affecting team workflows, but workaround exists |
| 2 | Enhancement or improvement that would help the team |
| 1 | Discussion, RFC, feature request, or nice-to-have |

**Action Clarity** — Is there something specific someone should do?

| Score | Meaning |
|-------|---------|
| 5 | Clear fix described, someone just needs to do it |
| 4 | Problem is well-defined, fix approach is apparent |
| 3 | Problem is clear but investigation needed to find the fix |
| 2 | Problem is vague, needs reproduction or design discussion |
| 1 | Open-ended discussion, RFC, or architectural question |

### Verdict Computation

Total = Relevance + Urgency + Action Clarity (range: 3-15)

| Verdict | Threshold | Meaning | Notification |
|---------|-----------|---------|-------------|
| ESCALATE | >= 12 | Team needs to act soon | Immediate Slack post |
| TRACK | >= 8 | Team should be aware | Daily digest |
| WATCH | >= 5 | Might become relevant | Logged to assessment history |
| SKIP | < 5 | Not for us | Logged, no notification |

**Override rules** (applied after threshold):
- If Urgency = 5 and Relevance >= 3, force ESCALATE regardless of total (a release blocker in a relevant area always escalates)
- If Relevance = 1, cap at WATCH regardless of total (unrelated issues never escalate even if urgent)

These override rules encode judgment that shouldn't depend on threshold arithmetic. A release blocker in a team-adjacent area should escalate even if the fix is unclear (low Action Clarity). An unrelated issue should never escalate even if it's a critical blocker — that's someone else's problem.

---

## Team Relevance Profile

The profile is a YAML file that gives the LLM context about what the team cares about. It's the same concept as github-issue-monitor's OpenShell profile, but calibrated for team relevance instead of newcomer difficulty.

```yaml
# profiles/openshell.yaml
repos:
  - "NVIDIA/OpenShell"

team_name: "Agent Ops"
team_context: |
  The Agent Ops team at Red Hat is responsible for integrating OpenShell
  into Red Hat OpenShift AI (RHOAI) as a Dev Preview feature for the 3.5
  release. The team's focus areas are:

  1. Running OpenShell on OpenShift — Helm deployment, SCCs, RBAC,
     Routes, NetworkPolicies, pod security
  2. Sandbox operator design — CRDs for declarative sandbox management
  3. Inference routing — proxying LLM requests through OpenShell's
     gateway to model endpoints (vLLM, Vertex AI)
  4. Agent identity — SPIFFE/OIDC token exchange, AuthBridge integration
  5. Go SDK synchronization — protobuf codegen that must stay in sync
     with the server. Sync failures block releases.
  6. Midstream/downstream pipeline — syncing upstream changes into
     opendatahub-io/agents-operator and Red Hat builds

  The team does NOT own:
  - The TUI (openshell-tui) — terminal dashboard, cosmetic
  - Docker driver (openshell-driver-docker) — local dev only
  - MicroVM driver — not used on OpenShift
  - macOS-specific issues — team deploys on Linux/OpenShift
  - General documentation unless it's about OpenShift deployment

pinned_version: "v0.0.85"

urgency_rules: |
  RELEASE BLOCKERS (Urgency 5):
  - Go SDK protobuf sync failures (auto-created by GitHub Actions,
    title pattern: "protobuf sync failed" or "codegen sync")
  - Any issue with labels: priority/critical, kind/blocker
  - CI failures that affect the release pipeline

  REGRESSIONS (Urgency 4):
  - Bugs in v0.0.85 that worked in previous versions
  - Security vulnerabilities (CVE mentions, label: area/security)

  BUGS (Urgency 3):
  - Reproducible bugs in team-relevant areas with workarounds

  ENHANCEMENTS (Urgency 2):
  - Feature requests that would benefit OpenShift deployment
  - Improvements to areas the team actively works on

  DISCUSSIONS (Urgency 1):
  - RFCs, design proposals, architecture discussions
  - Feature requests outside team scope

calibration_examples:
  - summary: "Go SDK protobuf sync failed for v0.4.2"
    scores: "Relevance=5 Urgency=5 Action=4"
    verdict: "ESCALATE"
    reason: "SDK sync errors are release blockers. Clear action: re-run sync after fixing proto definitions."

  - summary: "Helm chart fails when SCC restricts runAsUser"
    scores: "Relevance=5 Urgency=4 Action=4"
    verdict: "ESCALATE"
    reason: "Directly affects OpenShift deployment — the team's primary focus area. Fix approach is apparent."

  - summary: "TUI crashes when terminal window is resized"
    scores: "Relevance=1 Urgency=3 Action=3"
    verdict: "SKIP"
    reason: "TUI is not team-owned. Bug is real but irrelevant to Agent Ops work."

  - summary: "Add GPU passthrough support for sandbox pods"
    scores: "Relevance=4 Urgency=2 Action=2"
    verdict: "TRACK"
    reason: "Relevant to OpenShift sandbox work but not urgent. Needs design discussion."

  - summary: "Landlock policy not enforced inside Docker containers"
    scores: "Relevance=1 Urgency=3 Action=3"
    verdict: "SKIP"
    reason: "Docker driver issue. Team deploys on OpenShift, not Docker."

  - summary: "Route TLS termination breaks with custom CA certificates"
    scores: "Relevance=5 Urgency=4 Action=3"
    verdict: "ESCALATE"
    reason: "TLS/mTLS on OpenShift is a team-owned area. Regression in deployment workflow."

  - summary: "RFC: SDK conformance testing framework"
    scores: "Relevance=3 Urgency=1 Action=1"
    verdict: "WATCH"
    reason: "Tangentially relevant but it's an open-ended design discussion. No action needed from the team."

  - summary: "openshell-core: refactor config parsing into separate module"
    scores: "Relevance=3 Urgency=1 Action=2"
    verdict: "WATCH"
    reason: "Core crate refactoring affects everyone but is not team-initiated. Watch for breaking changes."
```

### Profile Extensibility

To monitor a second repo (e.g., `opendatahub-io/agent-ops`), add a second profile YAML. The agent loads all profiles from `profiles/` and matches each to its repo. The code doesn't change.

To adjust what the team cares about (e.g., team picks up TUI ownership), edit the profile YAML. No code change.

---

## Data Flow

### Hourly Triage Run

```
1. Load config (env vars + profile YAML)
2. Read state file (last_checked timestamp, seen_issue_ids, digest_buffer)
3. Query GitHub API:
   - GET /repos/NVIDIA/OpenShell/issues?since={last_checked}&state=open&sort=created
   - Filter out issues already in seen_issue_ids
   - For each new issue, fetch comments (for context)
4. For each new issue:
   a. Build LLM prompt (system prompt with profile context + issue data)
   b. Call Vertex AI (Claude Sonnet)
   c. Parse response → axis scores + reasoning
   d. Compute verdict (threshold + override rules)
   e. Log full assessment to assessment history
   f. If ESCALATE → send immediate Slack notification
   g. If TRACK → append to digest_buffer in state
   h. Add issue ID to seen_issue_ids
5. Update state file (new last_checked, updated seen_issue_ids, updated digest_buffer)
6. Exit
```

### Daily Digest Run

```
1. Read state file
2. If digest_buffer is non-empty:
   a. Format digest (grouped by verdict, sorted by urgency)
   b. Send digest via Slack
   c. Clear digest_buffer in state
3. Write updated state file
4. Exit
```

### Assessment History

Every assessment is appended to a log file (or stdout for container logs):

```json
{
  "timestamp": "2026-07-23T14:00:00Z",
  "repo": "NVIDIA/OpenShell",
  "issue_number": 2401,
  "issue_title": "protobuf sync failed for Go SDK v0.4.2",
  "scores": {
    "relevance": 5,
    "relevance_reason": "Go SDK sync is a release-blocking area owned by the team",
    "urgency": 5,
    "urgency_reason": "Sync failures directly block OpenShell releases",
    "action_clarity": 4,
    "action_clarity_reason": "Clear action: fix proto definitions and re-run sync"
  },
  "total": 14,
  "verdict": "ESCALATE",
  "override_applied": null,
  "notified": true
}
```

This serves three purposes:
1. **Debugging** — why did issue X get verdict Y?
2. **Tuning** — review assessments to find miscalibrations, add examples to profile
3. **Audit** — what did the agent do and when?

---

## Notification Format

### ESCALATE (Immediate Slack)

Keep it short. Seniors should be able to decide whether to click in under 5 seconds. The full assessment reasoning lives in the thread reply for anyone who wants detail.

**Channel message:** One-line summary with emoji, issue title, why it matters, link.

**Thread reply:** Full scores, reasoning, and recommended next step.

The exact formatting is a detail to iterate on during testing — the important architectural point is that the channel message is always short and the detail is always available in the thread.

### TRACK (Daily Digest)

A single Slack message posted once per day (morning, before standup). Groups issues by team area, sorted by urgency within each group. Each entry is one line: issue title + one-line reason + link.

Cap at 10 items per digest. If more than 10, show the top 10 by urgency and note how many were omitted. Nobody reads a 30-item digest.

### WATCH and SKIP

No notification. Logged to assessment history only. Available for review if someone wants to audit what the agent skipped.

---

## State Management

State is a single JSON file on a PersistentVolumeClaim:

```json
{
  "last_checked": "2026-07-23T13:00:00Z",
  "seen_issues": [2401, 2399, 2398, 2395],
  "digest_buffer": [
    {
      "issue_number": 2399,
      "title": "Helm values.yaml missing tolerations passthrough",
      "relevance": 4,
      "urgency": 2,
      "action_clarity": 5,
      "verdict": "TRACK",
      "reason": "OpenShift deployment gap — clear fix, not urgent",
      "url": "https://github.com/NVIDIA/OpenShell/issues/2399",
      "assessed_at": "2026-07-23T13:05:00Z"
    }
  ]
}
```

**Recovery:** If the state file is missing or corrupted, the agent defaults to checking the last 24 hours of issues. This may re-assess some issues, but since assessments are idempotent (same issue → same verdict) and notifications include the issue number (Slack deduplication), the worst case is a duplicate notification — not a missed one.

**Seen issues pruning:** Issues older than 30 days are removed from `seen_issues` on each run to prevent unbounded growth.

---

## Deployment

### On the Agent-Ops Cluster

The agent runs as a CronJob in its own namespace on Mark's agent-ops cluster. It does NOT run inside an OpenShell sandbox — it's a team process tool, not an agent workload demo. A plain container is simpler, cheaper, and appropriate.

**Container image:** Built from Dockerfile, pushed to `quay.io/gracesmith6504/team-issue-triage` (Grace's Quay namespace, same as the original issue monitor image).

**Secrets needed:**
- `GITHUB_TOKEN` — PAT with `repo:read` scope for NVIDIA/OpenShell
- `SLACK_WEBHOOK_URL` — Slack incoming webhook for the team channel
- `GCP_SA_KEY` — Google Cloud service account key for Vertex AI (same one as github-issue-monitor)

**CronJobs:**
- `triage-hourly`: runs every hour, assesses new issues
- `triage-digest`: runs daily at 08:00 UTC (before standup), flushes digest buffer

### Local Development

```bash
# Run locally against a real repo (your test repo)
export GITHUB_TOKEN=...
export LLM_PROVIDER=vertex
export VERTEX_PROJECT_ID=itpc-gcp-ai-eng-claude
export WATCH_REPOS=gracesmith6504/test-repo
python -m app.triage

# Run tests
make test

# Run linter
make lint
```

### Testing Progression (from Ignas)

1. **Week 1:** Point at Grace's own test repo. Create fake issues that mimic OpenShell patterns. Verify scoring, verdict, and notifications work correctly.
2. **Week 2+:** Point at NVIDIA/OpenShell. Review every assessment for the first week. Tune the profile based on what it gets wrong.
3. **Ongoing:** Add calibration examples to the profile as edge cases emerge.

---

## What to Copy from github-issue-monitor

| Component | Copy or Rebuild? | Notes |
|-----------|-----------------|-------|
| `app/core/llm.py` | Copy, minor cleanup | Multi-provider abstraction works. Keep Vertex + Anthropic, drop GitHub Models (expiring). |
| `app/core/assessment.py` | Copy structure, rewrite internals | Same orchestrator pattern (issue → LLM → scored result). New axes, new prompt. |
| `app/core/scoring.py` | Rebuild | New axes, new thresholds, new override rules. Keep `clamp_score` utility. |
| `app/core/prompt.py` | Rebuild | Completely different prompt for team relevance vs newcomer difficulty. Keep `build_system_prompt` pattern of injecting profile sections. |
| `app/core/profiles.py` | Copy structure, extend schema | Same YAML loading. New fields (team_areas, urgency_rules, etc). |
| `app/core/truncation.py` | Copy | Issue body truncation logic is universal. |
| `Dockerfile` | Copy, adjust | Same base image pattern. |
| `k8s/` | Copy, adapt | CronJob instead of Deployment. Add PVC for state. |
| `conftest.py` | Copy | Test setup patterns. |
| Polling logic | Do not copy | The original's polling mode has GitHub Actions-specific code (create notification issues). The new agent's polling is simpler: query API, assess, notify via Slack. |
| Action mode | Do not copy | Not relevant — this agent doesn't install on target repos. |

---

## Future Extensions (Not in V1)

These are architecturally accommodated (the interfaces support them) but NOT built in v1:

- **Jira integration:** A `JiraNotifier` that creates RHAIENG tickets for ESCALATE items. The notifier protocol supports this without changing assessment logic.
- **Multiple repos:** Add profile YAMLs for `opendatahub-io/agent-ops`, `opendatahub-io/agents-operator`, etc. The source and profile loading already support multiple repos.
- **Dashboard/report:** A `ReportNotifier` that generates a weekly HTML or Google Doc summary. Same interface.
- **Feedback loop:** A mechanism for team members to react to Slack notifications (thumbs up/down) to indicate whether the assessment was correct. Feed this back into profile tuning.
- **Jira cross-reference:** Enrich assessments with active Jira sprint data — "this issue touches the same area as RHAIENG-6376 which Varsha is working on."

These are noted here to ensure the architecture doesn't paint us into a corner, but they are explicitly out of scope for the initial build.

---

## Success Criteria

The agent is working when:

1. It runs hourly on the cluster without errors
2. It correctly identifies Go SDK sync failures as ESCALATE
3. It correctly identifies OpenShift-related bugs as TRACK or ESCALATE
4. It correctly identifies TUI/Docker/macOS issues as SKIP
5. The daily digest is useful and under 10 items
6. Ignas doesn't mute the channel after week 1 (the real test)
