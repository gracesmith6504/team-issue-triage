# Jinja2 Template Componentization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 1,294-line HTML/CSS/JS string embedded in `app/reports/renderers/html.py` with componentized Jinja2 templates, so each dashboard section lives in its own file and can be modified independently.

**Architecture:** Extract the monolithic `_HTML_TEMPLATE` string into a `templates/` directory with a base layout and per-section component includes. The Python module (`html.py`) keeps its existing public API (`render_html`) and data-preparation logic (`_report_to_dict`), but delegates HTML generation to Jinja2 instead of string replacement. The Dockerfile copies `templates/` alongside `app/` and `profiles/`.

**Tech Stack:** Jinja2 (ships with FastAPI/Starlette already, but we add `Jinja2>=3.1.0` to requirements.txt explicitly), Python 3.12, existing CSS and vanilla JS (no build toolchain).

## Global Constraints

- Python 3.12+, no npm or frontend build tools
- Jinja2 >= 3.1.0 (only new dependency)
- Public API unchanged: `render_html(report, enrichment=None, sparklines=None) -> str`
- `_report_to_dict` stays in `html.py` -- it's pure Python data transformation, not rendering
- XSS prevention: the existing `json.dumps(...).replace("<", "\\u003c")` pattern must be preserved when embedding JSON in `<script>` tags
- All 37 existing tests in `tests/reports/test_html_renderer.py` must continue to pass without modification
- `make test`, `make lint` must pass
- Template directory resolves relative to the package, not the working directory (use `pathlib.Path(__file__).parent / "templates"`)

## File Structure

```
app/reports/renderers/
  __init__.py              (unchanged)
  html.py                  (modify: replace _HTML_TEMPLATE string with Jinja2 render call)
  markdown.py              (unchanged)
  templates/
    base.html              (document shell: <html>, <head>, CSS, <body>, JS utilities, DOMContentLoaded assembly)
    components/
      topbar.js            (buildTopBar function)
      kpis.js              (buildKPIs function)
      alerts.js            (buildAlerts function)
      team_routing.js      (buildTeamRouting function)
      pr_health.js         (buildPRHealth function)
      contributor_health.js (buildContributorHealth function)
      area_breakdown.js    (buildAreaBreakdown function)
      issues_table.js      (buildAllIssuesTable + rebuildIssuesTable + filtering)
      duplicates.js        (buildDuplicates function)
      footer.js            (buildFooter function)
```

**Why JS files, not HTML component files:** The current dashboard is a single-page app that builds all DOM elements in JavaScript from the embedded `REPORT_DATA` JSON. The HTML body is just two empty divs (`<div id="topbar">` and `<div id="app">`). The actual "components" are JavaScript builder functions, not server-rendered HTML fragments. Jinja2's role here is to assemble the document shell (CSS + JS includes + JSON data injection), while each JS file contains one builder function. This means:

1. Each dashboard section is one file you can open and edit independently
2. Syntax highlighting works properly (`.js` files, not strings)
3. Adding a new section = new `.js` file + one `{% include %}` + one `app.appendChild()` call
4. The architecture doesn't lie about what's actually happening (client-side rendering)

---

### Task 1: Add Jinja2 dependency and template loading infrastructure

**Files:**
- Modify: `requirements.txt`
- Modify: `app/reports/renderers/html.py:1-10` (add Jinja2 import and template loader)
- Modify: `Dockerfile` (add `COPY templates/ templates/` -- but we'll do this in Task 3 after templates exist)
- Test: `tests/reports/test_html_renderer.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `_get_template() -> jinja2.Template` (module-level helper that loads `base.html` from the templates directory)

- [ ] **Step 1: Write the failing test**

Add a test that verifies the template directory exists and contains `base.html`:

```python
# tests/reports/test_html_renderer.py — append at bottom

def test_template_directory_exists():
    from pathlib import Path
    import app.reports.renderers.html as html_mod

    template_dir = Path(html_mod.__file__).parent / "templates"
    assert template_dir.is_dir(), f"Template directory missing: {template_dir}"
    assert (template_dir / "base.html").is_file(), "base.html template missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py::test_template_directory_exists -v`
Expected: FAIL with "Template directory missing"

- [ ] **Step 3: Add Jinja2 to requirements.txt**

Change `requirements.txt` to:

```
anthropic[vertex]>=0.49.0
requests>=2.31.0
PyYAML>=6.0
fastapi>=0.115.0
uvicorn>=0.30.0
Jinja2>=3.1.0
```

- [ ] **Step 4: Install the new dependency**

Run: `cd /Users/grasmith/github/team-issue-triage && pip install Jinja2>=3.1.0`

- [ ] **Step 5: Create the template directory structure and empty base.html**

```bash
mkdir -p /Users/grasmith/github/team-issue-triage/app/reports/renderers/templates/components
```

Create `app/reports/renderers/templates/base.html` with a minimal placeholder:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>OpenShell Overview</title>
</head>
<body>
<div class="topbar" id="topbar"></div>
<div class="dashboard" id="app"></div>
<script>
const REPORT_DATA = {{ report_json }};
</script>
</body>
</html>
```

- [ ] **Step 6: Add Jinja2 loader to html.py**

Add these imports and the loader at the top of `app/reports/renderers/html.py`, after the existing imports:

```python
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=False,  # We handle XSS via json.dumps escaping, not HTML autoescape
)


def _get_template():
    return _jinja_env.get_template("base.html")
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py::test_template_directory_exists -v`
Expected: PASS

- [ ] **Step 8: Run all existing tests to verify nothing broke**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py -v`
Expected: All 37 tests PASS (we haven't changed `render_html` yet)

- [ ] **Step 9: Commit**

```bash
git add requirements.txt app/reports/renderers/html.py app/reports/renderers/templates/
git commit -m "feat: add Jinja2 dependency and template loading infrastructure"
```

---

### Task 2: Extract CSS into base.html

**Files:**
- Modify: `app/reports/renderers/templates/base.html`
- Test: `tests/reports/test_html_renderer.py`

**Interfaces:**
- Consumes: `_get_template()` from Task 1
- Produces: `base.html` with full CSS in `<style>` block (lines 112-554 of current `_HTML_TEMPLATE`)

This task builds out `base.html` with the complete document shell and CSS. We don't switch `render_html` to use it yet -- that happens in Task 4 after all JS components are extracted.

- [ ] **Step 1: Write the failing test**

```python
# tests/reports/test_html_renderer.py — append at bottom

def test_base_template_has_css():
    from pathlib import Path

    template_path = Path(__file__).resolve().parents[2] / "app" / "reports" / "renderers" / "templates" / "base.html"
    content = template_path.read_text()
    assert "<style>" in content
    assert "--bg-body: #f4f5f7" in content
    assert "--urgency-critical:" in content
    assert "kpi-grid" in content
    assert "@media" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py::test_base_template_has_css -v`
Expected: FAIL (base.html only has placeholder content)

- [ ] **Step 3: Build out base.html with full document shell**

Replace the placeholder `base.html` with the complete document structure. Copy the `<head>` section (lines 112-120 of current `_HTML_TEMPLATE`), the full `<style>` block (lines 121-554), and the `<body>` structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenShell Overview</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
/* Copy lines 122-553 from the current _HTML_TEMPLATE verbatim */
/* This is the full CSS from :root { ... } through the @media queries */
:root {
  --bg-body: #f4f5f7;
  /* ... entire CSS block ... */
}
/* ... all CSS rules ... */
</style>
</head>
<body>

<div class="topbar" id="topbar"></div>
<div class="dashboard" id="app"></div>

<script>
const REPORT_DATA = {{ report_json }};
</script>
<script>
(function() {
  "use strict";

  /* PLACEHOLDER: JS component {% include %} directives and DOMContentLoaded */
  /* handler will be added in Task 3 after component files are created.     */
  /* Do NOT add {% include %} lines here yet -- the files don't exist.      */

})();
</script>
</body>
</html>
```

**Important:** Copy the CSS verbatim from lines 122-553 of the current `_HTML_TEMPLATE` in `html.py`. Do not modify, reformat, or "improve" it. The existing tests check for specific CSS values like `--bg-body: #f4f5f7`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py::test_base_template_has_css -v`
Expected: PASS

- [ ] **Step 5: Run all tests**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py -v`
Expected: All tests PASS (we still haven't changed `render_html`)

- [ ] **Step 6: Commit**

```bash
git add app/reports/renderers/templates/base.html
git commit -m "feat: extract CSS and document shell into base.html template"
```

---

### Task 3: Extract JavaScript into component files

**Files:**
- Create: `app/reports/renderers/templates/components/shared.js`
- Create: `app/reports/renderers/templates/components/topbar.js`
- Create: `app/reports/renderers/templates/components/kpis.js`
- Create: `app/reports/renderers/templates/components/alerts.js`
- Create: `app/reports/renderers/templates/components/team_routing.js`
- Create: `app/reports/renderers/templates/components/pr_health.js`
- Create: `app/reports/renderers/templates/components/contributor_health.js`
- Create: `app/reports/renderers/templates/components/area_breakdown.js`
- Create: `app/reports/renderers/templates/components/issues_table.js`
- Create: `app/reports/renderers/templates/components/duplicates.js`
- Create: `app/reports/renderers/templates/components/footer.js`
- Modify: `app/reports/renderers/templates/base.html` (add `{% include %}` directives)
- Test: `tests/reports/test_html_renderer.py`

**Interfaces:**
- Consumes: `base.html` from Task 2
- Produces: Complete set of JS component files that, when included via Jinja2, produce the same JavaScript output as the current `_HTML_TEMPLATE`

The JS in the current template (lines 561-1291) breaks into these natural sections:

| File | Current lines | Function(s) |
|------|--------------|-------------|
| `shared.js` | 566-611 | Constants (`TEAM_COLORS`, `URGENCY_COLORS`, etc.), utility functions (`esc`, `el`, `tc`, `uc`, `sparkSVG`, `makeTeamBadgeHTML`, `makeUrgencyBadgeHTML`), localStorage state management |
| `topbar.js` | 657-725 | `buildTopBar()` |
| `kpis.js` | 727-759 | `buildKPIs()` |
| `alerts.js` | 761-787 | `buildAlerts()` |
| `team_routing.js` | 789-843 | `buildTeamRouting()` |
| `pr_health.js` | 845-937 | `buildPRHealth()` |
| `contributor_health.js` | 939-1032 | `buildContributorHealth()` |
| `area_breakdown.js` | 1034-1079 | `buildAreaBreakdown()` |
| `issues_table.js` | 614-655, 1081-1248 | `matchesFilters()`, `applyAllFilters()`, `buildAllIssuesTable()`, `rebuildIssuesTable()`, `currentSort` state, `issuesTableBody` ref |
| `duplicates.js` | 1081-1106 | `buildDuplicates()` |
| `footer.js` | 1250-1255 | `buildFooter()` |

- [ ] **Step 1: Write the failing test**

```python
# tests/reports/test_html_renderer.py — append at bottom

def test_all_component_files_exist():
    from pathlib import Path

    components_dir = Path(__file__).resolve().parents[2] / "app" / "reports" / "renderers" / "templates" / "components"
    expected = [
        "shared.js", "topbar.js", "kpis.js", "alerts.js",
        "team_routing.js", "pr_health.js", "contributor_health.js",
        "area_breakdown.js", "issues_table.js", "duplicates.js", "footer.js",
    ]
    for name in expected:
        assert (components_dir / name).is_file(), f"Missing component: {name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py::test_all_component_files_exist -v`
Expected: FAIL

- [ ] **Step 3: Create shared.js**

File: `app/reports/renderers/templates/components/shared.js`

Copy lines 568-611 from the current `_HTML_TEMPLATE` — the constants block and utility functions. This includes:

```javascript
var TEAM_COLORS = {
  "agent-ops": "#6366F1", "acp": "#8B5CF6", "ai-safety": "#EC4899",
  "kata": "#14B8A6", "agentdev": "#F97316", "dashboard": "#06B6D4", "none": "#64748B"
};
var URGENCY_COLORS = {"critical": "#d1242f", "high": "#e16f24", "medium": "#d4a015", "low": "#1a7f37"};
var URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3};
var URGENCY_SHORT = {"critical": "CRIT", "high": "HIGH", "medium": "MED", "low": "LOW"};

function esc(t) { var d = document.createElement("div"); d.appendChild(document.createTextNode(t)); return d.innerHTML; }
function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; return e; }
function tc(team) { return TEAM_COLORS[team] || "#64748B"; }
function uc(u) { return URGENCY_COLORS[u] || "#64748B"; }

function sparkSVG(data, color, w, h) {
  // ... copy the full sparkSVG function (lines 581-592)
}

function makeTeamBadgeHTML(team) {
  // ... copy full function (lines 594-598)
}

function makeUrgencyBadgeHTML(u) {
  // ... copy full function (lines 600-603)
}

var STORAGE_KEY = "openshell-triage-v3";
function loadState() { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch(e) { return {}; } }
function saveState(s) { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); } catch(e) {} }

var state = loadState();
if (!state.dismissed) state.dismissed = [];
if (!state.collapsed) state.collapsed = {};
if (!state.dateRange) state.dateRange = "14d";

var d = REPORT_DATA;
```

Copy each function verbatim from the current `_HTML_TEMPLATE`.

- [ ] **Step 4: Create issues_table.js**

File: `app/reports/renderers/templates/components/issues_table.js`

This file contains the filter state, filter functions, and the issues table builder. Copy from the current template:

```javascript
var activeTeams = [];
var activeUrgencies = [];
var activeArea = "";
var searchQuery = "";

function matchesFilters(issue) {
  // ... copy lines 621-631
}

function applyAllFilters() {
  // ... copy lines 634-655
}

var issuesTableBody;
var currentSort = {col: "urgency", dir: "asc"};

function buildAllIssuesTable() {
  // ... copy lines 1111-1181
}

function rebuildIssuesTable() {
  // ... copy lines 1183-1248
}
```

Copy each function verbatim.

- [ ] **Step 5: Create the remaining component files**

For each of the following, create the file and copy the corresponding function verbatim from the current `_HTML_TEMPLATE`:

**`topbar.js`** — copy `buildTopBar()` (lines 657-725)
**`kpis.js`** — copy `buildKPIs()` (lines 727-759)
**`alerts.js`** — copy `buildAlerts()` (lines 761-787)
**`team_routing.js`** — copy `buildTeamRouting()` (lines 789-843)
**`pr_health.js`** — copy `buildPRHealth()` (lines 845-937)
**`contributor_health.js`** — copy `buildContributorHealth()` (lines 939-1032)
**`area_breakdown.js`** — copy `buildAreaBreakdown()` (lines 1034-1079)
**`duplicates.js`** — copy `buildDuplicates()` (lines 1081-1106)
**`footer.js`** — copy `buildFooter()` (lines 1250-1255)

Every function must be copied character-for-character. Do not rename variables, reformat, or "improve" the code. The goal is a pure extraction with zero behavior change.

- [ ] **Step 6: Update base.html to include components and wire up DOMContentLoaded**

Update the `<script>` section in `base.html` to include all component files and wire up the DOMContentLoaded handler:

```html
<script>
const REPORT_DATA = {{ report_json }};
</script>
<script>
(function() {
  "use strict";

  {% include "components/shared.js" %}
  {% include "components/issues_table.js" %}
  {% include "components/topbar.js" %}
  {% include "components/kpis.js" %}
  {% include "components/alerts.js" %}
  {% include "components/team_routing.js" %}
  {% include "components/pr_health.js" %}
  {% include "components/contributor_health.js" %}
  {% include "components/area_breakdown.js" %}
  {% include "components/duplicates.js" %}
  {% include "components/footer.js" %}

  document.addEventListener("DOMContentLoaded", function() {
    buildTopBar();
    var app = document.getElementById("app");

    var banner = el("div", "filter-banner");
    banner.id = "filter-banner";
    banner.innerHTML = '<span>Filtered:</span><span class="filter-tags"></span>';
    var clearBtn = el("button", "clear-filters", "Clear all");
    clearBtn.addEventListener("click", function() {
      activeTeams = []; activeUrgencies = []; activeArea = ""; searchQuery = "";
      document.querySelectorAll(".area-name.active-area").forEach(function(a) { a.classList.remove("active-area"); });
      document.querySelectorAll(".filter-pill.active").forEach(function(p) {
        p.classList.remove("active");
        p.style.background = "transparent"; p.style.color = "var(--text-muted)";
      });
      var searchEl = document.querySelector(".search-input");
      if (searchEl) searchEl.value = "";
      applyAllFilters();
    });
    banner.appendChild(clearBtn);
    app.appendChild(banner);

    app.appendChild(buildKPIs());
    app.appendChild(buildAlerts());
    app.appendChild(buildTeamRouting());
    if (d.pr_health) app.appendChild(buildPRHealth());
    if (d.vouch_status) app.appendChild(buildContributorHealth());
    app.appendChild(buildAreaBreakdown());
    app.appendChild(buildAllIssuesTable());
    app.appendChild(buildDuplicates());
    app.appendChild(buildFooter());
  });

})();
</script>
```

Copy the DOMContentLoaded handler (lines 1257-1288 of current template) verbatim.

- [ ] **Step 7: Run the component existence test**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py::test_all_component_files_exist -v`
Expected: PASS

- [ ] **Step 8: Run all tests**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py -v`
Expected: All tests PASS (we still haven't changed `render_html` -- old `_HTML_TEMPLATE` is still used)

- [ ] **Step 9: Commit**

```bash
git add app/reports/renderers/templates/
git commit -m "feat: extract JS into component files and wire up base.html includes"
```

---

### Task 4: Switch render_html to use Jinja2 and remove _HTML_TEMPLATE

**Files:**
- Modify: `app/reports/renderers/html.py` (change `render_html` to use `_get_template().render()`, delete `_HTML_TEMPLATE`)
- Modify: `Dockerfile` (add `COPY app/reports/renderers/templates/ app/reports/renderers/templates/`)
- Test: `tests/reports/test_html_renderer.py`

**Interfaces:**
- Consumes: `_get_template()` from Task 1, complete `base.html` from Tasks 2-3
- Produces: `render_html()` using Jinja2 instead of string replacement (same return type: `str`)

This is the switchover. After this task, the old `_HTML_TEMPLATE` string is gone.

- [ ] **Step 1: Write the failing test**

```python
# tests/reports/test_html_renderer.py — append at bottom

def test_render_html_uses_jinja2_template():
    """Verify render_html delegates to Jinja2, not string replacement."""
    import app.reports.renderers.html as html_mod
    assert not hasattr(html_mod, "_HTML_TEMPLATE"), \
        "_HTML_TEMPLATE should be removed after Jinja2 migration"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py::test_render_html_uses_jinja2_template -v`
Expected: FAIL (\_HTML\_TEMPLATE still exists)

- [ ] **Step 3: Update render_html to use Jinja2**

In `app/reports/renderers/html.py`, replace the `render_html` function:

```python
def render_html(
    report: BirdsEyeReport,
    enrichment: dict | None = None,
    sparklines: dict[str, list[int]] | None = None,
) -> str:
    data = _report_to_dict(report, enrichment, sparklines)
    report_json = json.dumps(data, indent=2).replace("<", "\\u003c")
    template = _get_template()
    return template.render(report_json=report_json)
```

- [ ] **Step 4: Delete the _HTML_TEMPLATE string**

Remove the entire `_HTML_TEMPLATE = """\` block (lines 111-1294 of the current file). This is the monolithic string being replaced.

After deletion, `html.py` should contain:
- Imports (including the new Jinja2 ones from Task 1)
- `_convert_value`, `_AREA_RE`, `_extract_area` (unchanged)
- `_TEMPLATE_DIR`, `_jinja_env`, `_get_template` (from Task 1)
- `_report_to_dict` (unchanged)
- `render_html` (updated to use Jinja2)

The file should be roughly 110-120 lines.

- [ ] **Step 5: Run the new test**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py::test_render_html_uses_jinja2_template -v`
Expected: PASS

- [ ] **Step 6: Run ALL existing tests**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py -v`
Expected: All 37 original tests + 3 new tests PASS.

If any test fails, the Jinja2 template output differs from the old string. Debug by comparing `render_html(make_report())` output before and after. Common issues:
- Jinja2 adds/removes whitespace: fix with `{%- -%}` trim markers or adjust the template
- `{{ report_json }}` needs to be wrapped in `{{ report_json | safe }}` if autoescape were on (but we set `autoescape=False`)
- Missing `{% include %}` directive

- [ ] **Step 7: Update the Dockerfile**

The Dockerfile already copies `app/` recursively (`COPY app/ app/`), which includes `app/reports/renderers/templates/`. Verify this by reading the Dockerfile. No change needed unless `templates/` is outside `app/`.

Verify: `COPY app/ app/` in the Dockerfile covers `app/reports/renderers/templates/` -- it does, because templates are inside the `app/` tree. No Dockerfile change needed.

- [ ] **Step 8: Run the full test suite**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 9: Run lint**

Run: `cd /Users/grasmith/github/team-issue-triage && make lint`
Expected: PASS (no lint errors)

- [ ] **Step 10: Commit**

```bash
git add app/reports/renderers/html.py Dockerfile
git commit -m "feat: switch render_html to Jinja2 templates, remove monolithic HTML string"
```

---

### Task 5: Verify end-to-end and clean up

**Files:**
- Modify: `app/reports/renderers/templates/base.html` (only if needed to fix issues found in verification)
- Test: `tests/reports/test_html_renderer.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4
- Produces: verified, working dashboard with visual confirmation

- [ ] **Step 1: Write an end-to-end template rendering test**

```python
# tests/reports/test_html_renderer.py — append at bottom

def test_render_html_end_to_end_structure():
    """Verify the full rendered output has all expected sections."""
    pr_data = {
        "total_open": 42, "awaiting_review": 5, "stale_14d": 3,
        "gator_coverage_pct": 60, "merge_velocity": 8, "merge_velocity_prev": 6,
        "avg_review_wait_days": 4.2, "stuck_prs": [],
        "codeowners": ["mrunalp"],
        "age_distribution": {
            "lt_1w": {"count": 10, "label": "< 1 week"},
            "1_2w": {"count": 8, "label": "1-2 weeks"},
            "2_4w": {"count": 12, "label": "2-4 weeks"},
            "gt_1m": {"count": 12, "label": "> 1 month"},
        },
    }
    vouch_data = {
        "total_pending": 3, "responded_in_7d": 1,
        "longest_wait_days": 45, "over_30d_count": 2,
        "pending_vouches": [{
            "author": "testuser", "discussion_number": 100,
            "url": "https://github.com/test/100",
            "wait_days": 45, "created_at": "2026-06-01T00:00:00Z",
        }],
    }
    html = render_html(make_report(pr_health=pr_data, vouch_status=vouch_data))

    assert "<!DOCTYPE html>" in html
    assert "REPORT_DATA" in html
    assert "buildTopBar" in html
    assert "buildKPIs" in html
    assert "buildAlerts" in html
    assert "buildTeamRouting" in html
    assert "buildPRHealth" in html
    assert "buildContributorHealth" in html
    assert "buildAreaBreakdown" in html
    assert "buildAllIssuesTable" in html
    assert "buildDuplicates" in html
    assert "buildFooter" in html
    assert "OpenShell Overview" in html
    assert "--bg-body: #f4f5f7" in html
```

- [ ] **Step 2: Run end-to-end test**

Run: `cd /Users/grasmith/github/team-issue-triage && python3 -m pytest tests/reports/test_html_renderer.py::test_render_html_end_to_end_structure -v`
Expected: PASS

- [ ] **Step 3: Generate a real dashboard and open it in browser**

```bash
cd /Users/grasmith/github/team-issue-triage
python3 -c "
from tests.reports.conftest import make_report, make_result
from app.core.models import Urgency
from app.reports.renderers.html import render_html

pr_data = {
    'total_open': 42, 'awaiting_review': 5, 'stale_14d': 3,
    'gator_coverage_pct': 60, 'merge_velocity': 8, 'merge_velocity_prev': 6,
    'avg_review_wait_days': 4.2,
    'stuck_prs': [{'number': 2401, 'url': 'https://github.com/NVIDIA/OpenShell/pull/2401', 'title': 'fix(sandbox): namespace cleanup', 'author': 'testuser', 'days_open': 21, 'last_activity': '14d', 'participants': ['reviewer1']}],
    'codeowners': ['mrunalp', 'maxamillion'],
    'age_distribution': {
        'lt_1w': {'count': 10, 'label': '< 1 week'},
        '1_2w': {'count': 8, 'label': '1-2 weeks'},
        '2_4w': {'count': 12, 'label': '2-4 weeks'},
        'gt_1m': {'count': 12, 'label': '> 1 month'},
    },
}
vouch_data = {
    'total_pending': 3, 'responded_in_7d': 1,
    'longest_wait_days': 45, 'over_30d_count': 2,
    'pending_vouches': [
        {'author': 'contributor1', 'discussion_number': 100, 'url': 'https://github.com/test/100', 'wait_days': 45, 'created_at': '2026-06-01T00:00:00Z'},
        {'author': 'contributor2', 'discussion_number': 101, 'url': 'https://github.com/test/101', 'wait_days': 12, 'created_at': '2026-07-01T00:00:00Z'},
    ],
}
report = make_report(
    all_issues=[
        make_result(1, 'feat(sandbox): SPIFFE crash on startup', team='agent-ops', urgency=Urgency.CRITICAL),
        make_result(2, 'fix(gateway): OIDC token refresh fails', team='acp', urgency=Urgency.HIGH),
        make_result(3, 'bug(cli): help text missing for new flags', team='agent-ops', urgency=Urgency.MEDIUM),
    ],
    pr_health=pr_data,
    vouch_status=vouch_data,
)
html = render_html(report)
open('/tmp/triage-test.html', 'w').write(html)
print('Dashboard written to /tmp/triage-test.html')
"
open /tmp/triage-test.html
```

- [ ] **Step 4: Visual verification**

Verify in the browser:
- [ ] Page loads without JavaScript errors (check browser console)
- [ ] KPI cards render with sparklines
- [ ] Alert strip shows high-urgency count and stale PR count
- [ ] Team routing section has expandable team bands
- [ ] PR Health section has age distribution bar and stuck PRs table
- [ ] Contributor Health section has vouch list with pagination
- [ ] Area Breakdown has clickable area filters
- [ ] All Issues table has sortable columns and urgency filter pills
- [ ] Search works in the topbar
- [ ] Footer shows generation date

- [ ] **Step 5: Run full test suite and lint**

```bash
cd /Users/grasmith/github/team-issue-triage && make test && make lint
```
Expected: All tests PASS, no lint errors

- [ ] **Step 6: Verify file sizes are sane**

```bash
wc -l app/reports/renderers/html.py
wc -l app/reports/renderers/templates/base.html
wc -l app/reports/renderers/templates/components/*.js
```

Expected:
- `html.py` — ~110-120 lines (down from 1,294)
- `base.html` — ~480-500 lines (CSS + document structure + DOMContentLoaded assembly)
- Largest JS component — ~170 lines (`issues_table.js`)
- Smallest JS component — ~6 lines (`footer.js`)

- [ ] **Step 7: Commit**

```bash
git add tests/reports/test_html_renderer.py
git commit -m "test: add end-to-end template rendering verification"
```
