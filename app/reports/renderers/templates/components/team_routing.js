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
    var urgencies = team.by_urgency || {};
    var total = team.total;
    var trend = team.trend || "0";

    // Calculate percentages for urgency bar chart
    var critCount = urgencies["critical"] || 0;
    var highCount = urgencies["high"] || 0;
    var medCount = urgencies["medium"] || 0;
    var lowCount = urgencies["low"] || 0;

    var critPct = total > 0 ? (critCount / total * 100) : 0;
    var highPct = total > 0 ? (highCount / total * 100) : 0;
    var medPct = total > 0 ? (medCount / total * 100) : 0;
    var lowPct = total > 0 ? (lowCount / total * 100) : 0;

    // Build urgency mix bar chart
    var tooltipText = critCount + ' critical · ' + highCount + ' high · ' +
                      medCount + ' medium · ' + lowCount + ' low';
    var mixHTML = '<span class="mix" title="' + esc(tooltipText) + '">';
    if (critPct > 0) mixHTML += '<i class="crit" style="width:' + critPct + '%"></i>';
    if (highPct > 0) mixHTML += '<i class="high" style="width:' + highPct + '%"></i>';
    if (medPct > 0) mixHTML += '<i class="med" style="width:' + medPct + '%"></i>';
    if (lowPct > 0) mixHTML += '<i class="low" style="width:' + lowPct + '%"></i>';
    mixHTML += '</span>';

    // Build simplified trend
    var trendClass = "";
    var trendText = "";
    if (trend.charAt(0) === "+") {
      trendClass = "up";
      trendText = "↑ " + trend.substring(1);
    } else if (trend.charAt(0) === "-") {
      trendText = "↓ " + trend.substring(1);
    } else if (trend === "flat" || trend === "0") {
      trendText = "→ flat";
    }
    var trendHTML = trendText
      ? '<span class="trend ' + trendClass + '">' + trendText + '</span>'
      : '';

    var header = el("summary", "team-band-header");
    header.innerHTML =
      '<span class="caret">&#9654;</span>' +
      '<span class="team-name">' + esc(teamId === "none" ? "Unassigned" : team.team_name || teamId) + '</span>' +
      '<span class="team-total">' + total + '</span>' +
      mixHTML +
      trendHTML;
    band.appendChild(header);

    var issues = d.team_issues[teamId] || [];
    if (issues.length) {
      var issuesDiv = el("div", "team-band-issues");

      // Group issues by area
      var byArea = {};
      issues.forEach(function(iss) {
        var prInfo = d.all_issues.find(function(ai) { return ai.issue_number === iss.number; });
        var areaKey = (prInfo && prInfo.area) ? prInfo.area : "(no area)";
        if (!byArea[areaKey]) {
          byArea[areaKey] = [];
        }
        byArea[areaKey].push(iss);
      });

      // Sort areas by issue count (descending)
      var areaKeys = Object.keys(byArea).sort(function(a, b) {
        return byArea[b].length - byArea[a].length;
      });

      // Render each area group
      areaKeys.forEach(function(areaKey) {
        var areaGroup = byArea[areaKey];
        var areaSection = el("div", "area");

        areaSection.innerHTML = '<div class="area-head">' +
          '<span class="area-name">' + esc(areaKey) + '</span>' +
          '<span class="area-n">' + areaGroup.length + '</span>' +
          '<span class="area-rule"></span>' +
          '</div>';

        // Add issue rows for this area
        areaGroup.forEach(function(iss) {
          var row = el("div", "team-issue-row");
          var prInfo = d.all_issues.find(function(ai) { return ai.issue_number === iss.number; });
          var prIcon = (prInfo && prInfo.has_linked_pr) ? ' <svg width="14" height="14" viewBox="0 0 16 16" fill="#1A7F37" style="vertical-align:-2px;"><path d="M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"/></svg>' : '';
          var areaTag = (prInfo && prInfo.area) ? ' <span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;background:var(--accent-glow);color:var(--accent);font-weight:600;">' + esc(prInfo.area) + '</span>' : '';
          var daysTag = (prInfo && prInfo.days_open != null) ? '<span style="color:var(--text-muted);font-size:12px;margin-left:auto;white-space:nowrap;">' + prInfo.days_open + 'd</span>' : '';
          row.style.cssText = 'display:flex;align-items:center;gap:6px;';
          row.innerHTML = makeUrgencyBadgeHTML(iss.urgency) +
            ' <a href="' + esc(iss.url) + '" target="_blank">#' + iss.number + '</a>' + areaTag + prIcon + ' ' +
            '<span style="color:var(--text-secondary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(iss.title) + '</span>' + daysTag;
          areaSection.appendChild(row);
        });

        issuesDiv.appendChild(areaSection);
      });

      band.appendChild(issuesDiv);
    }
    section.appendChild(band);
  });
  return section;
}
