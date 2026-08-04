# Phase 2: Bird's Eye View Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add weekly cross-team bird's eye view report with duplicate detection, computed from the JSONL assessment log built in Phase 1.

**Architecture:** Extend assessment_log.py with period-based queries. New `app/reports/` package contains data models, duplicate detector, report generator, and markdown renderer. Report generator computes all sections from TriageResult lists; one Sonnet call generates the narrative summary. CLI gets `--mode report` with optional `--output` flag.

**Tech Stack:** Python 3.12, dataclasses, existing LLMClientProtocol, pytest

## Global Constraints

- Run `make lint` before pushing. Never include Co-Authored-By lines in commits.
- One logical change per commit, squash before review.
- Do not rewrite what already works — Phase 1 code is stable (148 tests passing).
- `app/core/models.py` provides `TriageResult`, `Urgency`, `IssueData`, `IssueSignals` — do NOT modify.
- `app/core/llm.py` provides `LLMClientProtocol` with `.assess(system_prompt, user_prompt, model) -> dict | None` — do NOT modify.
- `app/state/assessment_log.py` provides `append_result()`, `read_results()`, `result_to_record()`, `record_to_result()`, `format_review()` — extend, do NOT rewrite.
- `app/config.py` provides `TriageConfig` — add fields, do NOT rewrite.
- `profiles/openshell.yaml` has `reporting: {period: weekly, period_start: monday, timezone: UTC}` — read-only.
- Test command: `python3 -m pytest tests/ -q`
- Lint command: `make lint`

---

### Task 1: Extend assessment_log with period queries + report data models

**Files:**
- Modify: `app/state/assessment_log.py`
- Create: `app/reports/__init__.py`
- Create: `app/reports/models.py`
- Test: `tests/state/test_assessment_log.py` (extend)
- Create: `tests/reports/__init__.py`
- Create: `tests/reports/test_models.py`

**Interfaces:**
- Consumes: `TriageResult`, `Urgency` from `app.core.models`
- Produces:
  - `read_results(log_path, *, since_hours, start_date, end_date, team_filter, urgency_filter) -> list[dict]` (extended)
  - `read_results_as_triage(log_path, **kwargs) -> list[TriageResult]` (new convenience)
  - `ReportSummary(new_this_period, by_urgency, period_label)` dataclass
  - `TeamSummary(team_id, total, by_urgency, new_this_period, previous_period, trend)` dataclass
  - `AreaTrend(area, current_count, previous_count, delta, trend)` dataclass
  - `DuplicateCluster(area, issues, similarity_reason)` dataclass
  - `BirdsEyeReport(summary, critical_list, team_breakdown, area_heatmap, duplicate_clusters, no_team_list, narrative, generated_at)` dataclass

- [ ] **Step 1: Write failing tests for period-based query**

```python
# tests/state/test_assessment_log.py — ADD these tests

def test_read_results_start_date_filters(tmp_path):
    log_path = tmp_path / "log.jsonl"
    old_result = make_result(assessed_at="2026-07-01T10:00:00+00:00")
    new_result = make_result(assessed_at="2026-07-28T10:00:00+00:00", issue_number=2)
    append_result(log_path, old_result)
    append_result(log_path, new_result)

    records = read_results(log_path, start_date="2026-07-20T00:00:00+00:00")
    assert len(records) == 1
    assert records[0]["issue_number"] == 2


def test_read_results_end_date_filters(tmp_path):
    log_path = tmp_path / "log.jsonl"
    old_result = make_result(assessed_at="2026-07-01T10:00:00+00:00")
    new_result = make_result(assessed_at="2026-07-28T10:00:00+00:00", issue_number=2)
    append_result(log_path, old_result)
    append_result(log_path, new_result)

    records = read_results(log_path, end_date="2026-07-15T00:00:00+00:00")
    assert len(records) == 1
    assert records[0]["issue_number"] == 1


def test_read_results_date_range(tmp_path):
    log_path = tmp_path / "log.jsonl"
    for i, date in enumerate(["2026-07-01T10:00:00+00:00", "2026-07-15T10:00:00+00:00", "2026-07-28T10:00:00+00:00"]):
        append_result(log_path, make_result(assessed_at=date, issue_number=i + 1))

    records = read_results(log_path, start_date="2026-07-10T00:00:00+00:00", end_date="2026-07-20T00:00:00+00:00")
    assert len(records) == 1
    assert records[0]["issue_number"] == 2


def test_read_results_as_triage(tmp_path):
    log_path = tmp_path / "log.jsonl"
    result = make_result()
    append_result(log_path, result)

    triage_results = read_results_as_triage(log_path)
    assert len(triage_results) == 1
    assert isinstance(triage_results[0], TriageResult)
    assert triage_results[0].issue_number == result.issue_number
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/state/test_assessment_log.py -v -k "start_date or end_date or date_range or as_triage"`
Expected: FAIL — `start_date`, `end_date` params don't exist, `read_results_as_triage` not defined

- [ ] **Step 3: Implement period-based filtering in assessment_log.py**

Add `start_date: str | None = None` and `end_date: str | None = None` parameters to `read_results()`. In the filtering logic, after the existing `cutoff` check, add:

```python
if start_date:
    try:
        start_dt = datetime.fromisoformat(start_date)
        assessed = datetime.fromisoformat(record["assessed_at"])
        if assessed < start_dt:
            continue
    except (KeyError, ValueError):
        continue

if end_date:
    try:
        end_dt = datetime.fromisoformat(end_date)
        assessed = datetime.fromisoformat(record["assessed_at"])
        if assessed > end_dt:
            continue
    except (KeyError, ValueError):
        continue
```

Add convenience function:

```python
def read_results_as_triage(
    log_path: Path,
    **kwargs,
) -> list[TriageResult]:
    records = read_results(log_path, **kwargs)
    return [record_to_result(r) for r in records]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/state/test_assessment_log.py -v`
Expected: ALL PASS

- [ ] **Step 5: Write report data models**

Create `app/reports/__init__.py` (empty).
Create `app/reports/models.py`:

```python
from dataclasses import dataclass, field

from app.core.models import TriageResult


@dataclass
class ReportSummary:
    new_this_period: int
    by_urgency: dict[str, int]
    period_label: str


@dataclass
class TeamSummary:
    team_id: str
    total: int
    by_urgency: dict[str, int]
    new_this_period: int
    previous_period: int
    trend: str


@dataclass
class AreaTrend:
    area: str
    current_count: int
    previous_count: int
    delta: int
    trend: str


@dataclass
class DuplicateCluster:
    area: str
    issues: list[TriageResult]
    similarity_reason: str


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

- [ ] **Step 6: Write model tests**

Create `tests/reports/__init__.py` (empty).
Create `tests/reports/test_models.py`:

```python
from app.reports.models import (
    AreaTrend,
    BirdsEyeReport,
    DuplicateCluster,
    ReportSummary,
    TeamSummary,
)


def test_report_summary_creation():
    s = ReportSummary(new_this_period=12, by_urgency={"critical": 2, "high": 7}, period_label="Jul 28 – Aug 3, 2026")
    assert s.new_this_period == 12
    assert s.by_urgency["critical"] == 2


def test_team_summary_creation():
    ts = TeamSummary(team_id="agent-ops", total=38, by_urgency={"critical": 0, "high": 3}, new_this_period=5, previous_period=3, trend="+2")
    assert ts.team_id == "agent-ops"
    assert ts.trend == "+2"


def test_area_trend_creation():
    at = AreaTrend(area="gateway", current_count=10, previous_count=2, delta=8, trend="spike")
    assert at.delta == 8
    assert at.trend == "spike"


def test_birds_eye_report_creation():
    summary = ReportSummary(new_this_period=0, by_urgency={}, period_label="test")
    report = BirdsEyeReport(
        summary=summary,
        critical_list=[],
        team_breakdown={},
        area_heatmap={},
        duplicate_clusters=[],
        no_team_list=[],
        narrative="No issues.",
        generated_at="2026-08-04T00:00:00+00:00",
    )
    assert report.narrative == "No issues."
    assert report.generated_at == "2026-08-04T00:00:00+00:00"
```

- [ ] **Step 7: Run all tests**

Run: `python3 -m pytest tests/state/test_assessment_log.py tests/reports/test_models.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add app/state/assessment_log.py app/reports/__init__.py app/reports/models.py tests/reports/__init__.py tests/reports/test_models.py tests/state/test_assessment_log.py
git commit -m "feat: extend assessment log with period queries, add report data models"
```

---

### Task 2: Duplicate detector

**Files:**
- Create: `app/reports/duplicates.py`
- Create: `tests/reports/test_duplicates.py`

**Interfaces:**
- Consumes: `TriageResult` from `app.core.models`, `DuplicateCluster` from `app.reports.models`
- Produces: `DuplicateDetector` class with `detect(results: list[TriageResult]) -> list[DuplicateCluster]`

Detection algorithm:
1. Extract title prefix from each result's `issue_title` using same `type(area):` regex as triage_engine
2. Group results by extracted area prefix
3. Within each group of 2+ issues, compute pairwise title token overlap
4. Two issues are potential duplicates if they share 2+ meaningful tokens (excluding stopwords and the prefix itself)
5. Only consider issues within a 7-day window of each other
6. Build clusters from connected pairs (if A~B and B~C, cluster is {A,B,C})
7. Return list of DuplicateCluster with area, issues, and similarity_reason (shared tokens)

Stopwords to exclude: common English words plus common OpenShell terms that appear everywhere ("fix", "feat", "bug", "add", "update", "issue", "error", "support", "when", "with", "from", "that", "this", "the", "for", "not", "and").

- [ ] **Step 1: Write failing tests**

```python
# tests/reports/test_duplicates.py
from app.core.models import TriageResult, Urgency
from app.reports.duplicates import DuplicateDetector


def _make_result(number, title, assessed_at="2026-07-28T10:00:00+00:00"):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=number,
        issue_title=title,
        issue_url=f"https://github.com/NVIDIA/OpenShell/issues/{number}",
        reasoning="test",
        any_team_cares=True,
        primary_team="agent-ops",
        primary_confidence=0.9,
        secondary_team=None,
        secondary_confidence=None,
        urgency=Urgency.MEDIUM,
        urgency_reasoning="test",
        summary="test",
        recommendation="test",
        confidence_flag=None,
        assessed_at=assessed_at,
    )


def test_detect_duplicates_by_shared_tokens():
    results = [
        _make_result(1, "feat(sandbox): add user namespace support"),
        _make_result(2, "bug(sandbox): enableUserNamespaces fails on namespace creation"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 1
    assert clusters[0].area == "sandbox"
    assert len(clusters[0].issues) == 2
    assert "namespace" in clusters[0].similarity_reason.lower()


def test_no_duplicates_different_areas():
    results = [
        _make_result(1, "feat(cli): add sandbox prune command"),
        _make_result(2, "feat(gateway): connection pool timeout"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 0


def test_no_duplicates_outside_time_window():
    results = [
        _make_result(1, "feat(sandbox): add user namespace support", "2026-07-01T10:00:00+00:00"),
        _make_result(2, "bug(sandbox): user namespace fails", "2026-07-20T10:00:00+00:00"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 0


def test_stopwords_excluded():
    results = [
        _make_result(1, "fix(cli): add support for new flag"),
        _make_result(2, "feat(cli): update support for old flag"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 1
    reason = clusters[0].similarity_reason.lower()
    assert "flag" in reason


def test_single_issue_no_cluster():
    results = [_make_result(1, "feat(sandbox): add namespace support")]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 0


def test_cluster_merges_transitive():
    results = [
        _make_result(1, "feat(sandbox): user namespace creation"),
        _make_result(2, "bug(sandbox): namespace creation fails"),
        _make_result(3, "fix(sandbox): creation timeout on namespace"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 1
    assert len(clusters[0].issues) == 3


def test_no_prefix_issues_grouped_by_body_tokens():
    results = [
        _make_result(1, "VM sandbox SSH disconnects randomly"),
        _make_result(2, "VM sandbox SSH connection drops"),
    ]
    detector = DuplicateDetector()
    clusters = detector.detect(results)
    assert len(clusters) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/reports/test_duplicates.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement DuplicateDetector**

Create `app/reports/duplicates.py`:

```python
import re
from datetime import datetime, timedelta

from app.core.models import TriageResult
from app.reports.models import DuplicateCluster

_PREFIX_RE = re.compile(r"^(?:feat|fix|bug|chore|docs|refactor|test|ci)\(([^)]+)\):\s*")

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "not", "be", "as", "was",
    "that", "this", "are", "were", "been", "has", "have", "had", "do",
    "does", "did", "will", "would", "can", "could", "should", "may",
    "when", "if", "then", "than", "so", "no", "all", "any", "each",
    "feat", "fix", "bug", "add", "update", "issue", "error", "support",
    "new", "old", "use", "using", "set", "get",
})

_WINDOW_DAYS = 7
_MIN_SHARED_TOKENS = 2


def _extract_prefix(title: str) -> str | None:
    m = _PREFIX_RE.match(title)
    return m.group(1) if m else None


def _tokenize(title: str) -> set[str]:
    clean = _PREFIX_RE.sub("", title)
    tokens = re.findall(r"[a-zA-Z]{3,}", clean.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def _within_window(a: TriageResult, b: TriageResult) -> bool:
    try:
        ta = datetime.fromisoformat(a.assessed_at)
        tb = datetime.fromisoformat(b.assessed_at)
        return abs((ta - tb).total_seconds()) <= _WINDOW_DAYS * 86400
    except (ValueError, TypeError):
        return False


class DuplicateDetector:
    def detect(self, results: list[TriageResult]) -> list[DuplicateCluster]:
        groups: dict[str, list[TriageResult]] = {}
        for r in results:
            prefix = _extract_prefix(r.issue_title)
            key = prefix if prefix else "__no_prefix__"
            groups.setdefault(key, []).append(r)

        clusters = []
        for area, group in groups.items():
            if len(group) < 2:
                continue

            token_sets = [(r, _tokenize(r.issue_title)) for r in group]

            adj: dict[int, set[int]] = {i: set() for i in range(len(group))}
            shared_tokens_map: dict[tuple[int, int], set[str]] = {}

            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if not _within_window(group[i], group[j]):
                        continue
                    shared = token_sets[i][1] & token_sets[j][1]
                    if len(shared) >= _MIN_SHARED_TOKENS:
                        adj[i].add(j)
                        adj[j].add(i)
                        shared_tokens_map[(i, j)] = shared

            visited = set()
            for start in range(len(group)):
                if start in visited or not adj[start]:
                    continue
                component = set()
                stack = [start]
                while stack:
                    node = stack.pop()
                    if node in component:
                        continue
                    component.add(node)
                    stack.extend(adj[node] - component)
                visited |= component

                all_shared = set()
                for i in component:
                    for j in component:
                        if i < j and (i, j) in shared_tokens_map:
                            all_shared |= shared_tokens_map[(i, j)]

                cluster_area = area if area != "__no_prefix__" else "no-prefix"
                clusters.append(DuplicateCluster(
                    area=cluster_area,
                    issues=[group[i] for i in sorted(component)],
                    similarity_reason=f"shared: {', '.join(sorted(all_shared))}",
                ))

        return clusters
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/reports/test_duplicates.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: ALL PASS (148 existing + new)

- [ ] **Step 6: Commit**

```bash
git add app/reports/duplicates.py tests/reports/test_duplicates.py
git commit -m "feat: add duplicate issue detector with token overlap clustering"
```

---

### Task 3: Bird's eye report generator

**Files:**
- Create: `app/reports/birds_eye.py`
- Create: `tests/reports/test_birds_eye.py`

**Interfaces:**
- Consumes:
  - `TriageResult`, `Urgency` from `app.core.models`
  - `ReportSummary`, `TeamSummary`, `AreaTrend`, `BirdsEyeReport`, `DuplicateCluster` from `app.reports.models`
  - `DuplicateDetector` from `app.reports.duplicates`
  - `LLMClientProtocol` from `app.core.llm`
- Produces: `BirdsEyeReportGenerator` class with `generate() -> BirdsEyeReport`

Constructor: `BirdsEyeReportGenerator(current: list[TriageResult], previous: list[TriageResult], llm_client: LLMClientProtocol, model: str, period_label: str)`

The generate() method:
1. Compute ReportSummary from current results
2. Extract critical_list: results where urgency is CRITICAL or HIGH, sorted by urgency then issue_number
3. Compute TeamSummary for each team: count by urgency, compare to previous period for trend
4. Compute AreaTrend: extract title prefix from each result, count per prefix, compare to previous
5. Run DuplicateDetector on current results
6. Extract no_team_list: results where primary_team == "none"
7. Build narrative prompt from computed data, send to LLM for a 2-3 sentence summary
8. Assemble BirdsEyeReport

Trend calculation: `delta = current - previous`. If delta > 0: "+N". If delta < 0: str(delta). If delta == 0: "flat".

- [ ] **Step 1: Write failing tests**

```python
# tests/reports/test_birds_eye.py
from unittest.mock import MagicMock

from app.core.models import TriageResult, Urgency
from app.reports.birds_eye import BirdsEyeReportGenerator
from app.reports.models import BirdsEyeReport


def _make_result(
    number=1,
    title="feat(cli): test issue",
    team="agent-ops",
    urgency=Urgency.MEDIUM,
    assessed_at="2026-07-28T10:00:00+00:00",
    any_team_cares=True,
):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=number,
        issue_title=title,
        issue_url=f"https://github.com/NVIDIA/OpenShell/issues/{number}",
        reasoning="test",
        any_team_cares=any_team_cares,
        primary_team=team,
        primary_confidence=0.9,
        secondary_team=None,
        secondary_confidence=None,
        urgency=urgency,
        urgency_reasoning="test",
        summary="test summary",
        recommendation="test recommendation",
        confidence_flag=None,
        assessed_at=assessed_at,
    )


def _mock_llm(narrative="No notable trends this period."):
    client = MagicMock()
    client.assess.return_value = {"narrative": narrative}
    return client


def test_generate_empty_report():
    gen = BirdsEyeReportGenerator([], [], _mock_llm(), "claude-sonnet-4-6", "Jul 28 – Aug 3")
    report = gen.generate()
    assert isinstance(report, BirdsEyeReport)
    assert report.summary.new_this_period == 0
    assert report.critical_list == []
    assert report.team_breakdown == {}
    assert report.duplicate_clusters == []


def test_generate_summary_counts():
    current = [
        _make_result(1, urgency=Urgency.CRITICAL),
        _make_result(2, urgency=Urgency.HIGH),
        _make_result(3, urgency=Urgency.MEDIUM),
        _make_result(4, urgency=Urgency.MEDIUM),
        _make_result(5, urgency=Urgency.LOW),
    ]
    gen = BirdsEyeReportGenerator(current, [], _mock_llm(), "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert report.summary.new_this_period == 5
    assert report.summary.by_urgency == {"critical": 1, "high": 1, "medium": 2, "low": 1}


def test_critical_list_sorted():
    current = [
        _make_result(1, urgency=Urgency.MEDIUM),
        _make_result(2, urgency=Urgency.CRITICAL),
        _make_result(3, urgency=Urgency.HIGH),
    ]
    gen = BirdsEyeReportGenerator(current, [], _mock_llm(), "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert len(report.critical_list) == 2
    assert report.critical_list[0].urgency == Urgency.CRITICAL
    assert report.critical_list[1].urgency == Urgency.HIGH


def test_team_breakdown_with_trend():
    current = [
        _make_result(1, team="agent-ops"),
        _make_result(2, team="agent-ops"),
        _make_result(3, team="acp"),
    ]
    previous = [
        _make_result(10, team="agent-ops"),
    ]
    gen = BirdsEyeReportGenerator(current, previous, _mock_llm(), "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert "agent-ops" in report.team_breakdown
    assert report.team_breakdown["agent-ops"].total == 2
    assert report.team_breakdown["agent-ops"].previous_period == 1
    assert report.team_breakdown["agent-ops"].trend == "+1"
    assert "acp" in report.team_breakdown
    assert report.team_breakdown["acp"].previous_period == 0
    assert report.team_breakdown["acp"].trend == "+1"


def test_area_heatmap():
    current = [
        _make_result(1, title="feat(gateway): test 1"),
        _make_result(2, title="bug(gateway): test 2"),
        _make_result(3, title="feat(cli): test 3"),
    ]
    previous = [
        _make_result(10, title="feat(gateway): old"),
    ]
    gen = BirdsEyeReportGenerator(current, previous, _mock_llm(), "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert "gateway" in report.area_heatmap
    assert report.area_heatmap["gateway"].current_count == 2
    assert report.area_heatmap["gateway"].previous_count == 1
    assert report.area_heatmap["gateway"].delta == 1


def test_no_team_list():
    current = [
        _make_result(1, team="agent-ops"),
        _make_result(2, team="none", any_team_cares=False),
        _make_result(3, team="none", any_team_cares=False),
    ]
    gen = BirdsEyeReportGenerator(current, [], _mock_llm(), "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert len(report.no_team_list) == 2


def test_narrative_from_llm():
    llm = _mock_llm("Gateway saw unusual activity this week.")
    gen = BirdsEyeReportGenerator([_make_result(1)], [], llm, "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert report.narrative == "Gateway saw unusual activity this week."
    llm.assess.assert_called_once()


def test_narrative_fallback_on_llm_failure():
    llm = MagicMock()
    llm.assess.return_value = None
    gen = BirdsEyeReportGenerator([_make_result(1)], [], llm, "claude-sonnet-4-6", "test")
    report = gen.generate()
    assert report.narrative != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/reports/test_birds_eye.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement BirdsEyeReportGenerator**

Create `app/reports/birds_eye.py`. The class takes current + previous TriageResult lists, LLM client, model, and period label. The `generate()` method computes each section:

Key implementation details:
- Title prefix extraction uses same regex as duplicates.py: `r"^(?:feat|fix|bug|chore|docs|refactor|test|ci)\(([^)]+)\):\s*"`
- Urgency sort order for critical_list: `{"critical": 0, "high": 1, "medium": 2, "low": 3}`
- Trend calculation: `f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "flat"`
- Narrative prompt asks the LLM to summarize the report data in 2-3 sentences, highlight spikes and critical items
- LLM response expected as JSON: `{"narrative": "..."}`
- If LLM returns None, fallback narrative: `f"{len(current)} issues triaged this period."`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/reports/test_birds_eye.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add app/reports/birds_eye.py tests/reports/test_birds_eye.py
git commit -m "feat: add bird's eye report generator with LLM narrative"
```

---

### Task 4: Markdown renderer

**Files:**
- Create: `app/reports/renderers/__init__.py`
- Create: `app/reports/renderers/markdown.py`
- Create: `tests/reports/test_markdown_renderer.py`

**Interfaces:**
- Consumes: `BirdsEyeReport`, `ReportSummary`, `TeamSummary`, `AreaTrend`, `DuplicateCluster` from `app.reports.models`, `TriageResult`, `Urgency` from `app.core.models`
- Produces: `render_markdown(report: BirdsEyeReport) -> str`

Output format matches the design doc section 6 "Weekly bird's eye view report":

```
OpenShell Triage — Bird's Eye View
Period: {period_label}

SUMMARY
  {new_this_period} new issues
  {critical} critical | {high} high | {medium} medium | {low} low

  "{narrative}"
  — generated by Sonnet from the report data

CRITICAL & HIGH ISSUES
  #     | Issue                                        | Team      | Days Open
  {number} | {title}                                   | {team}    | {days}

TEAM BREAKDOWN
  Team          | Total | Crit | High | Med | Low | Trend
  {team_id}     | ...

AREA HEATMAP
  {area}   | {current} this week (was {previous}) — {trend}

POTENTIAL DUPLICATES
  Cluster N — {area} (shared: {tokens})
    #{number} {title} — {team}

NO RED HAT TEAM ({count} issues)
  #{number} {title}
```

- [ ] **Step 1: Write failing tests**

```python
# tests/reports/test_markdown_renderer.py
from app.core.models import TriageResult, Urgency
from app.reports.models import (
    AreaTrend,
    BirdsEyeReport,
    DuplicateCluster,
    ReportSummary,
    TeamSummary,
)
from app.reports.renderers.markdown import render_markdown


def _make_result(number=1, title="test issue", team="agent-ops", urgency=Urgency.MEDIUM):
    return TriageResult(
        repo="NVIDIA/OpenShell", issue_number=number, issue_title=title,
        issue_url=f"https://github.com/NVIDIA/OpenShell/issues/{number}",
        reasoning="test", any_team_cares=True, primary_team=team,
        primary_confidence=0.9, secondary_team=None, secondary_confidence=None,
        urgency=urgency, urgency_reasoning="test", summary="test",
        recommendation="test", confidence_flag=None, assessed_at="2026-07-28T10:00:00+00:00",
    )


def _make_report(**overrides):
    defaults = dict(
        summary=ReportSummary(new_this_period=5, by_urgency={"critical": 1, "high": 2, "medium": 1, "low": 1}, period_label="Jul 28 – Aug 3, 2026"),
        critical_list=[_make_result(1, "critical issue", urgency=Urgency.CRITICAL)],
        team_breakdown={"agent-ops": TeamSummary(team_id="agent-ops", total=3, by_urgency={"critical": 1, "high": 1, "medium": 1, "low": 0}, new_this_period=3, previous_period=2, trend="+1")},
        area_heatmap={"gateway": AreaTrend(area="gateway", current_count=5, previous_count=2, delta=3, trend="+3")},
        duplicate_clusters=[],
        no_team_list=[],
        narrative="Gateway saw unusual activity this week.",
        generated_at="2026-08-04T00:00:00+00:00",
    )
    defaults.update(overrides)
    return BirdsEyeReport(**defaults)


def test_render_contains_header():
    md = render_markdown(_make_report())
    assert "Bird's Eye View" in md
    assert "Jul 28 – Aug 3, 2026" in md


def test_render_contains_summary():
    md = render_markdown(_make_report())
    assert "5 new issues" in md
    assert "critical" in md.lower()


def test_render_contains_narrative():
    md = render_markdown(_make_report())
    assert "Gateway saw unusual activity" in md


def test_render_contains_critical_list():
    md = render_markdown(_make_report())
    assert "critical issue" in md


def test_render_contains_team_breakdown():
    md = render_markdown(_make_report())
    assert "agent-ops" in md


def test_render_contains_area_heatmap():
    md = render_markdown(_make_report())
    assert "gateway" in md


def test_render_contains_duplicates_when_present():
    cluster = DuplicateCluster(area="sandbox", issues=[_make_result(1, "ns support"), _make_result(2, "ns fails")], similarity_reason="shared: namespace")
    md = render_markdown(_make_report(duplicate_clusters=[cluster]))
    assert "sandbox" in md
    assert "namespace" in md


def test_render_contains_no_team_list():
    no_team = [_make_result(10, "build system change", team="none")]
    md = render_markdown(_make_report(no_team_list=no_team))
    assert "build system change" in md


def test_render_empty_report():
    report = BirdsEyeReport(
        summary=ReportSummary(new_this_period=0, by_urgency={}, period_label="test"),
        critical_list=[], team_breakdown={}, area_heatmap={},
        duplicate_clusters=[], no_team_list=[], narrative="No issues.", generated_at="2026-08-04T00:00:00+00:00",
    )
    md = render_markdown(report)
    assert "0 new issues" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/reports/test_markdown_renderer.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement render_markdown**

Create `app/reports/renderers/__init__.py` (empty).
Create `app/reports/renderers/markdown.py` with `render_markdown(report: BirdsEyeReport) -> str`.

Build the output string section by section, matching the design doc format. Use fixed-width columns for tables where practical. Skip sections with no data (e.g., skip POTENTIAL DUPLICATES if no clusters, skip NO RED HAT TEAM if empty).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/reports/test_markdown_renderer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add app/reports/renderers/__init__.py app/reports/renderers/markdown.py tests/reports/test_markdown_renderer.py
git commit -m "feat: add markdown renderer for bird's eye view report"
```

---

### Task 5: Wire reports into CLI and orchestrator

**Files:**
- Modify: `app/config.py`
- Modify: `app/triage.py`
- Modify: `app/__main__.py`
- Modify: `tests/test_main.py` (extend)
- Create: `tests/integration/test_report.py`

**Interfaces:**
- Consumes:
  - `read_results_as_triage()` from `app.state.assessment_log`
  - `BirdsEyeReportGenerator` from `app.reports.birds_eye`
  - `render_markdown` from `app.reports.renderers.markdown`
  - `load_repo_config` from `app.core.profiles`
  - `TriageConfig`, `load_config()` from `app.config`
- Produces:
  - `run_report(config, *, output_path)` in `app.triage`
  - `--mode report` CLI option
  - `--output` CLI option (file path, default stdout)

`run_report()` logic:
1. Load repo config for reporting settings (period, period_start, timezone)
2. Compute current period boundaries (e.g., this Monday 00:00 UTC to now for weekly/monday)
3. Compute previous period boundaries (last Monday to this Monday)
4. Read assessment log for both periods via `read_results_as_triage()`
5. Create LLM client, instantiate `BirdsEyeReportGenerator`
6. Call `generate()` → `BirdsEyeReport`
7. Call `render_markdown(report)` → string
8. Print to stdout or write to output file

Config additions to `TriageConfig`:
- `report_output_path: Path | None` — default None (stdout)

- [ ] **Step 1: Write failing tests**

```python
# tests/integration/test_report.py
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import TriageConfig
from app.triage import run_report


def _make_config(tmp_path):
    log_path = tmp_path / "assessments.jsonl"
    log_path.touch()
    return TriageConfig(
        watch_repos=["NVIDIA/OpenShell"],
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        vertex_project_id=None,
        vertex_region="us-east5",
        anthropic_api_key="test-key",
        github_token="test-token",
        slack_webhook_url=None,
        state_path=tmp_path / "state.json",
        assessment_log_path=log_path,
        profiles_dir=Path("profiles"),
        default_lookback_hours=24,
        report_output_path=None,
    )


@patch("app.triage._build_llm_client")
def test_run_report_empty_log(mock_llm, tmp_path, capsys):
    config = _make_config(tmp_path)
    llm = MagicMock()
    llm.assess.return_value = {"narrative": "No issues."}
    mock_llm.return_value = llm

    run_report(config)
    output = capsys.readouterr().out
    assert "Bird's Eye View" in output


@patch("app.triage._build_llm_client")
def test_run_report_writes_to_file(mock_llm, tmp_path):
    config = _make_config(tmp_path)
    output_path = tmp_path / "report.md"
    config.report_output_path = output_path
    llm = MagicMock()
    llm.assess.return_value = {"narrative": "Test narrative."}
    mock_llm.return_value = llm

    run_report(config, output_path=output_path)
    assert output_path.exists()
    content = output_path.read_text()
    assert "Bird's Eye View" in content
```

Add to `tests/test_main.py`:

```python
def test_mode_report(monkeypatch):
    monkeypatch.setattr("sys.argv", ["app", "--mode", "report"])
    # Verify the parser accepts "report" as a valid mode
    from app.__main__ import main
    # (tested via argparse acceptance, actual run mocked in integration tests)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/integration/test_report.py -v`
Expected: FAIL — `run_report` not defined, `report_output_path` not in TriageConfig

- [ ] **Step 3: Implement config changes**

Add to `TriageConfig`:
```python
report_output_path: Path | None
```

Add to `load_config()`:
```python
report_output_path=Path(p) if (p := os.environ.get("REPORT_OUTPUT_PATH")) else None,
```

- [ ] **Step 4: Implement run_report in triage.py**

```python
def run_report(config: TriageConfig, *, output_path: Path | None = None) -> None:
    repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
    reporting = repo_config.reporting

    now = datetime.now(timezone.utc)
    period_days = 7 if reporting.get("period") == "weekly" else 1

    # Compute current period start (most recent period_start day)
    weekday_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    target_weekday = weekday_map.get(reporting.get("period_start", "monday"), 0)
    days_since = (now.weekday() - target_weekday) % 7
    current_start = (now - timedelta(days=days_since)).replace(hour=0, minute=0, second=0, microsecond=0)
    previous_start = current_start - timedelta(days=period_days)

    current = read_results_as_triage(
        config.assessment_log_path,
        start_date=current_start.isoformat(),
    )
    previous = read_results_as_triage(
        config.assessment_log_path,
        start_date=previous_start.isoformat(),
        end_date=current_start.isoformat(),
    )

    period_label = f"{current_start.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"

    llm_client = _build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)

    generator = BirdsEyeReportGenerator(current, previous, llm_client, model, period_label)
    report = generator.generate()

    md = render_markdown(report)

    dest = output_path or config.report_output_path
    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(md)
        logger.info(f"Report written to {dest}")
    else:
        print(md)
```

- [ ] **Step 5: Update __main__.py**

Add `"report"` to the `--mode` choices. Add `--output` argument. Call `run_report(config, output_path=args.output)` when mode is "report".

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 7: Run lint**

Run: `make lint`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/config.py app/triage.py app/__main__.py tests/integration/test_report.py tests/test_main.py
git commit -m "feat: wire bird's eye report into CLI with --mode report"
```
