var _lastStuckPRs = null, _lastStuckTotal = null, _lastNeglectDays = null;
var _prSortCol = "days_open", _prSortDir = -1;

function _sortPRs(prs) {
  if (!_prSortCol) return prs.slice();
  return prs.slice().sort(function(a, b) {
    var va = a[_prSortCol], vb = b[_prSortCol];
    if (va < vb) return -_prSortDir;
    if (va > vb) return _prSortDir;
    return 0;
  });
}

function _updatePRSortHeaders() {
  var thead = document.querySelector("#pr-health .data-table thead");
  if (!thead) return;
  thead.querySelectorAll("th[data-sort]").forEach(function(th) {
    var col = th.dataset.sort;
    var base = col === "number" ? "PR #" : col === "days_open" ? "Age" : "Author";
    th.textContent = (_prSortCol === col) ? base + (_prSortDir === 1 ? " ↑" : " ↓") : base;
  });
}

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

var _prAgeColors = ["#1a7f37", "#d4a015", "#e16f24", "#d1242f"];
var _prAgeKeys = ["lt_1w", "1_2w", "2_4w", "gt_1m"];

function _renderPRHealthTiles(totalOpen, awaitingReview, staleCount, staleDays) {
  var tiles = document.querySelectorAll("#pr-health .metric-tile");
  if (tiles.length >= 3) {
    tiles[0].querySelector(".tile-value").textContent = totalOpen;
    tiles[1].querySelector(".tile-value").textContent = awaitingReview;
    if (staleDays === null) {
      tiles[2].style.display = "none";
    } else {
      tiles[2].style.display = "";
      tiles[2].querySelector(".tile-value").textContent = staleCount;
      var staleLabel = tiles[2].querySelector(".tile-label");
      if (staleLabel && staleDays) staleLabel.innerHTML = esc("Stale (" + staleDays + "d+)") + hintHTML("No updates for " + staleDays + "+ days");
    }
  }
}

function _renderAgeDistribution(buckets) {
  var wrap = document.getElementById("pr-age-dist");
  if (!wrap) return;
  if (!buckets) { wrap.style.display = "none"; return; }
  wrap.style.display = "";

  var keys = Object.keys(buckets);
  var ageTotal = 0;
  keys.forEach(function(key) { ageTotal += buckets[key].count; });
  var barHtml = '<div class="stacked-bar">';
  if (ageTotal > 0) {
    keys.forEach(function(key, i) {
      var seg = buckets[key];
      var pct = (seg.count / ageTotal * 100).toFixed(1);
      barHtml += '<div class="bar-seg" style="width:' + pct + '%;background:' + _prAgeColors[i] + ';"><span>' + seg.count + '</span></div>';
    });
  }
  barHtml += '</div>';
  var legendHtml = '<div class="stacked-bar-legend">';
  keys.forEach(function(key, i) {
    legendHtml += '<span class="legend-item"><span class="legend-dot" style="background:' + _prAgeColors[i] + ';"></span>' + buckets[key].label + ' (' + buckets[key].count + ')</span>';
  });
  legendHtml += '</div>';
  wrap.innerHTML = '<div class="stacked-bar-label">PR Age Distribution</div>' + barHtml + legendHtml;
}

function _buildStuckPRRow(pr) {
  var participantLinks = (pr.participants || []).map(function(p) {
    return '<a href="https://github.com/' + esc(p) + '" target="_blank">@' + esc(p) + '</a>';
  }).join(', ') || '<span style="color:var(--status-blocked);font-weight:500;">No engagement</span>';
  var daysOpen = pr.days_open || 0;
  var activityText = pr.last_activity || (daysOpen + 'd');
  var assoc = pr.author_association || "NONE";
  var isMaintainer = assoc === "COLLABORATOR" || assoc === "MEMBER" || assoc === "OWNER";
  var roleBadge = isMaintainer ? ' <span class="author-role maintainer">maintainer</span>' : '';
  var pingedBadge = pr.author_pinged ? ' <span class="author-role pinged">awaiting response ' + pr.author_pinged_days + 'd</span>' : '';
  var tr = el("tr");
  tr.innerHTML = '<td><a href="' + esc(pr.url) + '" target="_blank">#' + pr.number + '</a></td>' +
    '<td><a href="' + esc(pr.url) + '" target="_blank">' + esc(pr.title) + '</a></td>' +
    '<td><a href="https://github.com/' + esc(pr.author) + '" target="_blank">@' + esc(pr.author) + '</a>' + roleBadge + '</td>' +
    '<td style="font-weight:600;color:var(--urgency-high);">' + daysOpen + 'd</td>' +
    '<td style="font-size:12px;color:var(--text-muted);">' + esc(activityText) + (pingedBadge ? '<br>' + pingedBadge : '') + '</td>' +
    '<td style="font-size:13px;">' + participantLinks + '</td>';
  return tr;
}

function _renderStuckPRs(stuckPrs, totalCount, neglectDays) {
  _lastStuckPRs = stuckPrs;
  _lastStuckTotal = totalCount;
  _lastNeglectDays = neglectDays;

  var tbody = document.getElementById("pr-stuck-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  var moreWrap = document.getElementById("pr-stuck-more");
  if (moreWrap) moreWrap.innerHTML = "";

  var nd = neglectDays || 7;
  var titleEl = document.getElementById("neglected-title");
  if (titleEl) {
    var countText = totalCount ? ' <span style="color:var(--text-dim);font-weight:400;">(' + totalCount + ' total)</span>' : '';
    titleEl.innerHTML = 'Neglected PRs' + countText + ' <span style="color:var(--text-dim);font-weight:400;">- no human review or comment for ' + nd + '+ days</span>';
  }

  if (stuckPrs.length === 0) {
    var tr = el("tr");
    tr.innerHTML = '<td colspan="6" style="text-align:center;color:var(--text-muted);padding:20px;">No neglected PRs in this time range</td>';
    tbody.appendChild(tr);
    _updatePRSortHeaders();
    return;
  }
  var sorted = _sortPRs(stuckPrs);
  var STUCK_VISIBLE = 5;
  sorted.forEach(function(pr, i) {
    var row = _buildStuckPRRow(pr);
    if (i >= STUCK_VISIBLE) row.classList.add("stuck-hidden");
    tbody.appendChild(row);
  });
  if (sorted.length > STUCK_VISIBLE && moreWrap) {
    var expanded = false;
    var remaining = sorted.length - STUCK_VISIBLE;
    var toggleBtn = el("button", "show-more-btn");
    toggleBtn.textContent = "Show " + remaining + " more";
    toggleBtn.addEventListener("click", function() {
      expanded = !expanded;
      tbody.querySelectorAll(".stuck-hidden").forEach(function(r) {
        r.style.display = expanded ? "table-row" : "none";
      });
      toggleBtn.textContent = expanded ? "Show less" : "Show " + remaining + " more";
    });
    moreWrap.appendChild(toggleBtn);
  }
  _updatePRSortHeaders();
}


function buildPRHealth() {
  var section = el("div", "section");
  section.id = "pr-health";

  var header = el("details", "section-collapse");
  header.open = state.collapsed["pr-health"] !== false;
  var summary = el("summary");
  summary.innerHTML = '<div class="section-title">PR Health</div>';
  header.appendChild(summary);

  var tiles = el("div", "metric-tiles metric-tiles-3");
  var tileData = [
    {value: d.pr_health.total_open, label: "Open PRs", color: "var(--text-primary)", accent: "var(--border)", filterKey: "all"},
    {value: d.pr_health.awaiting_review, label: "Awaiting Review", color: "var(--status-waiting)", accent: "var(--status-waiting)", filterKey: "awaiting"},
    {value: d.pr_health.stale_14d, label: "Stale (14d+)", color: "var(--urgency-high)", accent: "var(--urgency-high)", hint: "No updates for 14+ days (adjusted by time filter)", filterKey: "stale"}
  ];
  var _tileEls = [];
  tileData.forEach(function(t) {
    var tile = el("div", "metric-tile");
    tile.style.borderLeftColor = t.accent;
    tile.style.cursor = "pointer";
    tile.dataset.filterKey = t.filterKey;
    tile.innerHTML = '<div class="tile-value" style="color:' + t.color + '">' + t.value + '</div><div class="tile-label">' + esc(t.label) + (t.hint ? hintHTML(t.hint) : '') + '</div>';
    tile.addEventListener("click", function() {
      _prTileFilter = (_prTileFilter === t.filterKey) ? null : t.filterKey;
      _tileEls.forEach(function(te) {
        te.style.outline = (_prTileFilter && te.dataset.filterKey === _prTileFilter) ? "2px solid " + t.accent : "";
      });
      filterPRHealth();
    });
    _tileEls.push(tile);
    tiles.appendChild(tile);
  });
  header.appendChild(tiles);

  var ageWrap = el("div", "stacked-bar-wrap");
  ageWrap.id = "pr-age-dist";
  var ageDist = d.pr_health.age_distribution;
  var ageTotal = ageDist.lt_1w.count + ageDist["1_2w"].count + ageDist["2_4w"].count + ageDist.gt_1m.count;
  ageWrap.innerHTML = '<div class="stacked-bar-label">PR Age Distribution</div>';
  var barHtml = '<div class="stacked-bar">';
  if (ageTotal > 0) {
    _prAgeKeys.forEach(function(key, i) {
      var seg = ageDist[key];
      var pct = (seg.count / ageTotal * 100).toFixed(1);
      barHtml += '<div class="bar-seg" style="width:' + pct + '%;background:' + _prAgeColors[i] + ';"><span>' + seg.count + '</span></div>';
    });
  }
  barHtml += '</div>';
  var legendHtml = '<div class="stacked-bar-legend">';
  _prAgeKeys.forEach(function(key, i) {
    legendHtml += '<span class="legend-item"><span class="legend-dot" style="background:' + _prAgeColors[i] + ';"></span>' + ageDist[key].label + ' (' + ageDist[key].count + ')</span>';
  });
  legendHtml += '</div>';
  ageWrap.innerHTML += barHtml + legendHtml;
  header.appendChild(ageWrap);

  var stuckTitle = el("div", "stacked-bar-label");
  stuckTitle.id = "neglected-title";
  stuckTitle.innerHTML = 'Neglected PRs <span style="color:var(--text-dim);font-weight:400;">- no human review or comment for 7+ days</span>';
  header.appendChild(stuckTitle);

  var tableWrap = el("div", "data-table-wrap");
  var table = el("table", "data-table");
  table.innerHTML = '<thead><tr><th data-sort="number" style="cursor:pointer;user-select:none;">PR #</th><th>Title</th><th data-sort="author" style="cursor:pointer;user-select:none;">Author</th><th data-sort="days_open" style="cursor:pointer;user-select:none;">Age ↓</th><th>Last Activity</th><th>Participants</th></tr></thead>';
  table.querySelectorAll("th[data-sort]").forEach(function(th) {
    th.addEventListener("click", function() {
      var col = th.dataset.sort;
      if (_prSortCol === col) {
        _prSortDir = -_prSortDir;
      } else {
        _prSortCol = col;
        _prSortDir = -1;
      }
      if (_lastStuckPRs) _renderStuckPRs(_lastStuckPRs, _lastStuckTotal, _lastNeglectDays);
    });
  });
  var tbody = el("tbody");
  tbody.id = "pr-stuck-tbody";
  table.appendChild(tbody);
  tableWrap.appendChild(table);
  header.appendChild(tableWrap);

  var stuckMoreWrap = el("div");
  stuckMoreWrap.id = "pr-stuck-more";
  header.appendChild(stuckMoreWrap);

  var owners = (d.pr_health.codeowners || []).join(", ") || "CODEOWNERS";
  header.appendChild(el("p", "muted-note", "CODEOWNERS auto-assigns " + owners + " to every PR. Participants shown above are people who actually engaged (commented or reviewed)."));

  header.addEventListener("toggle", function() { state.collapsed["pr-health"] = header.open; saveState(state); });
  section.appendChild(header);
  return section;
}
