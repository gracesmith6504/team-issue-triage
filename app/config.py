import os
from dataclasses import dataclass
from pathlib import Path

from app.core.llm import PROVIDERS


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
    assessment_log_path: Path
    profiles_dir: Path
    default_lookback_hours: int


def load_config() -> TriageConfig:
    repos_str = os.environ.get("WATCH_REPOS", "NVIDIA/OpenShell")
    watch_repos = [r.strip() for r in repos_str.split(",") if r.strip()]

    llm_provider = os.environ.get("LLM_PROVIDER", "vertex")
    if llm_provider not in PROVIDERS:
        raise ValueError(
            f"Unsupported LLM_PROVIDER={llm_provider!r}. "
            f"Valid providers: {', '.join(PROVIDERS)}"
        )

    vertex_project_id = os.environ.get("VERTEX_PROJECT_ID")
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

    if llm_provider == "vertex" and not vertex_project_id:
        raise ValueError(
            "VERTEX_PROJECT_ID is required when LLM_PROVIDER=vertex. "
            "Set it to your GCP project ID."
        )
    if llm_provider == "anthropic" and not anthropic_api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic. "
            "Set it to your Anthropic API key."
        )

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise ValueError(
            "GITHUB_TOKEN is required. "
            "Set it to a GitHub personal access token with repo read access."
        )

    return TriageConfig(
        watch_repos=watch_repos,
        llm_provider=llm_provider,
        llm_model=os.environ.get("LLM_MODEL"),
        vertex_project_id=vertex_project_id,
        vertex_region=os.environ.get("VERTEX_REGION", "us-east5"),
        anthropic_api_key=anthropic_api_key,
        github_token=github_token,
        slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL"),
        state_path=Path(os.environ.get("STATE_PATH", "/data/state.json")),
        assessment_log_path=Path(
            os.environ.get("ASSESSMENT_LOG_PATH", "/data/assessments.jsonl")
        ),
        profiles_dir=Path(os.environ.get("PROFILES_DIR", "profiles")),
        default_lookback_hours=int(os.environ.get("DEFAULT_LOOKBACK_HOURS", "24")),
    )
