# Refined Visual Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the polished CSS refinement layer and JS bug fixes from the prototype dashboard into the componentized Jinja2 templates, upgrading the dashboard from "works" to "looks like a real product."

**Architecture:** The visual upgrade uses a two-layer CSS approach — the existing base styles remain untouched, and a second `<style id="refined">` block overrides them with upgraded typography, shadows, transitions, and card effects. Three JS component files get small bug fixes. All changes are additive — no existing code is modified in ways that could break tests.

**Tech Stack:** CSS custom properties, Google Fonts (Inter Tight, JetBrains Mono), Jinja2 templates, vanilla JavaScript

## Global Constraints

- NEVER include `Co-Authored-By` lines in commit messages
- Always run `make lint` before pushing
- One logical change = one commit, squash before review, use `--force-with-lease`
- All 292 existing tests must continue to pass
- Title must say "OpenShell Overview" everywhere
- No em/en dashes (use hyphens only)
- No npm/build toolchain — all CSS/JS is inline in the HTML template
- The source of truth for the visual refinements is `/Users/grasmith/Downloads/dashboard.html` (lines 488-806 for the refined CSS block)

---

### Task 1: Add refined CSS layer to base.html

**Files:**
- Modify: `app/reports/renderers/templates/base.html`
- Test: `tests/reports/test_html_renderer.py`

**Interfaces:**
- Consumes: nothing from other tasks
- Produces: updated `base.html` with refined CSS that all JS components render into

This task makes three types of CSS changes to `base.html`:
1. Update the Google Fonts `<link>` to include Inter Tight and JetBrains Mono
2. Add missing base CSS rules (4 small additions)
3. Add the complete `<style id="refined">` override block

- [ ] **Step 1: Update the Google Fonts link**

In `app/reports/renderers/templates/base.html`, replace line 9:

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

with:

```html
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=Inter:wght@400;450;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Add missing base CSS rules**

In the first `<style>` block, add these 4 rules at the exact locations specified:

**2a.** After `.team-dropdown label:hover { background: var(--bg-card-hover); }` (current line 111), add:

```css
.team-dropdown input[type="checkbox"] { accent-color: var(--accent); }
```

**2b.** Before `.team-band-bar .segment` (current line 188), add the parent rule:

```css
.team-band-bar {
  flex: 1; height: 8px; border-radius: 4px;
  background: var(--bg-surface); overflow: hidden;
  display: flex; margin: 0 12px;
}
```

**2c.** After `.area-trend { ... }` and the trend color rules (after current line 342), add the blocked contributor styles:

```css
.blocked-contributor {
  background: var(--bg-card); border-radius: var(--radius-md);
  padding: 16px 18px; margin-bottom: 10px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--status-blocked);
}
.blocked-contributor .bc-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.blocked-contributor .bc-author { font-weight: 600; font-size: 15px; }
.blocked-contributor .bc-author a { color: var(--accent); text-decoration: none; }
.blocked-contributor .bc-author a:hover { text-decoration: underline; }
.blocked-contributor .bc-meta { font-size: 13px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.5; }
.blocked-contributor .bc-links { display: flex; gap: 10px; }
.blocked-contributor .bc-links a {
  font-size: 13px; color: var(--accent); text-decoration: none;
  padding: 5px 14px; border: 1px solid var(--accent);
  border-radius: var(--radius-sm); transition: all var(--transition);
}
.blocked-contributor .bc-links a:hover { background: var(--accent); color: #fff; }
```

**2d.** After `.team-band.filtered-out { opacity: 0.25; pointer-events: none; }` (current line 426), add:

```css
.team-band.filtered-out .team-band-header { cursor: default; }
```

- [ ] **Step 3: Add the refined CSS override block**

After the closing `</style>` of the base CSS block (after the `@media` rules) and before `</head>`, add a second style block. Read the exact content from `/Users/grasmith/Downloads/dashboard.html` lines 488-806 (the `<style id="refined">` block). Copy it verbatim — it starts with:

```html
<style id="refined">
/* ══════════════════════════════════════════════════
   REFINED VISUAL LAYER — overrides base styles
   ══════════════════════════════════════════════════ */
:root {
  --bg-body: #f2f4f7;
```

and ends with:

```css
.active-filter-tag { background: var(--accent-soft); border-radius: 8px; padding: 3px 10px; }

</style>
```

This block is approximately 318 lines. Copy ALL of it exactly from the source file.

- [ ] **Step 4: Write a test for the refined CSS layer**

Add this test to `tests/reports/test_html_renderer.py` after `test_base_template_has_css`:

```python
def test_base_template_has_refined_css():
    from pathlib import Path

    template_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "reports"
        / "renderers"
        / "templates"
        / "base.html"
    )
    content = template_path.read_text()
    assert '<style id="refined">' in content
    assert "REFINED VISUAL LAYER" in content
    assert "Inter Tight" in content
    assert "cubic-bezier" in content
    assert "--accent-soft:" in content
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/reports/test_html_renderer.py -v`

Expected: ALL tests pass, including the new `test_base_template_has_refined_css`.

- [ ] **Step 6: Run lint**

Run: `make lint`

Expected: Clean pass (CSS/HTML changes don't affect Python lint).

- [ ] **Step 7: Commit**

```bash
git add app/reports/renderers/templates/base.html tests/reports/test_html_renderer.py
git commit -m "style: add refined visual layer with upgraded typography and card effects"
```

---

### Task 2: Fix JS component bugs to match polished prototype

**Files:**
- Modify: `app/reports/renderers/templates/components/topbar.js`
- Modify: `app/reports/renderers/templates/components/alerts.js`
- Modify: `app/reports/renderers/templates/components/footer.js`

**Interfaces:**
- Consumes: updated `base.html` CSS from Task 1 (but works independently)
- Produces: polished JS behavior matching the prototype

This task fixes 3 small JS bugs/improvements found in the prototype dashboard.

- [ ] **Step 1: Add DATE_LABELS and period text update to topbar.js**

In `app/reports/renderers/templates/components/topbar.js`, the date pill click handler currently just toggles the active class but doesn't update the period text. Replace the `buildTopBar` function with this version that adds a `DATE_LABELS` lookup and updates the period span:

Replace the entire content of `topbar.js` with:

```javascript
var DATE_LABELS = {
  "7d": "Last 7 Days",
  "14d": d.summary.period_label,
  "30d": d.summary.period_label
};

function buildTopBar() {
  var bar = document.getElementById("topbar");

  var left = el("div", "topbar-left");
  left.innerHTML = '<span class="topbar-title">OpenShell Overview</span><span class="topbar-period">' + esc(d.summary.period_label) + '</span>';
  bar.appendChild(left);

  var center = el("div", "topbar-center");
  ["7d", "14d", "30d"].forEach(function(range) {
    var pill = el("button", "date-pill" + (state.dateRange === range ? " active" : ""));
    pill.textContent = range;
    pill.title = "Date range filtering available in live mode";
    pill.addEventListener("click", function() {
      state.dateRange = range;
      saveState(state);
      bar.querySelectorAll(".date-pill").forEach(function(p) { p.classList.remove("active"); });
      pill.classList.add("active");
      var periodEl = bar.querySelector(".topbar-period");
      if (periodEl) periodEl.textContent = DATE_LABELS[range] || d.summary.period_label;
    });
    center.appendChild(pill);
  });
  bar.appendChild(center);

  var right = el("div", "topbar-right");

  var filterWrap = el("div", "team-filter-wrap");
  var filterBtn = el("button", "team-filter-btn");
  filterBtn.innerHTML = 'Jump to team <span class="chevron">&#9660;</span>';
  var dropdown = el("div", "team-dropdown");
  var teams = Object.keys(d.team_breakdown);
  teams.forEach(function(t) {
    var lbl = el("label");
    lbl.style.cursor = "pointer";
    lbl.innerHTML = makeTeamBadgeHTML(t);
    lbl.addEventListener("click", function(e) {
      e.stopPropagation();
      dropdown.classList.remove("open");
      filterBtn.classList.remove("open");
      var band = document.querySelector('.team-band[data-team="' + t + '"]');
      if (band) {
        band.open = true;
        band.scrollIntoView({behavior: "smooth", block: "center"});
      }
    });
    dropdown.appendChild(lbl);
  });
  filterBtn.addEventListener("click", function(e) {
    e.stopPropagation();
    filterBtn.classList.toggle("open");
    dropdown.classList.toggle("open");
  });
  document.addEventListener("click", function() { filterBtn.classList.remove("open"); dropdown.classList.remove("open"); });
  filterWrap.appendChild(filterBtn);
  filterWrap.appendChild(dropdown);
  right.appendChild(filterWrap);

  var searchInput = el("input", "search-input");
  searchInput.type = "text"; searchInput.placeholder = "Search issues...";
  var searchTimeout;
  searchInput.addEventListener("input", function() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(function() {
      searchQuery = searchInput.value;
      applyAllFilters();
    }, 200);
  });
  right.appendChild(searchInput);

  bar.appendChild(right);
}
```

- [ ] **Step 2: Fix longest vouch lookup in alerts.js**

In `app/reports/renderers/templates/components/alerts.js`, the longest vouch is currently taken from `pending_vouches[0]` (the first/newest). When the array is sorted by wait_days ascending (0, 2, 7, 12...), the longest wait is at the END of the array.

Replace this line (current line 17):

```javascript
    var longestVouch = d.vouch_status.pending_vouches.length ? d.vouch_status.pending_vouches[0] : null;
```

with:

```javascript
    var longestVouch = d.vouch_status.pending_vouches.length ? d.vouch_status.pending_vouches[d.vouch_status.pending_vouches.length - 1] : null;
```

- [ ] **Step 3: Add repo link to footer.js**

Replace the entire content of `app/reports/renderers/templates/components/footer.js` with:

```javascript
function buildFooter() {
  var footer = el("div", "footer");
  var genDate = d.generated_at ? new Date(d.generated_at).toLocaleDateString('en-US', {year: 'numeric', month: 'short', day: 'numeric'}) : 'unknown';
  footer.innerHTML = 'OpenShell Overview &middot; Generated ' + genDate + ' &middot; <a href="https://github.com/gracesmith6504/team-issue-triage" target="_blank">team-issue-triage</a>';
  return footer;
}
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/ -v`

Expected: ALL 292+ tests pass.

- [ ] **Step 5: Run lint**

Run: `make lint`

Expected: Clean pass.

- [ ] **Step 6: Commit**

```bash
git add app/reports/renderers/templates/components/topbar.js app/reports/renderers/templates/components/alerts.js app/reports/renderers/templates/components/footer.js
git commit -m "fix: add date label updates, correct longest vouch lookup, add repo link"
```
