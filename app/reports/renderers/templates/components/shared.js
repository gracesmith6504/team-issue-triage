var TEAM_COLORS = {
  "agent-ops": "#6366F1", "acp": "#8B5CF6", "ai-safety": "#EC4899",
  "kata": "#14B8A6", "agentdev": "#F97316", "dashboard": "#06B6D4", "none": "#64748B"
};
var URGENCY_COLORS = {"critical": "#d1242f", "high": "#e16f24", "medium": "#d4a015", "low": "#1a7f37"};
var URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3};
var URGENCY_SHORT = {"critical": "CRIT", "high": "HIGH", "medium": "MED", "low": "LOW"};

function esc(t) { var d = document.createElement("div"); d.appendChild(document.createTextNode(t)); return d.innerHTML; }
function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; return e; }
function hintHTML(text) { return ' <span class="hint-wrap"><span class="hint-trigger">i</span><span class="hint-popup">' + esc(text) + '</span></span>'; }
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
state.dateRange = "All";
state.issueTypeFilter = "Any";

var d;

function getFilterCutoffMs() {
  if (!state.dateRange || state.dateRange === "All") return null;
  var hours = state.dateRange === "24h" ? 24 : state.dateRange === "7d" ? 168 : 720;
  return hours * 60 * 60 * 1000;
}

function _staleDaysThreshold() {
  if (!state.dateRange || state.dateRange === "All") return 14;
  if (state.dateRange === "24h") return null;
  if (state.dateRange === "7d") return 5;
  if (state.dateRange === "14d") return 7;
  return 14;
}

function isWithinFilter(isoDateStr) {
  var cutoffMs = getFilterCutoffMs();
  if (cutoffMs === null) return true;
  if (!isoDateStr) return true;
  return (new Date() - new Date(isoDateStr)) <= cutoffMs;
}
