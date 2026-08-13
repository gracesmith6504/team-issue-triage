function _issueByNumber(num) {
  return d.all_issues.find(function(i) { return i.issue_number === num; });
}

function _issueRow(iss) {
  if (!iss) return null;
  var uClass = iss.urgency === "critical" ? "crit" : iss.urgency === "high" ? "high" : iss.urgency === "medium" ? "med" : "low";
  var row = el("div", "ds-expand-item");
  row.innerHTML =
    '<span class="dot ' + uClass + '"></span>' +
    '<a class="ds-expand-num" href="' + esc(iss.issue_url || iss.url || "") + '" target="_blank">#' + (iss.issue_number || iss.number) + '</a>' +
    '<span class="ds-expand-title">' + esc(iss.issue_title || iss.title || "") + '</span>' +
    '<span class="ds-expand-area">' + esc(iss.area || "") + '</span>' +
    '<span class="ds-expand-days">' + (iss.days_open || 0) + 'd</span>';
  return row;
}

function _disclosure(label, issues, opts) {
  opts = opts || {};
  var root = el(opts.inline ? "span" : "div", "disc" + (opts.cls ? " " + opts.cls : ""));
  var btn = el("button", "disc-btn");
  btn.innerHTML = '<span class="chev">&#9654;</span><span>' + label + '</span>';
  var panel = el("div", "disc-panel");
  issues.forEach(function(iss) {
    var row = _issueRow(iss);
    if (row) panel.appendChild(row);
  });
  btn.addEventListener("click", function() { root.classList.toggle("open"); });
  root.appendChild(btn);
  root.appendChild(panel);
  return root;
}

function _renderClaimText(claim, teamId) {
  var container = el("div", "ai-claim");
  var text = claim.text || "";
  var refs = claim.refs || {};
  var parts = text.split(/(\{ref:[^}]+\}|\{area:[^}]+\})/g);

  parts.forEach(function(part) {
    var refMatch = part.match(/^\{ref:([^}]+)\}$/);
    var areaMatch = part.match(/^\{area:([^}]+)\}$/);

    if (refMatch) {
      var key = refMatch[1];
      var ref = refs[key] || {};
      var label = ref.label || key.replace(/_/g, " ");
      var issueNums = ref.issues || [];
      var issues = issueNums.map(_issueByNumber).filter(Boolean);
      var worst = issues.some(function(i) { return i.urgency === "critical"; }) ? "crit"
        : issues.some(function(i) { return i.urgency === "high"; }) ? "high" : "";
      var disc = _disclosure(label + " (" + issues.length + ")", issues, {
        inline: true,
        cls: "claim-ref" + (worst ? " " + worst : ""),
      });
      container.appendChild(disc);
    } else if (areaMatch) {
      var areaName = areaMatch[1];
      var link = el("a", "ds-area-link");
      link.textContent = areaName;
      link.dataset.area = areaName;
      link.dataset.team = teamId;
      link.href = "#";
      link.addEventListener("click", function(e) {
        e.preventDefault();
        var band = document.querySelector('.team-band[data-team="' + teamId + '"]');
        if (!band) return;
        var areas = band.querySelectorAll(".area-name");
        areas.forEach(function(ah) {
          if (ah.textContent.trim() === areaName) {
            var sec = ah.closest(".area");
            if (sec) {
              sec.scrollIntoView({behavior: "smooth", block: "center"});
              sec.classList.add("ds-highlight");
              setTimeout(function() { sec.classList.remove("ds-highlight"); }, 1400);
            }
          }
        });
      });
      container.appendChild(link);
    } else if (part) {
      container.appendChild(document.createTextNode(part));
    }
  });

  return container;
}

function _timeSince(isoStr) {
  if (!isoStr) return "";
  var ms = Date.now() - new Date(isoStr).getTime();
  var h = Math.round(ms / 3600000);
  if (h < 1) return "just now";
  if (h < 24) return h + "h ago";
  return Math.round(h / 24) + "d ago";
}

function _renderAiContent(teamId, synth, container) {
  var claims = synth.claims || [];
  claims.forEach(function(claim) {
    container.appendChild(_renderClaimText(claim, teamId));
  });

  var actions = synth.structured_actions || [];
  if (actions.length) {
    var actsEl = el("div", "ai-actions");
    actions.forEach(function(action, i) {
      var row = el("div", "ai-action");
      var idx = el("span", "idx", (i + 1) + ".");
      var bodySpan = el("span", "body");
      bodySpan.appendChild(document.createTextNode(action.text + " "));

      var issueNums = action.issues || [];
      var issues = issueNums.map(_issueByNumber).filter(Boolean);
      if (issues.length) {
        var worst = issues.some(function(x) { return x.urgency === "critical"; }) ? "crit"
          : issues.some(function(x) { return x.urgency === "high"; }) ? "high" : "med";
        var countEl = el("span", "ai-count");
        countEl.innerHTML = '<span class="dot ' + worst + '"></span>' + issues.length + " issue" + (issues.length !== 1 ? "s" : "");
        bodySpan.appendChild(countEl);
      }

      row.appendChild(idx);
      row.appendChild(bodySpan);
      actsEl.appendChild(row);
    });
    container.appendChild(actsEl);
  }
}

function renderStructuredFocus(teamId, synth) {
  var wrap = el("div", "focus");
  wrap.innerHTML = '<span class="focus-label">Focus</span>';

  var body = el("div", "focus-body");

  // AI analysis as a collapsible disclosure
  var aiSection = el("div", "ai");

  var metaBtn = el("button", "disc-btn ai-meta-btn");
  var metaParts = '<span class="chev">&#9654;</span><span class="ai-meta-text">AI analysis';
  if (synth.covered_issues) metaParts += ' &middot; ' + synth.covered_issues + ' issues';
  if (synth.generated_at) metaParts += ' &middot; generated ' + _timeSince(synth.generated_at);
  metaParts += '</span>';
  metaBtn.innerHTML = metaParts;
  aiSection.appendChild(metaBtn);

  var aiPanel = el("div", "ai-panel");
  if (synth.claims && synth.claims.length) {
    _renderAiContent(teamId, synth, aiPanel);
  } else if (synth.focus_summary) {
    var claimEl = el("div", "ai-claim");
    claimEl.textContent = synth.focus_summary;
    aiPanel.appendChild(claimEl);
    if (synth.actions && synth.actions.length) {
      var actsEl = el("div", "ai-actions");
      synth.actions.forEach(function(action, i) {
        var row = el("div", "ai-action");
        row.innerHTML = '<span class="idx">' + (i + 1) + '.</span><span class="body">' + esc(action) + '</span>';
        actsEl.appendChild(row);
      });
      aiPanel.appendChild(actsEl);
    }
  }
  aiSection.appendChild(aiPanel);

  metaBtn.addEventListener("click", function() {
    aiSection.classList.toggle("open");
  });

  body.appendChild(aiSection);
  wrap.appendChild(body);
  return wrap;
}

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

    // Build simplified trend (hide when no baseline)
    var trendClass = "";
    var trendText = "";
    var hasPrevious = (team.previous_period || 0) > 0;
    if (hasPrevious) {
      if (trend.charAt(0) === "+") {
        trendClass = "up";
        trendText = "↑ " + trend.substring(1);
      } else if (trend.charAt(0) === "-") {
        trendText = "↓ " + trend.substring(1);
      } else if (trend === "flat" || trend === "0") {
        trendText = "→ flat";
      }
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
    if (synth.claims && synth.claims.length) {
      content.appendChild(renderStructuredFocus(teamId, synth));
    } else if (synth.focus_summary) {
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
          // Display COLLABORATOR as MAINTAINER (they have write access = maintainers)
          var displayRole = authorAssoc === 'COLLABORATOR' ? 'MAINTAINER' : authorAssoc;
          var authorBadge = '';
          if (displayRole === 'MAINTAINER') {
            authorBadge = '<span class="author-role maintainer">Maintainer</span>';
          }

          // Format PR icon (green if open, grey if draft, clickable)
          var prIcon = '';
          if (iss.has_linked_pr && iss.linked_pr_url) {
            var prColor = iss.linked_pr_draft ? '#6e7781' : '#1A7F37';
            prIcon = '<a href="' + esc(iss.linked_pr_url) + '" class="pr-icon" target="_blank" rel="noopener">' +
              '<svg width="16" height="16" viewBox="0 0 16 16" fill="' + prColor + '">' +
              '<path d="M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"/>' +
              '</svg></a>';
          }

          row.className = 'issue ' + urgencyClass;
          row.dataset.issueNumber = iss.issue_number || iss.number;
          row.innerHTML =
            '<div class="issue-top">' +
              '<i class="dot ' + dotClass + '"></i>' +
              critTag +
              '<a class="num" href="' + esc(iss.issue_url) + '">#' + iss.issue_number + '</a>' +
              '<span class="title"><a href="' + esc(iss.issue_url) + '">' + esc(iss.issue_title) + '</a></span>' +
              '<span class="issue-meta">' +
                (authorBadge ? authorBadge + ' ' : '') +
                (iss.author_login ? '<span>@' + esc(iss.author_login) + '</span>' : '') +
                (prIcon ? ' ' + prIcon : '') +
                (iss.comment_count ? ' <span title="' + iss.comment_count + ' comments">💬' + iss.comment_count + '</span>' : '') +
                (iss.days_open != null ? ' <span>' + iss.days_open + 'd</span>' : '') +
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
