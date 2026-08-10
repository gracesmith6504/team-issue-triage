# Dashboard Accuracy Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three accuracy bugs in the live dashboard: PR last-activity ignores comments, vouch responded count skips closed discussions, and no visibility into which PRs are blocked by unvouched contributors.

**Architecture:** All three fixes touch the data-fetching layer (`app/pr_health/fetcher.py`, `app/vouch/fetcher.py`) and one JS rendering template. Task 3 also adds a lightweight cross-referencing step in `app/reports/enrich.py` that connects existing PR and vouch data. No new dependencies, no schema changes to existing fields.

**Tech Stack:** Python 3.14, requests, GitHub REST + GraphQL APIs, vanilla JavaScript (inline in Jinja2 templates)

## Global Constraints

- NEVER include `Co-Authored-By` lines in commit messages
- Always run `make lint` before pushing
- One logical change = one commit, squash before review, use `--force-with-lease`
- All 293 existing tests must continue to pass
- No npm/build toolchain -- all CSS/JS is inline in the HTML template
- Test pattern: tests use `unittest.mock.patch` on `requests.get`/`requests.post` and a frozen `NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)`

---

### Task 1: Fix PR last-activity to include comment timestamps

**Files:**
- Modify: `app/pr_health/fetcher.py:172-211`
- Test: `tests/pr_health/test_fetcher.py`

**Interfaces:**
- Consumes: GitHub issue comments (already fetched at line 145-146)
- Produces: updated `last_activity` string on `PRStatus` (no model change needed, `last_activity: str` already exists)

The code already fetches PR comments (line 145-146) and iterates them (lines 172-176) but only uses them for participant tracking. The `last_activity` string (lines 207-211) only considers author push date and formal review date, ignoring the most recent human comment. When a reviewer comments (e.g. asking for changes) without submitting a formal review, the dashboard shows stale dates.

- [ ] **Step 1: Write the failing test**

Add to `tests/pr_health/test_fetcher.py`:

```python
@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_last_activity_includes_comment_date(mock_get, mock_dt):
    _patch_dt(mock_dt)
    old_pr = _make_pr(1, created_days_ago=30, author="contributor")
    review = {
        "user": {"login": "reviewer1"},
        "submitted_at": (NOW - timedelta(days=20)).isoformat(),
    }
    comment = {
        "user": {"login": "reviewer2"},
        "body": "Please address the feedback",
        "created_at": (NOW - timedelta(days=3)).isoformat(),
    }
    commit = {
        "commit": {"author": {"date": (NOW - timedelta(days=25)).isoformat()}},
        "author": {"login": "contributor"},
    }
    mock_get.side_effect = [
        _make_response([old_pr]),
        _make_response([review]),
        _make_response([comment]),
        _make_response([commit]),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert len(result.stuck_prs) == 1
    assert "last comment 3d ago" in result.stuck_prs[0].last_activity
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/pr_health/test_fetcher.py::test_last_activity_includes_comment_date -v`

Expected: FAIL -- `last_activity` does not contain "last comment 3d ago" (it currently only shows "last review 20d ago").

- [ ] **Step 3: Write a test for bot comments being excluded from last-activity**

Add to `tests/pr_health/test_fetcher.py`:

```python
@patch("app.pr_health.fetcher.datetime")
@patch("app.pr_health.fetcher.requests.get")
def test_last_activity_ignores_bot_comments(mock_get, mock_dt):
    _patch_dt(mock_dt)
    old_pr = _make_pr(1, created_days_ago=30, author="contributor")
    bot_comment = {
        "user": {"login": "github-actions[bot]"},
        "body": "This PR is stale",
        "created_at": (NOW - timedelta(days=1)).isoformat(),
    }
    commit = {
        "commit": {"author": {"date": (NOW - timedelta(days=25)).isoformat()}},
        "author": {"login": "contributor"},
    }
    mock_get.side_effect = [
        _make_response([old_pr]),
        _make_response([]),
        _make_response([bot_comment]),
        _make_response([commit]),
        _make_response([]),
    ]
    result = fetch_pr_health("test/repo", "fake-token")
    assert len(result.stuck_prs) == 1
    assert "last comment" not in result.stuck_prs[0].last_activity
```

- [ ] **Step 4: Implement the fix in `app/pr_health/fetcher.py`**

In `_find_stuck_prs`, replace lines 172-211 (from `participants: set[str] = set()` through the `activity_parts` construction) with:

```python
        participants: set[str] = set()
        last_comment_date = None
        for c in comments:
            commenter = c["user"]["login"]
            if commenter != author and not commenter.endswith("[bot]"):
                participants.add(commenter)
                cd = _parse_dt(c["created_at"])
                if last_comment_date is None or cd > last_comment_date:
                    last_comment_date = cd

        last_author_commit = None
        for c in reversed(commits):
            if c.get("author") and c["author"].get("login") == author:
                last_author_commit = _parse_dt(c["commit"]["author"]["date"])
                break
        if not last_author_commit:
            last_author_commit = created

        days_since_author = (now - last_author_commit).days
        days_since_review = (now - last_review_date).days if last_review_date else age
        days_since_comment = (now - last_comment_date).days if last_comment_date else None

        gator = None
        for label in pr.get("labels", []):
            if label["name"].startswith("gator:"):
                gator = label["name"]
                break

        requested = [
            r["login"]
            for r in pr.get("requested_reviewers", [])
            if r["login"] not in codeowners
        ]
        auto_assigned = [
            r["login"]
            for r in pr.get("requested_reviewers", [])
            if r["login"] in codeowners
        ]

        all_engaged = actual_reviewers | participants
        activity_parts = [f"Author pushed {days_since_author}d ago"]
        if last_review_date:
            activity_parts.append(f"last review {days_since_review}d ago")
        else:
            activity_parts.append("no reviews")
        if days_since_comment is not None:
            activity_parts.append(f"last comment {days_since_comment}d ago")
```

This preserves all existing logic and adds one new tracking variable (`last_comment_date`) and one new line to `activity_parts`. Comments from the PR author and bots are already filtered out by the existing `if` guard -- `last_comment_date` is only updated inside that guard.

- [ ] **Step 5: Run all tests**

Run: `python3 -m pytest tests/pr_health/test_fetcher.py -v`

Expected: ALL tests pass, including the two new ones.

- [ ] **Step 6: Run lint**

Run: `make lint`

Expected: Clean pass.

- [ ] **Step 7: Commit**

```bash
git add app/pr_health/fetcher.py tests/pr_health/test_fetcher.py
git commit -m "fix: include comment timestamps in PR last-activity"
```

---

### Task 2: Fix vouch responded count to include closed discussions

**Files:**
- Modify: `app/vouch/fetcher.py:69-94`
- Modify: `tests/vouch/test_fetcher.py`

**Interfaces:**
- Consumes: GitHub discussion data (already fetched by `_fetch_discussions`)
- Produces: corrected `responded_in_7d` count on `VouchFindings` (no model change needed)

The vouch fetcher (line 73) skips closed discussions entirely with `if disc.get("closed"): continue`. But when a contributor gets vouched, the discussion is typically closed. This means `responded_in_7d` always reads 0 because successfully-vouched discussions are never counted. Real data shows @gmenher (vouched at 5d, closed) and @andre-motta (vouched at 6d, closed) should bring the count to 2.

- [ ] **Step 1: Update the existing test for closed discussions**

The existing test `test_closed_discussions_skipped` asserts that closed discussions don't appear in `pending_vouches`. This is still correct -- they should not appear in the pending list. But the test name is misleading now. Rename and keep its assertion, then add a new test for the responded count.

In `tests/vouch/test_fetcher.py`, replace `test_closed_discussions_skipped` (the last test) with:

```python
@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_closed_discussions_excluded_from_pending(mock_post, mock_dt):
    _patch_dt(mock_dt)
    discs = [
        _make_discussion(1, created_days_ago=10, closed=True),
        _make_discussion(2, created_days_ago=5),
    ]
    mock_post.side_effect = [
        _make_response(_categories_response()),
        _make_response(_discussions_response(discs)),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert result.total_pending == 1
    assert result.pending_vouches[0].discussion_number == 2
```

- [ ] **Step 2: Write the failing test for responded count on closed+vouched discussions**

Add to `tests/vouch/test_fetcher.py`:

```python
@patch("app.vouch.fetcher.datetime")
@patch("app.vouch.fetcher.requests.post")
def test_responded_in_7d_counts_closed_vouched_discussions(mock_post, mock_dt):
    _patch_dt(mock_dt)
    discs = [
        _make_discussion(
            1,
            author="recentuser",
            created_days_ago=5,
            closed=True,
            comments=[_make_comment("/vouch", "MEMBER")],
        ),
        _make_discussion(
            2,
            author="olduser",
            created_days_ago=20,
            closed=True,
            comments=[_make_comment("/vouch", "MEMBER")],
        ),
        _make_discussion(3, author="waitinguser", created_days_ago=3),
    ]
    mock_post.side_effect = [
        _make_response(_categories_response()),
        _make_response(_discussions_response(discs)),
    ]
    result = fetch_vouch_status("test/repo", "fake-token")
    assert result.responded_in_7d == 1
    assert result.total_pending == 1
    assert result.pending_vouches[0].author == "waitinguser"
```

- [ ] **Step 3: Run tests to verify the new test fails**

Run: `python3 -m pytest tests/vouch/test_fetcher.py::test_responded_in_7d_counts_closed_vouched_discussions -v`

Expected: FAIL -- `responded_in_7d` is 0 because closed discussions are skipped before counting.

- [ ] **Step 4: Implement the fix in `app/vouch/fetcher.py`**

Replace lines 69-94 (from `pending: list[PendingVouch] = []` through the end of the `for disc in discussions` loop) with:

```python
    pending: list[PendingVouch] = []
    responded_count = 0

    for disc in discussions:
        author = disc["author"]["login"] if disc.get("author") else "unknown"
        created = datetime.fromisoformat(disc["createdAt"].replace("Z", "+00:00"))
        wait_days = (now - created).days

        has_vouch = _check_vouched(disc)

        if has_vouch and wait_days <= 7:
            responded_count += 1

        if disc.get("closed"):
            continue

        if not has_vouch:
            pending.append(
                PendingVouch(
                    author=author,
                    discussion_number=disc["number"],
                    url=f"https://github.com/{owner}/{name}/discussions/{disc['number']}",
                    wait_days=wait_days,
                    created_at=disc["createdAt"],
                )
            )
```

The key change: move the `responded_count` logic ABOVE the `if disc.get("closed"): continue` guard. Now closed+vouched discussions within 7 days are counted before being skipped for the pending list.

- [ ] **Step 5: Run all vouch tests**

Run: `python3 -m pytest tests/vouch/test_fetcher.py -v`

Expected: ALL tests pass, including the two updated/new ones.

- [ ] **Step 6: Verify the existing `test_responded_in_7d_counting` still passes**

This test creates an OPEN discussion with a vouch (3 days old). It should still return `responded_in_7d == 1`. Verify it didn't break.

Run: `python3 -m pytest tests/vouch/test_fetcher.py::test_responded_in_7d_counting -v`

Expected: PASS.

- [ ] **Step 7: Run lint**

Run: `make lint`

Expected: Clean pass.

- [ ] **Step 8: Commit**

```bash
git add app/vouch/fetcher.py tests/vouch/test_fetcher.py
git commit -m "fix: count closed vouched discussions in responded metric"
```

---

### Task 3: Show PRs blocked by unvouched contributors

**Files:**
- Modify: `app/vouch/models.py`
- Modify: `app/reports/enrich.py:46-71`
- Modify: `app/reports/renderers/templates/components/contributor_health.js`
- Modify: `app/reports/renderers/templates/components/alerts.js`
- Test: `tests/reports/test_enrich.py`

**Interfaces:**
- Consumes: `report.vouch_status["pending_vouches"]` (list of dicts with `"author"` key), `report.pr_health["stuck_prs"]` (list of dicts with `"author"`, `"number"`, `"title"`, `"url"` keys) -- both populated by earlier steps in `enrich_report`
- Produces: `report.vouch_status["blocked_prs"]` (new list of dicts: `{"pr_number": int, "pr_title": str, "pr_url": str, "author": str, "vouch_discussion": int, "vouch_wait_days": int}`)

This task cross-references the existing vouch and PR health data to surface PRs that are stuck because their author hasn't been vouched. The cross-referencing happens in `enrich_report` after both data sources are populated, NOT in the individual fetchers. The check compares all open PR authors (not just stuck ones) against pending vouch authors.

- [ ] **Step 1: Add `blocked_prs` field to `VouchFindings`**

In `app/vouch/models.py`, add a `field` import and the new field:

Replace the entire file with:

```python
from dataclasses import dataclass, field


@dataclass
class PendingVouch:
    author: str
    discussion_number: int
    url: str
    wait_days: int
    created_at: str


@dataclass
class BlockedPR:
    pr_number: int
    pr_title: str
    pr_url: str
    author: str
    vouch_discussion: int
    vouch_wait_days: int


@dataclass
class VouchFindings:
    total_pending: int
    responded_in_7d: int
    longest_wait_days: int
    over_30d_count: int
    pending_vouches: list[PendingVouch]
    blocked_prs: list[BlockedPR] = field(default_factory=list)
```

- [ ] **Step 2: Write the failing test for blocked PR enrichment**

Add to `tests/reports/test_enrich.py`:

```python
def test_enrich_cross_references_blocked_prs():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig()
    repo_config = _FakeRepoConfig()

    with (
        patch("app.reports.enrich._enrich_issue_counts"),
        patch("app.pr_health.fetcher.fetch_pr_health") as mock_pr,
        patch("app.vouch.fetcher.fetch_vouch_status") as mock_vouch,
    ):
        mock_pr.return_value = _stub_pr_health_with_prs()
        mock_vouch.return_value = _stub_vouch_with_pending()
        enrich_report(report, config, repo_config)

    assert report.vouch_status is not None
    blocked = report.vouch_status["blocked_prs"]
    assert len(blocked) == 1
    assert blocked[0]["author"] == "newcontrib"
    assert blocked[0]["pr_number"] == 42
    assert blocked[0]["vouch_discussion"] == 100
```

Also add these helper stubs at the bottom of the file:

```python
def _stub_pr_health_with_prs():
    from app.pr_health.models import PRHealthFindings, PRStatus

    return PRHealthFindings(
        total_open=2,
        awaiting_review=1,
        stale_14d=0,
        gator_coverage_pct=50,
        merge_velocity=5,
        merge_velocity_prev=3,
        avg_review_wait_days=2.0,
        stuck_prs=[
            PRStatus(
                number=42,
                title="feat: add widget",
                url="https://github.com/test/repo/pull/42",
                author="newcontrib",
                days_open=10,
                days_since_author_push=5,
                days_since_last_review=10,
                review_count=0,
                participants=[],
                last_activity="Author pushed 5d ago, no reviews",
                is_draft=False,
            ),
        ],
        age_distribution={},
    )


def _stub_vouch_with_pending():
    from app.vouch.models import PendingVouch, VouchFindings

    return VouchFindings(
        total_pending=1,
        responded_in_7d=0,
        longest_wait_days=12,
        over_30d_count=0,
        pending_vouches=[
            PendingVouch(
                author="newcontrib",
                discussion_number=100,
                url="https://github.com/test/repo/discussions/100",
                wait_days=12,
                created_at="2026-07-20T00:00:00Z",
            ),
        ],
    )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/reports/test_enrich.py::test_enrich_cross_references_blocked_prs -v`

Expected: FAIL -- `blocked_prs` key missing or empty (the cross-reference doesn't exist yet).

- [ ] **Step 4: Write a test for no matches**

Add to `tests/reports/test_enrich.py`:

```python
def test_enrich_blocked_prs_empty_when_no_overlap():
    from app.reports.enrich import enrich_report

    report = make_report()
    config = _FakeConfig()
    repo_config = _FakeRepoConfig()

    with (
        patch("app.reports.enrich._enrich_issue_counts"),
        patch("app.pr_health.fetcher.fetch_pr_health") as mock_pr,
        patch("app.vouch.fetcher.fetch_vouch_status") as mock_vouch,
    ):
        mock_pr.return_value = _stub_pr_health()
        mock_vouch.return_value = _stub_vouch()
        enrich_report(report, config, repo_config)

    assert report.vouch_status is not None
    assert report.vouch_status["blocked_prs"] == []
```

- [ ] **Step 5: Implement the cross-reference in `app/reports/enrich.py`**

Replace the entire `enrich_report` function (lines 46-71) with:

```python
def enrich_report(report, config, repo_config):
    try:
        _enrich_issue_counts(report, config, repo_config)
    except Exception:
        logger.exception("Issue count enrichment failed")

    if config.pr_health_enabled:
        try:
            from app.pr_health.fetcher import fetch_pr_health

            codeowners = repo_config.codeowners or []
            pr_health = fetch_pr_health(
                repo_config.repo, config.github_token, codeowners
            )
            report.pr_health = dataclasses.asdict(pr_health)
        except Exception:
            logger.exception("PR health fetch failed")

    if config.vouch_tracking_enabled:
        try:
            from app.vouch.fetcher import fetch_vouch_status

            vouch = fetch_vouch_status(repo_config.repo, config.github_token)
            report.vouch_status = dataclasses.asdict(vouch)
        except Exception:
            logger.exception("Vouch status fetch failed")

    _cross_reference_blocked_prs(report)


def _cross_reference_blocked_prs(report):
    if not report.pr_health or not report.vouch_status:
        return

    pending_by_author = {}
    for v in report.vouch_status.get("pending_vouches", []):
        pending_by_author[v["author"]] = v

    blocked = []
    for pr in report.pr_health.get("stuck_prs", []):
        vouch = pending_by_author.get(pr["author"])
        if vouch:
            blocked.append(
                {
                    "pr_number": pr["number"],
                    "pr_title": pr["title"],
                    "pr_url": pr["url"],
                    "author": pr["author"],
                    "vouch_discussion": vouch["discussion_number"],
                    "vouch_wait_days": vouch["wait_days"],
                }
            )

    report.vouch_status["blocked_prs"] = blocked
```

- [ ] **Step 6: Run all enrich tests**

Run: `python3 -m pytest tests/reports/test_enrich.py -v`

Expected: ALL tests pass (existing + two new). The existing tests still pass because `_stub_vouch()` has no pending authors that match `_stub_pr_health()` stuck PRs (which has an empty list), so `blocked_prs` will be `[]`.

- [ ] **Step 7: Add the blocked-PR alert to `alerts.js`**

In `app/reports/renderers/templates/components/alerts.js`, replace the vouch alert block (lines 14-18) with a version that also shows blocked PRs:

Replace:

```javascript
  if (d.vouch_status) {
    var vouchCount = d.vouch_status.total_pending || 0;
    var longestVouch = d.vouch_status.pending_vouches.length ? d.vouch_status.pending_vouches[d.vouch_status.pending_vouches.length - 1] : null;
    alertData.push({color: "#e16f24", text: '<strong>' + vouchCount + '</strong> contributors waiting for vouch' + (longestVouch ? ' - longest: <a href="' + esc(longestVouch.url) + '" target="_blank">@' + esc(longestVouch.author) + '</a> (' + longestVouch.wait_days + ' days)' : '')});
  }
```

with:

```javascript
  if (d.vouch_status) {
    var vouchCount = d.vouch_status.total_pending || 0;
    var longestVouch = d.vouch_status.pending_vouches.length ? d.vouch_status.pending_vouches[d.vouch_status.pending_vouches.length - 1] : null;
    var blockedPRs = d.vouch_status.blocked_prs || [];
    var vouchText = '<strong>' + vouchCount + '</strong> contributors waiting for vouch';
    if (longestVouch) vouchText += ' - longest: <a href="' + esc(longestVouch.url) + '" target="_blank">@' + esc(longestVouch.author) + '</a> (' + longestVouch.wait_days + ' days)';
    if (blockedPRs.length) vouchText += ' - <strong>' + blockedPRs.length + '</strong> PR' + (blockedPRs.length > 1 ? 's' : '') + ' blocked';
    alertData.push({color: "#e16f24", text: vouchText});
  }
```

- [ ] **Step 8: Add the blocked-PR list to `contributor_health.js`**

In `app/reports/renderers/templates/components/contributor_health.js`, add a blocked-PR section after the vouch note (before the toggle event listener). Insert the following block just before line 91 (`wrap.addEventListener("toggle", ...`):

```javascript
  var blockedPRs = d.vouch_status.blocked_prs || [];
  if (blockedPRs.length) {
    var bpTitle = el("div", "stacked-bar-label", "PRs Blocked by Missing Vouch");
    wrap.appendChild(bpTitle);
    blockedPRs.forEach(function(bp) {
      var row = el("div", "blocked-contributor");
      row.innerHTML =
        '<div class="bc-header"><span class="bc-author"><a href="https://github.com/' + esc(bp.author) + '" target="_blank">@' + esc(bp.author) + '</a></span></div>' +
        '<div class="bc-meta">PR <a href="' + esc(bp.pr_url) + '" target="_blank">#' + bp.pr_number + '</a>: ' + esc(bp.pr_title) + ' - vouch pending ' + bp.vouch_wait_days + ' days</div>' +
        '<div class="bc-links"><a href="' + esc(bp.pr_url) + '" target="_blank">View PR</a><a href="https://github.com/NVIDIA/OpenShell/discussions/' + bp.vouch_discussion + '" target="_blank">Vouch Discussion</a></div>';
      wrap.appendChild(row);
    });
  }
```

This reuses the existing `.blocked-contributor` CSS class already defined in `base.html`.

- [ ] **Step 9: Run all tests**

Run: `python3 -m pytest tests/ -v`

Expected: ALL 293+ tests pass.

- [ ] **Step 10: Run lint**

Run: `make lint`

Expected: Clean pass.

- [ ] **Step 11: Commit**

```bash
git add app/vouch/models.py app/reports/enrich.py app/reports/renderers/templates/components/alerts.js app/reports/renderers/templates/components/contributor_health.js tests/reports/test_enrich.py
git commit -m "feat: show PRs blocked by unvouched contributors"
```
