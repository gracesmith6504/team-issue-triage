import json

from app.core.models import Urgency
from app.reports.models import DuplicateCluster
from app.reports.renderers.html import _report_to_dict, render_html
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
    assert result["summary"]["period_label"] == "Jul 28 – Aug 3, 2026"


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


# --- HTML output tests ---


def test_render_html_returns_valid_html():
    html = render_html(make_report())
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "</html>" in html


def test_render_html_embeds_report_data():
    html = render_html(make_report())
    assert "REPORT_DATA" in html
    assert '"new_this_period": 5' in html


def test_render_html_includes_chart_js_cdn():
    html = render_html(make_report())
    assert "cdn.jsdelivr.net/npm/chart.js" in html


def test_render_html_includes_all_teams():
    html = render_html(make_report())
    assert "agent-ops" in html
    assert "ai-safety" in html


def test_render_html_includes_critical_issues():
    report = make_report(
        critical_list=[
            make_result(2518, "SPIFFE crash", urgency=Urgency.CRITICAL),
            make_result(2520, "sandbox fail", urgency=Urgency.HIGH),
        ]
    )
    html = render_html(report)
    assert "2518" in html
    assert "2520" in html


def test_render_html_no_team_issues_present():
    report = make_report(no_team_list=[make_result(99, "orphan issue", team="none")])
    html = render_html(report)
    assert "orphan issue" in html
    assert "Needs Triage" in html


def test_render_html_duplicate_clusters_present():
    cluster = DuplicateCluster(
        area="gateway",
        issues=[make_result(5, "gw bug 1"), make_result(6, "gw bug 2")],
        similarity_reason="shared: gateway, tls",
    )
    html = render_html(make_report(duplicate_clusters=[cluster]))
    assert "gateway" in html
    assert "shared: gateway, tls" in html


def test_render_html_hides_empty_critical():
    html = render_html(make_report(critical_list=[]))
    assert "Action Required" not in html


def test_render_html_hides_empty_duplicates():
    html = render_html(make_report(duplicate_clusters=[]))
    assert "Potential Duplicates" not in html


def test_render_html_hides_empty_no_team():
    html = render_html(make_report(no_team_list=[]))
    assert "Needs Triage" not in html


def test_render_html_title():
    html = render_html(make_report())
    assert "OpenShell Triage Overview" in html
