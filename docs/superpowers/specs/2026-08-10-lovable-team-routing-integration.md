# Lovable Team Routing Redesign Integration

**Date:** 2026-08-10  
**Status:** Approved  
**Goal:** Replace the Team Routing section CSS and JavaScript with the Lovable AI redesign for better scannability and visual hierarchy.

## Problem Statement

The current Team Routing section improvements (alternating backgrounds, removed urgency badges from area headers, enhanced trend indicators) still lack sufficient visual clarity. User feedback: "this looks terrible."

Lovable AI generated a superior design that:
- Uses horizontal bar charts instead of urgency badge lists
- Has cleaner typography with monospace for key elements
- Uses subtle left border accents for urgency indication
- Creates clear visual hierarchy through spacing and minimal design

## Design Source

The redesign comes from `/Users/grasmith/Downloads/team-routing-redesign.html` - a complete HTML mockup with inline CSS that was user-approved.

## Key Design Elements

### 1. Urgency Distribution Bar Chart

**Replace:** Team header urgency badges (CRIT 1  HIGH 3  MED 2  LOW 2)

**With:** Horizontal bar chart showing proportional distribution

```
[██████░░░░] (20% critical, 40% high, 40% medium)
```

**Implementation:**
- Container div with `display: flex`, fixed width (180px)
- Each urgency segment is an `<i>` with:
  - Width: percentage of total (e.g., 1 crit / 8 total = 12.5%)
  - Background color: urgency color
  - Height: 4px
  - Border-radius: 999px (pill shape)
- Tooltip shows full counts

**CSS:**
```css
.mix {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 2px;
  width: 180px;
}
.mix i {
  height: 4px;
  border-radius: 999px;
  display: block;
}
.mix i.crit { background: var(--urgency-critical); }
.mix i.high { background: var(--urgency-high); }
.mix i.med { background: var(--urgency-medium); }
.mix i.low { background: var(--urgency-low); }
```

### 2. Typography Updates

**Monospace usage:**
- Area names: uppercase, monospace, 11.5px, 600 weight, 0.07em letter-spacing
- Issue numbers: monospace, 12px
- Team totals: monospace, 12px, gray pill background
- Trend: monospace, 11.5px

**Primary font remains Inter** for titles, descriptions, body text.

**New variables:**
```css
--mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
--ink-2: #4c555e;  /* secondary text */
--ink-3: #818b96;  /* tertiary text */
--ink-4: #a8b1ba;  /* quaternary text */
--hair: #e6e9ec;   /* subtle dividers */
--hair-strong: #d5dae0;  /* stronger dividers */
--surface-sunken: #f3f4f6;  /* recessed backgrounds */
```

### 3. Area Headers with Sticky Positioning

**Structure:**
```html
<div class="area-head">
  <span class="area-name">sandbox</span>
  <span class="area-n">3</span>
  <span class="area-rule"></span>
</div>
```

**CSS:**
```css
.area-head {
  display: flex;
  align-items: center;
  gap: 10px;
  position: sticky;
  top: 0;
  z-index: 2;
  background: linear-gradient(var(--bg-body) 82%, rgba(247,248,249,0));
  padding: 6px 0 8px;
}
.area-name {
  font-family: var(--mono);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-primary);
}
.area-n {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-4);
}
.area-rule {
  flex: 1;
  height: 1px;
  background: var(--hair);
}
```

**Why sticky:** As you scroll through a long team's issues, the area name stays visible so you always know which section you're in.

### 4. Issue Row Redesign

**Left border urgency indicator:**
- 2px left border on each `.issue`
- Critical: `var(--urgency-critical)`
- High: `var(--urgency-high)`
- Medium: `var(--urgency-medium)`
- Low: transparent (no border)

**Minimal badge approach:**
- All issues: small colored dot (7px circle)
- Critical only: additional "CRIT" tag in small monospace

**Structure:**
```html
<article class="issue u-crit">
  <div class="issue-top">
    <i class="dot crit"></i>
    <span class="tag-crit">CRIT</span>
    <a class="num" href="#">#2588</a>
    <span class="title"><a href="#">Title here</a></span>
    <span class="issue-meta"><span>@user1</span><span>2d</span></span>
  </div>
  <div class="issue-sub">
    Summary text here.
    <div class="issue-rec">→ Recommendation here.</div>
  </div>
</article>
```

**CSS:**
```css
.issues {
  background: var(--bg-card);
  border-radius: 10px;
  overflow: hidden;
}
.issue {
  display: block;
  padding: 13px 16px 13px 14px;
  border-top: 1px solid var(--border-subtle);
  border-left: 2px solid transparent;
  transition: background 0.13s ease;
}
.issue:first-child { border-top: none; }
.issue:hover { background: #fafbfc; }
.issue.u-crit { border-left-color: var(--urgency-critical); }
.issue.u-high { border-left-color: var(--urgency-high); }
.issue.u-med { border-left-color: var(--urgency-medium); }

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.tag-crit {
  font-size: 9.5px;
  font-family: var(--mono);
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--urgency-critical);
  border: 1px solid color-mix(in oklab, var(--urgency-critical) 30%, transparent);
  border-radius: 4px;
  padding: 1px 5px;
  flex: none;
}
```

### 5. Focus Section Styling

**Structure:**
```html
<div class="focus">
  <span class="focus-label">Focus</span>
  <div>
    <p>Summary text here.</p>
    <ol>
      <li>Action 1</li>
      <li>Action 2</li>
    </ol>
  </div>
</div>
```

**CSS:**
```css
.focus {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  padding: 0 0 4px;
  margin: -4px 0 26px;
}
.focus-label {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--ink-4);
  padding-top: 2px;
  flex: none;
  width: 64px;
}
.focus p {
  font-size: 13.5px;
  color: var(--ink-2);
  max-width: 74ch;
}
.focus ol {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 13px;
  color: var(--ink-2);
}
```

**Changes from current:**
- Replace blue background box with minimal left-aligned label
- No border or background color
- "FOCUS" label in small monospace uppercase
- Smaller, cleaner typography

### 6. Trend Indicator Simplification

**Current:** `↑ 8 from last week` in a gray pill

**New:** `↑ 8` plain text, right-aligned

**Why:** Simpler. The arrow already implies comparison. "from last week" is redundant given the dashboard's weekly context.

**CSS:**
```css
.trend {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
  width: 64px;
  text-align: right;
  flex: none;
}
.trend.up { color: var(--urgency-high); }
```

**JavaScript:**
```javascript
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
```

### 7. Team Header Layout

**Structure:**
```html
<summary class="team-band-header">
  <span class="caret">&#9654;</span>
  <span class="team-name">Agent Ops</span>
  <span class="team-total">8</span>
  <span class="mix" title="1 critical · 3 high · 2 medium · 2 low">
    <i class="crit" style="width:12.5%"></i>
    <i class="high" style="width:37.5%"></i>
    <i class="med" style="width:25%"></i>
    <i class="low" style="width:25%"></i>
  </span>
  <span class="trend up">↑ 8</span>
</summary>
```

**Key changes:**
- Move urgency display into `.mix` bar chart
- Simplify trend
- Team total gets monospace styling with gray pill background

## Implementation Details

### CSS Changes (base.html)

**Remove/Replace:**
- `.team-band-badge` - replaced with `.team-name`
- `.team-band-count` - replaced with `.team-total`
- `.team-band-trend` - simplified
- `.area-group` - removed alternating background
- `.area-group-header` - replaced with `.area-head`
- `.area-label` - replaced with `.area-name`
- `.team-synthesis` - replaced with `.focus`
- `.issue-main` - replaced with `.issue-top`

**Add:**
- Lovable's CSS variables (--ink-2, --ink-3, --ink-4, --hair, etc.)
- `.mix` and `.mix i` for urgency bar chart
- `.area-head` sticky positioning
- `.area-rule` divider line
- `.issues` card container
- `.issue` with left border and hover
- `.dot` and `.tag-crit`
- `.focus` minimal styling

### JavaScript Changes (team_routing.js)

**1. Calculate urgency bar chart widths:**

```javascript
var urgencies = synth.by_urgency || {};
var total = synth.total;
var critCount = urgencies["critical"] || 0;
var highCount = urgencies["high"] || 0;
var medCount = urgencies["medium"] || 0;
var lowCount = urgencies["low"] || 0;

var critPct = total > 0 ? (critCount / total * 100) : 0;
var highPct = total > 0 ? (highCount / total * 100) : 0;
var medPct = total > 0 ? (medCount / total * 100) : 0;
var lowPct = total > 0 ? (lowCount / total * 100) : 0;

var mixHTML = '<span class="mix" title="' +
  critCount + ' critical · ' + highCount + ' high · ' +
  medCount + ' medium · ' + lowCount + ' low">';
if (critPct > 0) mixHTML += '<i class="crit" style="width:' + critPct + '%"></i>';
if (highPct > 0) mixHTML += '<i class="high" style="width:' + highPct + '%"></i>';
if (medPct > 0) mixHTML += '<i class="med" style="width:' + medPct + '%"></i>';
if (lowPct > 0) mixHTML += '<i class="low" style="width:' + lowPct + '%"></i>';
mixHTML += '</span>';
```

**2. Update team header:**

```javascript
header.innerHTML =
  '<span class="caret">&#9654;</span>' +
  '<span class="team-name">' + esc(teamId === "none" ? "Unassigned" : synth.team_name || teamId) + '</span>' +
  '<span class="team-total">' + total + '</span>' +
  mixHTML +
  trendHTML;
```

**3. Update area header:**

```javascript
areaSection.innerHTML = '<div class="area-head">' +
  '<span class="area-name">' + esc(areaKey) + '</span>' +
  '<span class="area-n">' + group.total + '</span>' +
  '<span class="area-rule"></span>' +
  '</div>';
```

**4. Update issue row:**

```javascript
var urgencyClass = 'u-' + iss.urgency;
var dotClass = iss.urgency;
var critTag = iss.urgency === 'critical' ? '<span class="tag-crit">CRIT</span>' : '';

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
```

**5. Update focus section:**

```javascript
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
```

## Backward Compatibility

The `buildTeamRoutingLegacy()` function remains unchanged. It's only called when `team_synthesis` data is missing (old assessment format). The legacy function uses the old styling, which will continue to work.

## Testing Plan

1. Generate sample dashboard with Lovable styles
2. Verify urgency bar chart widths calculate correctly
3. Verify sticky area headers work when scrolling
4. Test with teams that have:
   - All urgencies present
   - Only one urgency
   - Zero issues (should not appear)
5. Verify hover states on issue rows
6. Test responsive behavior (mobile)
7. Verify legacy fallback still works with old data

## Success Criteria

1. ✅ Urgency distribution is immediately scannable via bar chart
2. ✅ Area sections are visually distinct with sticky headers
3. ✅ Issue urgency is clear from left border color + dot
4. ✅ Typography creates clear hierarchy (monospace for labels/numbers, Inter for content)
5. ✅ Focus section is minimal and doesn't dominate the view
6. ✅ No regression in functionality - all data still displayed
7. ✅ User approves: "this looks good"

## Rollout

- Pure UI change, no data model changes
- Can deploy independently
- Works with both new (area-based) and old (team-based) assessment data
- No migration needed
