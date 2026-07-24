import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TriageConfig:
    watch_repos: list[str]
    llm_provider: str
    llm_model: str | None
    vertex_project_id: str | None
    vertex_region: str
    anthropic_api_key: str | None
    github_token: str
    slack_webhook_url: str | None
    state_path: Path
    profiles_dir: Path
    default_lookback_hours: int


def load_config() -> TriageConfig:
    repos_str = os.environ.get("WATCH_REPOS", "NVIDIA/OpenShell")
    watch_repos = [r.strip() for r in repos_str.split(",") if r.strip()]

    return TriageConfig(
        watch_repos=watch_repos,
        llm_provider=os.environ.get("LLM_PROVIDER", "vertex"),
        llm_model=os.environ.get("LLM_MODEL"),
        vertex_project_id=os.environ.get("VERTEX_PROJECT_ID"),
        vertex_region=os.environ.get("VERTEX_REGION", "us-east5"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        github_token=os.environ["GITHUB_TOKEN"],
        slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL"),
        state_path=Path(os.environ.get("STATE_PATH", "/data/state.json")),
        profiles_dir=Path(os.environ.get("PROFILES_DIR", "profiles")),
        default_lookback_hours=int(os.environ.get("DEFAULT_LOOKBACK_HOURS", "24")),
    )
