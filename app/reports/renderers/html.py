from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
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


_AREA_RE = re.compile(r"^(?:feat|fix|bug|chore|docs|refactor|test|ci)\(([^)]+)\):\s*")


def _extract_area(title: str) -> str:
    m = _AREA_RE.match(title)
    return m.group(1) if m else ""


def _report_to_dict(
    report: BirdsEyeReport,
    enrichment: dict | None = None,
    sparklines: dict[str, list[int]] | None = None,
) -> dict:
    raw = asdict(report)
    data = _convert_value(raw)

    now = datetime.now(timezone.utc)
    team_issues: dict[str, list] = {}
    for issue in data.get("all_issues", []):
        issue["area"] = _extract_area(issue.get("issue_title", ""))
        created_at = issue.get("created_at", "")
        if created_at:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            issue["days_open"] = (now - created).days
        else:
            issue["days_open"] = 0
        issue["has_linked_pr"] = False
        issue["comment_count"] = 0

        team = issue.get("primary_team", "none")
        team_issues.setdefault(team, []).append(
            {
                "number": issue["issue_number"],
                "title": issue["issue_title"],
                "url": issue["issue_url"],
                "urgency": issue["urgency"],
            }
        )

    if enrichment:
        for key in ("critical_list", "no_team_list", "all_issues"):
            for issue in data.get(key, []):
                enr = enrichment.get(issue["issue_number"])
                if enr:
                    issue["has_linked_pr"] = enr.has_linked_pr
        for cluster in data.get("duplicate_clusters", []):
            for issue in cluster.get("issues", []):
                enr = enrichment.get(issue["issue_number"])
                if enr:
                    issue["has_linked_pr"] = enr.has_linked_pr

    area_list = []
    for area_name, trend in data.get("area_heatmap", {}).items():
        trend["area"] = area_name
        area_list.append(trend)
    area_list.sort(key=lambda x: x["current_count"], reverse=True)

    total_open = data.get("summary", {}).get("total_open", 0)
    area_sum = sum(a["current_count"] for a in area_list)

    for cluster in data.get("duplicate_clusters", []):
        for iss in cluster.get("issues", []):
            iss["number"] = iss.get("issue_number", 0)
            iss["title"] = iss.get("issue_title", "")
            iss["url"] = iss.get("issue_url", "")

    data["team_issues"] = team_issues
    data["area_heatmap"] = area_list
    data["area_unlabeled"] = max(0, total_open - area_sum)
    data["sparklines"] = sparklines or {
        "triage": [0, 0, 0, 0, 0, 0, 0],
        "prs": [0, 0, 0, 0, 0, 0, 0],
        "blocked": [0, 0, 0, 0, 0, 0, 0],
        "velocity": [0, 0, 0, 0, 0, 0, 0],
    }

    return data


def render_html(
    report: BirdsEyeReport,
    enrichment: dict | None = None,
    sparklines: dict[str, list[int]] | None = None,
) -> str:
    data = _report_to_dict(report, enrichment, sparklines)
    report_json = json.dumps(data, indent=2).replace("<", "\\u003c")
    return _HTML_TEMPLATE.replace("__REPORT_JSON__", report_json)


_HTML_TEMPLATE = """\
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
:root {
  --bg-body: #f4f5f7;
  --bg-card: #ffffff;
  --bg-card-hover: #f6f8fa;
  --bg-surface: #f0f1f3;
  --bg-topbar: rgba(255, 255, 255, 0.97);
  --text-primary: #1f2328;
  --text-secondary: #555d66;
  --text-muted: #7d8590;
  --text-dim: #afb8c1;
  --border: #c9d1d9;
  --border-subtle: #dfe4ea;
  --accent: #0969da;
  --accent-glow: rgba(9, 105, 218, 0.06);
  --urgency-critical: #d1242f;
  --urgency-high: #e16f24;
  --urgency-medium: #d4a015;
  --urgency-low: #1a7f37;
  --status-waiting: #d4a015;
  --status-blocked: #d1242f;
  --status-healthy: #1a7f37;
  --status-stale: #57606a;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --shadow-card: 0 1px 3px rgba(0,0,0,0.06);
  --shadow-hover: 0 4px 12px rgba(0,0,0,0.08);
  --transition: 0.2s ease;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg-body);
  color: var(--text-primary);
  line-height: 1.55;
  -webkit-font-smoothing: auto;
  font-size: 15px;
}

.topbar {
  position: sticky; top: 0; z-index: 100;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(0,0,0,0.06);
  padding: 0 28px;
  height: 52px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px;
}
.topbar-left { display: flex; align-items: center; gap: 10px; }
.topbar-title { font-size: 15px; font-weight: 600; letter-spacing: -0.01em; white-space: nowrap; color: var(--text-primary); }
.topbar-period { font-size: 12px; color: var(--text-muted); white-space: nowrap; padding-left: 10px; border-left: 1px solid var(--border-subtle); }
.topbar-center { display: flex; align-items: center; gap: 4px; }
.topbar-right { display: flex; align-items: center; gap: 8px; }

.date-pill {
  padding: 4px 12px; border-radius: 6px;
  font-size: 11px; font-weight: 500;
  border: none;
  background: transparent; color: var(--text-muted);
  cursor: pointer; transition: all var(--transition);
}
.date-pill:hover { background: var(--bg-surface); color: var(--text-primary); }
.date-pill.active { background: var(--text-primary); color: #fff; }

.search-input {
  background: var(--bg-surface); border: 1px solid transparent;
  border-radius: 8px; padding: 6px 14px; color: var(--text-primary);
  font-size: 12px; width: 180px; outline: none;
  transition: all var(--transition);
}
.search-input::placeholder { color: var(--text-dim); }
.search-input:focus { border-color: var(--accent); background: var(--bg-card); box-shadow: 0 0 0 3px rgba(9,105,218,0.1); }

.team-filter-wrap { position: relative; }
.team-filter-btn {
  padding: 5px 12px; border-radius: 8px;
  font-size: 11px; font-weight: 500;
  border: 1px solid transparent;
  background: var(--bg-surface); color: var(--text-muted);
  cursor: pointer; transition: all var(--transition);
  display: flex; align-items: center; gap: 5px;
}
.team-filter-btn:hover { background: var(--border-subtle); color: var(--text-primary); }
.team-filter-btn .chevron { font-size: 10px; transition: transform var(--transition); }
.team-filter-btn.open .chevron { transform: rotate(180deg); }
.team-dropdown {
  display: none; position: absolute; top: calc(100% + 6px); right: 0;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-md); padding: 8px 0; min-width: 180px;
  box-shadow: var(--shadow-hover); z-index: 200;
}
.team-dropdown.open { display: block; }
.team-dropdown label {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px; cursor: pointer; font-size: 13px;
  color: var(--text-secondary); transition: background var(--transition);
}
.team-dropdown label:hover { background: var(--bg-card-hover); }

.dashboard { max-width: 1200px; margin: 0 auto; padding: 24px; }

.section { margin-bottom: 32px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px; padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}
.section-title {
  font-size: 17px; font-weight: 600; letter-spacing: -0.01em;
  color: var(--text-primary); display: flex; align-items: center; gap: 8px;
}
.section-title .count { color: var(--text-muted); font-weight: 400; font-size: 14px; }
.section-subtitle { font-size: 12px; color: var(--text-muted); }

details.section-collapse > summary {
  list-style: none; cursor: pointer;
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px; padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}
details.section-collapse > summary::-webkit-details-marker { display: none; }
details.section-collapse > summary::after {
  content: '\\25B6'; font-size: 10px; color: var(--text-muted);
  transition: transform var(--transition);
}
details.section-collapse[open] > summary::after { transform: rotate(90deg); }

.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 28px; }
.kpi-card {
  background: var(--bg-card); border-radius: var(--radius-lg);
  padding: 24px 24px 20px; border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--border);
  box-shadow: none; cursor: pointer;
  transition: all var(--transition);
  position: relative; overflow: hidden;
}
.kpi-card:hover { box-shadow: var(--shadow-hover); border-left-color: var(--accent); }
.kpi-number { font-size: 32px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
.kpi-label { font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-top: 8px; letter-spacing: 0.01em; }
.kpi-sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.kpi-sparkline { position: absolute; bottom: 14px; right: 16px; opacity: 0.5; }

.alert-strip { margin-bottom: 24px; display: flex; flex-direction: column; gap: 6px; }
.alert-line {
  display: flex; align-items: center; gap: 10px;
  font-size: 14px; color: var(--text-secondary); line-height: 1.6;
  padding: 6px 0;
}
.alert-line .alert-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.alert-line strong { color: var(--text-primary); font-weight: 600; }
.alert-line a { color: var(--accent); text-decoration: none; }
.alert-line a:hover { text-decoration: underline; }

.team-band {
  background: var(--bg-card); border-radius: var(--radius-md);
  margin-bottom: 8px; overflow: hidden;
  border: 1px solid var(--border);
  transition: opacity 0.3s ease;
}
.team-band-header {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; cursor: pointer;
  transition: background var(--transition);
}
.team-band-header:hover { background: var(--bg-card-hover); }
.team-band-badge {
  display: inline-flex; align-items: center;
  padding: 4px 14px; border-radius: 20px;
  font-size: 13px; font-weight: 600;
}
.team-band-count { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
.team-band-trend { font-size: 13px; font-weight: 500; margin-left: 4px; }
.team-band-bar .segment { height: 100%; transition: width var(--transition); }
.team-band-chevron { font-size: 11px; color: var(--text-muted); transition: transform var(--transition); }
.team-band[open] .team-band-chevron { transform: rotate(90deg); }
.team-band-issues { padding: 0 16px 12px; }
.team-issue-row {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 0; border-top: 1px solid var(--border-subtle);
  font-size: 14px;
}
.team-issue-row a { color: var(--accent); text-decoration: none; }
.team-issue-row a:hover { text-decoration: underline; }

.metric-tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
.metric-tile {
  background: var(--bg-card); border-radius: var(--radius-lg);
  padding: 20px 20px 16px; text-align: left;
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--border);
  box-shadow: none;
  transition: all var(--transition);
}
.metric-tile:hover { box-shadow: var(--shadow-hover); border-left-color: var(--accent); }
.metric-tile .tile-value { font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
.metric-tile .tile-label { font-size: 12px; font-weight: 500; color: var(--text-secondary); margin-top: 6px; }

.metric-tiles-3 { grid-template-columns: repeat(3, 1fr); }

.stacked-bar-wrap { margin-bottom: 16px; }
.stacked-bar-label { font-size: 14px; color: var(--text-primary); margin-bottom: 8px; font-weight: 600; }
.stacked-bar {
  height: 28px; border-radius: 6px; background: var(--bg-surface);
  overflow: hidden; display: flex;
}
.stacked-bar .bar-seg {
  height: 100%; display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600; color: #fff;
  transition: width var(--transition);
  min-width: 0;
}
.stacked-bar .bar-seg span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 6px; }
.stacked-bar-legend {
  display: flex; gap: 16px; margin-top: 8px; flex-wrap: wrap;
}
.legend-item { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-secondary); }
.legend-dot { width: 8px; height: 8px; border-radius: 2px; }

.data-table {
  width: 100%; border-collapse: collapse;
  font-size: 14px;
}
.data-table th {
  text-align: left; padding: 10px 12px;
  font-size: 12px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--text-muted);
  border-bottom: 2px solid var(--border);
  cursor: pointer; user-select: none;
  white-space: nowrap;
}
.data-table th:hover { color: var(--text-primary); }
.data-table th .sort-icon { font-size: 10px; margin-left: 4px; color: var(--text-dim); }
.data-table th.sorted .sort-icon { color: var(--accent); }
.data-table td {
  padding: 10px 12px; border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
}
.data-table tr { transition: background var(--transition); }
.data-table tbody tr:hover { background: var(--bg-card-hover); }
.data-table a { color: var(--accent); text-decoration: none; }
.data-table a:hover { text-decoration: underline; }

.urgency-badge {
  display: inline-block; padding: 3px 10px;
  border-radius: 4px; font-size: 12px; font-weight: 600;
  letter-spacing: 0.03em;
}
.team-badge {
  display: inline-block; padding: 3px 12px;
  border-radius: 12px; font-size: 12px; font-weight: 500;
  white-space: nowrap;
}
.area-badge {
  display: inline-block; padding: 3px 10px;
  border-radius: 4px; font-size: 12px;
  background: rgba(9,105,218,0.08); color: var(--accent);
}

.expand-btn {
  width: 24px; height: 24px; border-radius: 4px;
  background: transparent; border: 1px solid var(--border);
  color: var(--text-muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; transition: all var(--transition);
}
.expand-btn:hover { border-color: var(--accent); color: var(--accent); }
.expand-btn.open { transform: rotate(90deg); border-color: var(--accent); color: var(--accent); }
.detail-row { display: none; }
.detail-row.open { display: table-row; }
.detail-row td {
  padding: 16px 20px; background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}
.detail-content { font-size: 13px; line-height: 1.6; }
.detail-section { margin-bottom: 10px; }
.detail-section:last-child { margin-bottom: 0; }
.detail-section-label {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 3px;
}
.detail-section-text { color: var(--text-secondary); }

.filter-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.filter-pill {
  padding: 4px 12px; border-radius: 6px;
  font-size: 11px; font-weight: 600; border: none;
  background: transparent; color: var(--text-muted);
  cursor: pointer; transition: all var(--transition);
}
.filter-pill:hover { background: var(--bg-surface); color: var(--text-primary); }
.filter-pill.active { color: #fff; }
.active-filters { display: flex; gap: 6px; flex-wrap: wrap; }
.active-filter-tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 10px; border-radius: 12px;
  background: rgba(9,105,218,0.08); color: var(--accent);
  font-size: 11px; font-weight: 500;
}
.active-filter-tag .remove { cursor: pointer; opacity: 0.7; }
.active-filter-tag .remove:hover { opacity: 1; }

.area-row {
  display: flex; align-items: center; gap: 12px;
  padding: 6px 0;
}
.area-row .area-name {
  width: 140px; font-size: 14px; color: var(--text-secondary);
  flex-shrink: 0; cursor: pointer;
}
.area-row .area-name:hover { color: var(--accent); }
.area-row .area-name.active-area { color: var(--accent); font-weight: 600; }
.area-bar-track {
  flex: 1; height: 20px; background: var(--bg-surface);
  border-radius: 4px; overflow: hidden;
}
.area-bar-fill {
  height: 100%; border-radius: 4px;
  background: var(--accent); transition: width 0.4s ease;
  display: flex; align-items: center; justify-content: flex-end;
  padding-right: 8px;
}
.area-bar-fill span { font-size: 11px; font-weight: 600; color: #fff; }
.area-count { width: 40px; text-align: right; font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; }
.area-trend { width: 40px; font-size: 13px; font-weight: 600; text-align: right; }
.trend-up { color: var(--urgency-high); }
.trend-down { color: var(--status-healthy); }
.trend-flat { color: var(--text-dim); }

.vouch-list { padding: 0; }
.vouch-row {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border-bottom: 1px solid var(--border-subtle);
  font-size: 14px; transition: opacity 0.3s ease, background var(--transition);
  border-radius: var(--radius-sm);
}
.vouch-row:hover:not(.dismissed) { background: var(--bg-card-hover); }
.vouch-row.dismissed { opacity: 0.3; height: 0; padding: 0; overflow: hidden; transition: all 0.3s ease; }
.vouch-row .vouch-author a { color: var(--accent); text-decoration: none; font-weight: 500; }
.vouch-row .vouch-author a:hover { text-decoration: underline; }
.vouch-row .vouch-wait { color: var(--text-muted); font-size: 13px; }
.vouch-row .vouch-link a { color: var(--accent); text-decoration: none; font-size: 13px; }
.vouch-row .vouch-link a:hover { text-decoration: underline; }
.dismiss-btn {
  width: 22px; height: 22px; border-radius: 4px;
  background: transparent; border: 1px solid var(--border);
  color: var(--text-dim); cursor: pointer; font-size: 12px;
  display: flex; align-items: center; justify-content: center;
  transition: all var(--transition); margin-left: auto; flex-shrink: 0;
}
.dismiss-btn:hover { border-color: var(--status-blocked); color: var(--status-blocked); }
.vouch-controls { display: flex; align-items: center; gap: 12px; margin-top: 8px; font-size: 12px; }
.vouch-controls a { color: var(--accent); cursor: pointer; text-decoration: none; }
.vouch-controls a:hover { text-decoration: underline; }
.vouch-note { font-size: 11px; color: var(--text-dim); font-style: italic; margin-top: 8px; }

.cluster-card {
  background: var(--bg-card); border-radius: var(--radius-md);
  padding: 16px 18px; margin-bottom: 10px;
  border: 1px solid var(--border);
}
.cluster-reason { font-size: 13px; color: var(--text-secondary); margin-bottom: 10px; font-weight: 500; }
.cluster-issue {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 0; font-size: 14px;
}
.cluster-issue a { color: var(--accent); text-decoration: none; }
.cluster-issue a:hover { text-decoration: underline; }

.footer {
  text-align: center; padding: 28px 0;
  font-size: 13px; color: var(--text-dim);
  border-top: 1px solid var(--border);
  margin-top: 16px;
}
.footer a { color: var(--accent); text-decoration: none; }
.footer a:hover { text-decoration: underline; }

.muted-note { font-size: 13px; color: var(--text-muted); font-style: italic; margin-bottom: 14px; }
.velocity-strip {
  display: flex; align-items: center; gap: 20px;
  padding: 14px 18px; margin: 16px 0;
  background: var(--bg-surface); border-radius: var(--radius-md);
  font-size: 13px; color: var(--text-secondary);
}
.velocity-strip .vel-metric { display: flex; flex-direction: column; gap: 2px; }
.velocity-strip .vel-value { font-size: 20px; font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
.velocity-strip .vel-label { font-size: 11px; color: var(--text-muted); font-weight: 500; }
.velocity-strip .vel-divider { width: 1px; height: 32px; background: var(--border-subtle); }
.velocity-strip .vel-change { font-size: 14px; font-weight: 600; }
.vel-positive { color: var(--status-healthy); }
.vel-negative { color: var(--urgency-high); }

.filter-banner {
  display: none; align-items: center; gap: 10px;
  padding: 10px 16px; margin-bottom: 20px;
  background: var(--accent-glow); border: 1px solid rgba(9,105,218,0.15);
  border-radius: var(--radius-md); font-size: 13px; color: var(--accent);
}
.filter-banner.visible { display: flex; }
.filter-banner .filter-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.filter-banner .filter-tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 10px; border-radius: 12px;
  background: rgba(9,105,218,0.1); font-size: 12px; font-weight: 500;
}
.filter-banner .clear-filters {
  margin-left: auto; cursor: pointer; font-size: 12px;
  color: var(--accent); text-decoration: underline; background: none; border: none;
}

.team-band.filtered-out { opacity: 0.25; pointer-events: none; }

@media (max-width: 1024px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .metric-tiles { grid-template-columns: repeat(2, 1fr); }
  .metric-tiles-3 { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .topbar { height: auto; padding: 10px 16px; flex-wrap: wrap; }
  .topbar-center { order: 3; width: 100%; justify-content: center; }
  .kpi-grid { grid-template-columns: 1fr 1fr; }
  .metric-tiles, .metric-tiles-3 { grid-template-columns: 1fr; }
  .dashboard { padding: 16px; }
  .data-table { font-size: 12px; }
  .search-input { width: 140px; }
  .area-row .area-name { width: 100px; }
}
</style>
</head>
<body>

<div class="topbar" id="topbar"></div>
<div class="dashboard" id="app"></div>

<script>
const REPORT_DATA = __REPORT_JSON__;
</script>
<script>
(function() {
  "use strict";

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
    w = w || 60; h = h || 20;
    var max = Math.max.apply(null, data), min = Math.min.apply(null, data);
    var range = max - min || 1;
    var pts = data.map(function(v, i) {
      return (i * w / (data.length - 1)).toFixed(1) + "," + (h - ((v - min) / range) * h * 0.8 - h * 0.1).toFixed(1);
    }).join(" ");
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<polyline points="' + pts + '" stroke="' + color + '" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>' +
      '<circle cx="' + (w) + '" cy="' + (h - ((data[data.length-1] - min) / range) * h * 0.8 - h * 0.1).toFixed(1) + '" r="2" fill="' + color + '"/>' +
      '</svg>';
  }

  function makeTeamBadgeHTML(team) {
    var c = tc(team);
    var label = team === "none" ? "Unassigned" : team;
    return '<span class="team-badge" style="background:' + c + '20;color:' + c + ';">' + esc(label) + '</span>';
  }

  function makeUrgencyBadgeHTML(u) {
    var c = uc(u);
    return '<span class="urgency-badge" style="background:' + c + '20;color:' + c + ';">' + (URGENCY_SHORT[u] || u) + '</span>';
  }

  var STORAGE_KEY = "openshell-triage-v3";
  function loadState() { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch(e) { return {}; } }
  function saveState(s) { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); } catch(e) {} }

  var state = loadState();
  if (!state.dismissed) state.dismissed = [];
  if (!state.collapsed) state.collapsed = {};
  if (!state.dateRange) state.dateRange = "14d";

  var d = REPORT_DATA;

  var activeTeams = [];
  var activeUrgencies = [];
  var activeArea = "";
  var searchQuery = "";

  function matchesFilters(issue) {
    if (activeTeams.length && activeTeams.indexOf(issue.primary_team) === -1) return false;
    if (activeUrgencies.length && activeUrgencies.indexOf(issue.urgency) === -1) return false;
    if (activeArea && (issue.area || "") !== activeArea) return false;
    if (searchQuery) {
      var q = searchQuery.toLowerCase();
      var title = (issue.issue_title || issue.title || "").toLowerCase();
      var num = String(issue.issue_number || issue.number || "");
      if (title.indexOf(q) === -1 && num.indexOf(q) === -1) return false;
    }
    return true;
  }

  function applyAllFilters() {
    rebuildIssuesTable();
    var banner = document.getElementById("filter-banner");
    if (banner) {
      var tags = banner.querySelector(".filter-tags");
      tags.innerHTML = "";
      if (activeUrgencies.length || searchQuery || activeArea) {
        banner.classList.add("visible");
        activeUrgencies.forEach(function(u) {
          tags.innerHTML += '<span class="filter-tag">' + (URGENCY_SHORT[u] || u) + '</span>';
        });
        if (activeArea) {
          tags.innerHTML += '<span class="filter-tag">area:' + esc(activeArea) + '</span>';
        }
        if (searchQuery) {
          tags.innerHTML += '<span class="filter-tag">"' + esc(searchQuery) + '"</span>';
        }
      } else {
        banner.classList.remove("visible");
      }
    }
  }

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

  function buildKPIs() {
    var grid = el("div", "kpi-grid");
    var kpis = [
      {value: d.summary.triage_needed, label: "Issues Needing Triage", sub: d.summary.total_open + " total open issues", color: "var(--urgency-high)", spark: d.sparklines.triage, sparkColor: "#e16f24", target: "team-routing"}
    ];

    if (d.pr_health) {
      kpis.push({value: d.pr_health.awaiting_review, label: "PRs Waiting for Review", sub: d.pr_health.stale_14d + " stale (14d+)", color: "var(--status-waiting)", spark: d.sparklines.prs, sparkColor: "#d4a015", target: "pr-health"});
    }
    if (d.vouch_status) {
      kpis.push({value: d.vouch_status.total_pending, label: "Blocked Contributors", sub: d.vouch_status.over_30d_count + " waiting over 30 days", color: "var(--status-blocked)", spark: d.sparklines.blocked, sparkColor: "#d1242f", target: "contributor-health"});
    }
    if (d.pr_health) {
      kpis.push({value: d.pr_health.merge_velocity + "/wk", label: "Merge Velocity", sub: (d.pr_health.merge_velocity_prev || 0) + "/wk last period", color: "var(--status-healthy)", spark: d.sparklines.velocity, sparkColor: "#1a7f37", target: "pr-health"});
    }

    grid.style.gridTemplateColumns = "repeat(" + kpis.length + ", 1fr)";

    kpis.forEach(function(k) {
      var card = el("div", "kpi-card");
      card.style.borderLeftColor = k.color;
      var hasVariation = k.spark && k.spark.some(function(v) { return v !== k.spark[0]; });
      card.innerHTML = '<div class="kpi-number">' + k.value + '</div>' +
        '<div class="kpi-label">' + esc(k.label) + '</div>' +
        '<div class="kpi-sub">' + esc(k.sub) + '</div>' +
        (hasVariation ? '<div class="kpi-sparkline">' + sparkSVG(k.spark, k.sparkColor) + '</div>' : '');
      card.addEventListener("click", function() {
        var target = document.getElementById(k.target);
        if (target) target.scrollIntoView({behavior: "smooth", block: "start"});
      });
      grid.appendChild(card);
    });
    return grid;
  }

  function buildAlerts() {
    var strip = el("div", "alert-strip");
    var highCount = d.summary.by_urgency.high || 0;
    var alertData = [
      {color: "#d1242f", text: '<strong>' + highCount + '</strong> high-urgency issues this period'}
    ];

    if (d.pr_health) {
      var staleCount = d.pr_health.stale_14d || 0;
      var longestStuck = d.pr_health.stuck_prs.length ? d.pr_health.stuck_prs[0] : null;
      alertData.push({color: "#d4a015", text: '<strong>' + staleCount + '</strong> PRs stale for 14+ days' + (longestStuck ? ' - oldest: <a href="' + esc(longestStuck.url) + '" target="_blank">#' + longestStuck.number + '</a> (' + longestStuck.days_open + ' days)' : '')});
    }

    if (d.vouch_status) {
      var vouchCount = d.vouch_status.total_pending || 0;
      var longestVouch = d.vouch_status.pending_vouches.length ? d.vouch_status.pending_vouches[0] : null;
      alertData.push({color: "#e16f24", text: '<strong>' + vouchCount + '</strong> contributors waiting for vouch' + (longestVouch ? ' - longest: <a href="' + esc(longestVouch.url) + '" target="_blank">@' + esc(longestVouch.author) + '</a> (' + longestVouch.wait_days + ' days)' : '')});
    }

    alertData.forEach(function(a) {
      var line = el("div", "alert-line");
      line.innerHTML = '<span class="alert-dot" style="background:' + a.color + ';"></span>' + a.text;
      strip.appendChild(line);
    });
    return strip;
  }

  function buildTeamRouting() {
    var section = el("div", "section");
    section.id = "team-routing";
    section.innerHTML = '<div class="section-header"><div class="section-title">Team Routing <span class="count">(' + d.all_issues.length + ' issues across ' + Object.keys(d.team_breakdown).length + ' teams)</span></div></div>';

    var teamOrder = Object.keys(d.team_breakdown);
    teamOrder.forEach(function(teamId) {
      var team = d.team_breakdown[teamId];
      if (!team) return;
      var band = el("details", "team-band");
      band.dataset.team = teamId;
      var color = tc(teamId);
      var urgencies = team.by_urgency || {};
      var total = team.total;
      var trend = team.trend || "0";
      var trendClass = trend.charAt(0) === "+" ? "trend-up" : (trend.charAt(0) === "-" ? "trend-down" : "trend-flat");

      var urgencyBadges = "";
      ["critical","high","medium","low"].forEach(function(u) {
        var count = urgencies[u] || 0;
        if (count > 0) {
          urgencyBadges += ' ' + makeUrgencyBadgeHTML(u) + '<span style="font-size:13px;font-weight:600;color:var(--text-secondary);margin:0 8px 0 4px;">' + count + '</span>';
        }
      });

      var header = el("summary", "team-band-header");
      header.innerHTML =
        '<span class="team-band-badge" style="background:' + color + '20;color:' + color + ';">' + esc(teamId === "none" ? "Unassigned" : teamId) + '</span>' +
        '<span class="team-band-count">' + total + '</span>' +
        (trend !== "0" ? '<span class="team-band-trend ' + trendClass + '">' + esc(trend) + '</span>' : '') +
        '<span style="flex:1;display:flex;align-items:center;margin:0 12px;">' + urgencyBadges + '</span>' +
        '<span class="team-band-chevron">&#9654;</span>';
      band.appendChild(header);

      var issues = d.team_issues[teamId] || [];
      if (issues.length) {
        var issuesDiv = el("div", "team-band-issues");
        issues.forEach(function(iss) {
          var row = el("div", "team-issue-row");
          var prInfo = d.all_issues.find(function(ai) { return ai.issue_number === iss.number; });
          var prIcon = (prInfo && prInfo.has_linked_pr) ? ' <svg width="14" height="14" viewBox="0 0 16 16" fill="#1A7F37" style="vertical-align:-2px;"><path d="M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"/></svg>' : '';
          var areaTag = (prInfo && prInfo.area) ? ' <span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;background:var(--accent-glow);color:var(--accent);font-weight:600;">' + esc(prInfo.area) + '</span>' : '';
          var daysTag = (prInfo && prInfo.days_open != null) ? '<span style="color:var(--text-muted);font-size:12px;margin-left:auto;white-space:nowrap;">' + prInfo.days_open + 'd</span>' : '';
          row.style.cssText = 'display:flex;align-items:center;gap:6px;';
          row.innerHTML = makeUrgencyBadgeHTML(iss.urgency) +
            ' <a href="' + esc(iss.url) + '" target="_blank">#' + iss.number + '</a>' + areaTag + prIcon + ' ' +
            '<span style="color:var(--text-secondary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(iss.title) + '</span>' + daysTag;
          issuesDiv.appendChild(row);
        });
        band.appendChild(issuesDiv);
      }
      section.appendChild(band);
    });
    return section;
  }

  function buildPRHealth() {
    var section = el("div", "section");
    section.id = "pr-health";

    var header = el("details", "section-collapse");
    header.open = state.collapsed["pr-health"] !== false;
    var summary = el("summary");
    summary.innerHTML = '<div class="section-title">PR Health</div>';
    header.appendChild(summary);

    var tiles = el("div", "metric-tiles");
    var tileData = [
      {value: d.pr_health.total_open, label: "Open PRs", color: "var(--text-primary)", accent: "var(--border)"},
      {value: d.pr_health.awaiting_review, label: "Awaiting Review", color: "var(--status-waiting)", accent: "var(--status-waiting)"},
      {value: d.pr_health.stale_14d, label: "Stale (14d+)", color: "var(--urgency-high)", accent: "var(--urgency-high)"},
      {value: d.pr_health.gator_coverage_pct + "%", label: "Gator Coverage", color: "var(--accent)", accent: "var(--accent)"}
    ];
    tileData.forEach(function(t) {
      var tile = el("div", "metric-tile");
      tile.style.borderLeftColor = t.accent;
      tile.innerHTML = '<div class="tile-value" style="color:' + t.color + '">' + t.value + '</div><div class="tile-label">' + esc(t.label) + '</div>';
      tiles.appendChild(tile);
    });
    header.appendChild(tiles);

    var ageWrap = el("div", "stacked-bar-wrap");
    var ageDist = d.pr_health.age_distribution;
    var ageTotal = ageDist.lt_1w.count + ageDist["1_2w"].count + ageDist["2_4w"].count + ageDist.gt_1m.count;
    var ageColors = ["#1a7f37", "#d4a015", "#e16f24", "#d1242f"];
    var ageKeys = ["lt_1w", "1_2w", "2_4w", "gt_1m"];
    ageWrap.innerHTML = '<div class="stacked-bar-label">PR Age Distribution</div>';
    var barHtml = '<div class="stacked-bar">';
    if (ageTotal > 0) {
      ageKeys.forEach(function(key, i) {
        var seg = ageDist[key];
        var pct = (seg.count / ageTotal * 100).toFixed(1);
        barHtml += '<div class="bar-seg" style="width:' + pct + '%;background:' + ageColors[i] + ';"><span>' + seg.count + '</span></div>';
      });
    }
    barHtml += '</div>';
    var legendHtml = '<div class="stacked-bar-legend">';
    ageKeys.forEach(function(key, i) {
      legendHtml += '<span class="legend-item"><span class="legend-dot" style="background:' + ageColors[i] + ';"></span>' + ageDist[key].label + ' (' + ageDist[key].count + ')</span>';
    });
    legendHtml += '</div>';
    ageWrap.innerHTML += barHtml + legendHtml;
    header.appendChild(ageWrap);

    var stuckTitle = el("div", "stacked-bar-label", 'Neglected PRs <span style="color:var(--text-dim);font-weight:400;">- no meaningful review activity for 7+ days</span>');
    header.appendChild(stuckTitle);

    var table = el("table", "data-table");
    table.innerHTML = '<thead><tr><th>#</th><th>Title</th><th>Author</th><th>Age</th><th>Last Activity</th><th>Participants</th></tr></thead>';
    var tbody = el("tbody");
    d.pr_health.stuck_prs.forEach(function(pr) {
      var participantLinks = (pr.participants || []).map(function(p) {
        return '<a href="https://github.com/' + esc(p) + '" target="_blank">@' + esc(p) + '</a>';
      }).join(', ') || '<span style="color:var(--status-blocked);font-weight:500;">No engagement</span>';
      var daysOpen = pr.days_open || 0;
      var activityText = pr.last_activity || (daysOpen + 'd');
      var tr = el("tr");
      tr.innerHTML = '<td><a href="' + esc(pr.url) + '" target="_blank">#' + pr.number + '</a></td>' +
        '<td><a href="' + esc(pr.url) + '" target="_blank">' + esc(pr.title) + '</a></td>' +
        '<td><a href="https://github.com/' + esc(pr.author) + '" target="_blank">@' + esc(pr.author) + '</a></td>' +
        '<td style="font-weight:600;color:var(--urgency-high);">' + daysOpen + 'd</td>' +
        '<td style="font-size:12px;color:var(--text-muted);">' + esc(activityText) + '</td>' +
        '<td style="font-size:13px;">' + participantLinks + '</td>';
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    header.appendChild(table);

    var owners = (d.pr_health.codeowners || []).join(", ") || "CODEOWNERS";
    header.appendChild(el("p", "muted-note", "CODEOWNERS auto-assigns " + owners + " to every PR. Participants shown above are people who actually engaged (commented or reviewed)."));

    var velChange = d.pr_health.merge_velocity - d.pr_health.merge_velocity_prev;
    var velPrev = d.pr_health.merge_velocity_prev || 1;
    var velPct = Math.round(velChange / velPrev * 100);
    var velSign = velPct >= 0 ? '+' : '';
    var velClass = velPct >= 0 ? 'vel-positive' : 'vel-negative';
    var velStrip = el("div", "velocity-strip");
    velStrip.innerHTML =
      '<div class="vel-metric"><span class="vel-value">' + d.pr_health.merge_velocity + '/wk</span><span class="vel-label">This period</span></div>' +
      '<span class="vel-divider"></span>' +
      '<div class="vel-metric"><span class="vel-value">' + d.pr_health.merge_velocity_prev + '/wk</span><span class="vel-label">Last period</span></div>' +
      '<span class="vel-divider"></span>' +
      '<div class="vel-metric"><span class="vel-change ' + velClass + '">' + velSign + velPct + '%</span><span class="vel-label">Change</span></div>';
    header.appendChild(velStrip);

    header.addEventListener("toggle", function() { state.collapsed["pr-health"] = header.open; saveState(state); });
    section.appendChild(header);
    return section;
  }

  function buildContributorHealth() {
    var section = el("div", "section");
    section.id = "contributor-health";

    var wrap = el("details", "section-collapse");
    wrap.open = state.collapsed["contributor-health"] !== false;
    var summary = el("summary");
    summary.innerHTML = '<div class="section-title">Contributor Health</div>';
    wrap.appendChild(summary);

    var tiles = el("div", "metric-tiles metric-tiles-3");
    var tData = [
      {value: d.vouch_status.total_pending, label: "Pending Vouches", color: "var(--urgency-high)"},
      {value: d.vouch_status.responded_in_7d, label: "Responded (< 7d)", color: "var(--status-healthy)"},
      {value: d.vouch_status.longest_wait_days + " days", label: "Longest Wait", color: "var(--status-blocked)"}
    ];
    tData.forEach(function(t) {
      var tile = el("div", "metric-tile");
      tile.style.borderLeftColor = t.color;
      tile.innerHTML = '<div class="tile-value" style="color:' + t.color + '">' + t.value + '</div><div class="tile-label">' + esc(t.label) + '</div>';
      tiles.appendChild(tile);
    });
    wrap.appendChild(tiles);

    var hsTitle = el("div", "stacked-bar-label", "Pending Vouch Requests");
    wrap.appendChild(hsTitle);

    var VOUCH_INITIAL_SHOW = 5;
    var vouchList = el("div", "vouch-list");
    var allVouches = d.vouch_status.pending_vouches;
    allVouches.forEach(function(v, idx) {
      var isDismissed = state.dismissed.indexOf(v.author) !== -1;
      var row = el("div", "vouch-row" + (isDismissed ? " dismissed" : ""));
      row.dataset.author = v.author;
      if (idx >= VOUCH_INITIAL_SHOW) row.style.display = "none";
      var waitText = v.wait_days === 0 ? "today" : v.wait_days === 1 ? "1 day" : v.wait_days + " days";
      row.innerHTML =
        '<span class="vouch-author"><a href="https://github.com/' + esc(v.author) + '" target="_blank">@' + esc(v.author) + '</a></span>' +
        '<span class="vouch-link"><a href="' + esc(v.url) + '" target="_blank">#' + v.discussion_number + '</a></span>' +
        '<span class="vouch-wait">' + waitText + '</span>';
      var dismissBtn = el("button", "dismiss-btn", "\\u2715");
      dismissBtn.title = "Dismiss";
      dismissBtn.addEventListener("click", function() {
        if (state.dismissed.indexOf(v.author) === -1) state.dismissed.push(v.author);
        saveState(state);
        row.classList.add("dismissed");
        updateDismissedCount();
      });
      row.appendChild(dismissBtn);
      vouchList.appendChild(row);
    });
    wrap.appendChild(vouchList);

    var vouchExpanded = false;
    var remaining = allVouches.length - VOUCH_INITIAL_SHOW;
    if (remaining > 0) {
      var viewMoreLink = el("a");
      viewMoreLink.textContent = "View " + remaining + " more";
      viewMoreLink.style.cssText = "color:var(--accent);cursor:pointer;text-decoration:none;font-size:13px;font-weight:500;display:inline-block;margin-top:6px;";
      viewMoreLink.addEventListener("click", function() {
        vouchExpanded = !vouchExpanded;
        var rows = vouchList.querySelectorAll(".vouch-row");
        rows.forEach(function(r, i) {
          if (i >= VOUCH_INITIAL_SHOW) r.style.display = vouchExpanded ? "" : "none";
        });
        viewMoreLink.textContent = vouchExpanded ? "Show less" : "View " + remaining + " more";
      });
      wrap.appendChild(viewMoreLink);
    }

    var controls = el("div", "vouch-controls");
    var showDismissed = el("a");
    showDismissed.textContent = "Show dismissed (" + state.dismissed.length + ")";
    if (state.dismissed.length === 0) showDismissed.style.display = "none";
    showDismissed.addEventListener("click", function() {
      state.dismissed = [];
      saveState(state);
      vouchList.querySelectorAll(".vouch-row").forEach(function(r) { r.classList.remove("dismissed"); });
      updateDismissedCount();
    });
    controls.appendChild(showDismissed);
    wrap.appendChild(controls);

    function updateDismissedCount() {
      showDismissed.textContent = "Show dismissed (" + state.dismissed.length + ")";
      showDismissed.style.display = state.dismissed.length > 0 ? "" : "none";
    }

    wrap.appendChild(el("div", "vouch-note", "Items can be dismissed if the team has intentionally deferred a vouch decision."));

    wrap.addEventListener("toggle", function() { state.collapsed["contributor-health"] = wrap.open; saveState(state); });
    section.appendChild(wrap);
    return section;
  }

  function buildAreaBreakdown() {
    var section = el("div", "section");
    var wrap = el("details", "section-collapse");
    wrap.open = state.collapsed["area-breakdown"] !== false;
    var summary = el("summary");
    summary.innerHTML = '<div class="section-title">Area Breakdown <span class="count">(' + d.area_heatmap.length + ' areas)</span></div>';
    wrap.appendChild(summary);

    if (d.area_unlabeled > 0) {
      var unlabeledPct = Math.round(d.area_unlabeled / Math.max(1, d.summary.total_open) * 100);
      wrap.appendChild(el("div", "muted-note", '<span style="color:var(--urgency-high);font-style:normal;font-weight:600;">' + d.area_unlabeled + ' issues</span> have no area label (' + unlabeledPct + '% of open issues)'));
    }

    var maxCount = d.area_heatmap.reduce(function(m, a) { return Math.max(m, a.current_count); }, 0);
    d.area_heatmap.forEach(function(area) {
      var row = el("div", "area-row");
      var pct = maxCount > 0 ? (area.current_count / maxCount * 100).toFixed(0) : "0";
      var trendVal = area.trend;
      var showTrend = trendVal && trendVal !== "+1" && area.previous_count !== area.current_count - 1;
      var trendClass = trendVal && trendVal.charAt(0) === "+" ? "trend-up" : (trendVal && trendVal.charAt(0) === "-" ? "trend-down" : "trend-flat");
      var barOpacity = maxCount > 0 ? 0.5 + (area.current_count / maxCount) * 0.5 : 0.5;
      row.innerHTML =
        '<span class="area-name" title="Click to filter issues by area:' + esc(area.area) + '">area:' + esc(area.area) + '</span>' +
        '<div class="area-bar-track"><div class="area-bar-fill" style="width:' + pct + '%;opacity:' + barOpacity.toFixed(2) + ';"></div></div>' +
        '<span class="area-count">' + area.current_count + '</span>' +
        (showTrend ? '<span class="area-trend ' + trendClass + '">' + esc(trendVal) + '</span>' : '<span class="area-trend"></span>');
      var areaName = row.querySelector(".area-name");
      areaName.addEventListener("click", function() {
        document.querySelectorAll(".area-name.active-area").forEach(function(a) { a.classList.remove("active-area"); });
        if (activeArea === area.area) {
          activeArea = "";
        } else {
          activeArea = area.area;
          areaName.classList.add("active-area");
        }
        applyAllFilters();
        var issuesSection = document.getElementById("all-issues");
        if (issuesSection) issuesSection.scrollIntoView({behavior: "smooth", block: "start"});
      });
      wrap.appendChild(row);
    });

    wrap.addEventListener("toggle", function() { state.collapsed["area-breakdown"] = wrap.open; saveState(state); });
    section.appendChild(wrap);
    return section;
  }

  function buildDuplicates() {
    if (!d.duplicate_clusters || !d.duplicate_clusters.length) return el("div");
    var section = el("div", "section");
    var wrap = el("details", "section-collapse");
    wrap.open = state.collapsed["duplicates"] !== false;
    var summary = el("summary");
    summary.innerHTML = '<div class="section-title">Potential Duplicates <span class="count">(' + d.duplicate_clusters.length + ' clusters)</span></div>';
    wrap.appendChild(summary);

    d.duplicate_clusters.forEach(function(cluster) {
      var card = el("div", "cluster-card");
      card.innerHTML = '<div class="cluster-reason">' + esc(cluster.similarity_reason) + '</div>';
      cluster.issues.forEach(function(iss) {
        var issRow = el("div", "cluster-issue");
        issRow.innerHTML = makeUrgencyBadgeHTML(iss.urgency) +
          ' <a href="' + esc(iss.url || iss.issue_url) + '" target="_blank">#' + (iss.number || iss.issue_number) + '</a> ' +
          '<span style="color:var(--text-secondary);">' + esc(iss.title || iss.issue_title) + '</span>';
        card.appendChild(issRow);
      });
      wrap.appendChild(card);
    });

    wrap.addEventListener("toggle", function() { state.collapsed["duplicates"] = wrap.open; saveState(state); });
    section.appendChild(wrap);
    return section;
  }

  var issuesTableBody;
  var currentSort = {col: "urgency", dir: "asc"};

  function buildAllIssuesTable() {
    var section = el("div", "section");
    section.id = "all-issues";

    var header = el("div", "section-header");
    header.innerHTML = '<div class="section-title">All Issues <span class="count">(' + d.all_issues.length + ')</span></div>';
    section.appendChild(header);

    var filterBar = el("div", "filter-bar");
    ["critical", "high", "medium", "low"].forEach(function(u) {
      var pill = el("button", "filter-pill");
      pill.textContent = URGENCY_SHORT[u];
      pill.addEventListener("click", function() {
        pill.classList.toggle("active");
        if (pill.classList.contains("active")) {
          pill.style.background = uc(u); pill.style.color = "#fff";
          if (activeUrgencies.indexOf(u) === -1) activeUrgencies.push(u);
        } else {
          pill.style.background = "transparent"; pill.style.color = "var(--text-muted)";
          activeUrgencies = activeUrgencies.filter(function(x) { return x !== u; });
        }
        applyAllFilters();
      });
      filterBar.appendChild(pill);
    });
    section.appendChild(filterBar);

    var table = el("table", "data-table");
    var cols = [
      {key: "expand", label: "", sortable: false},
      {key: "urgency", label: "Urgency", sortable: true},
      {key: "issue_number", label: "#", sortable: true},
      {key: "issue_title", label: "Title", sortable: true},
      {key: "primary_team", label: "Team", sortable: true},
      {key: "area", label: "Area", sortable: true},
      {key: "days_open", label: "Days", sortable: true},
      {key: "has_linked_pr", label: "PR", sortable: true},
      {key: "comment_count", label: "Comments", sortable: true}
    ];
    var thead = el("thead");
    var headRow = el("tr");
    cols.forEach(function(col) {
      var th = el("th");
      th.textContent = col.label;
      if (col.sortable) {
        th.innerHTML += ' <span class="sort-icon">&#9650;</span>';
        th.addEventListener("click", function() {
          if (currentSort.col === col.key) {
            currentSort.dir = currentSort.dir === "asc" ? "desc" : "asc";
          } else {
            currentSort.col = col.key;
            currentSort.dir = "asc";
          }
          thead.querySelectorAll("th").forEach(function(t) { t.classList.remove("sorted"); });
          th.classList.add("sorted");
          th.querySelector(".sort-icon").textContent = currentSort.dir === "asc" ? "\\u25B2" : "\\u25BC";
          rebuildIssuesTable();
        });
      }
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    issuesTableBody = el("tbody");
    table.appendChild(issuesTableBody);
    section.appendChild(table);

    rebuildIssuesTable();
    return section;
  }

  function rebuildIssuesTable() {
    if (!issuesTableBody) return;
    issuesTableBody.innerHTML = "";
    var issues = d.all_issues.filter(matchesFilters);

    issues.sort(function(a, b) {
      var col = currentSort.col;
      var dir = currentSort.dir === "asc" ? 1 : -1;
      if (col === "urgency") {
        return (URGENCY_ORDER[a.urgency] - URGENCY_ORDER[b.urgency]) * dir;
      }
      var av = a[col], bv = b[col];
      if (av == null) av = ""; if (bv == null) bv = "";
      if (typeof av === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });

    var openDetailRow = null;

    issues.forEach(function(issue) {
      var tr = el("tr");
      var prCell = issue.has_linked_pr ? '<svg width="16" height="16" viewBox="0 0 16 16" fill="#1A7F37"><path d="M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"/></svg>' : '<span style="color:var(--text-dim);">-</span>';
      var commentCell = issue.comment_count > 0 ? '<span style="font-variant-numeric:tabular-nums;">' + issue.comment_count + '</span>' : '<span style="color:var(--text-dim);">-</span>';

      tr.innerHTML =
        '<td><button class="expand-btn">&#9654;</button></td>' +
        '<td>' + makeUrgencyBadgeHTML(issue.urgency) + '</td>' +
        '<td><a href="' + esc(issue.issue_url) + '" target="_blank">#' + issue.issue_number + '</a></td>' +
        '<td><a href="' + esc(issue.issue_url) + '" target="_blank">' + esc(issue.issue_title) + '</a></td>' +
        '<td>' + makeTeamBadgeHTML(issue.primary_team) + '</td>' +
        '<td>' + (issue.area ? '<span class="area-badge">area:' + esc(issue.area) + '</span>' : '<span style="color:var(--text-dim);">-</span>') + '</td>' +
        '<td style="font-variant-numeric:tabular-nums;">' + issue.days_open + '</td>' +
        '<td>' + prCell + '</td>' +
        '<td>' + commentCell + '</td>';
      var expandBtn = tr.querySelector(".expand-btn");

      var detailTr = el("tr", "detail-row");
      var detailTd = el("td");
      detailTd.colSpan = 9;
      var summaryText = issue.summary || "";
      var recText = issue.recommendation || "";
      var detailHtml = '<div class="detail-content">';
      if (summaryText) {
        detailHtml += '<div class="detail-section"><div class="detail-section-label">Summary</div><div class="detail-section-text">' + esc(summaryText) + '</div></div>';
      }
      if (recText) {
        detailHtml += '<div class="detail-section"><div class="detail-section-label">Recommended Action</div><div class="detail-section-text">' + esc(recText) + '</div></div>';
      }
      detailHtml += '</div>';
      detailTd.innerHTML = detailHtml;
      detailTr.appendChild(detailTd);

      expandBtn.addEventListener("click", function() {
        if (openDetailRow && openDetailRow !== detailTr) {
          openDetailRow.classList.remove("open");
          openDetailRow.previousElementSibling.querySelector(".expand-btn").classList.remove("open");
        }
        expandBtn.classList.toggle("open");
        detailTr.classList.toggle("open");
        openDetailRow = detailTr.classList.contains("open") ? detailTr : null;
      });

      issuesTableBody.appendChild(tr);
      issuesTableBody.appendChild(detailTr);
    });
  }

  function buildFooter() {
    var footer = el("div", "footer");
    var genDate = d.generated_at ? new Date(d.generated_at).toLocaleDateString('en-US', {year: 'numeric', month: 'short', day: 'numeric'}) : 'unknown';
    footer.innerHTML = 'OpenShell Overview &middot; Generated ' + genDate;
    return footer;
  }

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
</body>
</html>
"""
