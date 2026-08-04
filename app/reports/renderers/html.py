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


def render_html(report: BirdsEyeReport) -> str:
    data = _report_to_dict(report)
    labels = {}
    if data.get("critical_list"):
        labels["critical"] = "Action Required"
    if data.get("no_team_list"):
        labels["no_team"] = "Needs Triage"
    if data.get("duplicate_clusters"):
        labels["duplicates"] = "Potential Duplicates"
    data["_labels"] = labels
    report_json = json.dumps(data, indent=2).replace("<", "\\u003c")
    return _HTML_TEMPLATE.replace("__REPORT_JSON__", report_json)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenShell Triage Overview</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels"></script>
<style>
:root {
  --bg-primary: #0F172A;
  --bg-card: #1E293B;
  --bg-hover: #334155;
  --text-primary: #F1F5F9;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;
  --border: #334155;
  --accent: #6366F1;
  --urgency-critical: #EF4444;
  --urgency-high: #F97316;
  --urgency-medium: #EAB308;
  --urgency-low: #22C55E;
}

*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.dashboard {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  flex-wrap: wrap;
  gap: 8px;
}

.header h1 {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.header .period {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}

.header .generated-at {
  font-size: 12px;
  color: var(--text-muted);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.kpi-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px;
  border-left: 4px solid var(--border);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.kpi-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.kpi-number {
  font-size: 32px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 4px;
}

.kpi-label {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.pulse .kpi-number {
  animation: pulse 2s ease-in-out infinite;
}

.narrative {
  background: var(--bg-card);
  border-left: 4px solid var(--accent);
  border-radius: 0 12px 12px 0;
  padding: 20px 24px;
  margin-bottom: 32px;
  color: var(--text-primary);
  font-size: 16px;
  line-height: 1.7;
}

.narrative .attribution {
  display: block;
  margin-top: 8px;
  font-style: normal;
  font-size: 12px;
  color: var(--text-muted);
}

.section-heading {
  font-size: 20px;
  font-weight: 600;
  margin-top: 32px;
  margin-bottom: 16px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.section-heading .count {
  color: var(--text-secondary);
  font-weight: 400;
}

.issue-card {
  background: var(--bg-card);
  border-radius: 8px;
  padding: 16px;
  border-left: 4px solid var(--border);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  margin-bottom: 12px;
  text-decoration: none;
  display: block;
  color: inherit;
}

.issue-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}

.issue-card .issue-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.issue-card .issue-number {
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.issue-card .issue-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
}

.issue-card .issue-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.issue-card .issue-summary {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.issue-card .secondary-tag {
  display: inline-block;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 6px;
  padding: 2px 8px;
  background: rgba(99, 102, 241, 0.1);
  border-radius: 4px;
}

.urgency-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

.team-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.two-column {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 32px;
}

.chart-container {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 24px;
}

.chart-container h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-primary);
}

.chart-container canvas {
  max-height: 300px;
}

.issues-table {
  margin-bottom: 32px;
}

.table-header {
  display: grid;
  grid-template-columns: 64px 70px 1fr 120px 90px 100px;
  padding: 10px 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  border-bottom: 2px solid var(--border);
}

.table-row {
  display: grid;
  grid-template-columns: 64px 70px 1fr 120px 90px 100px;
  padding: 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s ease;
  align-items: center;
  text-decoration: none;
  color: inherit;
}

.table-row:nth-child(even) {
  background: var(--bg-card);
}

.table-row:hover {
  background: var(--bg-hover);
}

.table-row .cell-number {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.table-row .cell-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 12px;
}

.table-row .cell-confidence {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.table-row .cell-flag {
  font-size: 12px;
  color: var(--text-muted);
}

.filter-bar {
  background: rgba(99, 102, 241, 0.15);
  padding: 8px 16px;
  border-radius: 8px;
  display: none;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.clear-btn {
  background: rgba(99, 102, 241, 0.3);
  border: none;
  color: var(--text-primary);
  padding: 4px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  transition: background 0.15s ease;
}

.clear-btn:hover {
  background: rgba(99, 102, 241, 0.5);
}

.cluster-card {
  background: var(--bg-card);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
}

.cluster-card .cluster-area {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: 4px;
  color: var(--text-primary);
}

.cluster-card .cluster-reason {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 10px;
  font-style: italic;
}

.cluster-card .cluster-issue {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.cluster-card .cluster-issue a {
  color: var(--accent);
  text-decoration: none;
}

.cluster-card .cluster-issue a:hover {
  text-decoration: underline;
}

.no-team-compact {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 24px;
}

.no-team-compact h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-primary);
}

.no-team-item {
  display: block;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-decoration: none;
  color: inherit;
  transition: background 0.15s ease;
  border-radius: 6px;
}

.no-team-item:last-child {
  border-bottom: none;
}

.no-team-item:hover {
  background: var(--bg-hover);
}

.no-team-item .nt-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.no-team-item .nt-number {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.no-team-item .nt-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.no-team-item .nt-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-top: 2px;
  padding-left: 18px;
}

.no-team-item .nt-summary {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
  padding-left: 18px;
}

.full-width {
  grid-column: 1 / -1;
}

.urgency-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.flag-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  background: rgba(234, 179, 8, 0.15);
  color: #EAB308;
  white-space: nowrap;
}

.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.chart-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.chart-legend-item .legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.chart-legend-item .legend-count {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.footer {
  text-align: center;
  color: var(--text-muted);
  margin-top: 48px;
  padding: 24px 0;
  font-size: 12px;
  border-top: 1px solid var(--border);
}

/* Responsive */
@media (max-width: 768px) {
  .kpi-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .kpi-grid .kpi-card:nth-child(4),
  .kpi-grid .kpi-card:nth-child(5) {
    grid-column: auto;
  }
  .two-column {
    grid-template-columns: 1fr;
  }
  .table-header,
  .table-row {
    grid-template-columns: 50px 60px 1fr 90px 70px 80px;
    font-size: 12px;
    padding: 8px;
  }
  .header {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 480px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }
  .dashboard {
    padding: 16px;
  }
  .header h1 {
    font-size: 22px;
  }
  .table-header,
  .table-row {
    grid-template-columns: 40px 50px 1fr 80px;
  }
  .table-header .hide-mobile,
  .table-row .hide-mobile {
    display: none;
  }
}
</style>
</head>
<body>
<div class="dashboard" id="app"></div>

<script>
const REPORT_DATA = __REPORT_JSON__;
</script>
<script>
(function() {
  "use strict";

  var TEAM_COLORS = {
    "agent-ops": "#6366F1",
    "acp": "#8B5CF6",
    "ai-safety": "#EC4899",
    "kata": "#14B8A6",
    "agentdev": "#F97316",
    "dashboard": "#06B6D4",
    "none": "#64748B"
  };

  var URGENCY_COLORS = {
    "critical": "#EF4444",
    "high": "#F97316",
    "medium": "#EAB308",
    "low": "#22C55E"
  };

  var URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3};

  function getTeamColor(team) {
    return TEAM_COLORS[team] || "#64748B";
  }

  function getUrgencyColor(urgency) {
    return URGENCY_COLORS[urgency] || "#64748B";
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  function confidenceLabel(conf) {
    var pct = Math.round(conf * 100);
    return pct + "%";
  }

  function formatDate(iso) {
    var dt = new Date(iso);
    var months = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"];
    return months[dt.getUTCMonth()] + " " + dt.getUTCDate() +
      ", " + dt.getUTCFullYear();
  }

  function humanizeFlag(flag) {
    if (!flag) return "";
    return flag.replace(/_/g, " ").replace(/\\b\\w/g, function(c) {
      return c.toUpperCase();
    });
  }

  var URGENCY_SHORT = {
    "critical": "CRIT", "high": "HIGH", "medium": "MED", "low": "LOW"
  };

  function makeEl(tag, className, innerHTML) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (innerHTML) el.innerHTML = innerHTML;
    return el;
  }

  function makeDot(urgency) {
    var dot = makeEl("span", "urgency-dot");
    dot.style.backgroundColor = getUrgencyColor(urgency);
    return dot;
  }

  function makeTeamBadge(team) {
    var badge = makeEl("span", "team-badge");
    var color = getTeamColor(team);
    badge.style.backgroundColor = color + "20";
    badge.style.color = color;
    badge.textContent = team === "none" ? "unassigned" : team;
    return badge;
  }

  function makeUrgencyBadge(urgency) {
    var badge = makeEl("span", "urgency-badge");
    var color = getUrgencyColor(urgency);
    badge.style.backgroundColor = color + "20";
    badge.style.color = color;
    badge.textContent = URGENCY_SHORT[urgency] || urgency;
    return badge;
  }

  document.addEventListener("DOMContentLoaded", function() {
    var d = REPORT_DATA;
    var app = document.getElementById("app");

    // --- Header ---
    var header = makeEl("div", "header");
    var headerLeft = makeEl("div");
    headerLeft.appendChild(makeEl("h1", null, escapeHtml("OpenShell Triage Overview")));
    headerLeft.appendChild(makeEl("span", "period",
      escapeHtml(d.summary.period_label)));
    header.appendChild(headerLeft);
    header.appendChild(makeEl("span", "generated-at",
      "Generated " + formatDate(d.generated_at)));
    app.appendChild(header);

    // --- KPI cards ---
    var kpiGrid = makeEl("div", "kpi-grid");
    var kpis = [
      {key: "total", label: "New This Period", value: d.summary.new_this_period,
        color: "var(--accent)"},
      {key: "critical", label: "Critical", value: d.summary.by_urgency.critical || 0,
        color: "var(--urgency-critical)"},
      {key: "high", label: "High", value: d.summary.by_urgency.high || 0,
        color: "var(--urgency-high)"},
      {key: "medium", label: "Medium", value: d.summary.by_urgency.medium || 0,
        color: "var(--urgency-medium)"},
      {key: "low", label: "Low", value: d.summary.by_urgency.low || 0,
        color: "var(--urgency-low)"}
    ];

    kpis.forEach(function(kpi) {
      var card = makeEl("div", "kpi-card");
      card.style.borderLeftColor = kpi.color;
      if ((kpi.key === "critical" || kpi.key === "high") && kpi.value > 0) {
        card.classList.add("pulse");
      }
      card.appendChild(makeEl("div", "kpi-number", String(kpi.value)));
      card.appendChild(makeEl("div", "kpi-label", escapeHtml(kpi.label)));
      kpiGrid.appendChild(card);
    });
    app.appendChild(kpiGrid);

    // --- Narrative ---
    if (d.narrative) {
      var narrative = makeEl("blockquote", "narrative");
      narrative.appendChild(document.createTextNode(d.narrative));
      var attr = makeEl("span", "attribution", "AI-generated summary");
      narrative.appendChild(attr);
      app.appendChild(narrative);
    }

    // --- Critical/high issues ---
    if (d._labels.critical) {
      app.appendChild(makeEl("h2", "section-heading",
        escapeHtml(d._labels.critical) + ' <span class="count">(' +
        d.critical_list.length + ')</span>'));

      d.critical_list.forEach(function(issue) {
        var link = document.createElement("a");
        link.className = "issue-card";
        link.href = issue.issue_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.style.borderLeftColor = getUrgencyColor(issue.urgency);

        var headerDiv = makeEl("div", "issue-header");
        headerDiv.appendChild(makeDot(issue.urgency));
        headerDiv.appendChild(makeEl("span", "issue-number",
          "#" + issue.issue_number));
        headerDiv.appendChild(makeEl("span", "issue-title",
          escapeHtml(issue.issue_title)));
        link.appendChild(headerDiv);

        var meta = makeEl("div", "issue-meta");
        meta.appendChild(makeTeamBadge(issue.primary_team));
        meta.appendChild(document.createTextNode(
          confidenceLabel(issue.primary_confidence) + " confidence"));
        link.appendChild(meta);

        if (issue.summary) {
          link.appendChild(makeEl("div", "issue-summary",
            escapeHtml(issue.summary)));
        }

        if (issue.secondary_team) {
          var secConf = issue.secondary_confidence
            ? " (" + confidenceLabel(issue.secondary_confidence) + ")"
            : "";
          link.appendChild(makeEl("div", "secondary-tag",
            "also: " + escapeHtml(issue.secondary_team) + secConf));
        }

        app.appendChild(link);
      });
    }

    // --- Team Breakdown: chart + needs triage ---
    var twoCol = makeEl("div", "two-column");

    var chartBox = makeEl("div", "chart-container");
    chartBox.appendChild(makeEl("h3", null, "Team Breakdown"));
    var canvas = document.createElement("canvas");
    canvas.id = "teamChart";
    chartBox.appendChild(canvas);
    twoCol.appendChild(chartBox);

    if (d._labels.no_team) {
      var noTeamBox = makeEl("div", "no-team-compact");
      noTeamBox.appendChild(makeEl("h3", null,
        escapeHtml(d._labels.no_team) + ' <span class="count">(' +
        d.no_team_list.length + ')</span>'));

      d.no_team_list.forEach(function(issue) {
        var item = document.createElement("a");
        item.className = "no-team-item";
        item.href = issue.issue_url;
        item.target = "_blank";
        item.rel = "noopener noreferrer";

        var hdr = makeEl("div", "nt-header");
        hdr.appendChild(makeDot(issue.urgency));
        hdr.appendChild(makeEl("span", "nt-number",
          "#" + issue.issue_number));
        hdr.appendChild(makeEl("span", "nt-title",
          escapeHtml(issue.issue_title)));
        item.appendChild(hdr);

        var meta = makeEl("div", "nt-meta");
        meta.appendChild(makeTeamBadge("none"));
        item.appendChild(meta);

        if (issue.summary) {
          item.appendChild(makeEl("div", "nt-summary",
            escapeHtml(issue.summary)));
        }

        noTeamBox.appendChild(item);
      });

      twoCol.appendChild(noTeamBox);
    } else {
      chartBox.classList.add("full-width");
    }

    app.appendChild(twoCol);

    // --- Doughnut chart ---
    var teamLabels = Object.keys(d.team_breakdown);
    var teamCounts = teamLabels.map(function(t) {
      return d.team_breakdown[t].total;
    });
    var teamColors = teamLabels.map(function(t) {
      return getTeamColor(t);
    });

    var activeFilter = null;

    var ctx = document.getElementById("teamChart").getContext("2d");
    new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: teamLabels,
        datasets: [{
          data: teamCounts,
          backgroundColor: teamColors,
          borderWidth: 2,
          borderColor: "#1E293B",
          hoverBorderColor: "#F1F5F9",
          hoverBorderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        cutout: "60%",
        plugins: {
          legend: {display: false},
          tooltip: {
            backgroundColor: "#1E293B",
            titleColor: "#F1F5F9",
            bodyColor: "#94A3B8",
            borderColor: "#334155",
            borderWidth: 1,
            cornerRadius: 8,
            padding: 12,
            titleFont: {family: "'Inter', sans-serif", weight: "600"},
            bodyFont: {family: "'Inter', sans-serif"},
            callbacks: {
              label: function(context) {
                var total = context.dataset.data.reduce(function(a, b) {
                  return a + b;
                }, 0);
                var pct = total > 0
                  ? Math.round(context.raw / total * 100) : 0;
                return " " + context.raw + " issues (" + pct + "%)";
              }
            }
          },
          datalabels: {
            color: "#F1F5F9",
            font: {size: 11, weight: "bold", family: "'Inter', sans-serif"},
            formatter: function(value, context) {
              if (value === 0) return "";
              var total = context.dataset.data.reduce(function(a, b) {
                return a + b;
              }, 0);
              var pct = total > 0 ? Math.round(value / total * 100) : 0;
              if (pct < 8) return "";
              return context.chart.data.labels[context.dataIndex] +
                "\\n" + value;
            },
            textAlign: "center"
          }
        },
        onClick: function(evt, elements) {
          if (elements.length > 0) {
            var idx = elements[0].index;
            var team = teamLabels[idx];
            if (activeFilter === team) {
              activeFilter = null;
            } else {
              activeFilter = team;
            }
            filterIssues(activeFilter);
          }
        }
      },
      plugins: [ChartDataLabels]
    });

    // --- Chart legend ---
    var legend = makeEl("div", "chart-legend");
    teamLabels.forEach(function(team, i) {
      var item = makeEl("div", "chart-legend-item");
      var dot = makeEl("span", "legend-dot");
      dot.style.backgroundColor = teamColors[i];
      item.appendChild(dot);
      item.appendChild(document.createTextNode(
        team === "none" ? "unassigned" : team));
      item.appendChild(makeEl("span", "legend-count",
        "(" + teamCounts[i] + ")"));
      legend.appendChild(item);
    });
    chartBox.appendChild(legend);

    // --- Duplicate clusters ---
    if (d._labels.duplicates) {
      app.appendChild(makeEl("h2", "section-heading",
        escapeHtml(d._labels.duplicates) + ' <span class="count">(' +
        d.duplicate_clusters.length + ')</span>'));

      d.duplicate_clusters.forEach(function(cluster) {
        var card = makeEl("div", "cluster-card");
        card.appendChild(makeEl("div", "cluster-area",
          escapeHtml(cluster.area)));
        card.appendChild(makeEl("div", "cluster-reason",
          escapeHtml(cluster.similarity_reason)));

        cluster.issues.forEach(function(issue) {
          var row = makeEl("div", "cluster-issue");
          row.appendChild(makeDot(issue.urgency));
          var a = document.createElement("a");
          a.href = issue.issue_url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = "#" + issue.issue_number + " " +
            issue.issue_title;
          row.appendChild(a);
          card.appendChild(row);
        });

        app.appendChild(card);
      });
    }

    // --- All Issues table ---
    var allIssues = d.all_issues || [];
    allIssues.sort(function(a, b) {
      var ua = URGENCY_ORDER[a.urgency] !== undefined
        ? URGENCY_ORDER[a.urgency] : 9;
      var ub = URGENCY_ORDER[b.urgency] !== undefined
        ? URGENCY_ORDER[b.urgency] : 9;
      if (ua !== ub) return ua - ub;
      return a.issue_number - b.issue_number;
    });

    app.appendChild(makeEl("h2", "section-heading",
      'All Issues <span class="count">(' +
      allIssues.length + ')</span>'));

    var filterBar = makeEl("div", "filter-bar");
    filterBar.id = "filterBar";
    app.appendChild(filterBar);

    var table = makeEl("div", "issues-table");

    var headerRow = makeEl("div", "table-header");
    headerRow.innerHTML =
      '<span>Urg.</span>' +
      '<span>#</span>' +
      '<span>Title</span>' +
      '<span>Team</span>' +
      '<span class="hide-mobile">Conf.</span>' +
      '<span class="hide-mobile">Flag</span>';
    table.appendChild(headerRow);

    allIssues.forEach(function(issue) {
      var row = document.createElement("a");
      row.className = "table-row";
      row.href = issue.issue_url;
      row.target = "_blank";
      row.rel = "noopener noreferrer";
      row.dataset.team = issue.primary_team;

      var badgeCell = makeEl("span");
      badgeCell.appendChild(makeUrgencyBadge(issue.urgency));
      row.appendChild(badgeCell);

      row.appendChild(makeEl("span", "cell-number",
        "#" + issue.issue_number));
      row.appendChild(makeEl("span", "cell-title",
        escapeHtml(issue.issue_title)));

      var teamCell = makeEl("span");
      teamCell.appendChild(makeTeamBadge(issue.primary_team));
      row.appendChild(teamCell);

      row.appendChild(makeEl("span", "cell-confidence hide-mobile",
        confidenceLabel(issue.primary_confidence)));

      var flagCell = makeEl("span", "hide-mobile");
      if (issue.confidence_flag) {
        flagCell.appendChild(makeEl("span", "flag-badge",
          escapeHtml(humanizeFlag(issue.confidence_flag))));
      }
      row.appendChild(flagCell);

      table.appendChild(row);
    });

    app.appendChild(table);

    // --- Filter logic ---
    function filterIssues(team) {
      var rows = document.querySelectorAll(".table-row");
      var bar = document.getElementById("filterBar");

      rows.forEach(function(row) {
        if (!team || row.dataset.team === team) {
          row.style.display = "";
        } else {
          row.style.display = "none";
        }
      });

      if (team) {
        var visibleCount = document.querySelectorAll(
          '.table-row[data-team="' + team + '"]').length;
        bar.innerHTML = "";
        bar.style.display = "flex";
        bar.appendChild(document.createTextNode(
          "Showing: " + team + " (" + visibleCount + " issues)"));
        var clearBtn = makeEl("button", "clear-btn", "Clear");
        clearBtn.onclick = function() {
          activeFilter = null;
          filterIssues(null);
        };
        bar.appendChild(clearBtn);
      } else {
        bar.style.display = "none";
      }
    }

    // --- Footer ---
    app.appendChild(makeEl("div", "footer",
      "OpenShell Triage Dashboard &middot; Generated " +
      formatDate(d.generated_at)));
  });
})();
</script>
</body>
</html>
"""
