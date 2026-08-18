var activeTeams = [];
var activeUrgencies = [];
var activeArea = "";
var searchQuery = "";

function matchesFilters(issue) {
  if (!isWithinFilter(issue.created_at)) return false;

  if (state.issueTypeFilter && state.issueTypeFilter !== "Any") {
    var title = (issue.issue_title || issue.title || "").toLowerCase();
    var lbls = issue.labels || [];
    var isBug = title.indexOf("bug:") === 0 || title.indexOf("bug(") === 0 ||
                title.indexOf("fix:") === 0 || title.indexOf("fix(") === 0;
    var isFeature = title.indexOf("feat:") === 0 || title.indexOf("feat(") === 0 ||
                    title.indexOf("feature:") === 0 || title.indexOf("feature(") === 0 ||
                    lbls.indexOf("Feature") !== -1 || lbls.indexOf("feature request") !== -1;
    if (state.issueTypeFilter === "Bugs" && !isBug) return false;
    if (state.issueTypeFilter === "Features" && !isFeature) return false;
  }

  if (activeTeams.length && activeTeams.indexOf(issue.primary_team) === -1) return false;
  if (activeUrgencies.length && activeUrgencies.indexOf(issue.urgency) === -1) return false;
  if (activeArea && (issue.area || "") !== activeArea) return false;

  if (searchQuery) {
    var q = searchQuery.toLowerCase();
    if (q.charAt(0) === "@") {
      var userQ = q.substring(1);
      if ((issue.author_login || "").toLowerCase().indexOf(userQ) === -1) return false;
    } else {
      var t = (issue.issue_title || issue.title || "").toLowerCase();
      var num = String(issue.issue_number || issue.number || "");
      if (t.indexOf(q) === -1 && num.indexOf(q) === -1) return false;
    }
  }

  return true;
}

function getFilteredIssues() {
  return d.all_issues.filter(matchesFilters);
}

function hasActiveFilters() {
  return activeUrgencies.length || searchQuery || activeArea ||
    (state.dateRange && state.dateRange !== "All") ||
    (state.issueTypeFilter && state.issueTypeFilter !== "Any");
}

function resetAllFilters() {
  activeTeams = []; activeUrgencies = []; activeArea = ""; searchQuery = "";
  _prTileFilter = null;
  document.querySelectorAll("#pr-health .metric-tile").forEach(function(te) { te.style.outline = ""; });
  state.dateRange = "All";
  state.issueTypeFilter = "Any";
  saveState(state);
  document.querySelectorAll(".date-pill").forEach(function(p) { p.classList.remove("active"); });
  document.querySelectorAll(".type-pill").forEach(function(p) { p.classList.remove("active"); });
  var allDatePill = document.querySelector('.date-pill:last-of-type');
  var allTypePill = document.querySelector('.type-pill:first-of-type');
  document.querySelectorAll(".date-pill").forEach(function(p) {
    if (p.textContent === "All") p.classList.add("active");
  });
  document.querySelectorAll(".type-pill").forEach(function(p) {
    if (p.textContent === "Any") p.classList.add("active");
  });
  document.querySelectorAll(".area-name.active-area").forEach(function(a) { a.classList.remove("active-area"); });
  document.querySelectorAll(".filter-pill.active").forEach(function(p) {
    p.classList.remove("active");
    p.style.background = "transparent"; p.style.color = "var(--text-muted)";
  });
  var searchEl = document.querySelector(".search-input");
  if (searchEl) searchEl.value = "";
}

function applyAllFilters() {
  // Preserve scroll position relative to the nearest visible team band
  var scrollAnchor = null;
  var scrollOffset = 0;
  var bands = document.querySelectorAll(".team-band");
  for (var i = 0; i < bands.length; i++) {
    var rect = bands[i].getBoundingClientRect();
    if (rect.top >= -rect.height && rect.top <= window.innerHeight) {
      scrollAnchor = bands[i];
      scrollOffset = rect.top;
      break;
    }
  }

  var filtered = getFilteredIssues();

  filterTeamRouting(filtered);
  updateKPIs(filtered);
  updateAlerts(filtered);
  filterPRHealth();
  filterContributorHealth();

  // Restore scroll position so the page doesn't jump
  if (scrollAnchor) {
    var newRect = scrollAnchor.getBoundingClientRect();
    var drift = newRect.top - scrollOffset;
    if (Math.abs(drift) > 5) {
      window.scrollBy(0, drift);
    }
  }

  var banner = document.getElementById("filter-banner");
  if (banner) {
    if (hasActiveFilters() || _prTileFilter) {
      banner.classList.add("visible");
    } else {
      banner.classList.remove("visible");
    }
  }

  _updateTimeFilterNote();
}

function _updateTimeFilterNote() {
  var note = document.getElementById("user-time-note");
  var isUserSearch = searchQuery && searchQuery.charAt(0) === "@";
  var hasTimeFilter = state.dateRange && state.dateRange !== "All";

  if (!isUserSearch || !hasTimeFilter) {
    if (note) note.style.display = "none";
    return;
  }

  var userQ = searchQuery.substring(1).toLowerCase();
  var hidden = 0;

  d.all_issues.forEach(function(iss) {
    if ((iss.author_login || "").toLowerCase().indexOf(userQ) !== -1 && !isWithinFilter(iss.created_at)) hidden++;
  });
  var prs = (d.pr_health && d.pr_health.all_open_pr_summaries) || [];
  prs.forEach(function(pr) {
    var match = (pr.author || "").toLowerCase().indexOf(userQ) !== -1;
    if (!match) {
      (pr.participants || []).forEach(function(p) { if ((p || "").toLowerCase().indexOf(userQ) !== -1) match = true; });
    }
    if (match && !isWithinFilter(pr.created_at)) hidden++;
  });
  var vouches = (d.vouch_status && d.vouch_status.pending_vouches) || [];
  vouches.forEach(function(v) {
    if ((v.author || "").toLowerCase().indexOf(userQ) !== -1 && !isWithinFilter(v.created_at)) hidden++;
  });

  if (!note) {
    note = el("div", "user-time-note");
    note.id = "user-time-note";
    var dashboard = document.querySelector(".dashboard");
    if (dashboard) dashboard.insertBefore(note, dashboard.firstChild);
  }
  if (hidden > 0) {
    note.innerHTML = hidden + " more item" + (hidden !== 1 ? "s" : "") + " for <strong>" + esc(searchQuery) + "</strong> outside the " + state.dateRange + " filter — <a href=\"#\" class=\"note-switch\">switch to All</a>";
    note.style.display = "";
    note.querySelector(".note-switch").addEventListener("click", function(e) {
      e.preventDefault();
      state.dateRange = "All";
      saveState(state);
      document.querySelectorAll(".date-pill").forEach(function(p) {
        p.classList.toggle("active", p.textContent === "All");
      });
      applyAllFilters();
    });
  } else {
    note.style.display = "none";
  }
}

function _matchesSearchPR(pr) {
  if (!searchQuery) return true;
  var q = searchQuery.toLowerCase();
  if (q.charAt(0) !== "@") return true;
  var userQ = q.substring(1);
  if ((pr.author || "").toLowerCase().indexOf(userQ) !== -1) return true;
  var participants = pr.participants || [];
  for (var i = 0; i < participants.length; i++) {
    if ((participants[i] || "").toLowerCase().indexOf(userQ) !== -1) return true;
  }
  return false;
}

function _getFilteredPRSummaries() {
  var summaries = (d.pr_health && d.pr_health.all_open_pr_summaries) || [];
  var filtered = summaries;
  if (getFilterCutoffMs()) {
    filtered = filtered.filter(function(pr) { return isWithinFilter(pr.created_at); });
  }
  if (searchQuery) {
    filtered = filtered.filter(function(pr) { return _matchesSearchPR(pr); });
  }
  return filtered;
}

function _getFilteredVouches() {
  var vouches = (d.vouch_status && d.vouch_status.pending_vouches) || [];
  var filtered = vouches;
  if (getFilterCutoffMs()) {
    filtered = filtered.filter(function(v) { return isWithinFilter(v.created_at); });
  }
  if (searchQuery && searchQuery.charAt(0) === "@") {
    var userQ = searchQuery.substring(1).toLowerCase();
    filtered = filtered.filter(function(v) { return (v.author || "").toLowerCase().indexOf(userQ) !== -1; });
  }
  return filtered;
}

function filterPRHealth() {
  if (!d.pr_health) return;
  var section = document.getElementById("pr-health");
  if (!section) return;

  var filterDays = _filterDays();
  var is24h = filterDays && filterDays <= 1;

  var tiles = section.querySelector(".metric-tiles");
  var ageDist = document.getElementById("pr-age-dist");
  if (is24h) {
    _prTileFilter = null;
    section.querySelectorAll(".metric-tile").forEach(function(te) { te.style.outline = ""; });
  }
  if (tiles) { tiles.style.opacity = is24h ? "0.35" : ""; tiles.style.pointerEvents = is24h ? "none" : ""; }
  if (ageDist) { ageDist.style.opacity = is24h ? "0.35" : ""; ageDist.style.pointerEvents = is24h ? "none" : ""; }

  var dimNote = document.getElementById("pr-dim-note");
  if (is24h) {
    if (!dimNote && tiles) {
      dimNote = el("p", "muted-note");
      dimNote.id = "pr-dim-note";
      dimNote.textContent = "PR metrics not meaningful at 24h";
      tiles.parentNode.insertBefore(dimNote, tiles.nextSibling);
    }
    if (dimNote) dimNote.style.display = "";
  } else if (dimNote) {
    dimNote.style.display = "none";
  }

  var filtered = _getFilteredPRSummaries();

  if (!getFilterCutoffMs() && !searchQuery) {
    _renderPRHealthTiles(d.pr_health.total_open, d.pr_health.awaiting_review, d.pr_health.stale_14d);
    _renderAgeDistribution(d.pr_health.age_distribution);
  } else {
    var now = new Date();
    var totalOpen = filtered.length;
    var awaitingReview = filtered.filter(function(pr) { return pr.has_requested_reviewers; }).length;
    var staleDays = _staleDaysThreshold();
    var staleCount = staleDays ? filtered.filter(function(pr) {
      return (now - new Date(pr.updated_at)) / (1000 * 60 * 60 * 24) >= staleDays;
    }).length : 0;
    _renderPRHealthTiles(totalOpen, awaitingReview, staleCount, staleDays);

    var ageBuckets = null;
    if (filterDays === null || filterDays >= 30) {
      ageBuckets = {a: {count:0,label:"< 1 week"}, b: {count:0,label:"1-2 weeks"}, c: {count:0,label:"2-4 weeks"}, d: {count:0,label:"> 1 month"}};
      filtered.forEach(function(pr) {
        var age = (now - new Date(pr.created_at)) / 86400000;
        if (age < 7) ageBuckets.a.count++;
        else if (age < 14) ageBuckets.b.count++;
        else if (age < 28) ageBuckets.c.count++;
        else ageBuckets.d.count++;
      });
    } else if (filterDays >= 14) {
      ageBuckets = {a: {count:0,label:"< 3 days"}, b: {count:0,label:"3-7 days"}, c: {count:0,label:"7-10 days"}, d: {count:0,label:"10-14 days"}};
      filtered.forEach(function(pr) {
        var age = (now - new Date(pr.created_at)) / 86400000;
        if (age < 3) ageBuckets.a.count++;
        else if (age < 7) ageBuckets.b.count++;
        else if (age < 10) ageBuckets.c.count++;
        else ageBuckets.d.count++;
      });
    } else if (filterDays >= 7) {
      ageBuckets = {a: {count:0,label:"< 1 day"}, b: {count:0,label:"1-3 days"}, c: {count:0,label:"3-5 days"}, d: {count:0,label:"5-7 days"}};
      filtered.forEach(function(pr) {
        var age = (now - new Date(pr.created_at)) / 86400000;
        if (age < 1) ageBuckets.a.count++;
        else if (age < 3) ageBuckets.b.count++;
        else if (age < 5) ageBuckets.c.count++;
        else ageBuckets.d.count++;
      });
    }
    _renderAgeDistribution(ageBuckets);
  }

  if (_prTileFilter) {
    var tileNow = Date.now();
    var tileBase = _getFilteredPRSummaries();
    var tileSubset;
    if (_prTileFilter === "all") {
      tileSubset = tileBase.filter(function(pr) { return !pr.is_draft; });
    } else if (_prTileFilter === "awaiting") {
      tileSubset = tileBase.filter(function(pr) { return pr.has_requested_reviewers && !pr.is_draft; });
    } else if (_prTileFilter === "stale") {
      var staleDaysT = _staleDaysThreshold() || 14;
      tileSubset = tileBase.filter(function(pr) {
        return !pr.is_draft && (tileNow - new Date(pr.updated_at).getTime()) / 86400000 >= staleDaysT;
      });
    } else {
      tileSubset = [];
    }
    var tileFormatted = tileSubset.map(function(pr) {
      var daysOpen = Math.floor((tileNow - new Date(pr.created_at).getTime()) / 86400000);
      var daysSinceUpdate = pr.updated_at ? Math.floor((tileNow - new Date(pr.updated_at).getTime()) / 86400000) : daysOpen;
      return {
        number: pr.number,
        title: pr.title || "PR #" + pr.number,
        url: pr.url || "#",
        author: pr.author || "",
        author_association: pr.author_association || "NONE",
        days_open: daysOpen,
        last_activity: daysSinceUpdate + "d ago",
        participants: pr.participants || [],
        author_pinged: false,
        author_pinged_days: 0
      };
    }).sort(function(a, b) { return b.days_open - a.days_open; });
    var tileTitleLabels = {all: "All Open PRs", awaiting: "Awaiting Review", stale: "Stale PRs"};
    var tileTitleEl = document.getElementById("neglected-title");
    if (tileTitleEl) tileTitleEl.innerHTML = tileTitleLabels[_prTileFilter] + ' <span style="color:var(--text-dim);font-weight:400;">(' + tileFormatted.length + ' total)</span>';
    _renderStuckPRs(tileFormatted, tileFormatted.length, null);
    return;
  }

  var nowMs = Date.now();
  var filterDaysVal = _filterDays();
  var NEGLECT_DAYS = filterDaysVal && filterDaysVal <= 7 ? 3 : 7;

  function _neglectDays(pr) {
    var lastReview = pr.last_review_at ? new Date(pr.last_review_at).getTime() : 0;
    var lastComment = pr.last_human_comment_at ? new Date(pr.last_human_comment_at).getTime() : 0;
    var lastHuman = Math.max(lastReview, lastComment);
    if (lastHuman === 0) return Math.floor((nowMs - new Date(pr.created_at).getTime()) / 86400000);
    return Math.floor((nowMs - lastHuman) / 86400000);
  }

  var _isBotAuthor = function(login) {
    if (!login) return false;
    if (login.endsWith("[bot]") || login.endsWith("-bot")) return true;
    var bots = {"github-actions": 1, "copy-pr-bot": 1, "gator-agent": 1};
    return !!bots[login];
  };
  var _hadEngagement = function(pr) {
    return !!(pr.last_review_at || pr.last_human_comment_at);
  };
  var _isMaintainer = function(pr) {
    var a = pr.author_association || "NONE";
    return a === "COLLABORATOR" || a === "MEMBER" || a === "OWNER";
  };

  var _authorPinged = function(pr) {
    if (!pr.last_author_comment_at) return false;
    var authorTs = new Date(pr.last_author_comment_at).getTime();
    var lastReview = pr.last_review_at ? new Date(pr.last_review_at).getTime() : 0;
    var lastComment = pr.last_human_comment_at ? new Date(pr.last_human_comment_at).getTime() : 0;
    var lastHuman = Math.max(lastReview, lastComment);
    return authorTs > lastHuman;
  };

  var neglected = filtered.filter(function(pr) {
    if (pr.is_draft) return false;
    if (_isBotAuthor(pr.author)) return false;
    return _neglectDays(pr) >= NEGLECT_DAYS;
  }).sort(function(a, b) {
    var aHad = _hadEngagement(a) ? 1 : 0;
    var bHad = _hadEngagement(b) ? 1 : 0;
    if (bHad !== aHad) return bHad - aHad;
    var aPinged = _authorPinged(a) ? 1 : 0;
    var bPinged = _authorPinged(b) ? 1 : 0;
    if (bPinged !== aPinged) return bPinged - aPinged;
    var aMaint = _isMaintainer(a) ? 1 : 0;
    var bMaint = _isMaintainer(b) ? 1 : 0;
    if (aMaint !== bMaint) return aMaint - bMaint;
    return _neglectDays(b) - _neglectDays(a);
  });

  var MAX_PER_AUTHOR = 2;
  var authorCount = {};
  var capped = [];
  neglected.forEach(function(pr) {
    var a = pr.author || "";
    authorCount[a] = (authorCount[a] || 0) + 1;
    if (authorCount[a] <= MAX_PER_AUTHOR) capped.push(pr);
  });

  var totalNeglected = capped.length;
  neglected = capped.map(function(pr) {
    var daysOpen = Math.floor((nowMs - new Date(pr.created_at)) / 86400000);
    var nd = _neglectDays(pr);
    var lastReview = pr.last_review_at ? new Date(pr.last_review_at).getTime() : 0;
    var lastComment = pr.last_human_comment_at ? new Date(pr.last_human_comment_at).getTime() : 0;
    var lastHuman = Math.max(lastReview, lastComment);
    var activityText = lastHuman ? nd + "d ago" : "never";
    var pinged = _authorPinged(pr);
    var authorPingedDays = 0;
    if (pinged && pr.last_author_comment_at) {
      authorPingedDays = Math.floor((nowMs - new Date(pr.last_author_comment_at).getTime()) / 86400000);
    }
    return {
      number: pr.number,
      title: pr.title || "PR #" + pr.number,
      url: pr.url || "https://github.com/NVIDIA/OpenShell/pull/" + pr.number,
      author: pr.author || "",
      author_association: pr.author_association || "NONE",
      days_open: daysOpen,
      last_activity: activityText,
      participants: pr.participants || [],
      created_at: pr.created_at,
      author_pinged: pinged,
      author_pinged_days: authorPingedDays
    };
  });
  _renderStuckPRs(neglected, totalNeglected, NEGLECT_DAYS);
}

function filterContributorHealth() {
  if (!d.vouch_status) return;
  var section = document.getElementById("contributor-health");
  if (!section) return;

  var filtered = _getFilteredVouches();
  var totalPending = filtered.length;
  var longestWait = filtered.reduce(function(max, v) { return Math.max(max, v.wait_days); }, 0);
  _renderContribTiles(totalPending, longestWait);
  _renderVouchList(filtered);

  var filteredAuthors = {};
  filtered.forEach(function(v) { filteredAuthors[v.author] = true; });
  var filteredBlocked = (d.vouch_status.blocked_prs || []).filter(function(bp) {
    return filteredAuthors[bp.author];
  });
  _renderBlockedPRs(filteredBlocked);
}

function updateKPIs(filtered) {
  var issueCard = document.querySelector('.kpi-card[data-kpi="triage-needed"]');
  if (issueCard) {
    var kpiLabel = issueCard.querySelector(".kpi-label");
    if (hasActiveFilters()) {
      var triageFiltered = filtered.filter(function(iss) {
        return (iss.labels || []).indexOf("state:triage-needed") !== -1;
      });
      issueCard.querySelector(".kpi-number").textContent = triageFiltered.length;
      issueCard.querySelector(".kpi-sub").textContent = filtered.length + " issues shown";
    } else {
      issueCard.querySelector(".kpi-number").textContent = d.summary.triage_needed;
      issueCard.querySelector(".kpi-sub").textContent = d.summary.total_open + " total open issues";
    }
    if (kpiLabel) kpiLabel.innerHTML = esc("Issues Needing Triage") + hintHTML("Issues with the state:triage-needed label on GitHub");
  }

  if (d.pr_health) {
    var prCard = document.querySelector('.kpi-card[data-kpi="pr-health"]');
    if (prCard) {
      var prFiltered = _getFilteredPRSummaries();
      var awaitingReview = prFiltered.filter(function(pr) { return pr.has_requested_reviewers; }).length;
      var staleDays = _staleDaysThreshold();
      prCard.querySelector(".kpi-number").textContent = awaitingReview;
      if (staleDays === null) {
        prCard.querySelector(".kpi-sub").textContent = prFiltered.length + " open PRs";
      } else {
        var staleFiltered = getFilterCutoffMs() ? prFiltered.filter(function(pr) {
          return (new Date() - new Date(pr.updated_at)) / (1000 * 60 * 60 * 24) >= staleDays;
        }).length : d.pr_health.stale_14d;
        prCard.querySelector(".kpi-sub").textContent = staleFiltered + " stale (" + staleDays + "d+)";
      }
    }

    var velCard = document.querySelector('.kpi-card[data-kpi="pr-velocity"]');
    if (velCard) {
      var mergedDates = d.pr_health.merged_dates || [];
      var now = new Date();
      var weekAgo = new Date(now - 7 * 24 * 60 * 60 * 1000);
      var twoWeeksAgo = new Date(now - 14 * 24 * 60 * 60 * 1000);
      var thisWeek = 0, lastWeek = 0;
      mergedDates.forEach(function(dateStr) {
        var merged = new Date(dateStr);
        if (merged >= weekAgo) thisWeek++;
        else if (merged >= twoWeeksAgo) lastWeek++;
      });
      velCard.querySelector(".kpi-number").textContent = thisWeek;
      velCard.querySelector(".kpi-sub").textContent = lastWeek + " last week";
    }
  }

  if (d.vouch_status) {
    var vouchCard = document.querySelector('.kpi-card[data-kpi="contributor-health"]');
    if (vouchCard) {
      var allVouches = d.vouch_status.pending_vouches || [];
      vouchCard.querySelector(".kpi-number").textContent = allVouches.length;
      var dr = state.dateRange || "All";
      var thresholdDays = dr === "24h" ? 1 : dr === "7d" ? 7 : 30;
      var overCount = allVouches.filter(function(v) { return v.wait_days > thresholdDays; }).length;
      vouchCard.querySelector(".kpi-sub").textContent = overCount + " waiting over " + thresholdDays + " days";
    }
  }
}

function updateAlerts(filtered) {
  var strip = document.querySelector(".alert-strip");
  if (!strip) return;

  var issueAlert = strip.querySelector('[data-alert="issues"]');
  if (issueAlert) {
    var highCount = 0;
    filtered.forEach(function(iss) { if (iss.urgency === "high") highCount++; });
    var dot = issueAlert.querySelector(".alert-dot");
    var dotHtml = dot ? dot.outerHTML : '';
    issueAlert.innerHTML = dotHtml + '<strong>' + highCount + '</strong> high-urgency issues' + (hasActiveFilters() ? ' (filtered)' : ' this period');
  }

  if (d.pr_health) {
    var prAlert = strip.querySelector('[data-alert="prs"]');
    if (prAlert) {
      var prFiltered = _getFilteredPRSummaries();
      var staleDays = _staleDaysThreshold();
      if (staleDays === null) {
        prAlert.style.display = "none";
      } else {
        prAlert.style.display = "";
        var staleCount = getFilterCutoffMs() ? prFiltered.filter(function(pr) {
          return (new Date() - new Date(pr.updated_at)) / (1000 * 60 * 60 * 24) >= staleDays;
        }).length : d.pr_health.stale_14d;
        var dot2 = prAlert.querySelector(".alert-dot");
        var dotHtml2 = dot2 ? dot2.outerHTML : '';
        prAlert.innerHTML = dotHtml2 + '<strong>' + staleCount + '</strong> PRs stale for ' + staleDays + '+ days' +
          (hasActiveFilters() ? ' (filtered)' : '');
      }
    }
  }

  if (d.vouch_status) {
    var vouchAlert = strip.querySelector('[data-alert="vouches"]');
    if (vouchAlert) {
      var filteredVouches = _getFilteredVouches();
      var vouchCount = filteredVouches.length;
      var longestVouch = filteredVouches.length ? filteredVouches.reduce(function(max, v) {
        return v.wait_days > max.wait_days ? v : max;
      }, filteredVouches[0]) : null;
      var dot3 = vouchAlert.querySelector(".alert-dot");
      var dotHtml3 = dot3 ? dot3.outerHTML : '';
      var vouchText = '<strong>' + vouchCount + '</strong> contributors waiting for vouch';
      if (longestVouch) vouchText += ' - longest: <a href="' + esc(longestVouch.url) + '" target="_blank">@' + esc(longestVouch.author) + '</a> (' + longestVouch.wait_days + ' days)';
      var blockedPRs = (d.vouch_status && d.vouch_status.blocked_prs) || [];
      if (blockedPRs.length) vouchText += ' - <strong>' + blockedPRs.length + '</strong> PR' + (blockedPRs.length > 1 ? 's' : '') + ' blocked';
      if (hasActiveFilters()) vouchText += ' (filtered)';
      vouchAlert.innerHTML = dotHtml3 + vouchText;
    }
  }
}

function filterTeamRouting(filtered) {
  var filteredByTeam = {};
  filtered.forEach(function(iss) {
    var team = iss.primary_team || "none";
    if (!filteredByTeam[team]) filteredByTeam[team] = [];
    filteredByTeam[team].push(iss);
  });

  // Update section header count
  var routingHeader = document.querySelector("#team-routing .section-title");
  if (routingHeader) {
    var teamCount = Object.keys(filteredByTeam).length;
    routingHeader.innerHTML = 'Team Routing <span class="count">(' + filtered.length + ' issues across ' + teamCount + ' teams)</span>';
  }

  var bands = document.querySelectorAll(".team-band");
  bands.forEach(function(band) {
    var teamId = band.dataset.team;
    var issues = band.querySelectorAll(".issue");
    var visibleCount = 0;

    issues.forEach(function(issueEl) {
      var num = parseInt(issueEl.dataset.issueNumber, 10);
      var issueData = d.all_issues.find(function(ai) {
        return (ai.issue_number || ai.number) === num;
      });
      if (!issueData) {
        var teamIssues = d.team_issues[teamId] || [];
        issueData = teamIssues.find(function(ti) {
          return (ti.issue_number || ti.number) === num;
        });
      }
      if (issueData && matchesFilters(issueData)) {
        issueEl.style.display = "";
        visibleCount++;
      } else if (issueData) {
        issueEl.style.display = "none";
      } else {
        visibleCount++;
      }
    });

    // Update team total count with bug count
    var totalEl = band.querySelector(".team-total");
    if (totalEl) {
      var sourceIssues = hasActiveFilters() ? (filteredByTeam[teamId] || []) : (d.team_issues[teamId] || []);
      var displayCount = hasActiveFilters() ? visibleCount : sourceIssues.length;
      var bugCount = 0;
      sourceIssues.forEach(function(iss) {
        var title = (iss.issue_title || iss.title || "").toLowerCase();
        if (title.indexOf("bug:") === 0 || title.indexOf("bug(") === 0 ||
            title.indexOf("fix:") === 0 || title.indexOf("fix(") === 0) bugCount++;
      });
      totalEl.textContent = bugCount > 0
        ? displayCount + ' total, ' + bugCount + ' bug' + (bugCount === 1 ? '' : 's')
        : String(displayCount);
    }

    // Update urgency mix bar
    var mixEl = band.querySelector(".mix");
    if (mixEl) {
      var teamFiltered = filteredByTeam[teamId] || [];
      var critCount = 0, highCount = 0, medCount = 0, lowCount = 0;
      teamFiltered.forEach(function(iss) {
        if (iss.urgency === "critical") critCount++;
        else if (iss.urgency === "high") highCount++;
        else if (iss.urgency === "medium") medCount++;
        else if (iss.urgency === "low") lowCount++;
      });
      var total = teamFiltered.length || 1;
      var tooltipText = critCount + ' critical · ' + highCount + ' high · ' +
                        medCount + ' medium · ' + lowCount + ' low';
      mixEl.title = tooltipText;
      mixEl.innerHTML = '';
      if (critCount > 0) mixEl.innerHTML += '<i class="crit" style="width:' + (critCount/total*100) + '%"></i>';
      if (highCount > 0) mixEl.innerHTML += '<i class="high" style="width:' + (highCount/total*100) + '%"></i>';
      if (medCount > 0) mixEl.innerHTML += '<i class="med" style="width:' + (medCount/total*100) + '%"></i>';
      if (lowCount > 0) mixEl.innerHTML += '<i class="low" style="width:' + (lowCount/total*100) + '%"></i>';
    }

    band.querySelectorAll(".area").forEach(function(area) {
      var areaIssues = area.querySelectorAll(".issue");
      var areaVisible = 0;
      areaIssues.forEach(function(i) {
        if (i.style.display !== "none") areaVisible++;
      });
      area.style.display = areaVisible > 0 ? "" : "none";
      var areaN = area.querySelector(".area-n");
      if (areaN) areaN.textContent = areaVisible;
    });

    updateTeamFocus(band, teamId, filtered);

    if (hasActiveFilters()) {
      band.querySelectorAll(".trend").forEach(function(t) { t.style.opacity = "0.3"; });
    } else {
      band.querySelectorAll(".trend").forEach(function(t) { t.style.opacity = ""; });
    }

    if (visibleCount === 0 && issues.length > 0) {
      band.classList.add("filtered-out");
    } else {
      band.classList.remove("filtered-out");
    }
  });
}

var issuesTableBody;
var currentSort = {col: "urgency", dir: "asc"};

function buildAllIssuesTable() {
  var section = el("div", "section");
  section.id = "all-issues";

  var header = el("div", "section-header");
  header.innerHTML = '<div class="section-title">All Issues <span class="count">(' + d.all_issues.length + ')</span></div>';
  section.appendChild(header);

  var filterBar = el("div", "filter-bar");
  ["critical", "high", "medium", "low"].forEach(function(u) {
    var pill = el("button", "filter-pill");
    pill.textContent = URGENCY_SHORT[u];
    pill.addEventListener("click", function() {
      pill.classList.toggle("active");
      if (pill.classList.contains("active")) {
        pill.style.background = uc(u); pill.style.color = "#fff";
        if (activeUrgencies.indexOf(u) === -1) activeUrgencies.push(u);
      } else {
        pill.style.background = "transparent"; pill.style.color = "var(--text-muted)";
        activeUrgencies = activeUrgencies.filter(function(x) { return x !== u; });
      }
      applyAllFilters();
    });
    filterBar.appendChild(pill);
  });
  section.appendChild(filterBar);

  var table = el("table", "data-table");
  var cols = [
    {key: "expand", label: "", sortable: false},
    {key: "urgency", label: "Urgency", sortable: true},
    {key: "issue_number", label: "#", sortable: true},
    {key: "issue_title", label: "Title", sortable: true},
    {key: "primary_team", label: "Team", sortable: true},
    {key: "area", label: "Area", sortable: true},
    {key: "days_open", label: "Days", sortable: true},
    {key: "has_linked_pr", label: "PR", sortable: true},
    {key: "comment_count", label: "Comments", sortable: true}
  ];
  var thead = el("thead");
  var headRow = el("tr");
  cols.forEach(function(col) {
    var th = el("th");
    th.textContent = col.label;
    if (col.sortable) {
      th.innerHTML += ' <span class="sort-icon">&#9650;</span>';
      th.addEventListener("click", function() {
        if (currentSort.col === col.key) {
          currentSort.dir = currentSort.dir === "asc" ? "desc" : "asc";
        } else {
          currentSort.col = col.key;
          currentSort.dir = "asc";
        }
        thead.querySelectorAll("th").forEach(function(t) { t.classList.remove("sorted"); });
        th.classList.add("sorted");
        th.querySelector(".sort-icon").textContent = currentSort.dir === "asc" ? "▲" : "▼";
        rebuildIssuesTable();
      });
    }
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  issuesTableBody = el("tbody");
  table.appendChild(issuesTableBody);
  section.appendChild(table);

  rebuildIssuesTable();
  return section;
}

function rebuildIssuesTable() {
  if (!issuesTableBody) return;
  issuesTableBody.innerHTML = "";
  var issues = d.all_issues.filter(matchesFilters);

  issues.sort(function(a, b) {
    var col = currentSort.col;
    var dir = currentSort.dir === "asc" ? 1 : -1;
    if (col === "urgency") {
      return (URGENCY_ORDER[a.urgency] - URGENCY_ORDER[b.urgency]) * dir;
    }
    var av = a[col], bv = b[col];
    if (av == null) av = ""; if (bv == null) bv = "";
    if (typeof av === "number") return (av - bv) * dir;
    return String(av).localeCompare(String(bv)) * dir;
  });

  var openDetailRow = null;

  issues.forEach(function(issue) {
    var tr = el("tr");
    var prCell = issue.has_linked_pr ? '<svg width="16" height="16" viewBox="0 0 16 16" fill="#1A7F37"><path d="M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"/></svg>' : '<span style="color:var(--text-dim);">-</span>';
    var commentCell = issue.comment_count > 0 ? '<span style="font-variant-numeric:tabular-nums;">' + issue.comment_count + '</span>' : '<span style="color:var(--text-dim);">-</span>';

    tr.innerHTML =
      '<td><button class="expand-btn">&#9654;</button></td>' +
      '<td>' + makeUrgencyBadgeHTML(issue.urgency) + '</td>' +
      '<td><a href="' + esc(issue.issue_url) + '" target="_blank">#' + issue.issue_number + '</a></td>' +
      '<td><a href="' + esc(issue.issue_url) + '" target="_blank">' + esc(issue.issue_title) + '</a></td>' +
      '<td>' + makeTeamBadgeHTML(issue.primary_team) + '</td>' +
      '<td>' + (issue.area ? '<span class="area-badge">area:' + esc(issue.area) + '</span>' : '<span style="color:var(--text-dim);">-</span>') + '</td>' +
      '<td style="font-variant-numeric:tabular-nums;">' + issue.days_open + '</td>' +
      '<td>' + prCell + '</td>' +
      '<td>' + commentCell + '</td>';
    var expandBtn = tr.querySelector(".expand-btn");

    var detailTr = el("tr", "detail-row");
    var detailTd = el("td");
    detailTd.colSpan = 9;
    var summaryText = issue.summary || "";
    var recText = issue.recommendation || "";
    var detailHtml = '<div class="detail-content">';
    if (summaryText) {
      detailHtml += '<div class="detail-section"><div class="detail-section-label">Summary</div><div class="detail-section-text">' + esc(summaryText) + '</div></div>';
    }
    if (recText) {
      detailHtml += '<div class="detail-section"><div class="detail-section-label">Recommended Action</div><div class="detail-section-text">' + esc(recText) + '</div></div>';
    }
    detailHtml += '</div>';
    detailTd.innerHTML = detailHtml;
    detailTr.appendChild(detailTd);

    expandBtn.addEventListener("click", function() {
      if (openDetailRow && openDetailRow !== detailTr) {
        openDetailRow.classList.remove("open");
        openDetailRow.previousElementSibling.querySelector(".expand-btn").classList.remove("open");
      }
      expandBtn.classList.toggle("open");
      detailTr.classList.toggle("open");
      openDetailRow = detailTr.classList.contains("open") ? detailTr : null;
    });

    issuesTableBody.appendChild(tr);
    issuesTableBody.appendChild(detailTr);
  });
}
