# Median Time-to-First-Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the misleading "Avg Review Wait" tile (which only averages the 6 worst stuck PRs) with "Median First Review" — the median time from PR creation to first human review, computed from the 20 most recently merged PRs.

**Architecture:** Extend `_compute_merge_velocity()` to also fetch reviews for the 20 most recently merged PRs. For each, find the first non-bot, non-author review and compute `first_review_date - created_at` in days. Take the median. Rename the dataclass field from `avg_review_wait_days` to `median_first_review_days`. Update the tile label in the JS template. Remove the old stuck-PR average computation.

**Tech Stack:** Python 3.12 (dataclasses, statistics.median), GitHub REST API, inline JS in Jinja2 HTML templates

## Global Constraints

- NEVER include `Co-Authored-By` lines in commit messages
- No npm/build toolchain — CSS/JS is inline in HTML templates
- One logical change = one commit
- Always run `make lint` before pushing
- Always run `python3 -m pytest tests/ -q` before committing

---

## File Map

| File | Role | Change |
|------|------|--------|
| `app/pr_health/fetcher.py` | Fetches PR data from GitHub API | Extend `_compute_merge_velocity` to return median first-review time; remove old stuck-PR average |
| `app/pr_health/models.py` | Dataclass definitions | Rename `avg_review_wait_days` → `median_first_review_days` |
| `app/metrics/models.py` | Metrics snapshot dataclass | Rename `avg_review_wait_days` → `median_first_review_days` |
| `app/metrics/compute.py` | Builds metrics snapshots from reports | Update field reference |
| `app/reports/renderers/templates/components/pr_health.js` | KPI tiles | Update tile label and data source |
| `tests/pr_health/test_fetcher.py` | Fetcher tests | Add tests for median first-review computation |
| `tests/metrics/test_compute.py` | Metrics snapshot tests | Update field references |
| `tests/metrics/test_store.py` | Metrics store tests | Update field references |
| `tests/reports/test_enrich.py` | Enrich tests | Update field references |
| `tests/reports/test_html_renderer.py` | HTML renderer tests | Update field references |

---

### Task 1: Compute median time-to-first-review from merged PRs

**Files:**
- Modify: `app/pr_health/fetcher.py:249-279` (`_compute_merge_velocity` function)
- Modify: `app/pr_health/fetcher.py:54-59` (remove old stuck-PR average)
- Modify: `app/pr_health/fetcher.py:61-74` (update `fetch_pr_health` to use new return value)
- Test: `tests/pr_health/test_fetcher.py`

**Interfaces:**
- Consumes: GitHub REST API (`GET /repos/{repo}/pulls` with `state=closed`, `GET /repos/{repo}/pulls/{number}/reviews`)
- Consumes: `_gh_get()` helper (same file, line 12-15)
- Consumes: `_parse_dt()` helper (same file, line 18-19)
- Produces: `_compute_merge_velocity()` now returns `tuple[int, int, float | None]` — `(this_week_count, last_week_count, median_first_review_days)`
- Produces: `PRHealthFindings.median_first_review_days` (float or None, replacing `avg_review_wait_days`)

- [ ] **Step 1: Write the failing test for median first-review with reviews present**

In `tests/pr_health/test_fetcher.py`, add a new test. This test provides 3 merged PRs, each with one review at different delays, and asserts the median is correct.

The `mock_get.side_effect` sequence for `fetch_pr_health` is:
1. Open PRs (page 1)
2. Closed PRs (for velocity + first-review)
3. Reviews for merged PR #10 (first review 2d after creation)
4. Reviews for merged PR #11 (first review 5d after creation)
5. Reviews for merged PR #12 (first review 1d after creation)

```python
@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_median_first_review_from_merged_prs(mock_get, mock_dt):
    _patch_dt(mock_dt)
    merged_prs = [
        _make_pr(10, created_days_ago=20, merged_at=(NOW - timedelta(days=5)).isoformat()),
        _make_pr(11, created_days_ago=30, merged_at=(NOW - timedelta(days=3)).isoformat()),
        _make_pr(12, created_days_ago=15, merged_at=(NOW - timedelta(days=1)).isoformat()),
    ]
    reviews_10 = [{"user": {"login": "reviewer1"}, "submitted_at": (NOW - timedelta(days=18)).isoformat()}]
    reviews_11 = [{"user": {"login": "reviewer2"}, "submitted_at": (NOW - timedelta(days=25)).isoformat()}]
    reviews_12 = [{"user": {"login": "reviewer3"}, "submitted_at": (NOW - timedelta(days=14)).isoformat()}]
    mock_get.side_effect = [
        _make_response([]),       # open PRs (none)
        _make_response(merged_prs),  # closed PRs
        _make_response(reviews_10),  # reviews for PR #10
        _make_response(reviews_11),  # reviews for PR #11
        _make_response(reviews_12),  # reviews for PR #12
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert result.median_first_review_days == 2.0
```

Explanation of expected value: PR #10 was created 20d ago, first review 18d ago → 2d wait. PR #11 was created 30d ago, first review 25d ago → 5d wait. PR #12 was created 15d ago, first review 14d ago → 1d wait. Sorted: [1, 2, 5], median = 2.0.

- [ ] **Step 2: Write the failing test for median first-review with no reviews**

```python
@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_median_first_review_none_when_no_reviews(mock_get, mock_dt):
    _patch_dt(mock_dt)
    merged_prs = [
        _make_pr(10, created_days_ago=20, merged_at=(NOW - timedelta(days=5)).isoformat()),
    ]
    mock_get.side_effect = [
        _make_response([]),         # open PRs (none)
        _make_response(merged_prs), # closed PRs
        _make_response([]),         # reviews for PR #10 (none)
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert result.median_first_review_days is None
```

- [ ] **Step 3: Write the failing test for bot and self-review filtering**

```python
@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_median_first_review_filters_bots_and_self_reviews(mock_get, mock_dt):
    _patch_dt(mock_dt)
    merged_prs = [
        _make_pr(10, created_days_ago=20, author="contributor", merged_at=(NOW - timedelta(days=5)).isoformat()),
    ]
    reviews_10 = [
        {"user": {"login": "github-actions[bot]"}, "submitted_at": (NOW - timedelta(days=19)).isoformat()},
        {"user": {"login": "contributor"}, "submitted_at": (NOW - timedelta(days=18)).isoformat()},
        {"user": {"login": "real-reviewer"}, "submitted_at": (NOW - timedelta(days=15)).isoformat()},
    ]
    mock_get.side_effect = [
        _make_response([]),         # open PRs
        _make_response(merged_prs), # closed PRs
        _make_response(reviews_10), # reviews for PR #10
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert result.median_first_review_days == 5.0
```

Explanation: Bot review (1d) and self-review (2d) are filtered out. First real review is `real-reviewer` at 15d ago on a PR created 20d ago → 5d wait. Only 1 PR, so median = 5.0.

- [ ] **Step 4: Run tests to verify they fail**

Run: `python3 -m pytest tests/pr_health/test_fetcher.py::test_median_first_review_from_merged_prs tests/pr_health/test_fetcher.py::test_median_first_review_none_when_no_reviews tests/pr_health/test_fetcher.py::test_median_first_review_filters_bots_and_self_reviews -v`
Expected: All 3 FAIL (AttributeError: PRHealthFindings has no attribute `median_first_review_days`)

- [ ] **Step 5: Rename the dataclass field in `app/pr_health/models.py`**

In `app/pr_health/models.py`, change line 31:

```python
# BEFORE:
    avg_review_wait_days: float

# AFTER:
    median_first_review_days: float | None
```

Note: the type changes from `float` to `float | None` because when no merged PRs have reviews, the value is `None`.

- [ ] **Step 6: Implement `_compute_merge_velocity` to also return median first-review**

Replace the entire `_compute_merge_velocity` function in `app/pr_health/fetcher.py` (lines 249-279):

```python
def _compute_merge_velocity(
    repo: str, headers: dict, now: datetime,
) -> tuple[int, int, float | None]:
    try:
        merged_resp = _gh_get(
            f"{GITHUB_API}/repos/{repo}/pulls",
            headers,
            params={
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
            },
        )
    except Exception:
        logger.exception("Failed to fetch merged PRs")
        return 0, 0, None

    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    this_week = 0
    last_week = 0
    recently_merged = []

    for pr in merged_resp:
        if not pr.get("merged_at"):
            continue
        merged = _parse_dt(pr["merged_at"])
        if merged >= week_ago:
            this_week += 1
        elif merged >= two_weeks_ago:
            last_week += 1
        if len(recently_merged) < 20:
            recently_merged.append(pr)

    median_first_review = _compute_median_first_review(
        repo, recently_merged, headers,
    )

    return this_week, last_week, median_first_review
```

- [ ] **Step 7: Add the `_compute_median_first_review` helper function**

Add this new function right after `_compute_merge_velocity` (before the end of the file):

```python
def _compute_median_first_review(
    repo: str,
    merged_prs: list[dict],
    headers: dict,
) -> float | None:
    from statistics import median

    wait_times: list[float] = []
    for pr in merged_prs:
        author = pr["user"]["login"]
        created = _parse_dt(pr["created_at"])
        try:
            reviews = _gh_get(
                f"{GITHUB_API}/repos/{repo}/pulls/{pr['number']}/reviews",
                headers,
            )
        except Exception:
            logger.exception(
                "Failed to fetch reviews for PR #%d", pr["number"],
            )
            continue

        first_review_dt = None
        for r in reviews:
            reviewer = r["user"]["login"]
            if reviewer == author or reviewer.endswith("[bot]"):
                continue
            rd = _parse_dt(r["submitted_at"])
            if first_review_dt is None or rd < first_review_dt:
                first_review_dt = rd

        if first_review_dt is not None:
            wait_days = (first_review_dt - created).total_seconds() / 86400
            wait_times.append(round(wait_days, 1))

    if not wait_times:
        return None
    return round(median(wait_times), 1)
```

- [ ] **Step 8: Update `fetch_pr_health` to use the new return value**

In `app/pr_health/fetcher.py`, make two changes in `fetch_pr_health`:

1. Remove the old stuck-PR average computation (lines 54-59):

```python
# DELETE these lines:
    avg_review_wait = 0.0
    if stuck_prs:
        avg_review_wait = round(
            sum(p.days_since_last_review for p in stuck_prs) / len(stuck_prs),
            1,
        )
```

2. Update the `_compute_merge_velocity` call and the `PRHealthFindings` construction:

```python
# BEFORE (line 61):
    velocity, velocity_prev = _compute_merge_velocity(repo, headers, now)

# AFTER:
    velocity, velocity_prev, median_first_review = _compute_merge_velocity(
        repo, headers, now,
    )
```

```python
# BEFORE (line 70):
        avg_review_wait_days=avg_review_wait,

# AFTER:
        median_first_review_days=median_first_review,
```

- [ ] **Step 9: Run the 3 new tests to verify they pass**

Run: `python3 -m pytest tests/pr_health/test_fetcher.py::test_median_first_review_from_merged_prs tests/pr_health/test_fetcher.py::test_median_first_review_none_when_no_reviews tests/pr_health/test_fetcher.py::test_median_first_review_filters_bots_and_self_reviews -v`
Expected: All 3 PASS

- [ ] **Step 10: Run all existing fetcher tests to check for regressions**

Run: `python3 -m pytest tests/pr_health/test_fetcher.py -v`
Expected: Some tests will FAIL because their `mock_get.side_effect` sequences don't account for the new review-fetching API calls from `_compute_merge_velocity`. The tests that provide merged PRs in the velocity response (`test_merge_velocity_counts_by_week`) will need updated mock sequences.

- [ ] **Step 11: Fix `test_merge_velocity_counts_by_week` mock sequence**

This test provides 2 merged PRs (PR #10 and #11), so `_compute_merge_velocity` will now try to fetch reviews for each. Update the mock sequence:

```python
@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_merge_velocity_counts_by_week(mock_get, mock_dt):
    _patch_dt(mock_dt)
    closed_prs = [
        _make_pr(10, merged_at=(NOW - timedelta(days=2)).isoformat()),
        _make_pr(11, merged_at=(NOW - timedelta(days=5)).isoformat()),
        _make_pr(12, merged_at=(NOW - timedelta(days=10)).isoformat()),
        _make_pr(13),
    ]
    mock_get.side_effect = [
        _make_response([]),           # open PRs
        _make_response(closed_prs),   # closed PRs
        _make_response([]),           # reviews for PR #10
        _make_response([]),           # reviews for PR #11
        _make_response([]),           # reviews for PR #12
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert result.merge_velocity == 2
    assert result.merge_velocity_prev == 1
```

Note: only 3 review fetches for merged PRs #10, #11, #12. PR #13 has no `merged_at`, so it's skipped entirely.

- [ ] **Step 12: Fix `test_api_error_on_velocity_returns_zero`**

This test simulates the closed-PRs API call failing. Since `_compute_merge_velocity` now returns a 3-tuple on error `(0, 0, None)`, `fetch_pr_health` must unpack 3 values. The test itself doesn't need mock changes — the error prevents any review fetches — but the assertion should also check `median_first_review_days`:

```python
@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_api_error_on_velocity_returns_zero(mock_get, mock_dt):
    _patch_dt(mock_dt)
    import requests

    error_resp = MagicMock()
    error_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("403")

    mock_get.side_effect = [
        _make_response([]),
        error_resp,
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert result.merge_velocity == 0
    assert result.merge_velocity_prev == 0
    assert result.median_first_review_days is None
```

- [ ] **Step 13: Run all fetcher tests again**

Run: `python3 -m pytest tests/pr_health/test_fetcher.py -v`
Expected: All tests PASS

- [ ] **Step 14: Run the full test suite to find remaining references to `avg_review_wait_days`**

Run: `python3 -m pytest tests/ -q`
Expected: Several failures in `tests/metrics/`, `tests/reports/` — these still reference the old field name.

- [ ] **Step 15: Update `app/metrics/models.py` field name**

In `app/metrics/models.py`, line 21:

```python
# BEFORE:
    avg_review_wait_days: float | None

# AFTER:
    median_first_review_days: float | None
```

- [ ] **Step 16: Update `app/metrics/compute.py` field reference**

In `app/metrics/compute.py`, line 26:

```python
# BEFORE:
        avg_review_wait_days=pr["avg_review_wait_days"] if pr else None,

# AFTER:
        median_first_review_days=pr["median_first_review_days"] if pr else None,
```

- [ ] **Step 17: Update `tests/metrics/test_compute.py` field references**

There are 4 references to update. In each case, rename the field:

Line 35:
```python
# BEFORE:
        "avg_review_wait_days": 4.2,
# AFTER:
        "median_first_review_days": 4.2,
```

Line 46:
```python
# BEFORE:
    assert snap.avg_review_wait_days == 4.2
# AFTER:
    assert snap.median_first_review_days == 4.2
```

Line 99:
```python
# BEFORE:
            avg_review_wait_days=2.0,
# AFTER:
            median_first_review_days=2.0,
```

Line 126:
```python
# BEFORE:
        avg_review_wait_days=None,
# AFTER:
        median_first_review_days=None,
```

- [ ] **Step 18: Update `tests/metrics/test_store.py` field references**

Two references to update:

Line 20:
```python
# BEFORE:
        avg_review_wait_days=4.2,
# AFTER:
        median_first_review_days=4.2,
```

Line 113:
```python
# BEFORE:
        avg_review_wait_days=None,
# AFTER:
        median_first_review_days=None,
```

- [ ] **Step 19: Update `tests/reports/test_enrich.py` field references**

Two references to update:

Line 113:
```python
# BEFORE:
        avg_review_wait_days=3.5,
# AFTER:
        median_first_review_days=3.5,
```

Line 186:
```python
# BEFORE:
        avg_review_wait_days=2.0,
# AFTER:
        median_first_review_days=2.0,
```

- [ ] **Step 20: Update `tests/reports/test_html_renderer.py` field references**

Three references to update:

Line 258:
```python
# BEFORE:
        "avg_review_wait_days": 4.2,
# AFTER:
        "median_first_review_days": 4.2,
```

Line 345:
```python
# BEFORE:
        "avg_review_wait_days": 2.0,
# AFTER:
        "median_first_review_days": 2.0,
```

Line 451:
```python
# BEFORE:
        "avg_review_wait_days": 4.2,
# AFTER:
        "median_first_review_days": 4.2,
```

- [ ] **Step 21: Update the JS tile in `pr_health.js`**

In `app/reports/renderers/templates/components/pr_health.js`, line 27:

```javascript
// BEFORE:
    {value: d.pr_health.avg_review_wait_days + "d", label: "Avg Review Wait", color: "var(--status-waiting)", accent: "var(--status-waiting)"}

// AFTER:
    {value: d.pr_health.median_first_review_days != null ? d.pr_health.median_first_review_days + "d" : "—", label: "Median First Review", color: "var(--status-waiting)", accent: "var(--status-waiting)"}
```

This handles the `null` case by showing "—" instead of "nulld".

- [ ] **Step 22: Run the full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: All tests PASS

- [ ] **Step 23: Run lint**

Run: `make lint`
Expected: All checks passed

- [ ] **Step 24: Commit**

```bash
git add app/pr_health/fetcher.py app/pr_health/models.py app/metrics/models.py app/metrics/compute.py app/reports/renderers/templates/components/pr_health.js tests/pr_health/test_fetcher.py tests/metrics/test_compute.py tests/metrics/test_store.py tests/reports/test_enrich.py tests/reports/test_html_renderer.py
git commit -m "feat: replace avg review wait with median time-to-first-review from merged PRs"
```
