var DATE_LABELS = {
  "7d": "Last 7 Days",
  "14d": d.summary.period_label,
  "30d": d.summary.period_label
};

function buildTopBar() {
  var bar = document.getElementById("topbar");

  var left = el("div", "topbar-left");

  // Format timestamp
  var lastUpdated = 'Loading...';
  if (d.generated_at) {
    try {
      var date = new Date(d.generated_at);
      lastUpdated = date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      });
    } catch (e) {
      lastUpdated = 'Unknown';
    }
  }

  left.innerHTML = '<a href="https://github.com/NVIDIA/OpenShell" target="_blank" class="topbar-title">OpenShell Overview</a><span class="topbar-period">Last updated: ' + lastUpdated + '</span>';
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

  var searchInput = el("input", "search-input");
  searchInput.type = "text"; searchInput.placeholder = "Search issues...";
  var searchTimeout;
  searchInput.addEventListener("input", function() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(function() {
      searchQuery = searchInput.value;
      applyAllFilters();
    }, 200);
  });
  right.appendChild(searchInput);

  bar.appendChild(right);
}
