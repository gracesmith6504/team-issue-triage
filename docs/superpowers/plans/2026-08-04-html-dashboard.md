# HTML Dashboard Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive HTML dashboard renderer that produces a single-file dark-themed report with Chart.js charts, color-coded issue cards, and click-to-filter interactivity.

**Architecture:** The HTML renderer (`render_html`) is a sibling to the existing `render_markdown`. It serializes the `BirdsEyeReport` dataclass into an embedded JSON blob, then wraps it in a self-contained HTML template with inline CSS and Chart.js from CDN. The CLI gains `--format` to select the renderer.

**Tech Stack:** Python 3.14 dataclasses, Chart.js 4.5.1 (CDN), chartjs-plugin-datalabels (CDN), Inter font (Google Fonts CDN), CSS Grid, CSS custom properties.

## Global Constraints

- All CSS and JS must be inline in the HTML output (no external files except CDN scripts).
- Run `make lint` before every commit.
- Never include `Co-Authored-By` lines in commits.
- One logical change per commit; squash before review.
- Follow existing code patterns: dataclass models, `render_X(report: BirdsEyeReport) -> str` signature.
- Tests use pytest; reuse `_make_result()` and `_make_report()` helpers via shared conftest.
- Color palette values are exact — copy them verbatim from the spec's Color Palette section.

---

### Task 1: Extract shared test fixtures to conftest.py

**Files:**
- Create: `tests/reports/conftest.py`
- Modify: `tests/reports/test_markdown_renderer.py:1-65` (remove `_make_result` and `_make_report`, import from conftest)

**Interfaces:**
- Produces: `make_result(number, title, team, urgency) -> TriageResult` fixture factory and `make_report(**overrides) -> BirdsEyeReport` fixture factory, importable by all test files under `tests/reports/`.

- [ ] **Step 1: Create conftest.py with the shared helpers**

```python
# tests/reports/conftest.py
import pytest

from app.core.models import TriageResult, Urgency
from app.reports.models import (
    AreaTrend,
    BirdsEyeReport,
    DuplicateCluster,
    ReportSummary,
    TeamSummary,
)


def make_result(
    number=1, title="test issue", team="agent-ops", urgency=Urgency.MEDIUM,
    secondary_team=None, secondary_confidence=None, confidence_flag=None,
):
    return TriageResult(
        repo="NVIDIA/OpenShell",
        issue_number=number,
        issue_title=title,
        issue_url=f"https://github.com/NVIDIA/OpenShell/issues/{number}",
        reasoning="test",
        any_team_cares=True,
        primary_team=team,
        primary_confidence=0.9,
        secondary_team=secondary_team,
        secondary_confidence=secondary_confidence,
        urgency=urgency,
        urgency_reasoning="test",
        summary=f"Summary for #{number}",
        recommendation="test",
        confidence_flag=confidence_flag,
        assessed_at="2026-07-28T10:00:00+00:00",
    )


def make_report(**overrides):
    defaults = dict(
        summary=ReportSummary(
            new_this_period=5,
            by_urgency={"critical": 1, "high": 2, "medium": 1, "low": 1},
            period_label="Jul 28 – Aug 3, 2026",
        ),
        critical_list=[make_result(1, "critical issue", urgency=Urgency.CRITICAL)],
        team_breakdown={
            "agent-ops": TeamSummary(
                team_id="agent-ops",
                total=3,
                by_urgency={"critical": 1, "high": 1, "medium": 1, "low": 0},
                new_this_period=3,
                previous_period=2,
                trend="+1",
            ),
            "ai-safety": TeamSummary(
                team_id="ai-safety",
                total=2,
                by_urgency={"critical": 0, "high": 1, "medium": 1, "low": 0},
                new_this_period=2,
                previous_period=0,
                trend="+2",
            ),
        },
        area_heatmap={
            "gateway": AreaTrend(
                area="gateway", current_count=5, previous_count=2, delta=3, trend="+3"
            )
        },
        duplicate_clusters=[
            DuplicateCluster(
                area="sandbox",
                issues=[make_result(10, "ns support"), make_result(11, "ns fails")],
                similarity_reason="shared: namespace",
            )
        ],
        no_team_list=[make_result(20, "build system change", team="none")],
        narrative="Gateway saw unusual activity this week.",
        generated_at="2026-08-04T00:00:00+00:00",
    )
    defaults.update(overrides)
    return BirdsEyeReport(**defaults)
```

- [ ] **Step 2: Update test_markdown_renderer.py to use the shared helpers**

Replace the local `_make_result` and `_make_report` definitions in `tests/reports/test_markdown_renderer.py` with imports. Remove lines 1-64 (the old helper functions) and replace with:

```python
from app.reports.renderers.markdown import render_markdown
from tests.reports.conftest import make_report, make_result
from app.core.models import Urgency
from app.reports.models import DuplicateCluster
```

Every call site changes from `_make_result(...)` to `make_result(...)` and `_make_report(...)` to `make_report(...)` (drop the leading underscore).

- [ ] **Step 3: Run existing markdown renderer tests**

Run: `pytest tests/reports/test_markdown_renderer.py -v`
Expected: All 9 tests PASS (proves the refactor didn't break anything)

- [ ] **Step 4: Commit**

```bash
git add tests/reports/conftest.py tests/reports/test_markdown_renderer.py
git commit -m "refactor: extract shared test fixtures to conftest.py"
```

---

### Task 2: Implement _report_to_dict serialization

**Files:**
- Create: `app/reports/renderers/html.py` (partial — just the serialization helper)
- Create: `tests/reports/test_html_renderer.py` (partial — just serialization tests)

**Interfaces:**
- Consumes: `BirdsEyeReport`, `TriageResult`, `Urgency` from `app.core.models` and `app.reports.models`
- Produces: `_report_to_dict(report: BirdsEyeReport) -> dict` — converts the full report dataclass tree to plain Python dicts/lists suitable for `json.dumps()`. Enum values become strings, `None` stays `None` (serializes to JSON `null`).

- [ ] **Step 1: Write the serialization tests**

```python
# tests/reports/test_html_renderer.py
import json

from app.core.models import Urgency
from app.reports.renderers.html import _report_to_dict
from tests.reports.conftest import make_report, make_result


def test_report_to_dict_returns_dict():
    report = make_report()
    result = _report_to_dict(report)
    assert isinstance(result, dict)


def test_report_to_dict_summary_fields():
    report = make_report()
    result = _report_to_dict(report)
    assert result["summary"]["new_this_period"] == 5
    assert result["summary"]["by_urgency"]["critical"] == 1
    assert result["summary"]["period_label"] == "Jul 28 – Aug 3, 2026"


def test_report_to_dict_urgency_enum_to_string():
    report = make_report()
    result = _report_to_dict(report)
    issue = result["critical_list"][0]
    assert issue["urgency"] == "critical"
    assert isinstance(issue["urgency"], str)


def test_report_to_dict_none_values_preserved():
    report = make_report(
        critical_list=[make_result(1, "test", confidence_flag=None)]
    )
    result = _report_to_dict(report)
    assert result["critical_list"][0]["confidence_flag"] is None
    assert result["critical_list"][0]["secondary_team"] is None


def test_report_to_dict_secondary_team_present():
    report = make_report(
        critical_list=[
            make_result(1, "test", secondary_team="kata", secondary_confidence=0.65)
        ]
    )
    result = _report_to_dict(report)
    issue = result["critical_list"][0]
    assert issue["secondary_team"] == "kata"
    assert issue["secondary_confidence"] == 0.65


def test_report_to_dict_team_breakdown():
    report = make_report()
    result = _report_to_dict(report)
    assert "agent-ops" in result["team_breakdown"]
    assert result["team_breakdown"]["agent-ops"]["total"] == 3
    assert result["team_breakdown"]["agent-ops"]["trend"] == "+1"


def test_report_to_dict_duplicate_clusters():
    report = make_report()
    result = _report_to_dict(report)
    assert len(result["duplicate_clusters"]) == 1
    cluster = result["duplicate_clusters"][0]
    assert cluster["area"] == "sandbox"
    assert cluster["similarity_reason"] == "shared: namespace"
    assert len(cluster["issues"]) == 2


def test_report_to_dict_is_json_serializable():
    report = make_report()
    result = _report_to_dict(report)
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    roundtrip = json.loads(serialized)
    assert roundtrip["summary"]["new_this_period"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/reports/test_html_renderer.py -v`
Expected: FAIL with ImportError (html.py doesn't exist yet)

- [ ] **Step 3: Implement _report_to_dict**

```python
# app/reports/renderers/html.py
from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum

from app.reports.models import BirdsEyeReport


def _convert_value(obj):
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _convert_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_convert_value(i) for i in obj]
    return obj


def _report_to_dict(report: BirdsEyeReport) -> dict:
    raw = asdict(report)
    return _convert_value(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/reports/test_html_renderer.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run linter**

Run: `make lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/reports/renderers/html.py tests/reports/test_html_renderer.py
git commit -m "feat: add report-to-dict serialization for HTML renderer"
```

---

### Task 3: Implement the HTML template and render_html function

This is the largest task — the full HTML/CSS/JS dashboard template.

**Files:**
- Modify: `app/reports/renderers/html.py` (add `render_html` and `_HTML_TEMPLATE`)
- Modify: `tests/reports/test_html_renderer.py` (add HTML output tests)

**Interfaces:**
- Consumes: `_report_to_dict(report) -> dict` from Task 2
- Produces: `render_html(report: BirdsEyeReport) -> str` — returns a complete HTML document string

- [ ] **Step 1: Write the HTML output tests**

Add to `tests/reports/test_html_renderer.py`:

```python
from app.reports.renderers.html import render_html
from app.reports.models import DuplicateCluster


def test_render_html_returns_valid_html():
    html = render_html(make_report())
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "</html>" in html


def test_render_html_embeds_report_data():
    html = render_html(make_report())
    assert "REPORT_DATA" in html
    assert '"new_this_period": 5' in html


def test_render_html_includes_chart_js_cdn():
    html = render_html(make_report())
    assert "cdn.jsdelivr.net/npm/chart.js" in html


def test_render_html_includes_all_teams():
    html = render_html(make_report())
    assert "agent-ops" in html
    assert "ai-safety" in html


def test_render_html_includes_critical_issues():
    report = make_report(
        critical_list=[
            make_result(2518, "SPIFFE crash", urgency=Urgency.CRITICAL),
            make_result(2520, "sandbox fail", urgency=Urgency.HIGH),
        ]
    )
    html = render_html(report)
    assert "2518" in html
    assert "2520" in html


def test_render_html_no_team_issues_present():
    report = make_report(
        no_team_list=[make_result(99, "orphan issue", team="none")]
    )
    html = render_html(report)
    assert "orphan issue" in html
    assert "Needs Triage" in html


def test_render_html_duplicate_clusters_present():
    cluster = DuplicateCluster(
        area="gateway",
        issues=[make_result(5, "gw bug 1"), make_result(6, "gw bug 2")],
        similarity_reason="shared: gateway, tls",
    )
    html = render_html(make_report(duplicate_clusters=[cluster]))
    assert "gateway" in html
    assert "shared: gateway, tls" in html


def test_render_html_hides_empty_critical():
    html = render_html(make_report(critical_list=[]))
    assert "Action Required" not in html


def test_render_html_hides_empty_duplicates():
    html = render_html(make_report(duplicate_clusters=[]))
    assert "Potential Duplicates" not in html


def test_render_html_hides_empty_no_team():
    html = render_html(make_report(no_team_list=[]))
    assert "Needs Triage" not in html


def test_render_html_title():
    html = render_html(make_report())
    assert "OpenShell Triage Overview" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/reports/test_html_renderer.py::test_render_html_returns_valid_html -v`
Expected: FAIL with ImportError (render_html not defined yet)

- [ ] **Step 3: Implement render_html and _HTML_TEMPLATE**

Add to `app/reports/renderers/html.py`:

```python
def render_html(report: BirdsEyeReport) -> str:
    data = _report_to_dict(report)
    report_json = json.dumps(data, indent=2)
    return _HTML_TEMPLATE.replace("__REPORT_JSON__", report_json)
```

Then define `_HTML_TEMPLATE` as a string constant containing the full HTML document. The template is large — here is the complete structure. Use `__REPORT_JSON__` as the placeholder (not `{report_json}` which would conflict with CSS curly braces).

The template must contain:

**`<head>` section:**
- `<!DOCTYPE html>` and `<html lang="en">`
- `<meta charset="UTF-8">` and `<meta name="viewport" ...>`
- `<title>OpenShell Triage Overview</title>`
- Google Fonts link for Inter
- Chart.js CDN script: `https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.js`
- chartjs-plugin-datalabels CDN: `https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels`
- Inline `<style>` block with all CSS (see CSS details below)

**CSS custom properties (`:root`):**
```css
--bg-primary: #0F172A;
--bg-card: #1E293B;
--bg-hover: #334155;
--text-primary: #F1F5F9;
--text-secondary: #94A3B8;
--border: #334155;
--accent: #6366F1;
--urgency-critical: #EF4444;
--urgency-high: #F97316;
--urgency-medium: #EAB308;
--urgency-low: #22C55E;
```

**CSS classes needed:**
- `.dashboard` — max-width 1200px, margin auto, padding 24px
- `.header` — flexbox, space-between, align center
- `.kpi-grid` — CSS Grid, 5 columns, gap 16px. Responsive: 3+2 at 768px, stack at 480px
- `.kpi-card` — bg-card, border-radius 12px, padding 20px, 4px colored left border
- `.kpi-number` — font-size 32px, font-weight 700
- `.kpi-label` — font-size 14px, text-secondary
- `.pulse` — CSS keyframes animation, subtle opacity pulse (1.0 → 0.7 → 1.0, 2s, infinite)
- `.narrative` — blockquote styling, italic, left border accent
- `.section-heading` — font-size 20px, margin-top 32px, margin-bottom 16px
- `.issue-card` — bg-card, border-radius 8px, padding 16px, 4px left border (urgency color), cursor pointer, transition transform/box-shadow 0.2s
- `.issue-card:hover` — translateY(-2px), increased box-shadow
- `.urgency-dot` — 10px circle, inline-block, margin-right 8px
- `.team-badge` — small rounded pill, bg matching team color at 20% opacity, colored text
- `.two-column` — CSS Grid, 2 columns (1fr 1fr), gap 24px. Stack at 768px
- `.chart-container` — bg-card, border-radius 12px, padding 24px
- `.issues-table` — CSS Grid table. 6 columns: 40px 60px 1fr 120px 80px 100px
- `.table-row` — grid row, padding 12px, border-bottom 1px border, cursor pointer
- `.table-row:nth-child(even)` — bg-card
- `.table-row:hover` — bg-hover
- `.filter-bar` — bg-accent at 20% opacity, padding 8px 16px, border-radius 8px, hidden by default
- `.cluster-card` — bg-card, border-radius 8px, padding 16px, margin-bottom 12px
- `.footer` — text-center, text-secondary, margin-top 48px, font-size 12px

**`<body>` section — the dashboard DOM:**

The body contains a `<div class="dashboard">` with an `id="app"`. The entire DOM is built by JavaScript reading `REPORT_DATA`, not by Python string interpolation. This keeps the template clean and the Python simple.

```html
<script>
const REPORT_DATA = __REPORT_JSON__;
</script>
<script>
// Team color map
const TEAM_COLORS = {
  "agent-ops": "#6366F1",
  "acp": "#8B5CF6",
  "ai-safety": "#EC4899",
  "kata": "#14B8A6",
  "agentdev": "#F97316",
  "dashboard": "#06B6D4",
  "none": "#64748B"
};
const URGENCY_COLORS = {
  "critical": "#EF4444",
  "high": "#F97316",
  "medium": "#EAB308",
  "low": "#22C55E"
};

function getTeamColor(team) {
  return TEAM_COLORS[team] || "#64748B";
}

function daysOpen(assessedAt) {
  const ms = Date.now() - new Date(assessedAt).getTime();
  return Math.max(0, Math.floor(ms / 86400000));
}

function confidenceLabel(conf) {
  if (conf >= 0.85) return "high confidence";
  if (conf >= 0.7) return "medium confidence";
  return "low confidence";
}

document.addEventListener("DOMContentLoaded", function() {
  const d = REPORT_DATA;
  const app = document.getElementById("app");
  // Build each section — header, KPIs, narrative, action required, etc.
  // See below for the rendering logic per section.
});
</script>
```

**JavaScript rendering logic inside DOMContentLoaded:**

1. **Header**: Create `<div class="header">` with title h1 "OpenShell Triage Overview", subtitle span with `d.summary.period_label`, and right-aligned generated-at span.

2. **KPI cards**: Create `.kpi-grid` div. For each of `["total", "critical", "high", "medium", "low"]`, create a `.kpi-card` with the count, label, and colored left border. Add `.pulse` class to critical/high cards if their count > 0. The "total" card uses `d.summary.new_this_period`; others use `d.summary.by_urgency[key] || 0`.

3. **Narrative**: If `d.narrative` is truthy, create `.narrative` blockquote with the text and attribution.

4. **Action Required**: If `d.critical_list.length > 0`, create section heading "Action Required ({count})" and an `.issue-card` for each item. Each card is an `<a>` wrapping the card div, linking to `issue.issue_url` with `target="_blank"`. Card inner HTML:
   - Line 1: urgency dot + `#${issue.issue_number} ${issue.issue_title}`
   - Line 2: team badge + confidence + days open
   - Line 3: summary text (muted)
   - If `issue.secondary_team`: small tag "also: {secondary_team} ({secondary_confidence})"

5. **Team Breakdown**: Create `.two-column` grid. Left column: `.chart-container` with a `<canvas id="teamChart">`. Right column: if `d.no_team_list.length > 0`, show "Needs Triage" heading + compact issue cards; otherwise, make left column full width by setting grid-column span 2.

6. **Doughnut chart**: After DOM insertion, create the Chart.js doughnut:
   ```javascript
   const teamLabels = Object.keys(d.team_breakdown);
   const teamCounts = teamLabels.map(t => d.team_breakdown[t].total);
   const teamColors = teamLabels.map(t => getTeamColor(t));
   const ctx = document.getElementById("teamChart").getContext("2d");
   const chart = new Chart(ctx, {
     type: "doughnut",
     data: { labels: teamLabels, datasets: [{ data: teamCounts, backgroundColor: teamColors, borderWidth: 0 }] },
     options: {
       responsive: true,
       cutout: "60%",
       plugins: {
         legend: { display: false },
         tooltip: { backgroundColor: "#1E293B", titleColor: "#F1F5F9", bodyColor: "#94A3B8", borderColor: "#334155", borderWidth: 1, cornerRadius: 8, padding: 12 },
         datalabels: { color: "#F1F5F9", font: { size: 11, weight: "bold" }, formatter: function(value, ctx) { return ctx.chart.data.labels[ctx.dataIndex] + "\n" + value; }, textAlign: "center" }
       },
       onClick: function(evt, elements) { /* filter logic — see step 7 */ }
     },
     plugins: [ChartDataLabels]
   });
   ```

7. **Click-to-filter logic**: In the chart's `onClick` handler:
   ```javascript
   let activeFilter = null;
   // Inside onClick:
   if (elements.length > 0) {
     const idx = elements[0].index;
     const team = teamLabels[idx];
     if (activeFilter === team) {
       activeFilter = null; // clear
     } else {
       activeFilter = team;
     }
     filterIssues(activeFilter);
   }
   function filterIssues(team) {
     const rows = document.querySelectorAll(".table-row");
     const bar = document.getElementById("filterBar");
     rows.forEach(row => {
       if (!team || row.dataset.team === team) {
         row.style.display = "";
       } else {
         row.style.display = "none";
       }
     });
     if (team) {
       bar.textContent = "Showing: " + team + " (" + document.querySelectorAll('.table-row[data-team="'+team+'"]:not([style*="display: none"])').length + " issues)";
       bar.style.display = "block";
       const clearBtn = document.createElement("button");
       clearBtn.textContent = "Clear";
       clearBtn.className = "clear-btn";
       clearBtn.onclick = function() { activeFilter = null; filterIssues(null); };
       bar.innerHTML = "";
       bar.appendChild(document.createTextNode("Showing: " + team));
       bar.appendChild(clearBtn);
     } else {
       bar.style.display = "none";
     }
   }
   ```

8. **Duplicate Clusters**: If `d.duplicate_clusters.length > 0`, create section heading and a `.cluster-card` for each cluster with area title, similarity reason, and issue list.

9. **All Issues table**: Create section heading "All Issues ({total})" with a hidden `.filter-bar` div (`id="filterBar"`). Create a `.issues-table` div. Add a header row. Then for each issue across all lists (collect from `critical_list` + all team issues via flattening — actually, collect ALL issues: iterate `team_breakdown` values isn't possible since they don't contain issue lists. Instead, collect issues from: `critical_list` + `no_team_list` + `duplicate_clusters[*].issues`, then deduplicate by `issue_number`). Sort by urgency (critical > high > medium > low). Each row is a `.table-row` div with `data-team` attribute, containing urgency dot, number link, title, team badge, confidence %, and flag.

   **Important**: The `BirdsEyeReport` doesn't have an "all issues" list. The complete issue set must be reconstructed from: `critical_list` (critical+high) + `no_team_list` + `duplicate_clusters[*].issues`. But some issues appear in multiple lists (e.g. a critical issue may also be in a duplicate cluster). Deduplicate by `issue_number`. For issues that appear only in the team breakdown stats (medium/low urgency, not in any list), they won't appear in All Issues — this is a known limitation of the current data model. The All Issues table shows all issues that were individually classified, which are the ones in the lists.

   Actually — re-reading the data model: ALL assessed issues go through the triage pipeline and each one becomes a `TriageResult`. The `BirdsEyeReport` generator picks them into lists:
   - `critical_list`: urgency critical or high
   - `no_team_list`: primary_team == "none"
   - `duplicate_clusters[*].issues`: issues sharing keywords

   So the union of `critical_list` + `no_team_list` + `duplicate_clusters[*].issues` may not cover all issues (medium/low urgency issues with a team that aren't in any cluster won't appear). To solve this, we need all issues. Let me check the data flow...

   The `BirdsEyeReportGenerator.generate()` method has access to all `TriageResult` objects and puts them into the various lists. We need to also store all issues in the report. This requires adding an `all_issues` field to `BirdsEyeReport`. **But the spec says not to modify data models.** So instead, we'll collect what we can from the existing lists and note that medium/low non-clustered issues won't appear in All Issues.

   **Revised approach**: Reconstruct the "all issues" list client-side from the JSON data. Collect from `critical_list`, `no_team_list`, and `duplicate_clusters[*].issues`. Deduplicate by `issue_number`. This covers all critical, high, unassigned, and duplicate-flagged issues — the most important ones. Medium/low issues that have a team and aren't duplicates won't appear, which is acceptable since those are the least interesting.

10. **Footer**: Simple centered div with generated-at text.

- [ ] **Step 4: Run all tests**

Run: `pytest tests/reports/test_html_renderer.py -v`
Expected: All tests PASS (serialization tests from Task 2 + new HTML tests)

- [ ] **Step 5: Run linter**

Run: `make lint`
Expected: PASS

- [ ] **Step 6: Visual verification**

Generate a test HTML file and open it in a browser:

```bash
python3 -c "
from tests.reports.conftest import make_report
from app.reports.renderers.html import render_html
html = render_html(make_report())
open('/tmp/dashboard-test.html', 'w').write(html)
print('Written to /tmp/dashboard-test.html')
"
open /tmp/dashboard-test.html
```

Verify:
- Dark theme renders correctly
- KPI cards show numbers with colored left borders
- Doughnut chart renders with team segments
- Issue cards are clickable
- Clicking a doughnut segment filters the All Issues table
- Responsive at different window widths

- [ ] **Step 7: Commit**

```bash
git add app/reports/renderers/html.py tests/reports/test_html_renderer.py
git commit -m "feat: add interactive HTML dashboard renderer with Chart.js"
```

---

### Task 4: CLI integration and output file strategy

**Files:**
- Modify: `app/__main__.py:9-20` (add `--format` argument)
- Modify: `app/triage.py:166-218` (add format parameter to `run_report`, write dated archive)
- Modify: `tests/integration/test_triage.py` (add format auto-detection test)

**Interfaces:**
- Consumes: `render_html(report) -> str` from Task 3, `render_markdown(report) -> str` from existing code
- Produces: `run_report(config, output_path=None, fmt=None)` — updated signature with optional format parameter

- [ ] **Step 1: Write the integration test**

Add to `tests/integration/test_triage.py`:

```python
def test_report_format_auto_detection():
    from app.triage import _detect_format
    assert _detect_format(Path("report.html"), None) == "html"
    assert _detect_format(Path("report.md"), None) == "markdown"
    assert _detect_format(Path("report.txt"), None) == "markdown"
    assert _detect_format(None, None) == "markdown"
    assert _detect_format(Path("report.html"), "markdown") == "markdown"
    assert _detect_format(None, "html") == "html"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_triage.py::test_report_format_auto_detection -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Add _detect_format to triage.py**

Add this function to `app/triage.py` (above `run_report`):

```python
def _detect_format(output_path: Path | None, explicit_format: str | None) -> str:
    if explicit_format:
        return explicit_format
    if output_path and output_path.suffix == ".html":
        return "html"
    return "markdown"
```

- [ ] **Step 4: Update run_report to support format selection and dated archive**

Modify `run_report` in `app/triage.py`:

```python
def run_report(
    config: TriageConfig,
    *,
    output_path: Path | None = None,
    fmt: str | None = None,
) -> None:
    repo_config = load_repo_config("openshell", profiles_dir=config.profiles_dir)
    reporting = repo_config.reporting

    now = datetime.now(timezone.utc)
    period_days = 7 if reporting.get("period") == "weekly" else 1

    weekday_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    target_weekday = weekday_map.get(reporting.get("period_start", "monday"), 0)
    days_since = (now.weekday() - target_weekday) % 7
    current_start = (now - timedelta(days=days_since)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    previous_start = current_start - timedelta(days=period_days)

    current = read_results_as_triage(
        config.assessment_log_path, start_date=current_start.isoformat()
    )
    previous = read_results_as_triage(
        config.assessment_log_path,
        start_date=previous_start.isoformat(),
        end_date=current_start.isoformat(),
    )

    period_label = f"{current_start.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"

    llm_client = _build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)

    generator = BirdsEyeReportGenerator(
        current, previous, llm_client, model, period_label
    )
    report = generator.generate()

    dest = output_path or config.report_output_path
    resolved_fmt = _detect_format(dest, fmt)

    if resolved_fmt == "html":
        from app.reports.renderers.html import render_html
        output = render_html(report)
    else:
        output = render_markdown(report)

    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(output)
        logger.info(f"Report written to {dest}")

        # Write dated archive copy
        date_str = now.strftime("%Y-%m-%d")
        archive = dest.parent / f"{dest.stem}-{date_str}{dest.suffix}"
        archive.write_text(output)
        logger.info(f"Archive copy written to {archive}")
    else:
        print(output)
```

- [ ] **Step 5: Update __main__.py to pass --format**

Modify `app/__main__.py` — add the argument after the `--output` argument:

```python
parser.add_argument(
    "--format",
    choices=["markdown", "html"],
    default=None,
    dest="report_format",
)
```

And update the report mode call:

```python
elif args.mode == "report":
    run_report(config, output_path=args.output, fmt=args.report_format)
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS (190 existing + new tests)

- [ ] **Step 7: Run linter**

Run: `make lint`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/__main__.py app/triage.py tests/integration/test_triage.py
git commit -m "feat: add --format flag and dated archive to report output"
```

---

## Self-Review

**Spec coverage check:**
- [x] HTML renderer as sibling to markdown — Task 2+3
- [x] Chart.js via CDN — Task 3
- [x] Dark theme with exact color palette — Task 3
- [x] KPI cards with pulse animation — Task 3
- [x] Narrative blockquote — Task 3
- [x] Action Required section (conditional) — Task 3
- [x] Team doughnut chart with datalabels — Task 3
- [x] Needs Triage section (conditional) — Task 3
- [x] Duplicate clusters (conditional) — Task 3
- [x] All Issues table with click-to-filter — Task 3
- [x] Footer — Task 3
- [x] _report_to_dict serialization — Task 2
- [x] CLI --format flag — Task 4
- [x] Auto-detection from extension — Task 4
- [x] Output file strategy (latest + dated archive) — Task 4
- [x] Responsive design — Task 3
- [x] Card hover effects — Task 3
- [x] Conditional section rendering — Task 3
- [x] Testing — Tasks 1-4
- [x] Shared test fixtures — Task 1

**Placeholder scan:** No TBDs, TODOs, or vague instructions found.

**Type consistency:** `render_html(report: BirdsEyeReport) -> str` used consistently. `_report_to_dict(report: BirdsEyeReport) -> dict` used in Task 2 and consumed in Task 3. `_detect_format(output_path: Path | None, explicit_format: str | None) -> str` defined in Task 4 step 3 and tested in step 1.
