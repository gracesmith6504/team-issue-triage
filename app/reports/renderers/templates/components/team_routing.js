function buildTeamRouting() {
  var section = el("div", "section");
  section.id = "team-routing";
  section.innerHTML = '<div class="section-header"><div class="section-title">Team Routing <span class="count">(' + d.all_issues.length + ' issues across ' + Object.keys(d.team_breakdown).length + ' teams)</span></div></div>';

  var teamOrder = Object.keys(d.team_breakdown);
  // Sort teams: "none" (Unassigned) goes to bottom
  teamOrder.sort(function(a, b) {
    if (a === "none") return 1;  // "none" goes after everything
    if (b === "none") return -1; // everything goes before "none"
    return a.localeCompare(b);   // alphabetical for other teams
  });
  teamOrder.forEach(function(teamId) {
    var team = d.team_breakdown[teamId];
    if (!team) return;
    var band = el("details", "team-band");
    band.dataset.team = teamId;
    var urgencies = team.by_urgency || {};
    var total = team.total;
    var trend = team.trend || "0";

    // Calculate bug count for this team
    var issues = d.team_issues[teamId] || [];
    var bugCount = 0;
    issues.forEach(function(iss) {
      var title = (iss.issue_title || iss.title || "").toLowerCase();
      var isBug = title.indexOf("bug:") === 0 || title.indexOf("bug(") === 0 ||
                  title.indexOf("fix:") === 0 || title.indexOf("fix(") === 0;
      if (isBug) bugCount++;
    });

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
    var totalText = bugCount > 0 ? total + ' total, ' + bugCount + ' bug' + (bugCount === 1 ? '' : 's') : total + '';
    header.innerHTML =
      '<span class="caret">&#9654;</span>' +
      '<span class="team-name">' + esc(teamId === "none" ? "Unassigned" : team.team_name || teamId) + '</span>' +
      '<span class="team-total">' + totalText + '</span>' +
      mixHTML +
      trendHTML;
    band.appendChild(header);

    var content = el("div", "team-band-content");

    // Add focus section if synthesis data exists
    var synth = team.synthesis || {};
    if (synth.focus_summary) {
      var summaryDiv = el("div", "focus");
      var summaryHTML = '<span class="focus-label">Focus</span><div>';
      summaryHTML += '<p>' + esc(synth.focus_summary) + '</p>';
      if (synth.actions && synth.actions.length) {
        summaryHTML += '<ol>';
        synth.actions.forEach(function(action) {
          summaryHTML += '<li>' + esc(action) + '</li>';
        });
        summaryHTML += '</ol>';
      }
      summaryHTML += '</div>';
      summaryDiv.innerHTML = summaryHTML;
      content.appendChild(summaryDiv);
    }

    var issues = d.team_issues[teamId] || [];
    if (issues.length) {
      var issuesDiv = el("div", "team-band-issues");

      // Group issues by area
      var byArea = {};
      issues.forEach(function(iss) {
        var prInfo = d.all_issues.find(function(ai) { return ai.issue_number === iss.number; });
        var areaKey = (prInfo && prInfo.area) ? prInfo.area : "uncategorized";
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

        // Sort issues by urgency: critical > high > medium > low
        var urgencyOrder = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3};
        areaGroup.sort(function(a, b) {
          var aOrder = urgencyOrder[a.urgency] !== undefined ? urgencyOrder[a.urgency] : 99;
          var bOrder = urgencyOrder[b.urgency] !== undefined ? urgencyOrder[b.urgency] : 99;
          if (aOrder !== bOrder) return aOrder - bOrder;
          return a.issue_number - b.issue_number; // Then by issue number
        });

        var areaSection = el("div", "area");

        areaSection.innerHTML = '<div class="area-head">' +
          '<span class="area-name">' + esc(areaKey) + '</span>' +
          '<span class="area-n">' + areaGroup.length + '</span>' +
          '<span class="area-rule"></span>' +
          '</div>';

        // Add issue rows for this area
        var areaIssuesDiv = el("div", "area-group-issues");
        var issuesContainer = el("div", "issues");
        var issues = areaGroup || [];
        issues.forEach(function(iss) {
          var row = el("article", "issue");
          // Map full urgency names to short CSS classes
          var urgencyMap = {
            'critical': 'crit',
            'high': 'high',
            'medium': 'med',
            'low': 'low'
          };
          var shortUrgency = urgencyMap[iss.urgency] || iss.urgency;
          var urgencyClass = 'u-' + shortUrgency;
          var dotClass = shortUrgency;
          var critTag = iss.urgency === 'critical'
            ? '<span class="tag-crit">CRIT</span>'
            : '';

          var detailsHTML = '';
          if (iss.summary) {
            detailsHTML = '<div class="issue-sub">' + esc(iss.summary) + '</div>';
          }

          // Format author association badge
          var authorAssoc = iss.author_association || 'NONE';
          var authorBadge = '';
          if (authorAssoc !== 'NONE') {
            authorBadge = '<span class="author-role">' + esc(authorAssoc) + '</span>';
          }

          row.className = 'issue ' + urgencyClass;
          row.innerHTML =
            '<div class="issue-top">' +
              '<i class="dot ' + dotClass + '"></i>' +
              critTag +
              '<a class="num" href="' + esc(iss.issue_url) + '">#' + iss.issue_number + '</a>' +
              '<span class="title"><a href="' + esc(iss.issue_url) + '">' + esc(iss.issue_title) + '</a></span>' +
              '<span class="issue-meta">' +
                (iss.has_linked_pr ? '<span class="pr">PR</span>' : '') +
                (iss.author_login ? '<span>@' + esc(iss.author_login) + '</span>' : '') +
                authorBadge +
                (iss.days_open != null ? '<span>' + iss.days_open + 'd</span>' : '') +
              '</span>' +
            '</div>' +
            detailsHTML;
          issuesContainer.appendChild(row);
        });
        areaIssuesDiv.appendChild(issuesContainer);
        areaSection.appendChild(areaIssuesDiv);

        issuesDiv.appendChild(areaSection);
      });

      content.appendChild(issuesDiv);
    }
    band.appendChild(content);
    section.appendChild(band);
  });
  return section;
}
