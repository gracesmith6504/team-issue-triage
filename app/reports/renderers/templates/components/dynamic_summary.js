// Layer 1 — Stats computation (pure data, no DOM)
function computeTeamStats(teamId, filteredIssues) {
  var issues = filteredIssues.filter(function(iss) {
    return (iss.primary_team || "none") === teamId;
  });

  var urgency = {critical: 0, high: 0, medium: 0, low: 0};
  var areas = {};
  var noPR = 0;
  var noPRHigh = [];
  var bugCount = 0;
  var featureCount = 0;
  var oldest = null;
  var totalDays = 0;

  issues.forEach(function(iss) {
    var u = iss.urgency || "medium";
    urgency[u] = (urgency[u] || 0) + 1;

    var area = iss.area || "uncategorized";
    areas[area] = (areas[area] || 0) + 1;

    if (!iss.has_linked_pr) {
      noPR++;
      if (u === "critical" || u === "high") {
        noPRHigh.push(iss);
      }
    }

    var title = (iss.issue_title || iss.title || "").toLowerCase();
    var lbls = iss.labels || [];
    if (title.indexOf("bug:") === 0 || title.indexOf("bug(") === 0 ||
        title.indexOf("fix:") === 0 || title.indexOf("fix(") === 0) bugCount++;
    else if (title.indexOf("feat:") === 0 || title.indexOf("feat(") === 0 ||
             title.indexOf("feature:") === 0 || title.indexOf("feature(") === 0 ||
             lbls.indexOf("Feature") !== -1 || lbls.indexOf("feature request") !== -1) featureCount++;

    var days = iss.days_open || 0;
    totalDays += days;
    if (!oldest || days > oldest.days_open) oldest = iss;
  });

  var sortedAreas = Object.keys(areas).sort(function(a, b) { return areas[b] - areas[a]; });

  return {
    total: issues.length,
    urgency: urgency,
    areas: areas,
    sortedAreas: sortedAreas,
    noPR: noPR,
    noPRHigh: noPRHigh,
    bugCount: bugCount,
    featureCount: featureCount,
    oldest: oldest,
    avgDays: issues.length > 0 ? Math.round(totalDays / issues.length) : 0,
    issues: issues
  };
}

// Layer 2 — Insight detection (pattern matching, returns structured data)
function _filterDays() {
  var dr = state.dateRange || "All";
  if (dr === "24h") return 1;
  var m = dr.match(/^(\d+)d$/);
  return m ? parseInt(m[1], 10) : null;
}

function detectInsights(stats) {
  var insights = [];
  if (stats.total === 0) return insights;
  var filterDays = _filterDays();
  var prMinAge = filterDays ? Math.min(Math.floor(filterDays * 0.5), 7) : 0;

  // Critical issues — highest priority
  if (stats.urgency.critical > 0) {
    insights.push({
      type: "critical",
      severity: 0,
      text: stats.urgency.critical + " critical issue" + (stats.urgency.critical > 1 ? "s" : "") + " requiring immediate attention",
      isWarning: true,
      expandable: true,
      items: stats.issues.filter(function(i) { return i.urgency === "critical"; })
    });
  }

  // PR gap warning — skip issues too young to reasonably have a PR
  var prGapIssues = stats.noPRHigh.filter(function(i) { return (i.days_open || 0) >= prMinAge; });
  if (prGapIssues.length > 0) {
    var hasCrit = prGapIssues.some(function(i) { return i.urgency === "critical"; });
    var hasHigh = prGapIssues.some(function(i) { return i.urgency === "high"; });
    var urgLabel = (hasCrit && hasHigh) ? "high/critical" : hasCrit ? "critical" : "high";
    insights.push({
      type: "pr-gap",
      severity: 1,
      text: prGapIssues.length + " " + urgLabel + "-urgency issue" + (prGapIssues.length > 1 ? "s have" : " has") + " no linked PR",
      isWarning: true,
      expandable: true,
      items: prGapIssues
    });
  }

  // Area concentration
  if (stats.sortedAreas.length > 0 && stats.total >= 3) {
    var topArea = stats.sortedAreas[0];
    var topCount = stats.areas[topArea];
    var pct = Math.round(topCount / stats.total * 100);
    if (pct >= 50) {
      insights.push({
        type: "area-concentration",
        severity: 2,
        textParts: [
          {text: "Concentrated in "},
          {text: topArea, isArea: true, count: topCount},
          {text: " (" + pct + "%)"}
        ]
      });
    } else if (stats.sortedAreas.length >= 2) {
      var second = stats.sortedAreas[1];
      insights.push({
        type: "area-spread",
        severity: 3,
        textParts: [
          {text: "Busiest areas: "},
          {text: topArea, isArea: true, count: topCount},
          {text: " and "},
          {text: second, isArea: true, count: stats.areas[second]}
        ]
      });
    }
  }

  // High urgency concentrated in one area (skip if area insight already covers the same area)
  var hasAreaInsight = insights.some(function(i) { return i.type === "area-concentration" || i.type === "area-spread"; });
  if (!hasAreaInsight && stats.urgency.high + stats.urgency.critical >= 2 && stats.sortedAreas.length > 0) {
    var topAreaForUrgency = stats.sortedAreas[0];
    var highInTop = 0;
    var critInTop = 0;
    stats.issues.forEach(function(iss) {
      if ((iss.area || "uncategorized") === topAreaForUrgency) {
        if (iss.urgency === "high") highInTop++;
        if (iss.urgency === "critical") critInTop++;
      }
    });
    var totalHighInTop = highInTop + critInTop;
    if (totalHighInTop >= 2) {
      var urgDesc = (critInTop > 0 && highInTop > 0) ? "high/critical" : critInTop > 0 ? "critical" : "high";
      insights.push({
        type: "urgency-area",
        severity: 1,
        textParts: [
          {text: totalHighInTop + " " + urgDesc + " issues in "},
          {text: topAreaForUrgency, isArea: true}
        ]
      });
    }
  }

  // Neglected old issues — hide at short filters where everything is young
  var neglectMin = filterDays ? Math.max(filterDays * 0.7, 14) : 30;
  if (stats.oldest && stats.oldest.days_open >= neglectMin && stats.total >= 3) {
    insights.push({
      type: "neglect",
      severity: 3,
      text: "Oldest open: " + stats.oldest.days_open + " days (#" + (stats.oldest.issue_number || "") + "), avg age " + stats.avgDays + " days"
    });
  }

  // Low PR coverage — only count issues old enough to have a PR
  if (prGapIssues.length === 0 && stats.total >= 3) {
    var prEligible = stats.issues.filter(function(i) { return (i.days_open || 0) >= prMinAge; });
    var noPREligible = prEligible.filter(function(i) { return !i.has_linked_pr; });
    if (prEligible.length > 0) {
      var prPct = Math.round(noPREligible.length / prEligible.length * 100);
      if (prPct >= 40) {
        insights.push({
          type: "pr-coverage",
          severity: 4,
          text: prPct + "% of issues have no linked PR"
        });
      }
    }
  }

  insights.sort(function(a, b) { return a.severity - b.severity; });
  return insights.slice(0, 4);
}

// Layer 3 — Rendering
function _renderInsightPlainText(insight) {
  if (insight.textParts) {
    return insight.textParts.map(function(p) { return p.text; }).join("");
  }
  return insight.text || "";
}

function _renderInsightText(insight, teamId) {
  if (insight.textParts) {
    var html = '';
    insight.textParts.forEach(function(part) {
      if (part.isArea) {
        html += '<a class="ds-area-link" data-area="' + esc(part.text) + '" data-team="' + esc(teamId) + '">' +
          esc(part.text) + (part.count != null ? ' (' + part.count + ')' : '') + '</a>';
      } else {
        html += esc(part.text);
      }
    });
    return html;
  }
  return esc(insight.text);
}

function _renderExpandableItems(items) {
  var html = '<div class="ds-expand-list">';
  items.forEach(function(iss) {
    var num = iss.issue_number || iss.number || "";
    var title = iss.issue_title || iss.title || "";
    var url = iss.issue_url || iss.url || "";
    var days = iss.days_open || 0;
    var uClass = iss.urgency === "critical" ? "crit" : iss.urgency === "high" ? "high" : iss.urgency === "medium" ? "med" : "low";
    html += '<div class="ds-expand-item">' +
      '<i class="dot ' + uClass + '"></i>' +
      '<a href="' + esc(url) + '" target="_blank" class="ds-expand-num">#' + num + '</a>' +
      '<span class="ds-expand-title">' + esc(title) + '</span>' +
      '<span class="ds-expand-days">' + days + 'd</span>' +
      '</div>';
  });
  html += '</div>';
  return html;
}

function _scrollToArea(areaName, teamId) {
  var band = document.querySelector('.team-band[data-team="' + teamId + '"]');
  if (!band) return;
  band.querySelectorAll(".area-name").forEach(function(ah) {
    if (ah.textContent.trim() === areaName) {
      var sec = ah.closest(".area");
      if (sec) {
        sec.scrollIntoView({behavior: "smooth", block: "center"});
        sec.classList.add("ds-highlight");
        setTimeout(function() { sec.classList.remove("ds-highlight"); }, 1400);
      }
    }
  });
}

function renderDynamicSummary(teamId, stats, insights, filterLabel) {
  var wrap = el("div", "focus focus-dynamic");
  wrap.dataset.dynamicSummary = teamId;

  wrap.innerHTML = '<span class="focus-label">Focus</span>';
  var bodyEl = el("div", "ds-body");

  // Empty state
  if (stats.total === 0) {
    bodyEl.innerHTML = '<p class="ds-empty">No issues match the current filter for this team.</p>';
    wrap.appendChild(bodyEl);
    return wrap;
  }

  // Skip stats/insights for tiny sets — the issue list already shows everything
  if (stats.total >= 3) {
    // Headline — clickable urgency disclosures
    var headlineP = el("p", "ds-head");
    var urgLevels = [
      {key: "critical", label: "critical", cls: "crit"},
      {key: "high", label: "high", cls: "high"},
      {key: "medium", label: "med", cls: "med"},
      {key: "low", label: "low", cls: "low"},
    ];

    var addedCount = 0;
    urgLevels.forEach(function(lvl) {
      var count = stats.urgency[lvl.key] || 0;
      if (count === 0) return;

      if (addedCount > 0) headlineP.appendChild(document.createTextNode(", "));

      var urgIssues = stats.issues.filter(function(i) { return (i.urgency || "medium") === lvl.key; });
      var showIssues = urgIssues.slice(0, 15);
      var disc = _disclosure(count + " " + lvl.label, showIssues, {
        inline: true,
        cls: "claim-ref " + lvl.cls,
      });
      headlineP.appendChild(disc);
      addedCount++;
    });

    bodyEl.appendChild(headlineP);

    // Insights — area links and text
    if (insights.length > 0) {
      var insightsDiv = el("div", "ds-insights");
      var warnsDiv = el("div", "ds-warns");
      var hasInsights = false;
      var hasWarns = false;

      insights.forEach(function(insight) {
        if (insight.isWarning && insight.expandable && insight.items) {
          var w = el("div", "ds-warning" + (insight.items.some(function(i) { return i.urgency === "critical"; }) ? " crit" : ""));
          w.appendChild(_disclosure(
            _renderInsightPlainText(insight),
            insight.items,
            {cls: ""}
          ));
          warnsDiv.appendChild(w);
          hasWarns = true;
        } else if (!insight.isWarning) {
          var line = el("span", "ds-line");
          if (insight.textParts) {
            insight.textParts.forEach(function(part) {
              if (part.isArea) {
                var link = el("a", "ds-area-link");
                link.textContent = part.text + (part.count != null ? " (" + part.count + ")" : "");
                link.href = "#";
                link.addEventListener("click", function(e) {
                  e.preventDefault();
                  _scrollToArea(part.text, teamId);
                });
                line.appendChild(link);
              } else {
                line.appendChild(document.createTextNode(part.text));
              }
            });
          } else {
            line.textContent = insight.text;
          }
          insightsDiv.appendChild(line);
          hasInsights = true;
        }
      });

      if (hasInsights) bodyEl.appendChild(insightsDiv);
      if (hasWarns) bodyEl.appendChild(warnsDiv);
    }
  }

  // Add collapsible AI analysis section
  var teamData = d.team_breakdown[teamId];
  var synth = teamData && teamData.synthesis;
  if (synth && (synth.claims || synth.focus_summary)) {
    var aiSection = el("div", "ai");

    // Clickable metadata line (disclosure trigger)
    var issueCount = (d.team_issues[teamId] || []).length;
    var metaBtn = el("button", "disc-btn ai-meta-btn");
    var metaParts = '<span class="chev">&#9654;</span><span class="ai-meta-text">AI analysis';
    metaParts += ' &middot; ' + (synth.covered_issues || issueCount) + ' issues, all time';
    if (synth.generated_at) metaParts += ' &middot; generated ' + _timeSince(synth.generated_at);
    metaParts += '</span>';
    metaBtn.innerHTML = metaParts;
    aiSection.appendChild(metaBtn);

    // Collapsible panel
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

    bodyEl.appendChild(aiSection);
  }

  wrap.appendChild(bodyEl);
  return wrap;
}

// Build filter label from current state
function _getFilterLabel() {
  var parts = [];
  if (state.dateRange && state.dateRange !== "All") parts.push(state.dateRange);
  if (state.issueTypeFilter && state.issueTypeFilter !== "Any") parts.push(state.issueTypeFilter.toLowerCase());
  if (activeUrgencies.length) parts.push(activeUrgencies.map(function(u) { return URGENCY_SHORT[u]; }).join("+").toLowerCase());
  if (activeArea) parts.push(activeArea);
  if (searchQuery) parts.push('"' + searchQuery + '"');
  return parts.join(", ") || "filtered";
}

// Integration — called from filterTeamRouting
function updateTeamFocus(band, teamId, filteredIssues) {
  var existingDynamic = band.querySelector('[data-dynamic-summary="' + teamId + '"]');
  var originalFocus = band.querySelector('.focus:not(.focus-dynamic)');

  // Always hide the LLM synthesis and show the dynamic summary.
  // The LLM synthesis only covers the last lookback window, so it is misleading
  // on other tabs (e.g. "All" shows 78 issues but synthesis only saw 4).
  if (originalFocus) {
    originalFocus.style.display = "none";
  }

  var stats = computeTeamStats(teamId, filteredIssues);
  var insights = detectInsights(stats);
  var filterLabel = _getFilterLabel();
  var newSummary = renderDynamicSummary(teamId, stats, insights, filterLabel);

  if (existingDynamic) {
    existingDynamic.replaceWith(newSummary);
  } else {
    var content = band.querySelector(".team-band-content");
    if (content) content.insertBefore(newSummary, content.firstChild);
  }
}
