# PR Health & Vouch Tracking — Design Spec

## Goal

Add two new data sources to the triage agent: PR health monitoring and vouch request tracking. These run alongside issue triage, feeding into the same dashboard and weekly digest. No LLM calls — pure GitHub API queries + Python logic.

Both features solve problems proven by Slack channel analysis (Aug 2026): PRs sitting unreviewed for days, vouch requests blocking contributors with no visibility. These are also the features most likely to make NVIDIA want to upstream this tool.


## Module Interface

Each data source follows the same shape. No base class, no registry — just convention enforced by tests.

```python
class SomeModule:
    def fetch(self, github_token: str, repos: list[str]) -> Any:
        """Hit the GitHub API (REST or GraphQL), return raw data.
        Each module defines its own return type."""

    def analyze(self, raw: Any) -> Any:
        """Process raw data into structured findings.
        Each module defines its own findings dataclass."""

    def dashboard_section(self, findings: Any) -> dict:
        """Return a dict to merge into REPORT_DATA for the HTML dashboard."""

    def digest_lines(self, findings: Any) -> list[str]:
        """Return plain text lines for the weekly digest."""
```

The runner calls each module in sequence, merges dashboard sections into REPORT_DATA, concatenates digest lines. Adding a future module means: create a directory, add one line to the module list in config.

Modules are independent — they do not import from or reference each other. Cross-module data (e.g., linking vouch-blocked PRs to pending vouch requests) is handled by the runner after both modules return their findings.


## Module 1: PR Health

### What it tracks

For each repo in WATCH_REPOS, fetch all open PRs. No contributor filter — the tool tracks ALL open PRs regardless of author. (Red Hat deployments can optionally filter to team members via config, but the default is all PRs, which is what upstream needs.) Classify each PR into one of these states:

- **Waiting for review** — author has pushed or responded to all feedback, no new review activity. This is the bottleneck state. Threshold: 3+ days since last author action with no subsequent review.
- **Waiting for author** — reviewer left comments/requested changes, author hasn't responded. This is normal workflow, not a bottleneck. Not flagged.
- **Vouch-blocked** — PR was auto-closed by vouch-check.yml because the author isn't vouched. The runner cross-references PR health and vouch findings after both modules complete (modules themselves stay independent).
- **Stale** — no activity from anyone for 14+ days. Different from "waiting for review" because both sides went quiet.
- **Active** — recent activity from both sides. Not flagged.

### Why this is different from stale.yml

OpenShell's stale.yml counts calendar days since last activity. It doesn't know WHY something is inactive. A PR waiting for a reviewer for 5 days is a process failure. A PR waiting for the author to address 7 rounds of feedback is normal. stale.yml treats them the same. This module distinguishes them.

### Data source

GitHub REST API:
- `GET /repos/{repo}/pulls?state=open&sort=updated&direction=desc&per_page=100` — open PRs
- `GET /repos/{repo}/pulls/{number}/reviews` — review activity per PR
- `GET /repos/{repo}/issues/{number}/timeline` — for detecting vouch-check auto-close events (on recently closed PRs)

No new API auth needed — uses the same GITHUB_TOKEN already in TriageConfig.

### Analysis logic

For each open PR:
1. Get the most recent submitted review event (approved, changes_requested, commented — excludes draft/pending reviews) and its timestamp
2. Get the most recent push/commit from the author after that review (from the PR's commits endpoint, filtered by author)
3. If author pushed after last review AND no new review for 3+ days → **waiting for review**
4. If reviewer requested changes AND no author push for 3+ days → **waiting for author** (not flagged)
5. If no activity from anyone for 14+ days → **stale**
6. Otherwise → **active**

For reviewer bottleneck detection:
- Group "waiting for review" PRs by requested reviewer
- If any reviewer has 3+ PRs waiting → flag as a bottleneck

### Models

```python
@dataclass
class PRStatus:
    repo: str
    number: int
    title: str
    url: str
    author: str
    created_at: str
    updated_at: str
    state: str  # "waiting_for_review", "waiting_for_author", "stale", "vouch_blocked", "active"
    days_in_state: int
    requested_reviewers: list[str]
    last_review_by: str | None
    last_review_at: str | None
    last_author_push_at: str | None

@dataclass
class ReviewerBottleneck:
    reviewer: str
    waiting_prs: list[PRStatus]
    count: int

@dataclass
class PRHealthFindings:
    total_open: int
    waiting_for_review: list[PRStatus]
    stale: list[PRStatus]
    vouch_blocked: list[PRStatus]
    reviewer_bottlenecks: list[ReviewerBottleneck]
    avg_review_wait_days: float
```

### Dashboard output

New KPI cards:
- "Waiting for Review" — count, colored orange if > 5
- "Avg Review Wait" — days, colored red if > 5 days

New section: "PR Health" between the team breakdown and duplicate clusters:
- Table: PR number, title, author, state, days in state, requested reviewers
- Sorted by days_in_state descending (longest wait first)
- Reviewer bottleneck callout if any reviewer has 3+ waiting PRs

### Digest output

```
PR HEALTH
5 PRs waiting for review (avg 4.2 days)
Longest wait: #2598 PEP 517 proto stubs (7 days, reviewer: none assigned)
Bottleneck: @TaylorMutch has 3 PRs waiting

2 PRs stale (no activity 14+ days)
#2468 jjaggars — 18 days since last activity
```


## Module 2: Vouch Tracking

### What it tracks

OpenShell requires new contributors to be "vouched" before their PRs are accepted. The vouch process:
1. Contributor opens a Discussion in the "vouch-request" category
2. A maintainer comments `/vouch` on that discussion
3. The contributor is added to VOUCHED.td
4. Until vouched, the vouch-check.yml workflow auto-closes their PRs

The module surfaces pending vouch requests and connects them to blocked contributions.

### Data source

GitHub GraphQL API (Discussions are GraphQL-only, no REST endpoint):

```graphql
query {
  repository(owner: "NVIDIA", name: "OpenShell") {
    discussions(
      categoryId: "<vouch-request-category-id>"
      first: 50
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      nodes {
        number
        title
        author { login }
        createdAt
        comments(first: 20) {
          nodes {
            body
            author { login }
            authorAssociation
          }
        }
      }
    }
  }
}
```

Getting the category ID: one-time GraphQL lookup at startup. The fetcher queries `repository.discussionCategories` to find the category named "vouch-request" and caches its ID. If no matching category exists (non-OpenShell repos), the vouch module returns empty findings gracefully.

The module also needs to check if the author has any open or recently-closed PRs, to show what contributions vouching would unblock. This uses the existing REST API: `GET /repos/{repo}/pulls?state=all&sort=created&direction=desc` filtered by author.

### Analysis logic

For each vouch request discussion:
1. Check if any comment by a MEMBER or COLLABORATOR contains `/vouch` → **vouched** (skip)
2. If not vouched → **pending**
3. For pending requests, query open + recently closed PRs by that author → **blocked contributions**
4. Calculate wait time: now - discussion.createdAt

### Models

```python
@dataclass
class BlockedContribution:
    repo: str
    pr_number: int
    pr_title: str
    pr_url: str
    state: str  # "open" or "closed" (auto-closed by vouch-check)

@dataclass  
class PendingVouch:
    discussion_number: int
    discussion_url: str
    author: str
    created_at: str
    wait_days: int
    blocked_contributions: list[BlockedContribution]

@dataclass
class VouchFindings:
    pending: list[PendingVouch]
    total_pending: int
    total_blocked_prs: int
    longest_wait_days: int
```

### Dashboard output

New KPI card:
- "Pending Vouches" — count, colored orange if > 0

New section: "Contributor Onboarding" after PR Health:
- Each pending vouch shows: author, wait time, and what PRs are blocked
- Format: "Andre Lustosa — waiting 5 days — 1 PR blocked: PEP 517 proto stubs (7,000 lines, HIGH urgency)"
- The urgency comes from cross-referencing blocked PRs against triage results (if the PR fixes a triaged issue)

### Digest output

```
CONTRIBUTOR ONBOARDING
2 contributors waiting for vouch

Andre Lustosa — 5 days waiting
  Blocked: PR #2598 PEP 517 proto stubs fix (HIGH urgency)
  Vouch request: github.com/NVIDIA/OpenShell/discussions/2213

Daniels Nagornuks — 3 days waiting
  Blocked: PR #2301 Kata runtime config
  Vouch request: github.com/NVIDIA/OpenShell/discussions/2250
```


## Integration Points — What Changes in Existing Code

### New files

```
app/
  pr_health/
    __init__.py
    fetcher.py       # GitHub PR + review API calls
    analyzer.py      # State classification logic
    models.py        # PRStatus, PRHealthFindings, etc.
  vouch/
    __init__.py
    fetcher.py       # GitHub Discussions GraphQL + PR lookup
    analyzer.py      # Pending detection, blocked PR linkage
    models.py        # PendingVouch, VouchFindings, etc.
```

### Modified files

**`app/reports/models.py`** — extend `BirdsEyeReport`:
```python
@dataclass
class BirdsEyeReport:
    # ... existing fields ...
    pr_health: dict | None = None      # from PRHealthModule.dashboard_section()
    vouch_status: dict | None = None   # from VouchModule.dashboard_section()
```

Optional fields (defaulting to None) so the report works with or without the modules. No breaking change.

**`app/reports/renderers/html.py`** — add two new sections to the HTML template:
- PR Health section: KPI cards + table, inserted after team breakdown
- Vouch section: pending list with blocked contributions, inserted after PR health
- Both sections conditionally rendered (only if the data exists in REPORT_DATA)

**`app/triage.py`** — extend `run_report()`:
- After generating the bird's eye report from triage results, call PR health and vouch modules
- Merge their dashboard_section() output into the report
- Merge their digest_lines() output into digest mode

**`app/server.py`** — extend `_run_cycle()`:
- Same changes as triage.py: call modules, merge output

**`app/config.py`** — extend `TriageConfig`:
- `pr_health_enabled: bool = True`
- `vouch_tracking_enabled: bool = True`
- `pr_review_wait_threshold_days: int = 3`
- `pr_stale_threshold_days: int = 14`
- `vouch_category_id: str | None = None` (for the GraphQL query)

Feature flags so each module can be disabled independently.

### Files NOT changed

- `app/core/` — the triage engine, LLM client, models, prompt, scoring. Untouched.
- `app/notifications/` — PR health and vouch findings go through the dashboard and digest, not through the per-issue notification router. The notification adapter protocol stays unchanged.
- `app/sources/` — PR health and vouch have their own fetchers. The IssueSource protocol stays unchanged.
- `app/state/` — PR health and vouch are stateless (re-fetched each cycle from GitHub). No state tracking needed.
- `profiles/` — team profiles are unchanged. PR health and vouch data appears in the dashboard regardless of team configuration.


## Boy Scout Fixes (while we're here)

Issues found during codebase review that should be fixed alongside this work:

1. **Hardcoded repo name**: `"openshell"` is hardcoded in `triage.py` (3 places) and `server.py` (1 place). Extract to `TriageConfig.repo_config_name` with default `"openshell"`.

2. **Duplicated period computation**: The weekly period start calculation is copy-pasted between `triage.py:run_report()` and `server.py:_run_cycle()`. Extract to a shared function in `app/reports/` or `app/config.py`.

3. **Duplicated `_build_llm_client`**: Same factory function in both `triage.py` and `server.py`. Extract to `app/core/llm.py`.

4. **Protocol/implementation mismatch**: `IssueSource.fetch_new_issues` declares `seen_ids: set[int]` but `GitHubSource` uses `set[str]`. Fix the protocol to match the implementation.

5. **Enrichment key collision**: `enrich_issues` keys by `issue_number` (int) instead of `"repo#number"`. Fix to use the namespaced key format consistent with state tracking.

These are independent of the PR health / vouch work and should be separate commits.


## Testing Strategy

### PR Health tests
- `test_pr_state_classification` — unit tests for each state: waiting_for_review, waiting_for_author, stale, vouch_blocked, active. Mock the review/push timestamps and verify classification.
- `test_reviewer_bottleneck_detection` — 3+ PRs waiting for same reviewer triggers bottleneck.
- `test_dashboard_section_format` — output dict matches expected schema for the HTML renderer.
- `test_digest_lines_format` — output strings are well-formed.
- `test_fetcher_with_mock_api` — mock GitHub REST responses, verify correct API calls and pagination handling.

### Vouch tests
- `test_pending_detection` — discussion with no `/vouch` reply from MEMBER/COLLABORATOR is pending.
- `test_vouched_detection` — discussion with `/vouch` reply is skipped.
- `test_blocked_pr_linkage` — pending vouch with author's open/closed PRs correctly linked.
- `test_graphql_query_construction` — verify the GraphQL query is well-formed.
- `test_dashboard_section_format` — output dict matches expected schema.
- `test_digest_lines_format` — output strings are well-formed.

### Integration tests
- `test_report_with_modules` — generate a bird's eye report with PR health and vouch data, verify the HTML renders without errors.
- `test_report_without_modules` — generate a report with modules disabled, verify backward compatibility.
- `test_digest_includes_module_output` — run digest mode with modules, verify output includes PR health and vouch sections.


## API Rate Limits

GitHub REST API: 5,000 requests/hour with a token. Current issue triage uses ~3-5 requests per cycle (issue list + comments). PR health adds:
- 1 request for PR list per repo
- 1 request per open PR for reviews (up to ~108 for OpenShell currently)
- Worst case: ~110 additional requests per hourly cycle

GitHub GraphQL API: 5,000 points/hour. The vouch discussions query costs ~1 point. PR lookups per pending vouch author cost ~1 point each. Negligible.

Total: well within rate limits even at hourly cadence.


## What This Enables for Upstream

These features are not Red Hat-specific. Every open source project with >50 open PRs has the "stuck PRs" problem. Every project with a contributor approval process has the "blocked newcomers" problem.

For the NVIDIA upstream proposal:
- PR health replaces dumb stale detection with intelligent state classification
- Vouch tracking closes a gap in NVIDIA's own contributor onboarding workflow
- Both features work without any team profiles configured — they're universally useful
- Both features require zero LLM calls — no API key needed to use them
- The dashboard becomes a complete project health view, not just an issue classifier
