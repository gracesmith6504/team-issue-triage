# team-issue-triage

Multi-team GitHub issue triage agent for OpenShell. Classifies which of 6 Red Hat teams should own each new issue, rates urgency, sends Slack alerts, and serves a live dashboard with a cross-team bird's eye view report.

## How It Works

```
GitHub Issues → Signal Extraction → LLM Classification → Confidence Rules → Notify
```

1. **Fetch** — pulls all new issues from watched repos via GitHub API, skipping already-seen issues
2. **Extract signals** — parses conventional commit title prefixes (`feat(cli):`) and filters labels (`area:*`, `topic:*`)
3. **Classify** — one Claude Sonnet call per issue with all 6 team descriptions, a routing table, and calibration examples
4. **Apply confidence rules** — auto-assign (>0.8), flag multi-team (gap <0.2), flag uncertain (<0.5), force-none override (<0.75)
5. **Notify** — routes critical/high issues to team Slack channels immediately, medium/low accumulate for daily digest
6. **Report** — weekly bird's eye view with team breakdown, area heatmap, duplicate detection, and LLM-generated narrative
7. **Dashboard** — live HTML dashboard served via FastAPI, with status enrichment that re-checks each issue's current GitHub state (open/closed, comments, linked PRs)

### Teams

| Team | Primary Areas |
|------|--------------|
| Agent Ops | CLI, SDK, Helm, OpenShift, sandbox, docs, certgen, network |
| ACP | Gateway, auth, access-control, multi-tenancy |
| AI Safety | Policy engine, guardrails, red teaming |
| Kata | VM isolation, GPU passthrough, Kata containers |
| AgentDev | Inference, providers, router, harness validation |
| Dashboard | Admin UI (upstream API changes only) |

### Confidence Rules

| Confidence | Action |
|-----------|--------|
| Primary > 0.8, gap > 0.2 | Auto-assign to team |
| Gap < 0.2 | Flag both teams (multi-team) |
| Primary < 0.5 | Flag as uncertain |
| any_team_cares but confidence < 0.75 | Override to "no team" (forced-none) |

## Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| LLM | Claude Sonnet via `anthropic[vertex]` SDK |
| LLM Providers | Vertex AI (default), Anthropic API |
| Web Server | FastAPI + Uvicorn |
| Tests | pytest (236 tests) |
| Lint | ruff |
| Container | Docker (non-root) |
| Deploy | Kubernetes Deployment or CronJob + Kustomize |

## Quick Start

```bash
# Clone
git clone https://github.com/gracesmith6504/team-issue-triage.git
cd team-issue-triage

# Install
pip install -r requirements-dev.txt

# Run tests
make test

# Run locally
export GITHUB_TOKEN="ghp_..."
export LLM_PROVIDER="vertex"
export VERTEX_PROJECT_ID="your-gcp-project"
export WATCH_REPOS="NVIDIA/OpenShell"

python -m app --mode triage          # Classify new issues
python -m app --mode digest          # Send daily digest (medium/low)
python -m app --mode review --team agent-ops --since 48   # Review recent results
python -m app --mode report          # Generate bird's eye view report
python -m app --mode report --output report.html          # Write HTML report to file
python -m app --mode serve           # Start live dashboard (FastAPI on port 8080)
```

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `WATCH_REPOS` | `NVIDIA/OpenShell` | Comma-separated `owner/repo` list |
| `GITHUB_TOKEN` | *required* | GitHub personal access token |
| `LLM_PROVIDER` | `vertex` | `vertex` or `anthropic` |
| `LLM_MODEL` | auto | Model name (defaults per provider) |
| `VERTEX_PROJECT_ID` | — | GCP project ID (required for Vertex) |
| `VERTEX_REGION` | `us-east5` | GCP region |
| `ANTHROPIC_API_KEY` | — | API key (required for Anthropic provider) |
| `STATE_PATH` | `/data/state.json` | Where to persist seen-issue state |
| `ASSESSMENT_LOG_PATH` | `/data/assessments.jsonl` | JSONL assessment log for reports |
| `PROFILES_DIR` | `profiles` | Directory containing team YAML profiles |
| `DEFAULT_LOOKBACK_HOURS` | `24` | How far back to scan for new issues |
| `REPORT_OUTPUT_PATH` | — | File path for report output (omit for stdout) |
| `SLACK_WEBHOOK_AGENT_OPS` | — | Per-team Slack webhooks referenced from team YAMLs |

## Team Profiles

Profiles define what each team cares about. The repo config (`profiles/openshell.yaml`) references 6 team YAMLs in `profiles/teams/`:

```yaml
# profiles/teams/agent-ops.yaml
team_id: agent-ops
team_name: "Agent Ops"
description: |
  Core OpenShell integration on Red Hat OpenShift AI. Owns Helm deployment,
  SCCs, RBAC, Routes, Go SDK sync, sandbox operator design, and midstream
  pipeline.
areas:
  primary:
    - cli
    - sdk
    - helm
    - openshift
    - sandbox
  secondary:
    - gateway
    - supervisor
urgency_overrides:
  critical:
    - "Go SDK protobuf sync failures"
  high:
    - "Regressions in Helm/SCC/RBAC deployment"
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

The repo config also defines `no_team_prefixes` (build, ci, tui, rfc, etc.) for issues no Red Hat team owns, `confidence_thresholds`, and `none_examples` for calibration.

## Bird's Eye View Report

Weekly cross-team report generated from the JSONL assessment log:

```
OpenShell Triage — Bird's Eye View
Period: Jul 28 – Aug 03, 2026

SUMMARY
  12 new issues
  2 critical | 7 high | 41 medium | 248 low

  "Gateway saw unusual activity this week with 8 new issues..."
  — generated by Sonnet from the report data

CRITICAL & HIGH ISSUES
  #     | Issue                                        | Team      | Days Open
  2571  | bug(supervisor): SPIFFE sandboxes crash       | ai-safety | 4

TEAM BREAKDOWN
  Team          | Total | Crit | High | Med | Low | Trend
  agent-ops     | 38    | 0    | 3    | 15  | 20  | flat
  acp           | 14    | 1    | 2    | 8   | 3   | +4

AREA HEATMAP
  gateway   | 10 this week (was 2) — +8

POTENTIAL DUPLICATES
  Cluster 1 — sandbox (shared: namespace)
    #2554 add user namespace support — agent-ops
    #2520 enableUserNamespaces fails — agent-ops
```

## Kubernetes Deployment

Two deployment modes — choose one:

**Dashboard mode** (recommended) — a single Deployment serves the live dashboard and runs triage on a background schedule:

```bash
podman build -t quay.io/your-org/team-issue-triage:latest .
podman push quay.io/your-org/team-issue-triage:latest
kubectl apply -k k8s/
```

**Batch mode** — CronJobs for hourly triage and daily digest (no web UI). Edit `k8s/kustomization.yaml` to swap which resources are active.

Manifests in `k8s/`:
- `deployment.yaml` — live dashboard Deployment (dashboard mode)
- `service.yaml` — ClusterIP Service for the dashboard
- `route.yaml` — OpenShift Route with edge TLS
- `cronjob-triage.yaml` — hourly triage CronJob (batch mode)
- `cronjob-digest.yaml` — daily digest CronJob (batch mode)
- `pvc.yaml` — persistent volume for state and assessment log
- `configmap.yaml` — non-secret configuration
- `kustomization.yaml` — ties it all together

Secrets (`GITHUB_TOKEN`, `SLACK_WEBHOOK_*`, API keys) should be provided via a Kubernetes Secret not checked into the repo.

## Project Structure

```
team-issue-triage/
├── app/
│   ├── __main__.py          # CLI entry point (--mode triage|digest|review|report|serve)
│   ├── config.py            # Env var config loader
│   ├── server.py            # FastAPI web server with background triage scheduler
│   ├── triage.py            # Orchestrators: run_triage(), run_digest(), run_review(), run_report()
│   ├── core/
│   │   ├── models.py        # TriageResult, Urgency, IssueData, IssueSignals
│   │   ├── llm.py           # LLM client (Vertex AI, Anthropic) with protocol
│   │   ├── profiles.py      # RepoConfig, TeamProfile, YAML loader with validation
│   │   ├── prompt.py        # Multi-team system/user prompt construction
│   │   ├── scoring.py       # Confidence rules (auto, multi_team, uncertain, forced_none)
│   │   ├── triage_engine.py # Signal extraction, issue triage orchestration
│   │   └── truncation.py    # Body/comment truncation for context limits
│   ├── sources/
│   │   ├── source.py        # IssueSource protocol
│   │   ├── github.py        # GitHub API issue fetcher
│   │   └── enrichment.py    # Live GitHub status enrichment (open/closed, PRs, comments)
│   ├── notifications/
│   │   ├── adapter.py       # NotificationAdapter protocol, config dataclasses
│   │   ├── router.py        # NotificationRouter (immediate + digest routing)
│   │   ├── log.py           # Stdout logging adapter
│   │   └── slack_webhook.py # Slack webhook adapter (Block Kit)
│   ├── state/
│   │   ├── tracker.py       # JSON state persistence (atomic writes, namespaced keys)
│   │   └── assessment_log.py # JSONL append-only log with period queries
│   └── reports/
│       ├── models.py        # BirdsEyeReport, ReportSummary, TeamSummary, AreaTrend
│       ├── birds_eye.py     # Report generator (computes all sections + LLM narrative)
│       ├── duplicates.py    # Duplicate detector (prefix grouping + token overlap)
│       └── renderers/
│           ├── html.py      # Interactive HTML dashboard with Chart.js
│           └── markdown.py  # Markdown renderer for bird's eye report
├── profiles/
│   ├── openshell.yaml       # Repo config (references teams, thresholds, none_examples)
│   └── teams/               # 6 team profile YAMLs
├── k8s/                     # Kubernetes manifests
├── tests/                   # 236 tests (unit + integration)
├── Dockerfile               # Non-root container (UID 1001)
├── Makefile                 # test, lint, format, build
├── requirements.txt
└── requirements-dev.txt
```

## Architecture

Hexagonal architecture — pure core logic with pluggable adapters:

- **Core** (`app/core/`) — triage engine, prompt construction, confidence rules, profiles. No I/O, no framework dependencies. Fully unit-testable.
- **Sources** (`app/sources/`) — issue fetchers. Currently GitHub; protocol-based for extensibility.
- **Notifications** (`app/notifications/`) — adapter protocol with router. Log (stdout) and Slack (webhook). Per-team channel config from YAML.
- **State** (`app/state/`) — JSON tracker with atomic writes via `os.replace`, JSONL assessment log with period-based queries.
- **Reports** (`app/reports/`) — bird's eye view generator, duplicate detector, HTML dashboard and markdown renderers.
- **Server** (`app/server.py`) — FastAPI web server with background scheduler. Runs triage hourly, enriches issues with live GitHub state, caches and serves the HTML dashboard.

## Development

```bash
make test      # Run all 236 tests
make lint      # Check with ruff
make format    # Auto-format with ruff
make build     # Build Docker image
```
