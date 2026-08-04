# HTML Dashboard Renderer — Design Spec

## Goal

Add an HTML renderer to the existing report pipeline so `run_report()` can produce a single-file, interactive dashboard that an engineering manager can open in a browser Monday morning and understand the week's issue landscape in under 60 seconds.

## Architecture

The HTML renderer is a sibling to the existing markdown renderer. It receives the same `BirdsEyeReport` dataclass and returns an HTML string. The Python function serializes the report data into a JSON blob embedded in a `<script>` tag; the rest of the file is a static HTML/CSS/JS template that reads that blob and renders the dashboard client-side.

```
BirdsEyeReport (dataclass)
    │
    ├── render_markdown(report) → str   # exists
    └── render_html(report) → str       # new
```

## Tech Stack

- **Charts**: Chart.js 4.5.1 via CDN (`https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.js`)
- **Chart labels**: chartjs-plugin-datalabels via CDN (`https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels`)
- **Font**: Inter via Google Fonts CDN
- **CSS**: Inline, no framework. CSS Grid for layout, CSS custom properties for theming.
- **No build step**: Single `.html` file output, all CSS/JS inline except CDN scripts.

## Color Palette (Dark Theme)

```
--bg-primary:    #0F172A     (deep navy, softer than pure black)
--bg-card:       #1E293B     (slate card background)
--bg-hover:      #334155     (card hover state)
--text-primary:  #F1F5F9     (near-white text)
--text-secondary:#94A3B8     (muted labels)
--border:        #334155     (subtle card borders)
--accent:        #6366F1     (indigo, header/links)

--urgency-critical: #EF4444  (red)
--urgency-high:     #F97316  (orange)
--urgency-medium:   #EAB308  (yellow)
--urgency-low:      #22C55E  (green)
```

Team colors for the doughnut chart (7 teams max):

```
agent-ops:  #6366F1  (indigo)
acp:        #8B5CF6  (violet)
ai-safety:  #EC4899  (pink)
kata:       #14B8A6  (teal)
agentdev:   #F97316  (orange)
dashboard:  #06B6D4  (cyan)
none:       #64748B  (slate grey)
```

## Layout Sections (Top to Bottom)

### 1. Header

- Title: "OpenShell Triage Overview"
- Subtitle: period label from `report.summary.period_label`
- Right-aligned: "Generated {report.generated_at}" in muted text

### 2. KPI Cards (Horizontal Row)

Five cards in a CSS Grid row:

| Card    | Value Source                              | Color              |
|---------|-------------------------------------------|--------------------|
| Total   | `report.summary.new_this_period`          | `--accent`         |
| Critical| `report.summary.by_urgency["critical"]`   | `--urgency-critical`|
| High    | `report.summary.by_urgency["high"]`       | `--urgency-high`   |
| Medium  | `report.summary.by_urgency["medium"]`     | `--urgency-medium` |
| Low     | `report.summary.by_urgency["low"]`        | `--urgency-low`    |

Each card: large number (32px bold), label below (14px muted), colored left border (4px). The number for Critical and High should pulse subtly (CSS animation) if > 0 to draw the eye.

### 3. Narrative

`report.narrative` rendered as a styled blockquote. Italic text, left border accent, slightly smaller font (14px). Attribution line: "— AI-generated summary" in muted grey.

### 4. Action Required Section (conditionally rendered)

Only rendered if `len(report.critical_list) > 0`. Heading: "Action Required ({count})".

Issue cards for each item in `report.critical_list`, sorted critical first then high. Each card:

```
┌─────────────────────────────────────────────┐
│  🔴 #2518  bug(supervisor): SPIFFE crash    │
│  ai-safety • high confidence • 3 days open  │
│  "SPIFFE sandboxes crash on restart"        │
└─────────────────────────────────────────────┘
```

Fields per card:
- Urgency dot (colored circle, CSS) + `issue_number` + `issue_title`
- `primary_team` • confidence indicator based on `primary_confidence` • days open computed from `assessed_at`
- `summary` as one-line description
- Entire card is a link to `issue_url`
- Left border colored by urgency level

If a `secondary_team` exists with `secondary_confidence`, show it as a subtle tag: "also: agent-ops (0.65)"

### 5. Team Breakdown Section (Two-Column)

**Left column: Doughnut Chart**

- Data: `report.team_breakdown` — each team's `total` as a segment
- Colors: team color palette defined above
- Center label: total issue count
- Hover: tooltip showing team name and count
- Click: filters the "All Issues" section below to that team. Click again to clear.
- Datalabels plugin: show team name and count on each segment if count > 0

**Right column: Needs Triage (conditionally rendered)**

Only rendered if `len(report.no_team_list) > 0`.

- Heading: "Needs Triage ({count})" where count = `len(report.no_team_list)`
- Compact issue cards for `report.no_team_list` — same format as Action Required cards but with an orange "unassigned" tag instead of a team name
- These are highlighted because they represent gaps in team coverage
- If no_team_list is empty, the doughnut chart expands to full width

### 6. Duplicate Clusters Section (conditionally rendered)

Only rendered if `len(report.duplicate_clusters) > 0`. Heading: "Potential Duplicates ({count} clusters)"

For each `DuplicateCluster` in `report.duplicate_clusters`:

```
┌── Cluster: sandbox/supervisor ─────────────────────┐
│  Shared keywords: broken, podman, sandbox, ssh     │
│                                                     │
│  #2607 — sandbox download/upload broken... (none)  │
│  #2587 — VM sandbox SSH disconnects... (kata)      │
│  #2520 — enableUserNamespaces causes... (agent-ops)│
└─────────────────────────────────────────────────────┘
```

Fields:
- `cluster.area` as cluster title
- `cluster.similarity_reason` as subtitle
- List of `cluster.issues` with number, truncated title, team badge

### 7. All Issues Section

Heading: "All Issues ({total})" with active filter indicator if doughnut click is active.

A styled table (CSS Grid, not `<table>`) showing every issue from all sections:

| Column | Source | Width |
|--------|--------|-------|
| Urgency | Colored dot from `result.urgency` | 40px |
| # | `result.issue_number` (link to `issue_url`) | 60px |
| Title | `result.issue_title` | flex |
| Team | `result.primary_team` with colored badge | 120px |
| Confidence | `result.primary_confidence` as percentage | 80px |
| Flag | `result.confidence_flag` icon/text | 100px |

- Rows alternate background slightly for readability (`--bg-card` / `--bg-primary`)
- Clicking a row opens `issue_url` in a new tab
- When a team is selected via the doughnut chart, rows not matching that team are hidden with a CSS transition
- A "Clear filter" button appears when filtering is active

### 8. Footer

Single line: "Generated by team-issue-triage • {generated_at}" in muted text, centered.

## Data Embedding

The Python renderer serializes the `BirdsEyeReport` into a JSON object and embeds it in the HTML:

```html
<script>
const REPORT_DATA = { ... };
</script>
```

The JSON structure mirrors the dataclass but uses plain dicts/lists (no Python-specific types). The `Urgency` enum serializes to its string value. The `assessed_at` timestamps remain ISO8601 strings.

A `_report_to_dict(report: BirdsEyeReport) -> dict` helper handles the serialization, converting dataclass instances to dicts recursively, enum values to strings, and `None` values (e.g. `secondary_team`, `secondary_confidence`, `confidence_flag`) to JSON `null`.

## File Structure

```
app/reports/renderers/
├── __init__.py
├── markdown.py          # existing
└── html.py              # new — render_html(report) → str
```

`html.py` contains:
- `render_html(report: BirdsEyeReport) -> str` — public function
- `_report_to_dict(report: BirdsEyeReport) -> dict` — serialization helper
- `_HTML_TEMPLATE: str` — the full HTML template as a Python string constant with a `{report_json}` placeholder

## CLI Integration

Add a `--format` argument to `__main__.py`:

```
--format {markdown,html}   (default: auto-detect from --output extension, fallback markdown)
```

In `run_report()` in `triage.py`, select the renderer:

```python
if fmt == "html":
    output = render_html(report)
else:
    output = render_markdown(report)
```

Auto-detection: if `--output report.html`, use HTML renderer. If `--output report.md` or no output, use markdown.

## Interactivity Spec

**Doughnut chart click-to-filter:**
1. User clicks a doughnut segment → `onClick` handler reads the team label
2. All Issues section filters to show only rows matching that team
3. Non-matching rows get `display: none` with a CSS transition
4. A "Showing: {team} (X issues) [Clear]" bar appears above the table
5. Clicking the same segment again, or clicking "Clear", removes the filter

**Card hover:**
- Cards lift slightly on hover (`transform: translateY(-2px)`, `box-shadow` increase)
- Cursor changes to pointer

**Tooltips:**
- Chart.js default tooltips on chart hover, styled to match the dark theme

## Responsive Design

- KPI cards: 5 columns on desktop, 3+2 on tablet, stack on mobile
- Charts section: 2 columns on desktop, stack on mobile
- Issue cards: full width always
- All Issues table: horizontal scroll on mobile
- Breakpoints: 768px (tablet), 480px (mobile)

## Testing

Create `tests/reports/test_html_renderer.py`:

1. `test_render_html_returns_valid_html` — output contains `<!DOCTYPE html>`, `<html>`, `</html>`
2. `test_render_html_embeds_report_data` — output contains `REPORT_DATA` with correct issue count
3. `test_render_html_includes_chart_js_cdn` — output contains the Chart.js CDN URL
4. `test_render_html_includes_all_teams` — every team from `report.team_breakdown` appears in the output
5. `test_render_html_includes_critical_issues` — every issue from `report.critical_list` has its number in the output
6. `test_render_html_no_team_issues_present` — issues from `report.no_team_list` appear in the output
7. `test_render_html_duplicate_clusters_present` — cluster data appears
8. `test_report_to_dict_serialization` — `_report_to_dict` converts dataclasses to dicts, enums to strings
9. `test_render_html_format_auto_detection` — `.html` extension triggers HTML renderer

Tests reuse the `_make_result()` and `_make_report()` helpers from `tests/reports/test_markdown_renderer.py` (extract to a shared `conftest.py` fixture).

## Output File Strategy

When `--output` is a path like `data/report.html`, `run_report()` writes two files:

1. **`data/report.html`** — the file at the exact path specified. Overwritten each run. This is the "latest" that Dimitri bookmarks.
2. **`data/report-2026-08-04.html`** — a dated archive copy in the same directory. Never overwritten. Keeps history.

The dated filename is derived from `report.generated_at`. If the dated file already exists (multiple runs same day), it is overwritten — one archive per day is enough.

## Conditional Section Rendering

Sections with no data are hidden entirely — no empty headings or blank areas:

- **Action Required**: hidden if `len(report.critical_list) == 0`
- **Needs Triage**: hidden if `len(report.no_team_list) == 0` (doughnut chart goes full width)
- **Duplicate Clusters**: hidden if `len(report.duplicate_clusters) == 0`
- **Narrative**: hidden if `report.narrative` is empty string

KPI cards, Team Breakdown doughnut, and All Issues table are always shown.

## What This Spec Does NOT Cover

- Hosting/serving the HTML file (out of scope — it's just a file)
- Google Docs integration (separate renderer, not replaced)
- Historical trend charts (no multi-period data yet — future enhancement)
- Print/PDF styling (could add `@media print` later)
- Light theme toggle (single theme for now)
