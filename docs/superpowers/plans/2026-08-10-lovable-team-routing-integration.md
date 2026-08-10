# Lovable Team Routing Redesign Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Team Routing section CSS and JavaScript with Lovable AI redesign for better scannability and visual hierarchy.

**Architecture:** Pure UI replacement. Extract CSS from Lovable's redesign (`/Users/grasmith/Downloads/team-routing-redesign.html`) and adapt JavaScript to generate matching HTML structure. No data model changes - works with existing TeamSynthesis/AreaGroup data.

**Tech Stack:** Vanilla JavaScript, inline CSS in Jinja2 templates, existing test suite

## Global Constraints

- No npm/build toolchain - all CSS/JS inline in HTML templates
- Must work with existing TeamSynthesis/AreaGroup data structures from BirdsEyeReport
- Keep `buildTeamRoutingLegacy()` function unchanged for backward compatibility
- All 317 existing tests must pass
- No changes to data models or backend logic

---

## File Structure

**Modified files:**
- `app/reports/renderers/templates/base.html` (lines ~10-270) - CSS styles in `<style>` tag
- `app/reports/renderers/templates/components/team_routing.js` (entire file) - HTML generation logic

**Reference files:**
- `/Users/grasmith/Downloads/team-routing-redesign.html` - Lovable redesign source
- `docs/superpowers/specs/2026-08-10-lovable-team-routing-integration.md` - Design spec

**No new files created.**

---

### Task 1: Add CSS Variables and Base Typography

**Files:**
- Modify: `app/reports/renderers/templates/base.html:11-27` (`:root` variables section)

**Interfaces:**
- Consumes: Existing CSS variables (--bg-body, --text-primary, etc.)
- Produces: New CSS variables for Lovable design (--mono, --ink-2, --ink-3, --ink-4, --hair, --hair-strong, --surface-sunken)

- [ ] **Step 1: Read current CSS variables**

```bash
grep -A 30 ":root" app/reports/renderers/templates/base.html | head -40
```

Expected: See existing variables like `--bg-body`, `--bg-card`, `--text-primary`, etc.

- [ ] **Step 2: Add new CSS variables to :root**

Add these variables inside the existing `:root` block (after the existing variables):

```css
  --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  --ink-2: #4c555e;
  --ink-3: #818b96;
  --ink-4: #a8b1ba;
  --hair: #e6e9ec;
  --hair-strong: #d5dae0;
  --surface-sunken: #f3f4f6;
```

Location: Add after line 33 (after `--transition: 0.2s ease;`)

- [ ] **Step 3: Verify CSS is valid**

```bash
# Check that the file is still valid HTML
python3 -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('app/reports/renderers/templates')); env.get_template('base.html')" 2>&1
```

Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add app/reports/renderers/templates/base.html
git commit -m "style: add CSS variables for Lovable Team Routing redesign

Add monospace font stack and semantic color variables:
- --mono for code/numbers typography
- --ink-2/3/4 for text hierarchy
- --hair for subtle dividers
- --surface-sunken for recessed backgrounds"
```

---

### Task 2: Replace Team Header Styles with Bar Chart Design

**Files:**
- Modify: `app/reports/renderers/templates/base.html:182-188` (team-band-* styles)
- Modify: `app/reports/renderers/templates/components/team_routing.js:26-60` (team header generation)

**Interfaces:**
- Consumes: TeamSynthesis.by_urgency (dict with critical/high/medium/low counts)
- Produces: HTML with `.mix` bar chart and simplified `.trend`

- [ ] **Step 1: Replace team header CSS**

In `base.html`, replace the existing team-band styles (lines ~182-196) with:

```css
.team-band-header {
  display: flex; align-items: center; gap: 14px;
  padding: 22px 4px; cursor: pointer;
  transition: opacity 0.15s ease;
}
.team-band-header:hover { opacity: 0.72; }
.caret {
  width: 10px; flex: none; color: var(--ink-4);
  font-size: 9px; transition: transform 0.18s ease;
}
.team-band[open] .caret { transform: rotate(90deg); }
.team-name {
  font-size: 17px; font-weight: 600; letter-spacing: -0.015em;
}
.team-total {
  font-family: var(--mono); font-size: 12px; font-weight: 600;
  color: var(--ink-3); background: var(--surface-sunken);
  border-radius: 999px; padding: 2px 9px;
}
.mix {
  margin-left: auto; display: flex; align-items: center;
  gap: 2px; width: 180px;
}
.mix i { height: 4px; border-radius: 999px; display: block; }
.mix i.crit { background: var(--urgency-critical); }
.mix i.high { background: var(--urgency-high); }
.mix i.med { background: var(--urgency-medium); }
.mix i.low { background: var(--urgency-low); }
.trend {
  font-family: var(--mono); font-size: 11.5px;
  color: var(--ink-3); width: 64px; text-align: right; flex: none;
}
.trend.up { color: var(--urgency-high); }
```

- [ ] **Step 2: Update JavaScript to generate bar chart**

In `team_routing.js`, replace lines 26-60 (the team header generation) with:

```javascript
    var urgencies = synth.by_urgency || {};
    var total = synth.total;
    var trend = synth.trend || "0";
    
    // Calculate percentages for urgency bar chart
    var critCount = urgencies["critical"] || 0;
    var highCount = urgencies["high"] || 0;
    var medCount = urgencies["medium"] || 0;
    var lowCount = urgencies["low"] || 0;
    
    var critPct = total > 0 ? (critCount / total * 100) : 0;
    var highPct = total > 0 ? (highCount / total * 100) : 0;
    var medPct = total > 0 ? (medCount / total * 100) : 0;
    var lowPct = total > 0 ? (lowCount / total * 100) : 0;
    
    // Build urgency mix bar chart
    var tooltipText = critCount + ' critical · ' + highCount + ' high · ' +
                      medCount + ' medium · ' + lowCount + ' low';
    var mixHTML = '<span class="mix" title="' + esc(tooltipText) + '">';
    if (critPct > 0) mixHTML += '<i class="crit" style="width:' + critPct + '%"></i>';
    if (highPct > 0) mixHTML += '<i class="high" style="width:' + highPct + '%"></i>';
    if (medPct > 0) mixHTML += '<i class="med" style="width:' + medPct + '%"></i>';
    if (lowPct > 0) mixHTML += '<i class="low" style="width:' + lowPct + '%"></i>';
    mixHTML += '</span>';
    
    // Build simplified trend
    var trendClass = "";
    var trendText = "";
    if (trend.charAt(0) === "+") {
      trendClass = "up";
      trendText = "↑ " + trend.substring(1);
    } else if (trend.charAt(0) === "-") {
      trendText = "↓ " + trend.substring(1);
    } else if (trend === "flat" || trend === "0") {
      trendText = "→ flat";
    }
    var trendHTML = trendText 
      ? '<span class="trend ' + trendClass + '">' + trendText + '</span>'
      : '';
    
    var header = el("summary", "team-band-header");
    header.innerHTML =
      '<span class="caret">&#9654;</span>' +
      '<span class="team-name">' + esc(teamId === "none" ? "Unassigned" : synth.team_name || teamId) + '</span>' +
      '<span class="team-total">' + total + '</span>' +
      mixHTML +
      trendHTML;
    band.appendChild(header);
```

- [ ] **Step 3: Test rendering with sample data**

```bash
python3 /Users/grasmith/.claude/jobs/90fd781d/tmp/generate_sample.py
```

Expected: Dashboard saved, check that team headers show bar charts

- [ ] **Step 4: Open dashboard and verify**

```bash
open /Users/grasmith/Desktop/triage-dashboard-preview.html
```

Verify:
- Team header shows horizontal bar chart (not badge list)
- Trend shows "↑ 8" or "↓ 2" or "→ flat"
- Hovering over bar chart shows tooltip with counts

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/ -q
```

Expected: All 317 tests pass

- [ ] **Step 6: Commit**

```bash
git add app/reports/renderers/templates/base.html app/reports/renderers/templates/components/team_routing.js
git commit -m "feat: replace team header urgency badges with bar chart

Replace urgency badge lists (CRIT 1 HIGH 3 MED 2 LOW 2) with
horizontal bar chart showing proportional distribution.
Simplify trend from '↑ 8 from last week' to '↑ 8'."
```

---

### Task 3: Update Area Header Styling (Sticky + Monospace)

**Files:**
- Modify: `app/reports/renderers/templates/base.html:225-238` (area-group styles)
- Modify: `app/reports/renderers/templates/components/team_routing.js:87-95` (area header generation)

**Interfaces:**
- Consumes: AreaGroup.area, AreaGroup.total
- Produces: HTML with `.area-head` containing `.area-name`, `.area-n`, `.area-rule`

- [ ] **Step 1: Replace area group CSS**

In `base.html`, replace the `.area-group` and `.area-group-header` styles with:

```css
.area {
  margin-top: 30px;
}
.area:first-of-type { margin-top: 0; }
.area-head {
  display: flex; align-items: center; gap: 10px;
  position: sticky; top: 0; z-index: 2;
  background: linear-gradient(var(--bg-body) 82%, rgba(247,248,249,0));
  padding: 6px 0 8px;
}
.area-name {
  font-family: var(--mono); font-size: 11.5px; font-weight: 600;
  letter-spacing: 0.07em; text-transform: uppercase;
  color: var(--text-primary);
}
.area-n {
  font-family: var(--mono); font-size: 11px; color: var(--ink-4);
}
.area-rule {
  flex: 1; height: 1px; background: var(--hair);
}
```

Note: Remove the old `.area-group`, `.area-group-header`, `.area-label`, `.area-count` styles entirely.

- [ ] **Step 2: Update JavaScript area header generation**

In `team_routing.js`, replace the area header generation (around line 87-95) with:

```javascript
      var areaSection = el("div", "area");
      
      areaSection.innerHTML = '<div class="area-head">' +
        '<span class="area-name">' + esc(areaKey) + '</span>' +
        '<span class="area-n">' + group.total + '</span>' +
        '<span class="area-rule"></span>' +
        '</div>';
```

- [ ] **Step 3: Test rendering**

```bash
python3 /Users/grasmith/.claude/jobs/90fd781d/tmp/generate_sample.py
open /Users/grasmith/Desktop/triage-dashboard-preview.html
```

Verify:
- Area names are uppercase monospace (CLI, SANDBOX, etc.)
- Divider line extends across the section
- Headers stick when scrolling (test by scrolling in Agent Ops section)

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/reports/test_birds_eye.py -q
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add app/reports/renderers/templates/base.html app/reports/renderers/templates/components/team_routing.js
git commit -m "style: add sticky area headers with monospace typography

Area headers now:
- Use uppercase monospace (CLI, SANDBOX)
- Stick to top when scrolling
- Show horizontal divider line
- Remove redundant urgency badges"
```

---

### Task 4: Update Issue Row Styling (Left Border + Minimal Badges)

**Files:**
- Modify: `app/reports/renderers/templates/base.html:238-270` (issue styles)
- Modify: `app/reports/renderers/templates/components/team_routing.js:103-125` (issue row generation)

**Interfaces:**
- Consumes: TriageResult (urgency, issue_number, issue_title, author_login, days_open, has_linked_pr, summary, recommendation)
- Produces: HTML with `.issue` containing `.issue-top` and `.issue-sub`

- [ ] **Step 1: Add issue container and row CSS**

In `base.html`, add after the area styles:

```css
.issues {
  background: var(--bg-card); border-radius: 10px; overflow: hidden;
}
.issue {
  display: block; padding: 13px 16px 13px 14px;
  border-top: 1px solid var(--border-subtle);
  border-left: 2px solid transparent;
  transition: background 0.13s ease;
}
.issue:first-child { border-top: none; }
.issue:hover { background: #fafbfc; }
.issue.u-crit { border-left-color: var(--urgency-critical); }
.issue.u-high { border-left-color: var(--urgency-high); }
.issue.u-med { border-left-color: var(--urgency-medium); }
.issue.u-low { border-left-color: transparent; }

.issue-top {
  display: flex; align-items: baseline; gap: 9px;
}
.issue-top .dot { margin-top: 5px; }
.dot {
  width: 7px; height: 7px; border-radius: 50%; flex: none;
}
.dot.crit { background: var(--urgency-critical); }
.dot.high { background: var(--urgency-high); }
.dot.med { background: var(--urgency-medium); }
.dot.low { background: var(--urgency-low); }
.tag-crit {
  font-size: 9.5px; font-family: var(--mono); font-weight: 600;
  letter-spacing: 0.08em; color: var(--urgency-critical);
  border: 1px solid color-mix(in oklab, var(--urgency-critical) 30%, transparent);
  border-radius: 4px; padding: 1px 5px; flex: none;
}
.num {
  font-family: var(--mono); font-size: 12px;
  color: var(--ink-4); text-decoration: none; flex: none;
}
.num:hover { color: var(--link); }
.title {
  font-size: 14px; font-weight: 500; color: var(--text-primary);
  letter-spacing: -0.005em; flex: 1;
}
.title a {
  color: inherit; text-decoration: none;
}
.title a:hover {
  text-decoration: underline;
  text-decoration-color: var(--hair-strong);
  text-underline-offset: 3px;
}
.issue-meta {
  display: flex; gap: 10px; font-size: 11.5px;
  color: var(--ink-4); flex: none;
  font-variant-numeric: tabular-nums;
}
.pr { color: var(--urgency-low); }

.issue-sub {
  margin: 5px 0 0 25px; font-size: 13px;
  color: var(--ink-2); max-width: 78ch;
}
.issue-rec {
  margin-top: 3px; font-size: 12.5px; color: var(--ink-3);
}
.issue-rec::before {
  content: "→ "; color: var(--ink-4);
}
```

Note: Remove old `.team-issue-row`, `.issue-main`, `.issue-title`, `.issue-meta`, `.issue-days`, `.author-tag`, `.issue-details`, `.issue-summary` styles.

- [ ] **Step 2: Update JavaScript issue row generation**

In `team_routing.js`, replace the issue row generation (lines ~103-125) with:

```javascript
      var issuesDiv = el("div", "area-group-issues");
      var issuesContainer = el("div", "issues");
      var issues = group.issues || [];
      issues.forEach(function(iss) {
        var row = el("article", "issue");
        var urgencyClass = 'u-' + iss.urgency;
        var dotClass = iss.urgency;
        var critTag = iss.urgency === 'critical' 
          ? '<span class="tag-crit">CRIT</span>' 
          : '';

        var detailsHTML = '';
        if (iss.summary || iss.recommendation) {
          detailsHTML = '<div class="issue-sub">';
          if (iss.summary) detailsHTML += esc(iss.summary);
          if (iss.recommendation) {
            detailsHTML += '<div class="issue-rec">' + esc(iss.recommendation) + '</div>';
          }
          detailsHTML += '</div>';
        }

        row.className = 'issue ' + urgencyClass;
        row.innerHTML =
          '<div class="issue-top">' +
            '<i class="dot ' + dotClass + '"></i>' +
            critTag +
            '<a class="num" href="' + esc(iss.issue_url) + '">#' + iss.issue_number + '</a>' +
            '<span class="title"><a href="' + esc(iss.issue_url) + '">' + esc(iss.issue_title) + '</a></span>' +
            '<span class="issue-meta">' +
              (iss.has_linked_pr ? '<span class="pr">PR</span>' : '') +
              (iss.author_login ? '<span>@' + esc(iss.author_login) + '</span>' : '') +
              (iss.days_open != null ? '<span>' + iss.days_open + 'd</span>' : '') +
            '</span>' +
          '</div>' +
          detailsHTML;
        issuesContainer.appendChild(row);
      });
      issuesDiv.appendChild(issuesContainer);
      areaSection.appendChild(issuesDiv);
```

- [ ] **Step 3: Test rendering**

```bash
python3 /Users/grasmith/.claude/jobs/90fd781d/tmp/generate_sample.py
open /Users/grasmith/Desktop/triage-dashboard-preview.html
```

Verify:
- Issues have left border (red for critical, orange for high)
- Critical issues show "CRIT" tag
- Dot shows for all issues
- Issue numbers are monospace
- Hover state works

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/ -q
```

Expected: All 317 tests pass

- [ ] **Step 5: Commit**

```bash
git add app/reports/renderers/templates/base.html app/reports/renderers/templates/components/team_routing.js
git commit -m "style: add left border urgency indicators to issues

Issues now show urgency via:
- Colored left border (red=critical, orange=high)
- Small dot icon
- CRIT tag for critical issues only
- Card container with hover state"
```

---

### Task 5: Update Focus Section Styling

**Files:**
- Modify: `app/reports/renderers/templates/base.html:206-223` (focus/synthesis styles)
- Modify: `app/reports/renderers/templates/components/team_routing.js:63-77` (focus section generation)

**Interfaces:**
- Consumes: TeamSynthesis.focus_summary, TeamSynthesis.actions
- Produces: HTML with `.focus` containing `.focus-label` and content div

- [ ] **Step 1: Replace focus section CSS**

In `base.html`, replace `.team-synthesis`, `.synthesis-summary`, `.synthesis-actions*` styles with:

```css
.team-band-content { padding: 0 0 34px 24px; }

.focus {
  display: flex; gap: 16px; align-items: flex-start;
  padding: 0 0 4px; margin: -4px 0 26px;
}
.focus-label {
  font-family: var(--mono); font-size: 10px;
  letter-spacing: 0.09em; text-transform: uppercase;
  color: var(--ink-4); padding-top: 2px;
  flex: none; width: 64px;
}
.focus p {
  font-size: 13.5px; color: var(--ink-2); max-width: 74ch;
}
.focus ol {
  margin: 6px 0 0; padding-left: 16px;
  font-size: 13px; color: var(--ink-2);
}
.focus li { margin-top: 2px; }
```

- [ ] **Step 2: Update JavaScript focus generation**

In `team_routing.js`, replace the focus section generation (around lines 63-77) with:

```javascript
    if (synth.focus_summary) {
      var summaryDiv = el("div", "focus");
      var summaryHTML = '<span class="focus-label">Focus</span><div>';
      summaryHTML += '<p>' + esc(synth.focus_summary) + '</p>';
      if (synth.actions && synth.actions.length) {
        summaryHTML += '<ol>';
        synth.actions.forEach(function(action) {
          summaryHTML += '<li>' + esc(action) + '</li>';
        });
        summaryHTML += '</ol>';
      }
      summaryHTML += '</div>';
      summaryDiv.innerHTML = summaryHTML;
      content.appendChild(summaryDiv);
    }
```

- [ ] **Step 3: Test rendering**

```bash
python3 /Users/grasmith/.claude/jobs/90fd781d/tmp/generate_sample.py
open /Users/grasmith/Desktop/triage-dashboard-preview.html
```

Verify:
- "FOCUS" label is small uppercase monospace on left
- Summary text is clean, no blue background box
- Actions list is indented numbered list
- Minimal, doesn't dominate the view

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/ -q
```

Expected: All 317 tests pass

- [ ] **Step 5: Commit**

```bash
git add app/reports/renderers/templates/base.html app/reports/renderers/templates/components/team_routing.js
git commit -m "style: simplify focus section to minimal label layout

Replace blue box synthesis with:
- Small uppercase 'FOCUS' label on left
- Plain text summary
- Clean numbered action list
- No background/border decoration"
```

---

### Task 6: Cleanup and Final Testing

**Files:**
- Modify: `app/reports/renderers/templates/base.html` (remove unused styles)

**Interfaces:**
- Consumes: All previous tasks
- Produces: Clean, working dashboard with all tests passing

- [ ] **Step 1: Remove unused CSS classes**

In `base.html`, remove these unused styles if they still exist:
- `.team-band-badge`
- `.synthesis-summary`
- `.synthesis-actions`
- `.synthesis-actions-label`
- `.area-label`
- `.area-count`
- `.area-group-issues`
- `.confidence-flag`
- `.secondary-area`
- `.author-tag`

Search for each and delete the entire block.

- [ ] **Step 2: Verify no CSS/JS errors**

```bash
# Check HTML template validity
python3 -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('app/reports/renderers/templates')); env.get_template('base.html')" 2>&1

# Check JS syntax
node -c app/reports/renderers/templates/components/team_routing.js 2>&1 || echo "Node not available, skip JS check"
```

Expected: No errors

- [ ] **Step 3: Generate final dashboard**

```bash
python3 /Users/grasmith/.claude/jobs/90fd781d/tmp/generate_sample.py
```

Expected: Dashboard saved successfully

- [ ] **Step 4: Visual verification**

```bash
open /Users/grasmith/Desktop/triage-dashboard-preview.html
```

Checklist:
- [ ] Team headers show horizontal bar charts
- [ ] Trend shows "↑ 8" format
- [ ] Area headers are uppercase monospace with divider
- [ ] Area headers stick when scrolling
- [ ] Issues have left border color (red/orange/yellow)
- [ ] Critical issues show CRIT tag
- [ ] All issues show dot icon
- [ ] Focus section has minimal FOCUS label
- [ ] No blue background box on focus
- [ ] Issue hover states work
- [ ] Overall design matches Lovable mockup

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest tests/ -q
```

Expected: All 317 tests pass

- [ ] **Step 6: Run linter**

```bash
make lint
```

Expected: All checks pass

- [ ] **Step 7: Final commit**

```bash
git add app/reports/renderers/templates/base.html
git commit -m "chore: remove unused Team Routing CSS classes

Clean up old styles replaced by Lovable redesign:
- team-band-badge, synthesis-*, area-label, etc.
- All functionality preserved in new classes"
```

---

## Testing Checklist

After completing all tasks, verify:

1. **Visual Design**
   - [ ] Team headers show urgency bar chart (not badge list)
   - [ ] Area headers are uppercase monospace with sticky positioning
   - [ ] Issues have colored left borders
   - [ ] Focus section is minimal (no blue box)

2. **Functionality**
   - [ ] All issue data displayed (number, title, author, days, PR icon)
   - [ ] Recommendations and summaries shown
   - [ ] Trends show correct direction (↑ ↓ →)
   - [ ] Teams collapse/expand correctly

3. **Tests**
   - [ ] All 317 tests pass
   - [ ] No new console errors
   - [ ] Lint passes

4. **Backward Compatibility**
   - [ ] Legacy fallback function unchanged
   - [ ] Works with old assessment data (no team_synthesis)

## Rollout Notes

This is a pure UI change with no data model modifications:
- Can deploy independently
- No database migration needed
- Works with both new (area-based) and old (team-based) assessment data
- Legacy fallback preserved for old data format
