function _countVouchedInRange() {
  var completed = (d.vouch_status && d.vouch_status.completed_vouches) || [];
  var cutoffMs = getFilterCutoffMs();
  if (!cutoffMs) return completed.length;
  var cutoffDate = Date.now() - cutoffMs;
  return completed.filter(function(c) {
    return new Date(c.vouched_at).getTime() >= cutoffDate;
  }).length;
}

function _renderContribTiles(totalPending, longestWait) {
  var tiles = document.querySelectorAll("#contributor-health .metric-tile");
  if (tiles.length >= 3) {
    tiles[0].querySelector(".tile-value").textContent = totalPending;
    var vouchedCount = _countVouchedInRange();
    tiles[1].querySelector(".tile-value").textContent = vouchedCount;
    var label1 = tiles[1].querySelector(".tile-label");
    var filterLabel = state.dateRange && state.dateRange !== "All" ? state.dateRange : "All Time";
    if (label1) label1.textContent = "Vouched (" + filterLabel + ")";
    tiles[2].querySelector(".tile-value").textContent = longestWait + " days";
  }
}

function _renderVouchList(filteredVouches) {
  var VOUCH_INITIAL_SHOW = 5;
  var list = document.getElementById("vouch-list-container");
  if (!list) return;
  var filteredAuthors = {};
  filteredVouches.forEach(function(v) { filteredAuthors[v.author] = true; });
  var visibleCount = 0;
  list.querySelectorAll(".vouch-row").forEach(function(row) {
    var author = row.dataset.author;
    if (filteredAuthors[author]) {
      visibleCount++;
      row.style.display = visibleCount <= VOUCH_INITIAL_SHOW ? "" : "none";
    } else {
      row.style.display = "none";
    }
  });
  var wrap = list.closest(".section-collapse") || list.parentElement;
  var viewMore = wrap.querySelector("a[style*='cursor:pointer']");
  if (viewMore) {
    var totalHidden = visibleCount - VOUCH_INITIAL_SHOW;
    if (totalHidden > 0) {
      viewMore.style.display = "";
      viewMore.textContent = "View " + totalHidden + " more";
    } else {
      viewMore.style.display = "none";
    }
  }
}

function _renderBlockedPRs(filteredBlocked) {
  var section = document.getElementById("contributor-health");
  if (!section) return;
  var filteredAuthors = {};
  filteredBlocked.forEach(function(bp) { filteredAuthors[bp.author] = true; });
  section.querySelectorAll(".blocked-contributor").forEach(function(card) {
    var authorLink = card.querySelector(".bc-author a");
    if (!authorLink) return;
    var author = authorLink.textContent.replace("@", "");
    card.style.display = filteredAuthors[author] ? "" : "none";
  });
}

function buildContributorHealth() {
  var section = el("div", "section");
  section.id = "contributor-health";

  var wrap = el("details", "section-collapse");
  wrap.open = state.collapsed["contributor-health"] !== false;
  var summary = el("summary");
  summary.innerHTML = '<div class="section-title">Contributor Health</div>';
  wrap.appendChild(summary);

  var tiles = el("div", "metric-tiles metric-tiles-3");
  var tData = [
    {value: d.vouch_status.total_pending, label: "Pending Vouches", color: "var(--urgency-high)", hint: "New contributors need a vouch from an existing contributor before PRs can merge"},
    {value: ((d.vouch_status.completed_vouches) || []).length, label: "Vouched (All Time)", color: "var(--status-healthy)"},
    {value: d.vouch_status.longest_wait_days + " days", label: "Longest Wait", color: "var(--status-blocked)"}
  ];
  tData.forEach(function(t) {
    var tile = el("div", "metric-tile");
    tile.style.borderLeftColor = t.color;
    tile.innerHTML = '<div class="tile-value" style="color:' + t.color + '">' + t.value + '</div><div class="tile-label">' + esc(t.label) + (t.hint ? hintHTML(t.hint) : '') + '</div>';
    tiles.appendChild(tile);
  });
  wrap.appendChild(tiles);

  var hsTitle = el("div", "stacked-bar-label", "Pending Vouch Requests");
  wrap.appendChild(hsTitle);

  var VOUCH_INITIAL_SHOW = 5;
  var vouchList = el("div", "vouch-list");
  vouchList.id = "vouch-list-container";
  var allVouches = d.vouch_status.pending_vouches;
  allVouches.forEach(function(v, idx) {
    var isDismissed = state.dismissed.indexOf(v.author) !== -1;
    var row = el("div", "vouch-row" + (isDismissed ? " dismissed" : ""));
    row.dataset.author = v.author;
    if (idx >= VOUCH_INITIAL_SHOW) row.style.display = "none";
    var waitText = v.wait_days === 0 ? "today" : v.wait_days === 1 ? "1 day" : v.wait_days + " days";
    row.innerHTML =
      '<span class="vouch-author"><a href="https://github.com/' + esc(v.author) + '" target="_blank">@' + esc(v.author) + '</a></span>' +
      '<span class="vouch-link"><a href="' + esc(v.url) + '" target="_blank">#' + v.discussion_number + '</a></span>' +
      '<span class="vouch-wait">' + waitText + '</span>';
    var dismissBtn = el("button", "dismiss-btn", "✕");
    dismissBtn.title = "Dismiss";
    dismissBtn.addEventListener("click", function() {
      if (state.dismissed.indexOf(v.author) === -1) state.dismissed.push(v.author);
      saveState(state);
      row.classList.add("dismissed");
      updateDismissedCount();
    });
    row.appendChild(dismissBtn);
    vouchList.appendChild(row);
  });
  wrap.appendChild(vouchList);

  var vouchExpanded = false;
  var remaining = allVouches.length - VOUCH_INITIAL_SHOW;
  if (remaining > 0) {
    var viewMoreLink = el("a");
    viewMoreLink.textContent = "View " + remaining + " more";
    viewMoreLink.style.cssText = "color:var(--accent);cursor:pointer;text-decoration:none;font-size:13px;font-weight:500;display:inline-block;margin-top:6px;";
    viewMoreLink.addEventListener("click", function() {
      vouchExpanded = !vouchExpanded;
      var rows = vouchList.querySelectorAll(".vouch-row");
      rows.forEach(function(r, i) {
        if (i >= VOUCH_INITIAL_SHOW) r.style.display = vouchExpanded ? "" : "none";
      });
      viewMoreLink.textContent = vouchExpanded ? "Show less" : "View " + remaining + " more";
    });
    wrap.appendChild(viewMoreLink);
  }

  var controls = el("div", "vouch-controls");
  var showDismissed = el("a");
  showDismissed.textContent = "Show dismissed (" + state.dismissed.length + ")";
  if (state.dismissed.length === 0) showDismissed.style.display = "none";
  showDismissed.addEventListener("click", function() {
    state.dismissed = [];
    saveState(state);
    vouchList.querySelectorAll(".vouch-row").forEach(function(r) { r.classList.remove("dismissed"); });
    updateDismissedCount();
  });
  controls.appendChild(showDismissed);
  wrap.appendChild(controls);

  function updateDismissedCount() {
    showDismissed.textContent = "Show dismissed (" + state.dismissed.length + ")";
    showDismissed.style.display = state.dismissed.length > 0 ? "" : "none";
  }

  wrap.appendChild(el("div", "vouch-note", "Items can be dismissed if the team has intentionally deferred a vouch decision."));

  var blockedPRs = d.vouch_status.blocked_prs || [];
  if (blockedPRs.length) {
    var bpTitle = el("div", "stacked-bar-label", "PRs Blocked by Missing Vouch");
    wrap.appendChild(bpTitle);
    blockedPRs.forEach(function(bp) {
      var row = el("div", "blocked-contributor");
      row.innerHTML =
        '<div class="bc-header"><span class="bc-author"><a href="https://github.com/' + esc(bp.author) + '" target="_blank">@' + esc(bp.author) + '</a></span></div>' +
        '<div class="bc-meta">PR <a href="' + esc(bp.pr_url) + '" target="_blank">#' + bp.pr_number + '</a>: ' + esc(bp.pr_title) + ' - vouch pending ' + bp.vouch_wait_days + ' days</div>' +
        '<div class="bc-links"><a href="' + esc(bp.pr_url) + '" target="_blank">View PR</a><a href="' + esc(bp.vouch_url) + '" target="_blank">Vouch Discussion</a></div>';
      wrap.appendChild(row);
    });
  }

  wrap.addEventListener("toggle", function() { state.collapsed["contributor-health"] = wrap.open; saveState(state); });
  section.appendChild(wrap);
  return section;
}
