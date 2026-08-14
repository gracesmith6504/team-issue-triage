import logging
from datetime import timedelta, timezone, datetime

from app.cache.section_cache import SectionCache
from app.cache.sections import SECTION_TTLS, Section
from app.config import TriageConfig
from app.state.assessment_log import read_results_as_triage

logger = logging.getLogger(__name__)


def refresh_issues(config: TriageConfig, cache: SectionCache) -> None:
    results = read_results_as_triage(config.assessment_log_path)
    current = [r for r in results if not r.closed]

    now = datetime.now(timezone.utc)
    previous_start = now - timedelta(days=60)
    current_start = now - timedelta(days=30)
    previous = [r for r in read_results_as_triage(
        config.assessment_log_path,
        start_date=previous_start.isoformat(),
        end_date=current_start.isoformat(),
    ) if not r.closed]

    from app.reports.birds_eye import BirdsEyeReportGenerator
    generator = BirdsEyeReportGenerator(current, previous, None, None, "All time")
    report = generator.generate(include_synthesis=False)

    enrichment = None
    try:
        from app.sources.enrichment import enrich_issues
        enrichment = enrich_issues(current, config.github_token)
    except Exception:
        logger.exception("Enrichment failed during issues refresh")

    from app.reports.renderers.html import _report_to_dict
    data = _report_to_dict(report, enrichment=enrichment)

    issues_keys = (
        "summary", "critical_list", "team_breakdown", "area_heatmap",
        "area_unlabeled", "duplicate_clusters", "no_team_list",
        "all_issues", "team_issues", "generated_at",
    )
    issues_data = {k: data[k] for k in issues_keys if k in data}
    cache.set(Section.ISSUES, issues_data, SECTION_TTLS[Section.ISSUES])
    logger.info("Issues section refreshed: %d issues", len(current))
