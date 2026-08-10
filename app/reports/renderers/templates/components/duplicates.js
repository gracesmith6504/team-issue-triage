function buildDuplicates() {
  if (!d.duplicate_clusters || !d.duplicate_clusters.length) return el("div");
  var section = el("div", "section");
  var wrap = el("details", "section-collapse");
  wrap.open = state.collapsed["duplicates"] !== false;
  var summary = el("summary");
  summary.innerHTML = '<div class="section-title">Potential Duplicates <span class="count">(' + d.duplicate_clusters.length + ' clusters)</span></div>';
  wrap.appendChild(summary);

  d.duplicate_clusters.forEach(function(cluster) {
    var card = el("div", "cluster-card");
    card.innerHTML = '<div class="cluster-reason">' + esc(cluster.similarity_reason) + '</div>';
    cluster.issues.forEach(function(iss) {
      var issRow = el("div", "cluster-issue");
      issRow.innerHTML = makeUrgencyBadgeHTML(iss.urgency) +
        ' <a href="' + esc(iss.url || iss.issue_url) + '" target="_blank">#' + (iss.number || iss.issue_number) + '</a> ' +
        '<span style="color:var(--text-secondary);">' + esc(iss.title || iss.issue_title) + '</span>';
      card.appendChild(issRow);
    });
    wrap.appendChild(card);
  });

  wrap.addEventListener("toggle", function() { state.collapsed["duplicates"] = wrap.open; saveState(state); });
  section.appendChild(wrap);
  return section;
}
