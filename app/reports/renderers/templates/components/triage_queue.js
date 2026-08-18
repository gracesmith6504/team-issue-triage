var _tqSortCol = "urgency";
var _tqSortDir = -1;
var _TQ_URGENCY_SCORE = {critical: 3, high: 2, medium: 1, low: 0};
var _TQ_VISIBLE = 10;

function _isTriage(iss) {
  return (iss.labels || []).indexOf("state:triage-needed") !== -1;
}

function _sortTQ(issues) {
  return issues.slice().sort(function(a, b) {
    var va, vb;
    if (_tqSortCol === "urgency") {
      va = _TQ_URGENCY_SCORE[a.urgency] !== undefined ? _TQ_URGENCY_SCORE[a.urgency] : -1;
      vb = _TQ_URGENCY_SCORE[b.urgency] !== undefined ? _TQ_URGENCY_SCORE[b.urgency] : -1;
    } else {
      va = a[_tqSortCol] !== undefined ? a[_tqSortCol] : 0;
      vb = b[_tqSortCol] !== undefined ? b[_tqSortCol] : 0;
    }
    if (va < vb) return -_tqSortDir;
    if (va > vb) return _tqSortDir;
    return 0;
  });
}

function _updateTQSortHeaders() {
  var thead = document.querySelector("#triage-queue .data-table thead");
  if (!thead) return;
  thead.querySelectorAll("th[data-sort]").forEach(function(th) {
    var col = th.dataset.sort;
    var base = col === "urgency" ? "Urgency" : "Age";
    th.textContent = (_tqSortCol === col) ? base + (_tqSortDir === -1 ? " ↓" : " ↑") : base;
  });
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
    if (emptyEl) {
      emptyEl.style.display = "";
      emptyEl.textContent = "No issues needing triage in this filter.";
    }
    _updateTQSortHeaders();
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

  _updateTQSortHeaders();

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
  _renderTQRows(filtered.filter(_isTriage));
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
    '<th data-sort="urgency" style="cursor:pointer;user-select:none;width:90px">Urgency ↓</th>' +
    '<th style="width:60px">#</th>' +
    '<th>Title</th>' +
    '<th style="width:110px">Team</th>' +
    '<th data-sort="days_open" style="cursor:pointer;user-select:none;width:60px">Age</th>' +
    '<th>Summary</th>' +
    '</tr></thead>' +
    '<tbody id="triage-queue-tbody"></tbody>';

  table.querySelectorAll("th[data-sort]").forEach(function(th) {
    th.addEventListener("click", function() {
      var col = th.dataset.sort;
      if (_tqSortCol === col) { _tqSortDir = -_tqSortDir; }
      else { _tqSortCol = col; _tqSortDir = -1; }
      filterTriageQueue(getFilteredIssues());
    });
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
