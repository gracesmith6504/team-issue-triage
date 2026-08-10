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
    {value: d.pr_health.avg_review_wait_days + "d", label: "Avg Review Wait", color: "var(--status-waiting)", accent: "var(--status-waiting)"}
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
  table.innerHTML = '<thead><tr><th>#</th><th>Title</th><th>Author</th><th>Age</th><th>Last Activity</th><th>Gator</th><th>Participants</th></tr></thead>';
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
      '<td>' + gatorBadge(pr.gator_label) + '</td>' +
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
