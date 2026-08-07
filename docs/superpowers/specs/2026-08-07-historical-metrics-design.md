# Historical Metrics System Design

## Problem

Each triage run is a snapshot with no memory. The dashboard has sparklines and trend indicators but they are all fake -- hardcoded "+1" trends, flat sparkline arrays of zeros. GitHub Insights shows activity counts but cannot show LLM-classified urgency trends, team routing load shifts, vouch response trajectories, or triage coverage improvements. Those are our unique value for the NVIDIA upstream proposal.

The system runs as a CronJob on Kubernetes with a PVC, twice daily. After 6 months that is ~365 runs. The architecture must support pluggable storage backends because Org Pulse integration may need a different backend later.

## Design

### Architecture Overview

Three new components, one per concern:

1. **MetricsSnapshot dataclass** (`app/metrics/models.py`) -- the shape of one point-in-time measurement
2. **MetricsStore Protocol + JsonlMetricsStore** (`app/metrics/store.py`) -- pluggable storage interface with a JSONL v1 backend
3. **compute_snapshot()** (`app/metrics/compute.py`) -- pure function that extracts a snapshot from an already-computed BirdsEyeReport

After each triage cycle, `compute_snapshot()` produces a `MetricsSnapshot` from the report data already in memory (no extra API calls). The snapshot is appended to the store. At render time, the last 7 snapshots are read from the store and fed into the dashboard sparklines.

### Data Model

```python
@dataclass
class MetricsSnapshot:
    timestamp: str                          # ISO datetime of this run
    period_label: str                       # e.g. "Jul 28 - Aug 3, 2026"

    # Urgency distribution
    total_issues: int
    by_urgency: dict[str, int]              # {"critical": 3, "high": 7, ...}

    # Team routing load
    by_team: dict[str, int]                 # {"agent-ops": 5, "ai-safety": 3, ...}

    # Triage coverage
    triage_needed: int                      # issues not yet triaged
    total_open: int                         # total open issues

    # PR health (None if module disabled)
    pr_total_open: int | None
    pr_awaiting_review: int | None
    pr_stale_14d: int | None
    merge_velocity: int | None
    avg_review_wait_days: float | None

    # Vouch health (None if module disabled)
    vouch_pending: int | None
    vouch_responded_7d: int | None
    vouch_longest_wait: int | None
```

Flat fields, no nested dataclasses. Each snapshot is self-contained and serializes to ~500 bytes of JSON. At twice-daily for 6 months: ~365 snapshots, ~180KB total. No compaction needed.

### Storage Interface

```python
class MetricsStore(Protocol):
    def append(self, snapshot: MetricsSnapshot) -> None: ...
    def read(
        self, *, since: str | None = None, limit: int | None = None
    ) -> list[MetricsSnapshot]: ...
```

Follows the same `typing.Protocol` pattern as `LLMClientProtocol`, `IssueSource`, and `NotificationAdapter`.

- `append`: writes one snapshot
- `read`: returns snapshots in chronological order, optionally filtered by `since` (ISO datetime) or capped by `limit` (most recent N)

**v1 implementation: `JsonlMetricsStore`**

```python
class JsonlMetricsStore:
    def __init__(self, path: Path): ...
```

- Same append pattern as `assessment_log.append_result()`: open in append mode, `json.dumps(asdict(snapshot))`, newline
- Same read pattern as `assessment_log.read_results()`: linear scan, parse each line, filter/limit
- Default path: `/data/metrics.jsonl` (alongside `state.json` and `assessments.jsonl` on the PVC)

### Snapshot Computation

```python
def compute_snapshot(report: BirdsEyeReport, now: datetime) -> MetricsSnapshot:
```

A pure function. Reads from `report.summary`, `report.team_breakdown`, `report.pr_health`, and `report.vouch_status`. Everything it needs is already on the `BirdsEyeReport` dataclass after `enrich_report()` runs.

```python
def build_sparklines(snapshots: list[MetricsSnapshot]) -> dict[str, list[int]]:
```

A second pure function in the same module. Takes a list of snapshots and returns the sparklines dict expected by the renderer. Extracts one field per sparkline key from each snapshot.

### Wiring

Called in two places, after `enrich_report()` and before rendering:

1. `run_report()` in `app/triage.py`
2. `_run_cycle()` in `app/server.py`

Pattern:
```python
enrich_report(report, config, repo_config)

store = JsonlMetricsStore(config.metrics_path)
snapshot = compute_snapshot(report, now)
store.append(snapshot)

recent = store.read(limit=7)
sparklines = build_sparklines(recent)
```

### Config

One new field on `TriageConfig`:

```python
metrics_path: Path  # env: METRICS_PATH, default: /data/metrics.jsonl
```

### Dashboard Integration

**Sparklines:** Replace hardcoded `[0,0,0,0,0,0,0]` with real data from the last 7 snapshots:

```python
sparklines = {
    "triage": [s.triage_needed for s in recent],
    "prs": [s.pr_awaiting_review or 0 for s in recent],
    "blocked": [s.vouch_pending or 0 for s in recent],
    "velocity": [s.merge_velocity or 0 for s in recent],
}
```

Updated renderer signature:

```python
def render_html(report, enrichment=None, sparklines=None) -> str:
```

In `_report_to_dict()`, use passed sparklines if present, fall back to zeros if None (backward compatible).

The JS `sparkSVG()` function already handles variable-length arrays and checks for variation before rendering. If there are fewer than 7 snapshots (early runs), shorter arrays are fine.

### Error Handling

- **First run (no snapshots):** sparklines is None, falls back to zeros. Dashboard renders as today.
- **Fewer than 7 snapshots:** Pass whatever exists. JS handles variable-length arrays.
- **Corrupted JSONL line:** try/except around `json.loads()`, log warning, skip line.
- **PR health or vouch disabled:** Fields are None on snapshot. Sparkline uses `or 0`.
- **Disk full / write failure:** Wrap append in try/except, log error, continue. Metrics are observability, not core functionality.
- **Concurrent writes:** Not a concern in v1 (single CronJob pod). JSONL append is atomic under PIPE_BUF for future safety. Protocol allows proper locking in future backends.

### Testing

**`tests/metrics/test_compute.py`** -- Unit tests for `compute_snapshot()`. Pure function, no mocking. Uses `make_report()` fixture. Cases: with pr_health, without pr_health, empty team_breakdown. (~4-5 tests)

**`tests/metrics/test_store.py`** -- Unit tests for `JsonlMetricsStore`. Uses `tmp_path` fixture. Cases: append + read roundtrip, read with `since` filter, read with `limit`, empty/missing file, corrupted line skipped. (~5-6 tests)

**`tests/reports/test_html_renderer.py`** -- Update existing tests. Add `test_render_html_sparklines_from_history` (non-zero sparklines passed through). Update `test_report_to_dict_adds_sparklines` to assert 7 zeros (was 5). (~2-3 updated tests)

Estimated: ~12-15 new tests, ~2-3 updated tests.

### Files

**New files (7):**
- `app/metrics/__init__.py`
- `app/metrics/models.py` -- MetricsSnapshot dataclass
- `app/metrics/store.py` -- MetricsStore Protocol + JsonlMetricsStore
- `app/metrics/compute.py` -- compute_snapshot() and build_sparklines()
- `tests/metrics/__init__.py`
- `tests/metrics/test_compute.py`
- `tests/metrics/test_store.py`

**Modified files (6):**
- `app/config.py` -- add `metrics_path` field
- `app/triage.py` -- wire snapshot append + sparklines in `run_report()`
- `app/server.py` -- wire snapshot append + sparklines in `_run_cycle()`
- `app/reports/renderers/html.py` -- accept `sparklines` param, use real data in `_report_to_dict()`
- `tests/reports/test_html_renderer.py` -- update sparkline tests
- `tests/reports/conftest.py` -- update if needed

**Not changed:**
- `app/core/` -- triage engine, LLM, models untouched
- `app/pr_health/`, `app/vouch/` -- read-only consumers, untouched
- `app/reports/birds_eye.py` -- report generation untouched
- `app/state/` -- assessment log and tracker untouched
