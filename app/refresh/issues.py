import logging
from datetime import datetime, timezone

from app.cache.section_cache import SectionCache
from app.cache.sections import SECTION_TTLS, Section
from app.config import TriageConfig
from app.state.assessment_log import read_results_as_triage

logger = logging.getLogger(__name__)


def refresh_issues(config: TriageConfig, cache: SectionCache) -> None:
    from app.core.profiles import load_repo_config
    from app.reports.birds_eye import BirdsEyeReportGenerator
    from app.reports.periods import compute_period

    repo_config = load_repo_config(
        config.profile_name, profiles_dir=config.profiles_dir
    )
    now = datetime.now(timezone.utc)
    current_start, previous_start, period_label = compute_period(
        repo_config.reporting, now
    )

    current = [
        r
        for r in read_results_as_triage(
            config.assessment_log_path, start_date=current_start.isoformat()
        )
        if not r.closed
    ]
    previous = [
        r
        for r in read_results_as_triage(
            config.assessment_log_path,
            start_date=previous_start.isoformat(),
            end_date=current_start.isoformat(),
        )
        if not r.closed
    ]

    all_results = [
        r for r in read_results_as_triage(config.assessment_log_path) if not r.closed
    ]

    generator = BirdsEyeReportGenerator(
        current, previous, None, None, period_label, all_results=all_results
    )
    report = generator.generate(include_synthesis=False)

    # Fetch live issue metadata from GitHub: one bulk paginated call that gives us
    # current labels (for triage_needed count) and comment counts for all open issues.
    from app.reports.enrich import _fetch_issue_metadata

    try:
        issue_meta = _fetch_issue_metadata(repo_config.repo, config.github_token)
        report.summary.triage_needed = sum(
            1 for m in issue_meta.values() if "state:triage-needed" in m["labels"]
        )
        report.summary.total_open = len(issue_meta)
        for issue in report.all_issues:
            meta = issue_meta.get(issue.issue_number)
            if meta:
                issue.labels = meta["labels"]
                issue.comment_count = meta["comment_count"]
    except Exception:
        logger.exception("Live issue metadata fetch failed during issues refresh")

    enrichment = None
    try:
        from app.sources.enrichment import enrich_issues

        # Only enrich the current-period issues — enrichment makes one GitHub API call
        # per issue (to check for linked PRs). Historical issues show without PR linkage.
        enrichment = enrich_issues(current, config.github_token)
    except Exception:
        logger.exception("Enrichment failed during issues refresh")

    from app.reports.renderers.html import _report_to_dict

    data = _report_to_dict(report, enrichment=enrichment)

    issues_keys = (
        "summary",
        "critical_list",
        "team_breakdown",
        "area_heatmap",
        "area_unlabeled",
        "duplicate_clusters",
        "no_team_list",
        "all_issues",
        "team_issues",
        "generated_at",
    )
    issues_data = {k: data[k] for k in issues_keys if k in data}
    cache.set(Section.ISSUES, issues_data, SECTION_TTLS[Section.ISSUES])
    logger.info(
        "Issues section refreshed: %d current, %d previous", len(current), len(previous)
    )
