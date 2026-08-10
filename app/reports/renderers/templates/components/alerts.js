function buildAlerts() {
  var strip = el("div", "alert-strip");
  var highCount = d.summary.by_urgency.high || 0;
  var alertData = [
    {color: "#d1242f", text: '<strong>' + highCount + '</strong> high-urgency issues this period'}
  ];

  if (d.pr_health) {
    var staleCount = d.pr_health.stale_14d || 0;
    var longestStuck = d.pr_health.stuck_prs.length ? d.pr_health.stuck_prs[0] : null;
    alertData.push({color: "#d4a015", text: '<strong>' + staleCount + '</strong> PRs stale for 14+ days' + (longestStuck ? ' - oldest: <a href="' + esc(longestStuck.url) + '" target="_blank">#' + longestStuck.number + '</a> (' + longestStuck.days_open + ' days)' : '')});
  }

  if (d.vouch_status) {
    var vouchCount = d.vouch_status.total_pending || 0;
    var longestVouch = d.vouch_status.pending_vouches.length ? d.vouch_status.pending_vouches[d.vouch_status.pending_vouches.length - 1] : null;
    alertData.push({color: "#e16f24", text: '<strong>' + vouchCount + '</strong> contributors waiting for vouch' + (longestVouch ? ' - longest: <a href="' + esc(longestVouch.url) + '" target="_blank">@' + esc(longestVouch.author) + '</a> (' + longestVouch.wait_days + ' days)' : '')});
  }

  alertData.forEach(function(a) {
    var line = el("div", "alert-line");
    line.innerHTML = '<span class="alert-dot" style="background:' + a.color + ';"></span>' + a.text;
    strip.appendChild(line);
  });
  return strip;
}
