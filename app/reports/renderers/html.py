from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.reports.birds_eye import _extract_prefix, _infer_area_from_content
from app.reports.models import BirdsEyeReport

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=False,  # We handle XSS via json.dumps escaping, not HTML autoescape
)


def _get_template():
    return _jinja_env.get_template("base.html")


def _convert_value(obj):
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _convert_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_convert_value(i) for i in obj]
    return obj


def _get_area(title: str, summary: str) -> str:
    """Get area using same logic as birds_eye: prefix or keyword inference."""
    prefix = _extract_prefix(title)
    if prefix:
        return prefix
    # Infer from content if no prefix
    area = _infer_area_from_content(title, summary)
    return area if area != "uncategorized" else ""


def _report_to_dict(
    report: BirdsEyeReport,
    enrichment: dict | None = None,
    sparklines: dict[str, list[int]] | None = None,
) -> dict:
    raw = asdict(report)
    data = _convert_value(raw)

    now = datetime.now(timezone.utc)
    team_issues: dict[str, list] = {}
    seen_issue_numbers: set[int] = set()  # Deduplicate by issue number

    for issue in data.get("all_issues", []):
        issue_num = issue.get("issue_number", 0)

        # Deduplicate - skip if already seen
        if issue_num in seen_issue_numbers:
            continue
        seen_issue_numbers.add(issue_num)

        area_label = next(
            (
                lbl.split(":", 1)[1]
                for lbl in issue.get("labels", [])
                if lbl.startswith("area:")
            ),
            None,
        )
        issue["area"] = area_label or _get_area(
            issue.get("issue_title", ""), issue.get("summary", "")
        )
        created_at = issue.get("created_at", "")
        if created_at:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            issue["days_open"] = (now - created).days
        else:
            issue["days_open"] = 0
        issue["has_linked_pr"] = False

        summary = issue.get("summary", "")

        team = issue.get("primary_team", "none")
        team_issues.setdefault(team, []).append(
            {
                "number": issue_num,
                "title": issue["issue_title"],
                "url": issue["issue_url"],
                "urgency": issue["urgency"],
                "issue_number": issue_num,
                "issue_title": issue["issue_title"],
                "issue_url": issue["issue_url"],
                "author_login": issue.get("author_login", ""),
                "author_association": issue.get("author_association", "NONE"),
                "days_open": issue.get("days_open", 0),
                "has_linked_pr": issue.get("has_linked_pr", False),
                "created_at": issue.get("created_at", ""),
                "summary": summary,
                "labels": issue.get("labels", []),
                "comment_count": issue.get("comment_count", 0),
            }
        )

    if enrichment:
        for key in ("critical_list", "no_team_list", "all_issues"):
            for issue in data.get(key, []):
                enr = enrichment.get(issue["issue_number"])
                if enr:
                    issue["has_linked_pr"] = enr.has_linked_pr
                    issue["linked_pr_url"] = enr.linked_pr_url
                    issue["linked_pr_draft"] = enr.linked_pr_draft

        # Apply enrichment to team_issues as well
        for team_id, issues in team_issues.items():
            for issue in issues:
                enr = enrichment.get(issue["issue_number"])
                if enr:
                    issue["has_linked_pr"] = enr.has_linked_pr
                    issue["linked_pr_url"] = enr.linked_pr_url
                    issue["linked_pr_draft"] = enr.linked_pr_draft
        for cluster in data.get("duplicate_clusters", []):
            for issue in cluster.get("issues", []):
                enr = enrichment.get(issue["issue_number"])
                if enr:
                    issue["has_linked_pr"] = enr.has_linked_pr
                    issue["linked_pr_url"] = enr.linked_pr_url
                    issue["linked_pr_draft"] = enr.linked_pr_draft

    area_list = []
    for area_name, trend in data.get("area_heatmap", {}).items():
        trend["area"] = area_name
        area_list.append(trend)
    area_list.sort(key=lambda x: x["current_count"], reverse=True)

    total_open = data.get("summary", {}).get("total_open", 0)
    area_sum = sum(a["current_count"] for a in area_list)

    for cluster in data.get("duplicate_clusters", []):
        for iss in cluster.get("issues", []):
            iss["number"] = iss.get("issue_number", 0)
            iss["title"] = iss.get("issue_title", "")
            iss["url"] = iss.get("issue_url", "")

    data["team_issues"] = team_issues
    data["area_heatmap"] = area_list
    data["area_unlabeled"] = max(0, total_open - area_sum)
    data["sparklines"] = sparklines or {
        "triage": [0, 0, 0, 0, 0, 0, 0],
        "prs": [0, 0, 0, 0, 0, 0, 0],
        "blocked": [0, 0, 0, 0, 0, 0, 0],
        "velocity": [0, 0, 0, 0, 0, 0, 0],
    }

    # Attach synthesis data to team_breakdown
    if data.get("team_synthesis"):
        for team_id, team in data.get("team_breakdown", {}).items():
            synth = data["team_synthesis"].get(team_id)
            if synth:
                team["synthesis"] = {
                    "focus_summary": synth.get("focus_summary", ""),
                    "actions": synth.get("actions", []),
                    "claims": synth.get("claims"),
                    "structured_actions": synth.get("structured_actions"),
                    "generated_at": synth.get("generated_at", ""),
                    "covered_issues": synth.get("covered_issues", 0),
                    "model": synth.get("model", ""),
                }

    return data


def render_html(
    report: BirdsEyeReport,
    enrichment: dict | None = None,
    sparklines: dict[str, list[int]] | None = None,
) -> str:
    data = _report_to_dict(report, enrichment, sparklines)
    report_json = json.dumps(data, indent=2).replace("<", "\\u003c")
    template = _get_template()
    return template.render(report_json=report_json)


def render_shell() -> str:
    template = _get_template()
    return template.render()
