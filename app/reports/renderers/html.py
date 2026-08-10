from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

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


_AREA_RE = re.compile(r"^(?:feat|fix|bug|chore|docs|refactor|test|ci)\(([^)]+)\):\s*")


def _extract_area(title: str) -> str:
    m = _AREA_RE.match(title)
    return m.group(1) if m else ""


def _report_to_dict(
    report: BirdsEyeReport,
    enrichment: dict | None = None,
    sparklines: dict[str, list[int]] | None = None,
) -> dict:
    raw = asdict(report)
    data = _convert_value(raw)

    now = datetime.now(timezone.utc)
    team_issues: dict[str, list] = {}
    for issue in data.get("all_issues", []):
        issue["area"] = _extract_area(issue.get("issue_title", ""))
        created_at = issue.get("created_at", "")
        if created_at:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            issue["days_open"] = (now - created).days
        else:
            issue["days_open"] = 0
        issue["has_linked_pr"] = False
        issue["comment_count"] = 0

        team = issue.get("primary_team", "none")
        team_issues.setdefault(team, []).append(
            {
                "number": issue["issue_number"],
                "title": issue["issue_title"],
                "url": issue["issue_url"],
                "urgency": issue["urgency"],
            }
        )

    if enrichment:
        for key in ("critical_list", "no_team_list", "all_issues"):
            for issue in data.get(key, []):
                enr = enrichment.get(issue["issue_number"])
                if enr:
                    issue["has_linked_pr"] = enr.has_linked_pr
        for cluster in data.get("duplicate_clusters", []):
            for issue in cluster.get("issues", []):
                enr = enrichment.get(issue["issue_number"])
                if enr:
                    issue["has_linked_pr"] = enr.has_linked_pr

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
