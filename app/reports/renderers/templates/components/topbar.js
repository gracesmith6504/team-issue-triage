function _timeAgo(isoStr) {
  if (!isoStr) return "unknown";
  var mins = Math.round((new Date() - new Date(isoStr)) / 60000);
  if (mins < 2) return "just now";
  if (mins < 60) return mins + "m ago";
  var hrs = Math.round(mins / 60);
  if (hrs < 24) return hrs + "h ago";
  var days = Math.round(hrs / 24);
  return days + "d ago";
}

function buildTopBar() {
  var bar = document.getElementById("topbar");

  var left = el("div", "topbar-left");

  var sections = (d._meta && d._meta.sections) || {};
  var issuesMeta = sections["issues"];
  var freshnessLabel = issuesMeta
    ? "Issues: " + _timeAgo(issuesMeta.generated_at)
    : (d.generated_at ? "Updated: " + _timeAgo(d.generated_at) : "Loading...");

  var SECTION_LABELS = {
    "issues": "Issues", "pr_health": "PR Health",
    "vouch": "Vouches", "synthesis": "Summaries", "metrics": "Metrics"
  };
  var tooltipRows = Object.keys(SECTION_LABELS).filter(function(k) { return sections[k]; }).map(function(k) {
    return '<div style="display:flex;justify-content:space-between;gap:20px">' +
      '<span>' + SECTION_LABELS[k] + '</span><span style="opacity:0.75">' + _timeAgo(sections[k].generated_at) + '</span></div>';
  }).join("");

  var hintMarkup = tooltipRows
    ? '<span class="hint-wrap"><span class="hint-trigger">i</span><span class="hint-popup hint-popup-down">' + tooltipRows + '</span></span>'
    : "";

  left.innerHTML = '<a href="https://github.com/NVIDIA/OpenShell" target="_blank" class="topbar-title">OpenShell Overview</a>' +
    '<span class="topbar-period">' + freshnessLabel + hintMarkup + '</span>';
  bar.appendChild(left);

  var center = el("div", "topbar-center");

  var dateGroup = el("div", "seg-group");
  ["24h", "7d", "30d", "All"].forEach(function(range) {
    var pill = el("button", "date-pill" + (state.dateRange === range ? " active" : ""));
    pill.textContent = range;
    pill.addEventListener("click", function() {
      state.dateRange = range;
      saveState(state);
      bar.querySelectorAll(".date-pill").forEach(function(p) { p.classList.remove("active"); });
      pill.classList.add("active");
      applyAllFilters();
    });
    dateGroup.appendChild(pill);
  });
  center.appendChild(dateGroup);

  var typeGroup = el("div", "seg-group");
  ["Any", "Bugs", "Features"].forEach(function(filter) {
    var pill = el("button", "type-pill" + (state.issueTypeFilter === filter ? " active" : ""));
    pill.textContent = filter;
    pill.addEventListener("click", function() {
      state.issueTypeFilter = filter;
      saveState(state);
      bar.querySelectorAll(".type-pill").forEach(function(p) { p.classList.remove("active"); });
      pill.classList.add("active");
      applyAllFilters();
    });
    typeGroup.appendChild(pill);
  });
  center.appendChild(typeGroup);

  bar.appendChild(center);

  var right = el("div", "topbar-right");

  var filterWrap = el("div", "team-filter-wrap");
  var filterBtn = el("button", "team-filter-btn");
  filterBtn.innerHTML = 'Jump to team <span class="chevron">&#9660;</span>';
  var dropdown = el("div", "team-dropdown");
  var teams = Object.keys(d.team_breakdown);
  teams.forEach(function(t) {
    var lbl = el("label");
    lbl.style.cursor = "pointer";
    lbl.innerHTML = makeTeamBadgeHTML(t);
    lbl.addEventListener("click", function(e) {
      e.stopPropagation();
      dropdown.classList.remove("open");
      filterBtn.classList.remove("open");
      var band = document.querySelector('.team-band[data-team="' + t + '"]');
      if (band) {
        band.open = true;
        // Wait for details to open, then scroll with offset for sticky topbar
        setTimeout(function() {
          var rect = band.getBoundingClientRect();
          var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
          var targetY = rect.top + scrollTop - 70; // 70px offset for sticky topbar
          window.scrollTo({top: targetY, behavior: 'smooth'});
        }, 50);
      }
    });
    dropdown.appendChild(lbl);
  });
  filterBtn.addEventListener("click", function(e) {
    e.stopPropagation();
    filterBtn.classList.toggle("open");
    dropdown.classList.toggle("open");
  });
  document.addEventListener("click", function() { filterBtn.classList.remove("open"); dropdown.classList.remove("open"); });
  filterWrap.appendChild(filterBtn);
  filterWrap.appendChild(dropdown);
  right.appendChild(filterWrap);

  var allUsers = (function() {
    var set = {};
    (d.all_issues || []).forEach(function(i) { if (i.author_login) set[i.author_login] = 1; });
    var prs = (d.pr_health && d.pr_health.all_open_pr_summaries) || [];
    prs.forEach(function(pr) {
      if (pr.author) set[pr.author] = 1;
      (pr.participants || []).forEach(function(p) { if (p) set[p] = 1; });
    });
    var vouches = (d.vouch_status && d.vouch_status.pending_vouches) || [];
    vouches.forEach(function(v) { if (v.author) set[v.author] = 1; });
    return Object.keys(set).sort(function(a, b) { return a.toLowerCase().localeCompare(b.toLowerCase()); });
  })();

  var searchWrap = el("div", "search-wrap");
  var searchInput = el("input", "search-input");
  searchInput.type = "text"; searchInput.placeholder = "Search issues or @user...";
  var userDropdown = el("div", "user-dropdown");

  function _showUserDropdown(query) {
    userDropdown.innerHTML = "";
    var q = query.toLowerCase();
    var matches = allUsers.filter(function(u) { return u.toLowerCase().indexOf(q) !== -1; });
    if (!matches.length) { userDropdown.classList.remove("open"); return; }
    matches.slice(0, 8).forEach(function(user) {
      var opt = el("div", "user-option");
      opt.textContent = "@" + user;
      opt.addEventListener("mousedown", function(e) {
        e.preventDefault();
        searchInput.value = "@" + user;
        searchQuery = "@" + user;
        userDropdown.classList.remove("open");
        applyAllFilters();
      });
      userDropdown.appendChild(opt);
    });
    userDropdown.classList.add("open");
  }

  var searchTimeout;
  searchInput.addEventListener("input", function() {
    clearTimeout(searchTimeout);
    var val = searchInput.value;
    if (val.indexOf("@") === 0 && val.length > 1) {
      _showUserDropdown(val.substring(1));
    } else {
      userDropdown.classList.remove("open");
    }
    searchTimeout = setTimeout(function() {
      searchQuery = val;
      applyAllFilters();
    }, 200);
  });
  searchInput.addEventListener("blur", function() {
    setTimeout(function() { userDropdown.classList.remove("open"); }, 150);
  });

  searchWrap.appendChild(searchInput);
  searchWrap.appendChild(userDropdown);
  right.appendChild(searchWrap);

  bar.appendChild(right);
}
