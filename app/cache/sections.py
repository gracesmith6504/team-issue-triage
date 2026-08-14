from enum import Enum


class Section(str, Enum):
    ISSUES = "issues"
    PR_HEALTH = "pr_health"
    VOUCH = "vouch"
    SYNTHESIS = "synthesis"
    METRICS = "metrics"
    ENRICHMENT = "enrichment"


SECTION_TTLS = {
    Section.ISSUES: 7200,
    Section.PR_HEALTH: 14400,
    Section.VOUCH: 14400,
    Section.SYNTHESIS: 86400,
    Section.METRICS: 3600,
    Section.ENRICHMENT: 7200,
}
