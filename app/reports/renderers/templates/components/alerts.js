function buildAlerts() {
  var strip = el("div", "alert-strip");
  var highCount = d.summary.by_urgency.high || 0;
  var alertData = [
    {key: "issues", color: "#d1242f", text: '<strong>' + highCount + '</strong> high-urgency issues this period'}
  ];

  if (d.pr_health) {
    var staleCount = d.pr_health.stale_14d || 0;
    alertData.push({key: "prs", color: "#d4a015", text: '<strong>' + staleCount + '</strong> PRs stale for 14+ days'});
  }

  if (d.vouch_status) {
    var vouchCount = d.vouch_status.total_pending || 0;
    var longestVouch = d.vouch_status.pending_vouches.length ? d.vouch_status.pending_vouches[0] : null;
    var blockedPRs = d.vouch_status.blocked_prs || [];
    var vouchText = '<strong>' + vouchCount + '</strong> contributors waiting for vouch';
    if (longestVouch) vouchText += ' - longest: <a href="' + esc(longestVouch.url) + '" target="_blank">@' + esc(longestVouch.author) + '</a> (' + longestVouch.wait_days + ' days)';
    if (blockedPRs.length) vouchText += ' - <strong>' + blockedPRs.length + '</strong> PR' + (blockedPRs.length > 1 ? 's' : '') + ' blocked';
    alertData.push({key: "vouches", color: "#e16f24", text: vouchText});
  }

  alertData.forEach(function(a) {
    var line = el("div", "alert-line");
    line.dataset.alert = a.key;
    line.innerHTML = '<span class="alert-dot" style="background:' + a.color + ';"></span>' + a.text;
    strip.appendChild(line);
  });
  return strip;
}
