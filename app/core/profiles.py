import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).parent.parent.parent / "profiles"


@dataclass
class TeamProfile:
    name: str
    repos: list[str]
    team_name: str
    team_context: str = ""
    pinned_version: str = ""
    urgency_rules: str = ""
    calibration_examples: list[dict] = field(default_factory=list)
    verdict_thresholds: dict[str, int] | None = None


def load_profile(name: str, profiles_dir: Path | None = None) -> TeamProfile:
    directory = profiles_dir or PROFILES_DIR
    stem = name.removesuffix(".yaml").removesuffix(".yml")
    path = directory / f"{stem}.yaml"
    if not path.exists():
        path = directory / f"{stem}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {stem}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        raise ValueError(f"Profile {stem} is empty or not a mapping")
    if "repos" not in data or not data["repos"]:
        raise ValueError(f"Profile {stem} must have a non-empty 'repos' list")

    return TeamProfile(
        name=stem,
        repos=data["repos"],
        team_name=data.get("team_name", ""),
        team_context=data.get("team_context", ""),
        pinned_version=data.get("pinned_version", ""),
        urgency_rules=data.get("urgency_rules", ""),
        calibration_examples=data.get("calibration_examples", []),
        verdict_thresholds=data.get("verdict_thresholds"),
    )


def find_profile_for_repo(
    repo: str, profiles_dir: Path | None = None
) -> TeamProfile | None:
    directory = profiles_dir or PROFILES_DIR
    if not directory.exists():
        return None

    repo_lower = repo.lower()
    for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
        try:
            profile = load_profile(path.stem, profiles_dir=directory)
            if any(r.lower() == repo_lower for r in profile.repos):
                return profile
        except (ValueError, yaml.YAMLError) as e:
            logger.warning(f"Skipping malformed profile {path.name}: {e}")

    return None
