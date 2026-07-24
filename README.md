# team-issue-triage

LLM-powered GitHub issue triage agent that scores issues against your team's profile and routes notifications via Slack.

## How It Works

```
GitHub Issues → Fetch & Truncate → LLM Assessment → Score & Verdict → Notify
```

1. **Fetch** — pulls new issues from watched repos via GitHub API, skipping already-seen issues
2. **Truncate** — trims issue bodies and comments to fit LLM context limits
3. **Assess** — sends each issue to Claude (Vertex AI or Anthropic API) with your team profile as system prompt
4. **Score** — extracts three axes (Team Relevance, Urgency, Action Clarity, 1–5 each) and computes a verdict
5. **Notify** — routes ESCALATE/TRACK verdicts to Slack, logs everything, accumulates a daily digest

### Scoring

| Axis | What it measures |
|------|-----------------|
| Team Relevance | How closely the issue maps to your team's owned areas |
| Urgency | Time sensitivity — release blockers, regressions, CVEs |
| Action Clarity | Whether there's a concrete next step your team can take |

### Verdicts

| Verdict | Total Score | Meaning |
|---------|------------|---------|
| ESCALATE | >= 12 | Needs immediate team attention |
| TRACK | >= 8 | Worth following, review at next standup |
| WATCH | >= 5 | Keep an eye on it |
| SKIP | < 5 | Not relevant to the team |

**Override rules:** Relevance=1 caps any issue at WATCH (irrelevant issues never escalate). Urgency=5 with Relevance>=3 forces ESCALATE (urgent + relevant = act now).

## Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| LLM | Claude via `anthropic[vertex]` SDK |
| LLM Providers | Vertex AI (default), Anthropic API |
| Tests | pytest (98 tests) |
| Lint | ruff |
| Container | Docker (non-root) |
| Deploy | Kubernetes CronJob + Kustomize |

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | >= 3.12 | Runtime |
| Docker | any | Container builds |
| kubectl | any | Deployment (optional) |
| A GitHub token | — | Issue fetching |
| GCP credentials | — | Vertex AI auth (if using Vertex) |

## Quick Start

```bash
# Clone
git clone https://github.com/gracesmith6504/team-issue-triage.git
cd team-issue-triage

# Install
pip install -r requirements-dev.txt

# Run tests
make test

# Run locally (triage mode)
export GITHUB_TOKEN="ghp_..."
export LLM_PROVIDER="vertex"
export VERTEX_PROJECT_ID="your-gcp-project"
export WATCH_REPOS="NVIDIA/OpenShell"
python -m app --mode triage

# Run locally (digest mode)
python -m app --mode digest
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
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook (omit for log-only) |
| `STATE_PATH` | `/data/state.json` | Where to persist seen-issue state |
| `PROFILES_DIR` | `profiles` | Directory containing team YAML profiles |
| `DEFAULT_LOOKBACK_HOURS` | `24` | How far back to scan for new issues |

## Team Profiles

Profiles tell the LLM what your team cares about. Each profile is a YAML file in `profiles/`:

```yaml
repos:
  - "NVIDIA/OpenShell"

team_name: "Agent Ops"
team_context: |
  What the team owns, what it doesn't, and why.

pinned_version: "v0.0.85"

urgency_rules: |
  RELEASE BLOCKERS (Urgency 5): ...
  REGRESSIONS (Urgency 4): ...

calibration_examples:
  - summary: "Go SDK protobuf sync failed for v0.4.2"
    scores: "Relevance=5 Urgency=5 Action=4"
    verdict: "ESCALATE"
    reason: "SDK sync errors are release blockers."
```

The profile is injected into the LLM system prompt, so the model scores issues from your team's perspective. See `profiles/openshell.yaml` for a full example.

## Kubernetes Deployment

The agent runs as two CronJobs — hourly triage and daily digest:

```bash
# Build and push the image
docker build -t your-registry/team-issue-triage:latest .
docker push your-registry/team-issue-triage:latest

# Deploy with Kustomize
kubectl apply -k k8s/
```

Manifests in `k8s/`:
- `cronjob-triage.yaml` — runs every hour, assesses new issues
- `cronjob-digest.yaml` — runs daily at 09:00 UTC, flushes accumulated digest
- `pvc.yaml` — persistent volume for state file
- `configmap.yaml` — non-secret configuration
- `kustomization.yaml` — ties it all together

Secrets (`GITHUB_TOKEN`, `SLACK_WEBHOOK_URL`, API keys) should be provided via a Kubernetes Secret not checked into the repo.

## Project Structure

```
team-issue-triage/
├── app/
│   ├── __main__.py          # CLI entry point (--mode triage|digest)
│   ├── config.py            # Env var config loader
│   ├── triage.py            # Orchestrators: run_triage(), run_digest()
│   ├── core/
│   │   ├── models.py        # Verdict, IssueData, Assessment, DigestEntry
│   │   ├── llm.py           # LLM client (Vertex AI, Anthropic)
│   │   ├── profiles.py      # YAML team profile loader
│   │   ├── prompt.py        # System/user prompt construction
│   │   ├── scoring.py       # Score clamping, verdict logic, overrides
│   │   ├── assessment.py    # Issue assessment pipeline
│   │   └── truncation.py    # Body/comment truncation for context limits
│   ├── sources/
│   │   ├── source.py        # IssueSource protocol
│   │   └── github.py        # GitHub API issue fetcher
│   ├── notifications/
│   │   ├── notifier.py      # Notifier protocol
│   │   ├── log.py           # Stdout logging notifier
│   │   └── slack.py         # Slack webhook notifier
│   └── state/
│       └── tracker.py       # JSON state persistence (atomic writes)
├── profiles/
│   └── openshell.yaml       # Agent Ops team profile
├── k8s/                     # Kubernetes manifests
├── tests/                   # 98 tests (unit + integration)
├── Dockerfile               # Non-root container (UID 1001)
├── Makefile                 # test, lint, format, build
├── requirements.txt
└── requirements-dev.txt
```

## Architecture

Hexagonal architecture — pure core logic with pluggable adapters:

- **Core** (`app/core/`) — scoring, prompts, assessment. No I/O, no framework dependencies. Fully unit-testable.
- **Sources** (`app/sources/`) — issue fetchers. Currently GitHub; protocol-based so you can add GitLab, Jira, etc.
- **Notifications** (`app/notifications/`) — output adapters. Log (stdout) and Slack (webhook). Add email, PagerDuty, etc.
- **State** (`app/state/`) — persistence. JSON file with atomic writes via `os.replace`.

## Development

```bash
make test      # Run all 98 tests
make lint      # Check with ruff
make format    # Auto-format with ruff
make build     # Build Docker image
```

## Known Limitations

- **Single-repo state collision** — `seen_ids` are keyed by bare issue number, so multi-repo mode will collide. Fix before enabling multiple repos.
- **No GitHub pagination** — fetches the first page of issues only. Fix before pointing at repos with high issue volume.
- **No Slack thread replies** — ESCALATE verdicts post a single message, not a thread with details.
- **No resource limits** — CronJob manifests don't set CPU/memory requests. Add before deploying to shared clusters.
