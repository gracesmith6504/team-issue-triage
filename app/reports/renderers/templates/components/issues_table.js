var activeTeams = [];
var activeUrgencies = [];
var activeArea = "";
var searchQuery = "";

function matchesFilters(issue) {
  if (activeTeams.length && activeTeams.indexOf(issue.primary_team) === -1) return false;
  if (activeUrgencies.length && activeUrgencies.indexOf(issue.urgency) === -1) return false;
  if (activeArea && (issue.area || "") !== activeArea) return false;
  if (searchQuery) {
    var q = searchQuery.toLowerCase();
    var title = (issue.issue_title || issue.title || "").toLowerCase();
    var num = String(issue.issue_number || issue.number || "");
    if (title.indexOf(q) === -1 && num.indexOf(q) === -1) return false;
  }
  return true;
}

function applyAllFilters() {
  rebuildIssuesTable();
  var banner = document.getElementById("filter-banner");
  if (banner) {
    var tags = banner.querySelector(".filter-tags");
    tags.innerHTML = "";
    if (activeUrgencies.length || searchQuery || activeArea) {
      banner.classList.add("visible");
      activeUrgencies.forEach(function(u) {
        tags.innerHTML += '<span class="filter-tag">' + (URGENCY_SHORT[u] || u) + '</span>';
      });
      if (activeArea) {
        tags.innerHTML += '<span class="filter-tag">area:' + esc(activeArea) + '</span>';
      }
      if (searchQuery) {
        tags.innerHTML += '<span class="filter-tag">"' + esc(searchQuery) + '"</span>';
      }
    } else {
      banner.classList.remove("visible");
    }
  }
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
