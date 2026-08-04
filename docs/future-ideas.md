# Future Ideas

Backlog of enhancements discussed but not yet planned. Pick these up as follow-on work.

## GitHub Action Wrapper
Package the triage agent as a reusable GitHub Action so any repo can add automated issue triage with one workflow file. Lowest friction path for NVIDIA upstream adoption — no cluster needed, runs in their existing CI.

## Slack Notifications After Triage
Post a dashboard summary to a Slack channel after each triage cycle. Infrastructure already exists in `app/notifications/` (SlackWebhookAdapter, NotificationRouter). Wire the web server's triage cycle to send a digest after each run.

## NVIDIA Upstream Proposal
Pitch the tool to NVIDIA for OpenShell's own issue triage. Package as a GitHub Action (see above) for easiest adoption. OpenShell has 289+ open issues and 5-8 new daily — manual triage is a pain point.

## Per-Team Dashboard URLs
Add routes like `GET /team/ai-safety` that serve a pre-filtered dashboard for one team. Useful for team-specific bookmarks and Slack channel topic links.

## Area Heatmap Visualization
The `area_heatmap` data exists in `BirdsEyeReport` (computed in `birds_eye.py` lines 132-160) but isn't rendered in the HTML template. Visualize as a grid/treemap showing which code areas have the most activity and trending direction.

## Recommendation Field Display
`TriageResult.recommendation` is the most actionable field the LLM produces (specific next steps for each issue) but isn't shown in the dashboard. Add an expandable section on each issue card.

## Team Trend Sparklines
`TeamSummary.trend` data exists but is only shown as "+1" / "-2" / "flat" text. Add small sparkline charts showing team workload over multiple periods.

## Authentication / RBAC
Add authentication to the dashboard Route. Options: OpenShift OAuth proxy sidecar, or simple token-based auth via a shared secret. Currently the Route is open to anyone who can reach it.

## Multi-Repo Support
Deploy one dashboard instance that monitors multiple repositories (not just OpenShell). The `WATCH_REPOS` config already accepts a comma-separated list — the dashboard would need repo-level filtering in the UI.

## Historical Trend Dashboard
Store weekly report snapshots and show trends over time — total issue count, team workload, resolution rates. Requires a small schema for historical data.
