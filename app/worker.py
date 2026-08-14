import logging
import os

import requests

from app.config import TriageConfig
from app.core.llm import build_llm_client, resolve_model
from app.core.profiles import load_repo_config
from app.core.prompt import build_system_prompt
from app.core.triage_engine import triage_issue
from app.sources.github import GitHubSource
from app.state.assessment_log import result_to_record
from app.triage import _build_notification_router

logger = logging.getLogger(__name__)


class DashboardClient:
    def __init__(self, base_url: str, api_token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.headers = {}
        if api_token:
            self.headers["Authorization"] = f"Bearer {api_token}"

    def get_state(self) -> dict:
        resp = requests.get(
            f"{self.base_url}/api/state",
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def post_assessments(self, results: list[dict]) -> dict:
        resp = requests.post(
            f"{self.base_url}/api/assessments",
            json={"results": results},
            headers=self.headers,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def trigger_report(self) -> dict:
        resp = requests.post(
            f"{self.base_url}/api/report/trigger",
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


def worker_triage(config: TriageConfig) -> None:
    dashboard_url = os.environ.get("DASHBOARD_URL")
    dashboard_token = os.environ.get("DASHBOARD_TOKEN")
    if not dashboard_url:
        raise ValueError("DASHBOARD_URL is required for worker mode")

    client = DashboardClient(dashboard_url, dashboard_token)

    state = client.get_state()
    seen_numbers = set()
    for key in state["seen_issues"]:
        key_str = str(key)
        if "#" in key_str:
            try:
                seen_numbers.add(int(key_str.split("#")[1]))
            except (ValueError, IndexError):
                pass
        elif key_str.isdigit():
            seen_numbers.add(int(key_str))

    logger.info("Dashboard reports %d seen issues", len(seen_numbers))

    source = GitHubSource(config.github_token)
    new_issues = source.fetch_new_issues(
        config.watch_repos,
        state["last_checked"],
        seen_numbers,
    )

    logger.info("Found %d new issues to triage", len(new_issues))

    if not new_issues:
        return

    repo_config = load_repo_config(
        config.profile_name, profiles_dir=config.profiles_dir
    )
    system_prompt = build_system_prompt(repo_config)
    router = _build_notification_router(repo_config)

    llm_client = build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)

    results = []
    for issue in new_issues:
        result = triage_issue(issue, llm_client, model, repo_config, system_prompt)
        if result is None:
            continue

        router.route(result)
        results.append(result_to_record(result))

    if results:
        resp = client.post_assessments(results)
        logger.info("Posted %d assessments to dashboard: %s", len(results), resp)


def worker_report(config: TriageConfig) -> None:
    dashboard_url = os.environ.get("DASHBOARD_URL")
    dashboard_token = os.environ.get("DASHBOARD_TOKEN")
    if not dashboard_url:
        raise ValueError("DASHBOARD_URL is required for worker mode")

    client = DashboardClient(dashboard_url, dashboard_token)
    resp = client.trigger_report()
    logger.info("Triggered report generation: %s", resp)
