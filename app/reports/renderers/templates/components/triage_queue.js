var _tqFilterHigh = false;
var _tqSortKey = "default"; // "default" | "age_asc" | "age_desc" | "team_asc" | "team_desc"
var _TQ_URGENCY_SCORE = {critical: 3, high: 2, medium: 1, low: 0};
var _TQ_VISIBLE = 5;

function _isTriage(iss) {
  return (iss.labels || []).indexOf("state:triage-needed") !== -1;
}

function _sortTQ(issues) {
  return issues.slice().sort(function(a, b) {
    if (_tqSortKey === "age_desc") return (b.days_open || 0) - (a.days_open || 0);
    if (_tqSortKey === "age_asc")  return (a.days_open || 0) - (b.days_open || 0);
    if (_tqSortKey === "team_asc") return (a.primary_team || "").localeCompare(b.primary_team || "");
    if (_tqSortKey === "team_desc") return (b.primary_team || "").localeCompare(a.primary_team || "");
    var va = _TQ_URGENCY_SCORE[a.urgency] !== undefined ? _TQ_URGENCY_SCORE[a.urgency] : -1;
    var vb = _TQ_URGENCY_SCORE[b.urgency] !== undefined ? _TQ_URGENCY_SCORE[b.urgency] : -1;
    if (va !== vb) return vb - va;
    return (b.days_open || 0) - (a.days_open || 0);
  });
}

function _updateTQHeaders() {
  var thead = document.querySelector("#triage-queue .data-table thead");
  if (!thead) return;
  var thU = thead.querySelector("th[data-filter='urgency']");
  var thA = thead.querySelector("th[data-sort='age']");
  var thT = thead.querySelector("th[data-sort='team']");
  if (thU) thU.style.color = _tqFilterHigh ? "var(--accent)" : "";
  if (thA) {
    var ageActive = _tqSortKey === "age_asc" || _tqSortKey === "age_desc";
    thA.style.color = ageActive ? "var(--accent)" : "";
    thA.textContent = "Age" + (_tqSortKey === "age_asc" ? " ↑" : _tqSortKey === "age_desc" ? " ↓" : "");
  }
  if (thT) {
    var teamActive = _tqSortKey === "team_asc" || _tqSortKey === "team_desc";
    thT.style.color = teamActive ? "var(--accent)" : "";
    thT.textContent = "Team" + (_tqSortKey === "team_asc" ? " ↑" : _tqSortKey === "team_desc" ? " ↓" : "");
  }
}

function _tqSnippet(text) {
  if (!text) return "";
  var dot = text.indexOf(".");
  if (dot > 0 && dot < 120) return text.substring(0, dot + 1);
  return text.length > 100 ? text.substring(0, 100) + "…" : text;
}

function _renderTQRows(triageIssues) {
  var tbody = document.getElementById("triage-queue-tbody");
  var moreWrap = document.getElementById("triage-queue-more");
  var emptyEl = document.getElementById("triage-queue-empty");
  var titleSpan = document.querySelector("#triage-queue .count");
  if (!tbody) return;

  tbody.innerHTML = "";
  if (moreWrap) moreWrap.innerHTML = "";
  if (titleSpan) titleSpan.textContent = "(" + triageIssues.length + " issues)";

  if (triageIssues.length === 0) {
    if (emptyEl) { emptyEl.style.display = ""; emptyEl.textContent = "No issues match the current filter."; }
    _updateTQHeaders();
    return;
  }
  if (emptyEl) emptyEl.style.display = "none";

  var sorted = _sortTQ(triageIssues);
  sorted.forEach(function(iss, i) {
    var tr = document.createElement("tr");
    if (i >= _TQ_VISIBLE) { tr.classList.add("tq-hidden"); tr.style.display = "none"; }
    tr.innerHTML =
      '<td>' + makeUrgencyBadgeHTML(iss.urgency) + '</td>' +
      '<td><a href="' + esc(iss.issue_url || iss.url || "") + '" target="_blank">#' + (iss.issue_number || iss.number) + '</a></td>' +
      '<td style="max-width:260px">' + esc(iss.issue_title || iss.title || "") + '</td>' +
      '<td>' + makeTeamBadgeHTML(iss.primary_team || "none") + '</td>' +
      '<td>' + (iss.days_open || 0) + 'd</td>' +
      '<td style="max-width:280px;color:var(--text-dim);font-size:12px">' + esc(_tqSnippet(iss.summary)) + '</td>';
    tbody.appendChild(tr);
  });

  _updateTQHeaders();

  var hiddenCount = sorted.length - _TQ_VISIBLE;
  if (hiddenCount > 0 && moreWrap) {
    var link = el("a");
    link.textContent = "View " + hiddenCount + " more";
    link.style.cssText = "color:var(--accent);cursor:pointer;text-decoration:none;font-size:13px;font-weight:500;display:inline-block;margin-top:8px;";
    link.addEventListener("click", function() {
      var isExpanded = link.dataset.expanded !== "true";
      link.dataset.expanded = isExpanded ? "true" : "false";
      tbody.querySelectorAll(".tq-hidden").forEach(function(r) {
        r.style.display = isExpanded ? "" : "none";
      });
      link.textContent = isExpanded ? "Show less" : "View " + hiddenCount + " more";
    });
    moreWrap.appendChild(link);
  }
}

function filterTriageQueue(filtered) {
  var triageIssues = filtered.filter(_isTriage);
  if (_tqFilterHigh) triageIssues = triageIssues.filter(function(iss) { return iss.urgency === "critical" || iss.urgency === "high"; });
  _renderTQRows(triageIssues);
}

function buildTriageQueue() {
  var section = el("div", "section");
  section.id = "triage-queue";

  var wrap = el("details", "section-collapse");
  wrap.open = state.collapsed["triage-queue"] !== false;

  var summary = el("summary");
  summary.innerHTML = '<div class="section-title">Triage Queue <span class="count">(...)</span></div>';
  wrap.appendChild(summary);

  var table = document.createElement("table");
  table.className = "data-table";
  table.innerHTML =
    '<thead><tr>' +
    '<th data-filter="urgency" style="cursor:pointer;user-select:none;width:90px">Urgency</th>' +
    '<th style="width:60px">#</th>' +
    '<th>Title</th>' +
    '<th data-sort="team" style="cursor:pointer;user-select:none;width:110px">Team</th>' +
    '<th data-sort="age" style="cursor:pointer;user-select:none;width:60px">Age</th>' +
    '<th>Summary</th>' +
    '</tr></thead>' +
    '<tbody id="triage-queue-tbody"></tbody>';

  table.querySelector("th[data-filter='urgency']").addEventListener("click", function() {
    _tqFilterHigh = !_tqFilterHigh;
    filterTriageQueue(getFilteredIssues());
  });
  table.querySelector("th[data-sort='age']").addEventListener("click", function() {
    _tqSortKey = _tqSortKey === "age_desc" ? "age_asc" : "age_desc";
    filterTriageQueue(getFilteredIssues());
  });
  table.querySelector("th[data-sort='team']").addEventListener("click", function() {
    _tqSortKey = _tqSortKey === "team_asc" ? "team_desc" : "team_asc";
    filterTriageQueue(getFilteredIssues());
  });

  wrap.appendChild(table);

  var emptyEl = el("div");
  emptyEl.id = "triage-queue-empty";
  emptyEl.style.cssText = "text-align:center;color:var(--text-muted);padding:20px;display:none;";
  wrap.appendChild(emptyEl);

  var moreWrap = el("div");
  moreWrap.id = "triage-queue-more";
  moreWrap.style.padding = "0 0 8px 0";
  wrap.appendChild(moreWrap);

  wrap.addEventListener("toggle", function() {
    state.collapsed["triage-queue"] = wrap.open;
    saveState(state);
  });

  section.appendChild(wrap);
  return section;
}
