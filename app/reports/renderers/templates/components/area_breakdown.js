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
