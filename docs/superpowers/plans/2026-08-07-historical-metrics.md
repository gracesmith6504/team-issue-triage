# Historical Metrics System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded sparkline zeros with real historical trend data computed from triage runs.

**Architecture:** Three new modules under `app/metrics/` — a `MetricsSnapshot` dataclass, a `MetricsStore` Protocol with JSONL backend, and two pure functions (`compute_snapshot`, `build_sparklines`). After each triage cycle, a snapshot is extracted from the already-computed `BirdsEyeReport` and appended to a JSONL file. At render time, the last 7 snapshots become the sparkline data.

**Tech Stack:** Python 3.12 dataclasses, `typing.Protocol`, JSONL via `json` stdlib, `pytest` with `tmp_path` fixture.

## Global Constraints

- Run `make lint` before pushing (ruff check + ruff format)
- Run `make test` before pushing (pytest)
- Conventional commits (`feat:`, `fix:`, `test:`, `refactor:`)
- No `Co-Authored-By` lines in commits
- Squash to one commit per logical change before review
- All existing 259 tests must continue passing after every task

---

## File Map

**New files (7):**
| File | Responsibility |
|------|---------------|
| `app/metrics/__init__.py` | Package marker |
| `app/metrics/models.py` | `MetricsSnapshot` dataclass |
| `app/metrics/store.py` | `MetricsStore` Protocol + `JsonlMetricsStore` |
| `app/metrics/compute.py` | `compute_snapshot()` + `build_sparklines()` pure functions |
| `tests/metrics/__init__.py` | Package marker |
| `tests/metrics/test_compute.py` | Tests for `compute_snapshot()` + `build_sparklines()` |
| `tests/metrics/test_store.py` | Tests for `JsonlMetricsStore` |

**Modified files (5):**
| File | Change |
|------|--------|
| `app/config.py` | Add `metrics_path: Path` field to `TriageConfig` |
| `app/triage.py` | Wire snapshot append + sparklines into `run_report()` |
| `app/server.py` | Wire snapshot append + sparklines into `_run_cycle()` |
| `app/reports/renderers/html.py` | Accept `sparklines` param, replace hardcoded zeros |
| `tests/reports/test_html_renderer.py` | Update sparkline length assertion, add real-sparklines test |

---

### Task 1: MetricsSnapshot dataclass + MetricsStore protocol + JSONL backend

**Files:**
- Create: `app/metrics/__init__.py`
- Create: `app/metrics/models.py`
- Create: `app/metrics/store.py`
- Create: `tests/metrics/__init__.py`
- Create: `tests/metrics/test_store.py`

**Interfaces:**
- Consumes: nothing (leaf module)
- Produces:
  - `MetricsSnapshot` dataclass with fields: `timestamp: str`, `period_label: str`, `total_issues: int`, `by_urgency: dict[str, int]`, `by_team: dict[str, int]`, `triage_needed: int`, `total_open: int`, `pr_total_open: int | None`, `pr_awaiting_review: int | None`, `pr_stale_14d: int | None`, `merge_velocity: int | None`, `avg_review_wait_days: float | None`, `vouch_pending: int | None`, `vouch_responded_7d: int | None`, `vouch_longest_wait: int | None`
  - `MetricsStore` Protocol with `append(snapshot: MetricsSnapshot) -> None` and `read(*, since: str | None = None, limit: int | None = None) -> list[MetricsSnapshot]`
  - `JsonlMetricsStore(path: Path)` implementing `MetricsStore`

- [ ] **Step 1: Write store tests**

Create `tests/metrics/__init__.py` (empty) and `tests/metrics/test_store.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from app.metrics.models import MetricsSnapshot
from app.metrics.store import JsonlMetricsStore


def _make_snapshot(timestamp: str = "2026-08-01T00:00:00+00:00") -> MetricsSnapshot:
    return MetricsSnapshot(
        timestamp=timestamp,
        period_label="Jul 28 – Aug 3, 2026",
        total_issues=10,
        by_urgency={"critical": 1, "high": 3, "medium": 4, "low": 2},
        by_team={"agent-ops": 5, "ai-safety": 3, "none": 2},
        triage_needed=4,
        total_open=10,
        pr_total_open=42,
        pr_awaiting_review=5,
        pr_stale_14d=3,
        merge_velocity=8,
        avg_review_wait_days=4.2,
        vouch_pending=3,
        vouch_responded_7d=1,
        vouch_longest_wait=45,
    )


def test_append_and_read_roundtrip(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    snap = _make_snapshot()
    store.append(snap)
    result = store.read()
    assert len(result) == 1
    assert result[0].timestamp == snap.timestamp
    assert result[0].total_issues == 10
    assert result[0].by_urgency == {"critical": 1, "high": 3, "medium": 4, "low": 2}


def test_read_with_limit(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    for i in range(5):
        store.append(_make_snapshot(f"2026-08-0{i + 1}T00:00:00+00:00"))
    result = store.read(limit=3)
    assert len(result) == 3
    assert result[0].timestamp == "2026-08-03T00:00:00+00:00"


def test_read_with_since(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    store.append(_make_snapshot("2026-07-01T00:00:00+00:00"))
    store.append(_make_snapshot("2026-08-01T00:00:00+00:00"))
    store.append(_make_snapshot("2026-08-05T00:00:00+00:00"))
    result = store.read(since="2026-08-01T00:00:00+00:00")
    assert len(result) == 2
    assert result[0].timestamp == "2026-08-01T00:00:00+00:00"


def test_read_empty_file(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    result = store.read()
    assert result == []


def test_read_missing_file(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "nonexistent" / "metrics.jsonl")
    result = store.read()
    assert result == []


def test_corrupted_line_skipped(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    store = JsonlMetricsStore(path)
    store.append(_make_snapshot("2026-08-01T00:00:00+00:00"))
    with open(path, "a") as f:
        f.write("not valid json\n")
    store.append(_make_snapshot("2026-08-02T00:00:00+00:00"))
    result = store.read()
    assert len(result) == 2
    assert result[0].timestamp == "2026-08-01T00:00:00+00:00"
    assert result[1].timestamp == "2026-08-02T00:00:00+00:00"


def test_none_fields_roundtrip(tmp_path: Path):
    store = JsonlMetricsStore(tmp_path / "metrics.jsonl")
    snap = MetricsSnapshot(
        timestamp="2026-08-01T00:00:00+00:00",
        period_label="Jul 28 – Aug 3, 2026",
        total_issues=5,
        by_urgency={"medium": 5},
        by_team={"agent-ops": 5},
        triage_needed=2,
        total_open=5,
        pr_total_open=None,
        pr_awaiting_review=None,
        pr_stale_14d=None,
        merge_velocity=None,
        avg_review_wait_days=None,
        vouch_pending=None,
        vouch_responded_7d=None,
        vouch_longest_wait=None,
    )
    store.append(snap)
    result = store.read()
    assert result[0].pr_total_open is None
    assert result[0].vouch_pending is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/metrics/test_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.metrics'`

- [ ] **Step 3: Create the models module**

Create `app/metrics/__init__.py` (empty).

Create `app/metrics/models.py`:

```python
from dataclasses import dataclass


@dataclass
class MetricsSnapshot:
    timestamp: str
    period_label: str

    total_issues: int
    by_urgency: dict[str, int]

    by_team: dict[str, int]

    triage_needed: int
    total_open: int

    pr_total_open: int | None
    pr_awaiting_review: int | None
    pr_stale_14d: int | None
    merge_velocity: int | None
    avg_review_wait_days: float | None

    vouch_pending: int | None
    vouch_responded_7d: int | None
    vouch_longest_wait: int | None
```

- [ ] **Step 4: Create the store module**

Create `app/metrics/store.py`:

```python
import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.metrics.models import MetricsSnapshot

logger = logging.getLogger(__name__)


class MetricsStore(Protocol):
    def append(self, snapshot: MetricsSnapshot) -> None: ...

    def read(
        self, *, since: str | None = None, limit: int | None = None
    ) -> list[MetricsSnapshot]: ...


class JsonlMetricsStore:
    def __init__(self, path: Path):
        self._path = path

    def append(self, snapshot: MetricsSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(asdict(snapshot)) + "\n")

    def read(
        self, *, since: str | None = None, limit: int | None = None
    ) -> list[MetricsSnapshot]:
        if not self._path.exists():
            return []

        since_dt = None
        if since:
            since_dt = datetime.fromisoformat(since)

        snapshots: list[MetricsSnapshot] = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping corrupted metrics line")
                    continue

                if since_dt:
                    try:
                        ts = datetime.fromisoformat(record["timestamp"])
                        if ts < since_dt:
                            continue
                    except (KeyError, ValueError):
                        continue

                snapshots.append(MetricsSnapshot(**record))

        if limit is not None:
            snapshots = snapshots[-limit:]

        return snapshots
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/metrics/test_store.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Run full test suite + lint**

```bash
make test
make lint
```

Expected: all 266+ tests pass, lint clean.

- [ ] **Step 7: Commit**

```bash
git add app/metrics/__init__.py app/metrics/models.py app/metrics/store.py tests/metrics/__init__.py tests/metrics/test_store.py
git commit -m "feat: add MetricsSnapshot model and JsonlMetricsStore"
```

---

### Task 2: compute_snapshot() and build_sparklines() pure functions

**Files:**
- Create: `app/metrics/compute.py`
- Create: `tests/metrics/test_compute.py`

**Interfaces:**
- Consumes:
  - `app.reports.models.BirdsEyeReport` (existing) — fields: `summary.by_urgency`, `summary.triage_needed`, `summary.total_open`, `summary.period_label`, `team_breakdown` (dict of `TeamSummary`), `pr_health` (dict or None), `vouch_status` (dict or None)
  - `app.metrics.models.MetricsSnapshot` from Task 1
- Produces:
  - `compute_snapshot(report: BirdsEyeReport, now: datetime) -> MetricsSnapshot`
  - `build_sparklines(snapshots: list[MetricsSnapshot]) -> dict[str, list[int]]` — returns keys `"triage"`, `"prs"`, `"blocked"`, `"velocity"` with lists of ints

- [ ] **Step 1: Write compute tests**

Create `tests/metrics/test_compute.py`:

```python
from datetime import datetime, timezone

from app.metrics.compute import build_sparklines, compute_snapshot
from app.metrics.models import MetricsSnapshot
from tests.reports.conftest import make_report


NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def test_compute_snapshot_basic():
    report = make_report()
    snap = compute_snapshot(report, NOW)
    assert snap.timestamp == NOW.isoformat()
    assert snap.period_label == "Jul 28 – Aug 3, 2026"
    assert snap.total_issues == 5
    assert snap.by_urgency == {"critical": 1, "high": 2, "medium": 1, "low": 1}
    assert snap.total_open == 5
    assert snap.triage_needed == 0


def test_compute_snapshot_team_breakdown():
    report = make_report()
    snap = compute_snapshot(report, NOW)
    assert snap.by_team == {"agent-ops": 3, "ai-safety": 2}


def test_compute_snapshot_with_pr_health():
    pr_data = {
        "total_open": 42,
        "awaiting_review": 5,
        "stale_14d": 3,
        "merge_velocity": 8,
        "merge_velocity_prev": 6,
        "avg_review_wait_days": 4.2,
        "stuck_prs": [],
        "age_distribution": {},
        "gator_coverage_pct": 60,
    }
    report = make_report(pr_health=pr_data)
    snap = compute_snapshot(report, NOW)
    assert snap.pr_total_open == 42
    assert snap.pr_awaiting_review == 5
    assert snap.pr_stale_14d == 3
    assert snap.merge_velocity == 8
    assert snap.avg_review_wait_days == 4.2


def test_compute_snapshot_without_pr_health():
    report = make_report(pr_health=None)
    snap = compute_snapshot(report, NOW)
    assert snap.pr_total_open is None
    assert snap.pr_awaiting_review is None
    assert snap.merge_velocity is None


def test_compute_snapshot_with_vouch_status():
    vouch_data = {
        "total_pending": 3,
        "responded_in_7d": 1,
        "longest_wait_days": 45,
        "over_30d_count": 2,
        "pending_vouches": [],
    }
    report = make_report(vouch_status=vouch_data)
    snap = compute_snapshot(report, NOW)
    assert snap.vouch_pending == 3
    assert snap.vouch_responded_7d == 1
    assert snap.vouch_longest_wait == 45


def test_compute_snapshot_without_vouch():
    report = make_report(vouch_status=None)
    snap = compute_snapshot(report, NOW)
    assert snap.vouch_pending is None
    assert snap.vouch_responded_7d is None


def test_compute_snapshot_empty_team_breakdown():
    report = make_report(team_breakdown={})
    snap = compute_snapshot(report, NOW)
    assert snap.by_team == {}


def test_build_sparklines_basic():
    snaps = [
        MetricsSnapshot(
            timestamp=f"2026-08-0{i}T00:00:00+00:00",
            period_label="test",
            total_issues=10 + i,
            by_urgency={"critical": i},
            by_team={"agent-ops": 5},
            triage_needed=i,
            total_open=10,
            pr_total_open=40 + i,
            pr_awaiting_review=3 + i,
            pr_stale_14d=1,
            merge_velocity=5 + i,
            avg_review_wait_days=2.0,
            vouch_pending=2 + i,
            vouch_responded_7d=1,
            vouch_longest_wait=30,
        )
        for i in range(7)
    ]
    result = build_sparklines(snaps)
    assert result["triage"] == [0, 1, 2, 3, 4, 5, 6]
    assert result["prs"] == [3, 4, 5, 6, 7, 8, 9]
    assert result["blocked"] == [2, 3, 4, 5, 6, 7, 8]
    assert result["velocity"] == [5, 6, 7, 8, 9, 10, 11]


def test_build_sparklines_none_fields_become_zero():
    snap = MetricsSnapshot(
        timestamp="2026-08-01T00:00:00+00:00",
        period_label="test",
        total_issues=5,
        by_urgency={},
        by_team={},
        triage_needed=2,
        total_open=5,
        pr_total_open=None,
        pr_awaiting_review=None,
        pr_stale_14d=None,
        merge_velocity=None,
        avg_review_wait_days=None,
        vouch_pending=None,
        vouch_responded_7d=None,
        vouch_longest_wait=None,
    )
    result = build_sparklines([snap])
    assert result["prs"] == [0]
    assert result["blocked"] == [0]
    assert result["velocity"] == [0]


def test_build_sparklines_empty():
    result = build_sparklines([])
    assert result == {"triage": [], "prs": [], "blocked": [], "velocity": []}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/metrics/test_compute.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.metrics.compute'`

- [ ] **Step 3: Implement compute_snapshot and build_sparklines**

Create `app/metrics/compute.py`:

```python
from datetime import datetime

from app.metrics.models import MetricsSnapshot
from app.reports.models import BirdsEyeReport


def compute_snapshot(report: BirdsEyeReport, now: datetime) -> MetricsSnapshot:
    summary = report.summary
    by_team = {
        team_id: ts.total for team_id, ts in report.team_breakdown.items()
    }

    pr = report.pr_health
    vouch = report.vouch_status

    return MetricsSnapshot(
        timestamp=now.isoformat(),
        period_label=summary.period_label,
        total_issues=summary.new_this_period,
        by_urgency=dict(summary.by_urgency),
        by_team=by_team,
        triage_needed=summary.triage_needed,
        total_open=summary.total_open,
        pr_total_open=pr["total_open"] if pr else None,
        pr_awaiting_review=pr["awaiting_review"] if pr else None,
        pr_stale_14d=pr["stale_14d"] if pr else None,
        merge_velocity=pr["merge_velocity"] if pr else None,
        avg_review_wait_days=pr["avg_review_wait_days"] if pr else None,
        vouch_pending=vouch["total_pending"] if vouch else None,
        vouch_responded_7d=vouch["responded_in_7d"] if vouch else None,
        vouch_longest_wait=vouch["longest_wait_days"] if vouch else None,
    )


def build_sparklines(snapshots: list[MetricsSnapshot]) -> dict[str, list[int]]:
    return {
        "triage": [s.triage_needed for s in snapshots],
        "prs": [s.pr_awaiting_review or 0 for s in snapshots],
        "blocked": [s.vouch_pending or 0 for s in snapshots],
        "velocity": [s.merge_velocity or 0 for s in snapshots],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/metrics/test_compute.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Run full test suite + lint**

```bash
make test
make lint
```

Expected: all tests pass, lint clean.

- [ ] **Step 6: Commit**

```bash
git add app/metrics/compute.py tests/metrics/test_compute.py
git commit -m "feat: add compute_snapshot and build_sparklines functions"
```

---

### Task 3: Wire metrics into triage runs + dashboard rendering

**Files:**
- Modify: `app/config.py` (line 18, after `vouch_tracking_enabled`)
- Modify: `app/triage.py:164-213` (`run_report()`)
- Modify: `app/server.py:109-178` (`_run_cycle()`)
- Modify: `app/reports/renderers/html.py:30-97` (`_report_to_dict` and `render_html`)
- Modify: `tests/reports/test_html_renderer.py:120-123`

**Interfaces:**
- Consumes:
  - `JsonlMetricsStore(path: Path)` from Task 1
  - `compute_snapshot(report, now)` from Task 2
  - `build_sparklines(snapshots)` from Task 2
- Produces: real sparkline data in the rendered HTML dashboard

- [ ] **Step 1: Add metrics_path to TriageConfig**

In `app/config.py`, add field to the dataclass (after `vouch_tracking_enabled` on line 25):

```python
metrics_path: Path = Path("/data/metrics.jsonl")
```

In `load_config()`, add to the `return TriageConfig(...)` block (after line 80, before the closing paren):

```python
metrics_path=Path(os.environ.get("METRICS_PATH", "/data/metrics.jsonl")),
```

- [ ] **Step 2: Update render_html to accept sparklines parameter**

In `app/reports/renderers/html.py`, change `_report_to_dict` signature (line 30) to:

```python
def _report_to_dict(
    report: BirdsEyeReport,
    enrichment: dict | None = None,
    sparklines: dict[str, list[int]] | None = None,
) -> dict:
```

Replace the hardcoded sparklines block (lines 90-95):

```python
    data["sparklines"] = sparklines or {
        "triage": [0, 0, 0, 0, 0, 0, 0],
        "prs": [0, 0, 0, 0, 0, 0, 0],
        "blocked": [0, 0, 0, 0, 0, 0, 0],
        "velocity": [0, 0, 0, 0, 0, 0, 0],
    }
```

Change `render_html` signature (line 100) to:

```python
def render_html(
    report: BirdsEyeReport,
    enrichment: dict | None = None,
    sparklines: dict[str, list[int]] | None = None,
) -> str:
    data = _report_to_dict(report, enrichment, sparklines)
```

- [ ] **Step 3: Wire into run_report() in triage.py**

In `app/triage.py`, add imports in the `run_report()` function body (after line 171, alongside the other deferred imports):

```python
from app.metrics.compute import build_sparklines, compute_snapshot
from app.metrics.store import JsonlMetricsStore
```

After `enrich_report(report, config, repo_config)` (after line 198), add:

```python
    sparklines = None
    try:
        store = JsonlMetricsStore(config.metrics_path)
        snapshot = compute_snapshot(report, now)
        store.append(snapshot)
        recent = store.read(limit=7)
        sparklines = build_sparklines(recent)
    except Exception:
        logger.exception("Metrics collection failed")
```

Update the `render_html` call (line 213) to pass sparklines:

```python
        output = render_html(report, enrichment=enrichment, sparklines=sparklines)
```

- [ ] **Step 4: Wire into _run_cycle() in server.py**

In `app/server.py`, inside `_run_cycle()`, after `enrich_report(report, config, repo_config)` (after line 166), add:

```python
        sparklines = None
        try:
            from app.metrics.compute import build_sparklines, compute_snapshot
            from app.metrics.store import JsonlMetricsStore

            store = JsonlMetricsStore(config.metrics_path)
            snapshot = compute_snapshot(report, now)
            store.append(snapshot)
            recent = store.read(limit=7)
            sparklines = build_sparklines(recent)
        except Exception:
            logger.exception("Metrics collection failed")
```

Update the `render_html` call (line 170) to pass sparklines:

```python
        app.state.cached_html = render_html(report, enrichment=enrichment, sparklines=sparklines)
```

- [ ] **Step 5: Update existing sparkline test**

In `tests/reports/test_html_renderer.py`, update `test_report_to_dict_adds_sparklines` (line 120-123):

```python
def test_report_to_dict_adds_sparklines():
    result = _report_to_dict(make_report())
    assert "sparklines" in result
    assert len(result["sparklines"]["triage"]) == 7
```

- [ ] **Step 6: Add test for real sparklines passed through**

In `tests/reports/test_html_renderer.py`, add after the updated test:

```python
def test_report_to_dict_uses_passed_sparklines():
    sparklines = {
        "triage": [1, 2, 3, 4, 5, 6, 7],
        "prs": [3, 3, 4, 4, 5, 5, 6],
        "blocked": [2, 2, 1, 1, 0, 0, 0],
        "velocity": [5, 6, 7, 8, 8, 9, 10],
    }
    result = _report_to_dict(make_report(), sparklines=sparklines)
    assert result["sparklines"]["triage"] == [1, 2, 3, 4, 5, 6, 7]
    assert result["sparklines"]["velocity"] == [5, 6, 7, 8, 8, 9, 10]
```

- [ ] **Step 7: Run full test suite + lint**

```bash
make test
make lint
```

Expected: all tests pass (including updated sparkline length from 5 → 7), lint clean.

- [ ] **Step 8: Commit**

```bash
git add app/config.py app/triage.py app/server.py app/reports/renderers/html.py tests/reports/test_html_renderer.py
git commit -m "feat: wire historical metrics into triage runs and dashboard"
```
