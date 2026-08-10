function buildFooter() {
  var footer = el("div", "footer");
  var genDate = d.generated_at ? new Date(d.generated_at).toLocaleDateString('en-US', {year: 'numeric', month: 'short', day: 'numeric'}) : 'unknown';
  footer.innerHTML = 'OpenShell Overview &middot; Generated ' + genDate + ' &middot; <a href="https://github.com/gracesmith6504/team-issue-triage" target="_blank">team-issue-triage</a>';
  return footer;
}
