# Gator Tile Swap & PR Stage Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the low-signal "Gator Coverage" KPI tile with actionable "Avg Review Wait" and add per-PR gator stage badges to the neglected PRs table.

**Architecture:** Pure frontend change — all data fields already exist in the Python dataclasses and are populated by the fetcher. The tile swap changes one entry in a JS array. The gator column adds a `<th>`, a `<td>` with a colored badge, and CSS for badge colors.

**Tech Stack:** Inline JS/CSS in Jinja2 HTML templates (no build toolchain)

## Global Constraints

- NEVER include `Co-Authored-By` lines in commit messages
- No npm/build toolchain — CSS/JS is inline in HTML templates
- One logical change = one commit
- Always run `make lint` before pushing
- All existing tests must pass (`python3 -m pytest tests/ -q`)

---

## File Map

| File | Role | Change |
|------|------|--------|
| `app/reports/renderers/templates/components/pr_health.js` | PR Health KPI tiles + neglected PRs table | Swap tile, add column |
| `app/reports/renderers/templates/base.html` | All CSS | Add `.gator-badge` styles |

No Python or test changes required — `avg_review_wait_days` (float) and `gator_label` (string|null) are already computed and serialized to JSON by the existing pipeline.

---

### Task 1: Swap Gator Coverage tile for Avg Review Wait and add gator stage column

**Files:**
- Modify: `app/reports/renderers/templates/components/pr_health.js:12-17` (tile data array)
- Modify: `app/reports/renderers/templates/components/pr_health.js:52-69` (stuck PRs table)
- Modify: `app/reports/renderers/templates/base.html:274-278` (CSS, add after `.area-badge`)
- Modify: `app/reports/renderers/templates/base.html:702-705` (responsive CSS, add after `.area-badge`)

**Interfaces:**
- Consumes: `d.pr_health.avg_review_wait_days` (float, already in JSON — e.g. `3.5`)
- Consumes: `pr.gator_label` (string|null per stuck PR — e.g. `"gator:in-review"`, `"gator:blocked"`, or `null`)
- Produces: visible tile and column in the rendered HTML (no downstream consumers)

- [ ] **Step 1: Swap the KPI tile**

In `app/reports/renderers/templates/components/pr_health.js`, replace the 4th tile in the `tileData` array (line 16):

```javascript
// BEFORE (line 16):
{value: d.pr_health.gator_coverage_pct + "%", label: "Gator Coverage", color: "var(--accent)", accent: "var(--accent)"}

// AFTER:
{value: d.pr_health.avg_review_wait_days + "d", label: "Avg Review Wait", color: "var(--status-waiting)", accent: "var(--status-waiting)"}
```

- [ ] **Step 2: Add Gator column header to the table**

In `app/reports/renderers/templates/components/pr_health.js`, update the `thead` (line 53):

```javascript
// BEFORE:
table.innerHTML = '<thead><tr><th>#</th><th>Title</th><th>Author</th><th>Age</th><th>Last Activity</th><th>Participants</th></tr></thead>';

// AFTER:
table.innerHTML = '<thead><tr><th>#</th><th>Title</th><th>Author</th><th>Age</th><th>Last Activity</th><th>Gator</th><th>Participants</th></tr></thead>';
```

- [ ] **Step 3: Add gator badge helper function**

Add this function at the top of `pr_health.js`, before the `buildPRHealth` function (before line 1):

```javascript
function gatorBadge(label) {
  if (!label) return '<span class="gator-badge gator-none">—</span>';
  var stage = label.replace('gator:', '');
  var cls = 'gator-other';
  if (stage === 'merge-ready') cls = 'gator-green';
  else if (stage === 'approval-needed') cls = 'gator-blue';
  else if (stage === 'in-review' || stage === 'watch-pipeline') cls = 'gator-yellow';
  else if (stage === 'blocked' || stage === 'follow-up-needed') cls = 'gator-red';
  return '<span class="gator-badge ' + cls + '">' + esc(stage) + '</span>';
}
```

- [ ] **Step 4: Add Gator cell to each table row**

In `app/reports/renderers/templates/components/pr_health.js`, update the `tr.innerHTML` in the `forEach` (around line 62). Insert a gator `<td>` between the Last Activity and Participants cells:

```javascript
// BEFORE:
tr.innerHTML = '<td><a href="' + esc(pr.url) + '" target="_blank">#' + pr.number + '</a></td>' +
  '<td><a href="' + esc(pr.url) + '" target="_blank">' + esc(pr.title) + '</a></td>' +
  '<td><a href="https://github.com/' + esc(pr.author) + '" target="_blank">@' + esc(pr.author) + '</a></td>' +
  '<td style="font-weight:600;color:var(--urgency-high);">' + daysOpen + 'd</td>' +
  '<td style="font-size:12px;color:var(--text-muted);">' + esc(activityText) + '</td>' +
  '<td style="font-size:13px;">' + participantLinks + '</td>';

// AFTER:
tr.innerHTML = '<td><a href="' + esc(pr.url) + '" target="_blank">#' + pr.number + '</a></td>' +
  '<td><a href="' + esc(pr.url) + '" target="_blank">' + esc(pr.title) + '</a></td>' +
  '<td><a href="https://github.com/' + esc(pr.author) + '" target="_blank">@' + esc(pr.author) + '</a></td>' +
  '<td style="font-weight:600;color:var(--urgency-high);">' + daysOpen + 'd</td>' +
  '<td style="font-size:12px;color:var(--text-muted);">' + esc(activityText) + '</td>' +
  '<td>' + gatorBadge(pr.gator_label) + '</td>' +
  '<td style="font-size:13px;">' + participantLinks + '</td>';
```

- [ ] **Step 5: Add gator badge CSS (light mode)**

In `app/reports/renderers/templates/base.html`, add after the `.area-badge` block (after line 278):

```css
.gator-badge {
  display: inline-block; padding: 2px 8px;
  border-radius: 4px; font-size: 11px; font-weight: 500;
  white-space: nowrap;
}
.gator-green { background: rgba(26,127,55,0.1); color: #1a7f37; }
.gator-blue { background: rgba(9,105,218,0.1); color: #0969da; }
.gator-yellow { background: rgba(212,160,21,0.1); color: #9a6700; }
.gator-red { background: rgba(209,36,47,0.1); color: #d1242f; }
.gator-none { color: var(--text-dim); font-style: italic; }
.gator-other { background: rgba(128,128,128,0.1); color: var(--text-muted); }
```

- [ ] **Step 6: Add gator badge CSS (responsive / dark mode overrides)**

In `app/reports/renderers/templates/base.html`, add after the responsive `.area-badge` block (after line 705):

```css
.gator-badge { padding: 2px 7px; border-radius: 6px; font-size: 10.5px; font-weight: 550; }
```

- [ ] **Step 7: Verify all existing tests pass**

Run: `python3 -m pytest tests/ -q`
Expected: All 299 tests pass (no Python changes made)

- [ ] **Step 8: Run lint**

Run: `make lint`
Expected: All checks passed (no Python changes made)

- [ ] **Step 9: Commit**

```bash
git add app/reports/renderers/templates/components/pr_health.js app/reports/renderers/templates/base.html
git commit -m "feat: replace gator coverage tile with avg review wait, add gator stage to PR table"
```
