# Team Routing UI Clarity Improvements

**Date:** 2026-08-10  
**Status:** Approved  
**Goal:** Make the Team Routing section easier to scan and understand by improving visual hierarchy and removing redundant information.

## Problem Statement

The current Team Routing UI has several readability issues:

1. **Area sections blend together** - "cli", "sandbox", "cluster" sections have minimal visual separation, making it hard to see where one area ends and another begins
2. **Redundant urgency counts** - urgency badges appear both in the area header ("HIGH 1 MED 1") and on each individual issue, creating visual noise
3. **Unclear trend indicator** - the "+8" shown next to team totals is ambiguous (what does it mean? compared to what?)
4. **Poor scannability** - hard to quickly find a specific area or understand the structure at a glance

## User Feedback

From user testing with Grace (intern):
- "its not clear the different seciton eg cli, sandbox, cluster etc"
- "the high, med count here as its already beside the issue title"
- "the numbers beside the total count isnt good ui, its confusing"

## Design Solution

### 1. Area Section Visual Separation

Add clear visual boundaries between area sections:

- **Alternating backgrounds**: Odd-numbered areas get subtle gray background (`var(--bg-surface)`), even areas stay white
- **Thicker borders**: 2px top border on each area (was 1px bottom border)
- **Increased spacing**: 16px margin between areas (was 6px)
- **Internal padding**: 12px padding inside each area section

**Why:** Creates clear visual "lanes" that make each area distinct without adding heavy UI elements like cards or shadows.

### 2. Area Header Simplification

Remove urgency count badges from area headers:

**Before:**
```
cli  2  HIGH 1  MED 1
```

**After:**
```
cli  2
```

- Keep: area name badge (blue pill) + total count
- Remove: all urgency badges from header
- Rationale: Individual issues already show their urgency badges. The header summary is redundant and adds visual clutter.

### 3. Trend Indicator Enhancement

Make week-over-week trend clear and descriptive:

**Before:**
```
Agent Ops  8  +8  CRIT 1  HIGH 3  ...
```

**After:**
```
Agent Ops  8  CRIT 1  HIGH 3  ...  ↑ 8 from last week
```

**Changes:**
- Add directional arrow: ↑ for increase, ↓ for decrease, → for no change
- Add descriptive text: "from last week"
- Style as small gray pill/badge, positioned at end of urgency badges
- Use lighter color to de-emphasize (it's useful context, not primary data)

**Format rules:**
- Positive delta: `↑ 8 from last week`
- Negative delta: `↓ 3 from last week`
- Zero delta: `→ no change`
- Color: `var(--text-muted)` (not accent colors)

### 4. What Stays the Same

**No changes to:**
- Individual issue urgency badges (CRIT, HIGH, MED, LOW)
- Issue details (summary, recommendation, author, days open)
- AI synthesis summary box
- Team header structure and urgency counts
- Area name styling (blue pill badge)
- Issue row layout

## Technical Implementation

### Files to Modify

**1. CSS (`app/reports/renderers/templates/base.html`)**

Add/modify these styles:

```css
.area-group {
  margin-bottom: 16px;  /* was 6px */
  padding: 12px;
  border-radius: var(--radius-sm);
}

.area-group:nth-child(odd) {
  background: var(--bg-surface);
}

.area-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-top: 2px solid var(--border);  /* was border-bottom: 1px */
  padding-top: 0;  /* first area doesn't need top padding */
  margin-bottom: 8px;
}

.area-group:first-child .area-group-header {
  border-top: none;  /* no border on first area */
}

.team-band-trend {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-surface);
  white-space: nowrap;
}
```

**2. JavaScript (`app/reports/renderers/templates/components/team_routing.js`)**

**Change 1: Remove area header urgency badges (lines 74-81)**

```javascript
// DELETE THIS BLOCK:
var areaUrgencyBadges = "";
["critical","high","medium","low"].forEach(function(u) {
  var count = areaUrgencies[u] || 0;
  if (count > 0) {
    areaUrgencyBadges += ' ' + makeUrgencyBadgeHTML(u) + '...';
  }
});
```

**Change 2: Simplify area header HTML (lines 83-87)**

```javascript
// BEFORE:
areaSection.innerHTML = '<div class="area-group-header">' +
  '<span class="area-label">' + esc(areaKey) + '</span>' +
  '<span class="area-count">' + group.total + '</span>' +
  '<span style="display:flex;align-items:center;">' + areaUrgencyBadges + '</span>' +
  '</div>';

// AFTER:
areaSection.innerHTML = '<div class="area-group-header">' +
  '<span class="area-label">' + esc(areaKey) + '</span>' +
  '<span class="area-count">' + group.total + '</span>' +
  '</div>';
```

**Change 3: Update trend formatting (line 16)**

```javascript
// BEFORE:
var trendClass = trend.charAt(0) === "+" ? "trend-up" : ...;

// AFTER:
var trendIcon = "";
var trendText = "";
if (trend.charAt(0) === "+") {
  trendIcon = "↑";
  trendText = trend.substring(1) + " from last week";
} else if (trend.charAt(0) === "-") {
  trendIcon = "↓";
  trendText = trend.substring(1) + " from last week";
} else if (trend === "flat" || trend === "0") {
  trendIcon = "→";
  trendText = "no change";
}
var trendHTML = trendIcon && trendText 
  ? '<span class="team-band-trend">' + trendIcon + ' ' + trendText + '</span>' 
  : '';
```

**Change 4: Update team header to use new trend HTML (line 27-32)**

```javascript
// BEFORE:
(trend !== "0" ? '<span class="team-band-trend ' + trendClass + '">' + esc(trend) + '</span>' : '')

// AFTER:
trendHTML  // positioned after urgency badges, before chevron
```

## Visual Mockup

**Before:**
```
Agent Ops  8  +8  CRIT 1  HIGH 3  MED 2  LOW 2  ▶
  [AI Summary box]
  
  cli  2  HIGH 1  MED 1
  ─────────────────────
    HIGH #2601 bug(cli): SSH proxy...
    MED  #2602 feat(cli): --json flag...
  
  sandbox  2  HIGH 1  MED 1
  ─────────────────────
    HIGH #2605 bug(sandbox): cleanup...
```

**After:**
```
Agent Ops  8  CRIT 1  HIGH 3  MED 2  LOW 2  ↑ 8 from last week  ▶
  [AI Summary box]
  
  ┌─────────────────────────────────┐
  │ cli  2                          │  ← gray background
  │ ═════════════                   │
  │   HIGH #2601 bug(cli): SSH...   │
  │   MED  #2602 feat(cli): --json..│
  └─────────────────────────────────┘
  
  ┌─────────────────────────────────┐
  │ sandbox  2                      │  ← white background
  │ ═════════════                   │
  │   HIGH #2605 bug(sandbox): ...  │
  └─────────────────────────────────┘
```

## Success Criteria

1. **Visual separation is clear** - users can instantly see where one area ends and another begins
2. **No redundant information** - urgency data appears once (on individual issues), not twice
3. **Trend is understandable** - "+8" becomes "↑ 8 from last week" with clear meaning
4. **Scannability improves** - users can quickly find specific areas and assess urgency distribution

## Non-Goals

- Adding area descriptions or tooltips (may add later if needed)
- Making areas collapsible (adds interaction complexity)
- Changing the issue row layout
- Modifying the AI synthesis box
- Adding new data or metrics

## Testing

Manual testing checklist:
1. Generate sample dashboard with multiple teams and areas
2. Verify alternating backgrounds render correctly
3. Verify area headers show only name + count (no urgency badges)
4. Verify trend indicators show arrows and descriptive text
5. Verify spacing/padding makes sections visually distinct
6. Test in browser at different zoom levels

## Rollout

This is a pure UI change with no data model changes:
- Can be deployed independently
- No migration needed
- Works with both old and new assessment data
- No API changes
