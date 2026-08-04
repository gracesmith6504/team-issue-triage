# Live Dashboard with Status Enrichment — Design Spec

## Goal

Replace the static HTML report with a live, always-on dashboard served from the shared OpenShift cluster. Add status enrichment so the dashboard shows each issue's current GitHub state (open/closed, comments, linked PRs) — not just the stale assessment from triage time.

## Architecture

A single FastAPI Deployment replaces the existing CronJob-based architecture for dashboard use cases. The Deployment runs the triage pipeline on a background schedule, enriches issues with live GitHub data, generates the HTML report, and serves it at a Route URL. Any team manager bookmarks the URL and filters to their team via the existing click-to-filter doughnut chart.

The existing CronJob YAMLs remain in the repo as an alternative deployment mode for teams that want batch-only triage without a web UI.

## Tech Stack

- **FastAPI** + **Uvicorn** — team standard for web services (matches Kagenti pattern)
- **threading.Timer** — background scheduler for hourly triage (no new dependency)
- **GitHub REST API** — status enrichment (issue state, comments, PRs)
- **OpenShift Route** — edge TLS termination, auto-generated hostname

## Components

### 1. Status Enrichment (`app/sources/enrichment.py`)

A new module that takes a list of `TriageResult` objects and returns enriched data by calling the GitHub API for each issue's current state.

**Input:** `list[TriageResult]` + GitHub token

**Output:** `list[EnrichedIssue]`

**`EnrichedIssue` dataclass** (new, in `app/sources/enrichment.py`):
```python
@dataclass
class EnrichedIssue:
    result: TriageResult
    is_open: bool
    comment_count: int
    assignees: list[str]
    has_linked_pr: bool
```

**Design decisions:**
- `EnrichedIssue` wraps `TriageResult` rather than modifying it. `TriageResult` represents the LLM assessment at a point in time; enrichment is live data that changes on every check. Keeping them separate means the assessment log stays clean.
- Assignees are fetched but not prominently displayed — OpenShell rarely uses formal assignment. Other teams that adopt this tool may use them.
- GitHub API rate limit: 5000 requests/hour with a token. Even 100 issues = 100 calls per refresh cycle, well within limits.
- Uses the same `GITHUB_API` base URL and auth header pattern as `GitHubSource`.

**GitHub API calls per issue:**
- `GET /repos/{owner}/{repo}/issues/{number}` — returns `state`, `comments`, `assignees`
- `GET /repos/{owner}/{repo}/issues/{number}/timeline` — check for `cross-referenced` events with pull requests (for `has_linked_pr`)

**Implementation:** Use per-issue `GET` calls (simpler, reliable). With typical report sizes of 20-50 issues, this completes in a few seconds. Batch-fetching via the list endpoint is a future optimization if report sizes grow significantly.

**Error handling:** If enrichment fails for a single issue (API error, rate limit), use defaults (`is_open=True`, `comment_count=0`, `assignees=[]`, `has_linked_pr=False`) and log a warning. Enrichment failure must never block the dashboard from rendering.

### 2. FastAPI Web Server (`app/server.py`)

A new module containing the FastAPI application.

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve the cached HTML dashboard |
| GET | `/api/health` | Health check for OpenShift probes |
| POST | `/api/refresh` | Trigger an immediate triage + report regeneration |

**`GET /`:**
- Returns the cached HTML string with `Content-Type: text/html`
- If no report has been generated yet (cold start), returns a simple HTML page: "Triage in progress, check back shortly" with auto-refresh meta tag (`<meta http-equiv="refresh" content="30">`)

**`GET /api/health`:**
- Returns `{"status": "ok", "last_triage": "<iso timestamp>", "issue_count": <int>}`
- Used for OpenShift liveness and readiness probes
- Readiness probe returns 503 until the first triage cycle completes

**`POST /api/refresh`:**
- Triggers an immediate triage + enrichment + report cycle
- Returns 429 if a refresh ran less than 5 minutes ago (prevents accidental LLM cost spikes)
- Returns 409 if a triage cycle is already in progress
- Returns 202 Accepted on success (the refresh runs asynchronously)

**Background scheduler:**
- On startup, kicks off the first triage cycle immediately in a background thread
- Schedules subsequent cycles every 60 minutes using `threading.Timer`
- Uses `threading.Lock` to prevent concurrent triage runs (scheduler vs manual refresh)
- All triage/enrichment/report-generation runs inside `asyncio.to_thread()` since the pipeline uses synchronous `requests` calls

**Error resilience:**
- If a scheduled triage cycle fails (GitHub down, LLM error), logs the error and continues serving the last successful report
- The scheduler does not crash — it retries on the next cycle
- The `/api/health` endpoint reflects the last successful triage time, so monitoring can detect staleness

**Startup sequence:**
1. Create FastAPI app
2. Load config from environment (same `load_config()` as CLI)
3. Start background triage thread
4. Start Uvicorn on `0.0.0.0:8080`

### 3. Report Pipeline Changes

**`app/reports/renderers/html.py`:**

The `render_html()` function signature changes to accept enriched data:
```python
def render_html(report: BirdsEyeReport, enrichment: dict[int, EnrichedIssue] | None = None) -> str:
```

The `enrichment` parameter is a dict keyed by issue number. When present, the template includes:
- **Closed badge:** greyed-out issue card with "Closed" pill badge for `is_open=False`
- **Comment count:** small indicator on issue cards (e.g., "12 comments")
- **Linked PR badge:** small "PR" badge on issues where `has_linked_pr=True`
- **Assignees:** small text under issue title when present (not prominent)
- **"Last refreshed" timestamp** in the dashboard footer

When `enrichment` is `None` (CLI usage without a server), the template renders without these fields — backward compatible with the existing `--mode report` flow.

**`app/reports/renderers/html.py` — `_report_to_dict()` changes:**

When enrichment data is provided, each issue dict in the JSON blob gets additional fields:
```python
{
    "issue_number": 2518,
    "issue_title": "...",
    # ... existing fields ...
    "is_open": true,
    "comment_count": 12,
    "assignees": ["username1"],
    "has_linked_pr": false
}
```

### 4. CLI Integration (`app/__main__.py`)

Add `"serve"` to the mode choices:
```python
parser.add_argument(
    "--mode",
    choices=["triage", "digest", "review", "report", "serve"],
    default="triage",
)
```

When `--mode serve` is selected:
```python
elif args.mode == "serve":
    from app.server import start_server
    start_server(config)
```

### 5. Kubernetes Manifests

Three new files in `k8s/`:

**`k8s/deployment.yaml`:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: triage-dashboard
spec:
  replicas: 1
  selector:
    matchLabels:
      app: triage-dashboard
  template:
    metadata:
      labels:
        app: triage-dashboard
    spec:
      containers:
        - name: dashboard
          image: quay.io/gracesmith6504/team-issue-triage:latest
          args: ["--mode", "serve"]
          ports:
            - containerPort: 8080
              name: http
          envFrom:
            - configMapRef:
                name: triage-config
            - secretRef:
                name: triage-secrets
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 200m
              memory: 256Mi
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
          livenessProbe:
            httpGet:
              path: /api/health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /api/health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          volumeMounts:
            - name: state
              mountPath: /data
      volumes:
        - name: state
          persistentVolumeClaim:
            claimName: triage-state
```

**`k8s/service.yaml`:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: triage-dashboard
spec:
  type: ClusterIP
  selector:
    app: triage-dashboard
  ports:
    - port: 8080
      targetPort: http
      protocol: TCP
```

**`k8s/route.yaml`:**
```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: triage-dashboard
spec:
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
  to:
    kind: Service
    name: triage-dashboard
    weight: 100
  port:
    targetPort: http
```

**`k8s/kustomization.yaml`** — add the three new resources.

**Deployment note:** When using the Deployment (dashboard mode), the CronJobs should not be deployed simultaneously — they would compete for the same PVC (`ReadWriteOnce`). The Kustomize file includes all resources; operators comment out or remove what they don't need. This is documented in a comment in `kustomization.yaml`.

### 6. Dockerfile

Minimal changes:
- Add `EXPOSE 8080` for documentation
- No structural changes — the existing entrypoint (`python -m app`) handles the `--mode serve` flag

### 7. Dependencies

Add to `requirements.txt`:
```
fastapi>=0.115.0
uvicorn>=0.30.0
```

No other new dependencies. The background scheduler uses `threading.Timer` from the standard library.

## Data Flow

```
[Hourly Schedule / Manual Refresh]
        │
        ▼
  ┌─────────────┐
  │  run_triage  │  ← fetches new issues from GitHub, triages with LLM
  │              │  ← writes to /data/assessments.jsonl
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │   enrich     │  ← calls GitHub API for current state of each issue
  │              │  ← returns EnrichedIssue list (in-memory, not persisted)
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │ run_report   │  ← reads assessments, generates BirdsEyeReport
  │              │  ← passes enrichment data to render_html()
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  Cache HTML  │  ← stored in-memory on the server
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  GET /       │  ← serves cached HTML instantly
  └─────────────┘
```

## Testing

### Unit tests for enrichment (`tests/sources/test_enrichment.py`):
- Test `enrich_issues()` with mocked GitHub API responses
- Test fallback to defaults when API fails for one issue
- Test `has_linked_pr` detection from timeline events
- Test deduplication (same issue in critical_list and duplicate_clusters)

### Unit tests for server (`tests/test_server.py`):
- Test `GET /` returns HTML with correct content-type
- Test `GET /` returns "in progress" page before first triage
- Test `GET /api/health` returns JSON with expected fields
- Test `POST /api/refresh` returns 429 within cooldown period
- Test `POST /api/refresh` returns 409 when triage is running
- Use FastAPI's `TestClient` for endpoint tests
- Mock the triage pipeline (don't call real LLM/GitHub in tests)

### Integration with existing tests:
- Existing `test_html_renderer.py` tests continue to pass (enrichment is optional)
- Existing CLI tests continue to pass (serve mode is additive)

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `app/sources/enrichment.py` | Create | Status enrichment module |
| `app/server.py` | Create | FastAPI web server |
| `app/__main__.py` | Modify | Add `serve` mode |
| `app/reports/renderers/html.py` | Modify | Accept enrichment data, add badges/indicators |
| `requirements.txt` | Modify | Add fastapi, uvicorn |
| `Dockerfile` | Modify | Add EXPOSE 8080 |
| `k8s/deployment.yaml` | Create | Dashboard Deployment |
| `k8s/service.yaml` | Create | ClusterIP Service |
| `k8s/route.yaml` | Create | OpenShift Route with edge TLS |
| `k8s/kustomization.yaml` | Modify | Add new resources |
| `tests/sources/test_enrichment.py` | Create | Enrichment unit tests |
| `tests/test_server.py` | Create | Server endpoint tests |
| `docs/future-ideas.md` | Create | Backlog of future enhancements |

## Non-Goals (Future Ideas)

These are captured in `docs/future-ideas.md`, not implemented in this phase:

- GitHub Action wrapper for CI-triggered triage
- Slack notification after each triage cycle
- NVIDIA upstream proposal
- Per-team filtered URLs (`/team/ai-safety`)
- Area heatmap visualization
- Recommendation field display in dashboard
- Team trend sparklines
- Authentication/RBAC on the dashboard Route
