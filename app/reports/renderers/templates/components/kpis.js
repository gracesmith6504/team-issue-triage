function buildKPIs() {
  var grid = el("div", "kpi-grid");
  var kpis = [
    {value: d.summary.triage_needed, label: "Issues Needing Triage", hint: "Issues with the state:triage-needed label on GitHub", sub: d.summary.total_open + " total open issues", color: "var(--urgency-high)", spark: d.sparklines.triage, sparkColor: "#e16f24", target: "team-routing"}
  ];

  if (d.pr_health) {
    kpis.push({value: d.pr_health.awaiting_review, label: "PRs Waiting for Review", sub: d.pr_health.stale_14d + " stale (14d+)", color: "var(--status-waiting)", spark: d.sparklines.prs, sparkColor: "#d4a015", target: "pr-health"});
  }
  if (d.vouch_status) {
    kpis.push({value: d.vouch_status.total_pending, label: "Pending Vouches", sub: d.vouch_status.over_30d_count + " waiting over 30 days", color: "var(--status-blocked)", spark: d.sparklines.blocked, sparkColor: "#d1242f", target: "contributor-health"});
  }
  if (d.pr_health) {
    kpis.push({value: d.pr_health.merge_velocity, label: "Merged This Week", sub: (d.pr_health.merge_velocity_prev || 0) + " last week", color: "var(--status-healthy)", spark: d.sparklines.velocity, sparkColor: "#1a7f37", target: "pr-velocity"});
  }

  grid.style.gridTemplateColumns = "repeat(" + kpis.length + ", 1fr)";

  kpis.forEach(function(k) {
    var card = el("div", "kpi-card");
    card.dataset.target = k.target;
    card.style.borderLeftColor = k.color;
    var hasVariation = k.spark && k.spark.some(function(v) { return v !== k.spark[0]; });
    card.innerHTML = '<div class="kpi-number">' + k.value + '</div>' +
      '<div class="kpi-label">' + esc(k.label) + (k.hint ? hintHTML(k.hint) : '') + '</div>' +
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
