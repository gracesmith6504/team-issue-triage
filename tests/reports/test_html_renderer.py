import json

from app.core.models import Urgency
from app.reports.renderers.html import _report_to_dict, render_html
from app.sources.enrichment import EnrichedIssue
from tests.reports.conftest import make_report, make_result


def test_report_to_dict_returns_dict():
    report = make_report()
    result = _report_to_dict(report)
    assert isinstance(result, dict)


def test_report_to_dict_summary_fields():
    report = make_report()
    result = _report_to_dict(report)
    assert result["summary"]["new_this_period"] == 5
    assert result["summary"]["by_urgency"]["critical"] == 1
    assert "Jul 28" in result["summary"]["period_label"]
    assert "Aug 3, 2026" in result["summary"]["period_label"]


def test_report_to_dict_urgency_enum_to_string():
    report = make_report()
    result = _report_to_dict(report)
    issue = result["critical_list"][0]
    assert issue["urgency"] == "critical"
    assert isinstance(issue["urgency"], str)


def test_report_to_dict_none_values_preserved():
    report = make_report(critical_list=[make_result(1, "test", confidence_flag=None)])
    result = _report_to_dict(report)
    assert result["critical_list"][0]["confidence_flag"] is None
    assert result["critical_list"][0]["secondary_team"] is None


def test_report_to_dict_secondary_team_present():
    report = make_report(
        critical_list=[
            make_result(1, "test", secondary_team="kata", secondary_confidence=0.65)
        ]
    )
    result = _report_to_dict(report)
    issue = result["critical_list"][0]
    assert issue["secondary_team"] == "kata"
    assert issue["secondary_confidence"] == 0.65


def test_report_to_dict_team_breakdown():
    report = make_report()
    result = _report_to_dict(report)
    assert "agent-ops" in result["team_breakdown"]
    assert result["team_breakdown"]["agent-ops"]["total"] == 3
    assert result["team_breakdown"]["agent-ops"]["trend"] == "+1"


def test_report_to_dict_duplicate_clusters():
    report = make_report()
    result = _report_to_dict(report)
    assert len(result["duplicate_clusters"]) == 1
    cluster = result["duplicate_clusters"][0]
    assert cluster["area"] == "sandbox"
    assert cluster["similarity_reason"] == "shared: namespace"
    assert len(cluster["issues"]) == 2


def test_report_to_dict_all_issues_field():
    report = make_report(
        all_issues=[
            make_result(1, "issue 1", urgency=Urgency.CRITICAL),
            make_result(2, "issue 2", urgency=Urgency.HIGH),
        ]
    )
    result = _report_to_dict(report)
    assert "all_issues" in result
    assert len(result["all_issues"]) == 2
    assert result["all_issues"][0]["issue_number"] == 1
    assert result["all_issues"][1]["issue_number"] == 2


def test_report_to_dict_is_json_serializable():
    report = make_report()
    result = _report_to_dict(report)
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    roundtrip = json.loads(serialized)
    assert roundtrip["summary"]["new_this_period"] == 5


def test_report_to_dict_builds_team_issues():
    report = make_report(
        all_issues=[
            make_result(1, "agent issue", team="agent-ops"),
            make_result(2, "safety issue", team="ai-safety"),
        ]
    )
    result = _report_to_dict(report)
    assert "team_issues" in result
    assert len(result["team_issues"]["agent-ops"]) == 1
    assert result["team_issues"]["agent-ops"][0]["number"] == 1
    assert len(result["team_issues"]["ai-safety"]) == 1


def test_report_to_dict_area_heatmap_is_sorted_list():
    report = make_report()
    result = _report_to_dict(report)
    assert isinstance(result["area_heatmap"], list)
    assert result["area_heatmap"][0]["area"] == "gateway"
    assert result["area_heatmap"][0]["current_count"] == 5


def test_report_to_dict_extracts_area_from_title():
    report = make_report(all_issues=[make_result(1, "feat(sandbox): add support")])
    result = _report_to_dict(report)
    assert result["all_issues"][0]["area"] == "sandbox"


def test_report_to_dict_adds_sparklines():
    result = _report_to_dict(make_report())
    assert "sparklines" in result
    assert len(result["sparklines"]["triage"]) == 7


def test_report_to_dict_uses_passed_sparklines():
    sparklines = {
        "triage": [1, 2, 3, 4, 5, 6, 7],
        "prs": [3, 3, 4, 4, 5, 5, 6],
        "blocked": [2, 2, 1, 1, 0, 0, 0],
        "velocity": [5, 6, 7, 8, 8, 9, 10],
    }
    result = _report_to_dict(make_report(), sparklines=sparklines)
    assert result["sparklines"]["triage"] == [1, 2, 3, 4, 5, 6, 7]
    assert result["sparklines"]["velocity"] == [5, 6, 7, 8, 8, 9, 10]


def test_report_to_dict_duplicate_cluster_short_fields():
    result = _report_to_dict(make_report())
    iss = result["duplicate_clusters"][0]["issues"][0]
    assert "number" in iss
    assert "title" in iss
    assert "url" in iss


# --- HTML output tests ---


def test_render_html_returns_valid_html():
    html = render_html(make_report())
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "</html>" in html


def test_render_html_fetches_from_api():
    html = render_html(make_report())
    assert "loadReport" in html
    assert "/api/v1/report" in html


def test_render_html_includes_all_teams():
    html = render_html(make_report())
    assert "agent-ops" in html
    assert "ai-safety" in html


def test_report_to_dict_includes_critical_issues():
    report = make_report(
        critical_list=[
            make_result(2518, "SPIFFE crash", urgency=Urgency.CRITICAL),
            make_result(2520, "sandbox fail", urgency=Urgency.HIGH),
        ]
    )
    data = _report_to_dict(report)
    numbers = [i["issue_number"] for i in data["critical_list"]]
    assert 2518 in numbers
    assert 2520 in numbers


def test_render_html_title():
    html = render_html(make_report())
    assert "OpenShell Overview" in html


def test_report_to_dict_preserves_special_chars():
    report = make_report(
        critical_list=[
            make_result(
                1, "</script><script>alert(1)</script>", urgency=Urgency.CRITICAL
            )
        ]
    )
    data = _report_to_dict(report)
    assert data["critical_list"][0]["issue_title"] == "</script><script>alert(1)</script>"


def test_render_html_urgency_badges_in_table():
    html = render_html(make_report())
    assert "CRIT" in html or "HIGH" in html or "MED" in html


def test_render_html_has_topbar():
    html = render_html(make_report())
    assert "topbar" in html
    assert "search-input" in html


def test_render_html_has_team_routing():
    html = render_html(make_report())
    assert "team-routing" in html
    assert "team-band" in html


def test_render_html_has_area_breakdown():
    html = render_html(make_report())
    assert "Area Breakdown" in html
    assert "area-bar-track" in html


def test_render_html_has_expandable_rows():
    html = render_html(make_report())
    assert "expand-btn" in html
    assert "detail-row" in html


def test_render_html_expandable_rows_use_summary():
    html = render_html(make_report())
    assert "Summary" in html
    assert "Recommended Action" in html


def test_render_html_no_chart_js():
    html = render_html(make_report())
    assert "chart.js" not in html
    assert "Chart(" not in html


def test_render_html_light_theme():
    html = render_html(make_report())
    assert "--bg-body: #f4f5f7" in html
    assert "#0F172A" not in html


def test_render_html_pr_health_absent_when_none():
    data = _report_to_dict(make_report(pr_health=None))
    assert data["pr_health"] is None


def test_render_html_pr_health_present_when_set():
    pr_data = {
        "total_open": 42,
        "awaiting_review": 5,
        "stale_14d": 3,
        "gator_coverage_pct": 60,
        "merge_velocity": 8,
        "merge_velocity_prev": 6,
        "avg_review_wait_days": 4.2,
        "age_distribution": {
            "lt_1w": {"count": 10, "label": "< 1 week"},
            "1_2w": {"count": 8, "label": "1-2 weeks"},
            "2_4w": {"count": 12, "label": "2-4 weeks"},
            "gt_1m": {"count": 12, "label": "> 1 month"},
        },
    }
    data = _report_to_dict(make_report(pr_health=pr_data))
    assert data["pr_health"]["total_open"] == 42


def test_render_html_vouch_absent_when_none():
    data = _report_to_dict(make_report(vouch_status=None))
    assert data["vouch_status"] is None


def test_render_html_vouch_present_when_set():
    vouch_data = {
        "total_pending": 3,
        "responded_in_7d": 1,
        "longest_wait_days": 45,
        "over_30d_count": 2,
        "pending_vouches": [
            {
                "author": "testuser",
                "discussion_number": 100,
                "url": "https://github.com/test/100",
                "wait_days": 45,
                "created_at": "2026-06-01T00:00:00Z",
            }
        ],
    }
    html = render_html(make_report(vouch_status=vouch_data))
    assert "Contributor Health" in html
    assert "Pending Vouches" in html


# --- Enrichment tests ---


def _make_enrichment(number, has_linked_pr=False):
    result = make_result(number, f"issue {number}")
    return EnrichedIssue(
        result=result,
        has_linked_pr=has_linked_pr,
    )


def test_render_html_without_enrichment_unchanged():
    html = render_html(make_report())
    assert "<!DOCTYPE html>" in html
    assert "loadReport" in html


def test_render_html_with_enrichment_adds_pr_field():
    enrichment = {1: _make_enrichment(1, has_linked_pr=True)}
    report = make_report(
        all_issues=[make_result(1, "test issue", urgency=Urgency.CRITICAL)]
    )
    data = _report_to_dict(report, enrichment=enrichment)
    assert data["all_issues"][0]["has_linked_pr"] is True


def test_render_html_shows_unassigned_for_none_team():
    html = render_html(
        make_report(no_team_list=[make_result(99, "orphan", team="none")])
    )
    assert "Unassigned" in html


def test_render_html_filter_pills():
    html = render_html(make_report())
    assert "filter-pill" in html
    assert "filter-banner" in html


def test_render_html_velocity_strip():
    pr_data = {
        "total_open": 10,
        "awaiting_review": 2,
        "stale_14d": 1,
        "gator_coverage_pct": 50,
        "merge_velocity": 5,
        "merge_velocity_prev": 3,
        "avg_review_wait_days": 2.0,
        "stuck_prs": [],
        "age_distribution": {
            "lt_1w": {"count": 5, "label": "< 1 week"},
            "1_2w": {"count": 2, "label": "1-2 weeks"},
            "2_4w": {"count": 2, "label": "2-4 weeks"},
            "gt_1m": {"count": 1, "label": "> 1 month"},
        },
    }
    html = render_html(make_report(pr_health=pr_data))
    assert "velocity-strip" in html


def test_template_directory_exists():
    from pathlib import Path
    import app.reports.renderers.html as html_mod

    template_dir = Path(html_mod.__file__).parent / "templates"
    assert template_dir.is_dir(), f"Template directory missing: {template_dir}"
    assert (template_dir / "base.html").is_file(), "base.html template missing"


def test_base_template_has_css():
    from pathlib import Path

    template_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "reports"
        / "renderers"
        / "templates"
        / "base.html"
    )
    content = template_path.read_text()
    assert "<style>" in content
    assert "--bg-body: #f4f5f7" in content
    assert "--urgency-critical:" in content
    assert "kpi-grid" in content
    assert "@media" in content


def test_base_template_has_refined_css():
    from pathlib import Path

    template_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "reports"
        / "renderers"
        / "templates"
        / "base.html"
    )
    content = template_path.read_text()
    assert '<style id="refined">' in content
    assert "REFINED VISUAL LAYER" in content
    assert "Inter Tight" in content
    assert "cubic-bezier" in content
    assert "--accent-soft:" in content


def test_all_component_files_exist():
    from pathlib import Path

    components_dir = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "reports"
        / "renderers"
        / "templates"
        / "components"
    )
    expected = [
        "shared.js",
        "topbar.js",
        "kpis.js",
        "alerts.js",
        "team_routing.js",
        "pr_health.js",
        "contributor_health.js",
        "area_breakdown.js",
        "issues_table.js",
        "duplicates.js",
        "footer.js",
    ]
    for name in expected:
        assert (components_dir / name).is_file(), f"Missing component: {name}"


def test_render_html_uses_jinja2_template():
    """Verify render_html delegates to Jinja2, not string replacement."""
    import app.reports.renderers.html as html_mod

    assert not hasattr(html_mod, "_HTML_TEMPLATE"), (
        "_HTML_TEMPLATE should be removed after Jinja2 migration"
    )


def test_render_html_end_to_end_structure():
    """Verify the full rendered output has all expected sections."""
    pr_data = {
        "total_open": 42,
        "awaiting_review": 5,
        "stale_14d": 3,
        "gator_coverage_pct": 60,
        "merge_velocity": 8,
        "merge_velocity_prev": 6,
        "avg_review_wait_days": 4.2,
        "stuck_prs": [],
        "codeowners": ["mrunalp"],
        "age_distribution": {
            "lt_1w": {"count": 10, "label": "< 1 week"},
            "1_2w": {"count": 8, "label": "1-2 weeks"},
            "2_4w": {"count": 12, "label": "2-4 weeks"},
            "gt_1m": {"count": 12, "label": "> 1 month"},
        },
    }
    vouch_data = {
        "total_pending": 3,
        "responded_in_7d": 1,
        "longest_wait_days": 45,
        "over_30d_count": 2,
        "pending_vouches": [
            {
                "author": "testuser",
                "discussion_number": 100,
                "url": "https://github.com/test/100",
                "wait_days": 45,
                "created_at": "2026-06-01T00:00:00Z",
            }
        ],
    }
    html = render_html(make_report(pr_health=pr_data, vouch_status=vouch_data))

    assert "<!DOCTYPE html>" in html
    assert "loadReport" in html
    assert "buildTopBar" in html
    assert "buildKPIs" in html
    assert "buildAlerts" in html
    assert "buildTeamRouting" in html
    assert "buildPRHealth" in html
    assert "buildContributorHealth" in html
    assert "buildAreaBreakdown" in html
    assert "buildAllIssuesTable" in html
    assert "buildDuplicates" in html
    assert "buildFooter" in html
    assert "OpenShell Overview" in html
    assert "--bg-body: #f4f5f7" in html
