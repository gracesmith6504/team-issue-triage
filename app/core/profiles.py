import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).parent.parent.parent / "profiles"


@dataclass
class TeamProfile:
    team_id: str
    team_name: str
    description: str
    areas: dict[str, list[str]]
    urgency_overrides: dict[str, list[str]]
    examples: list[dict]
    notifications: dict


@dataclass
class RepoConfig:
    repo: str
    pinned_version: str
    team_profiles: list[TeamProfile]
    no_team_prefixes: list[str]
    none_examples: list[dict]
    confidence_thresholds: dict[str, float]
    reporting: dict
    codeowners: list[str] | None = None


def _load_team_profile(path: Path) -> TeamProfile:
    with open(path) as f:
        data = yaml.safe_load(f)
    return TeamProfile(
        team_id=data["team_id"],
        team_name=data["team_name"],
        description=data.get("description", ""),
        areas=data.get("areas", {"primary": [], "secondary": []}),
        urgency_overrides=data.get("urgency_overrides", {}),
        examples=data.get("examples", []),
        notifications=data.get("notifications", {}),
    )


def _validate_profiles(
    profiles: list[TeamProfile], no_team_prefixes: list[str]
) -> None:
    team_ids = [p.team_id for p in profiles]
    duplicates = [tid for tid in team_ids if team_ids.count(tid) > 1]
    if duplicates:
        raise ValueError(
            f"team_id '{duplicates[0]}' is duplicate — each team_id must be unique"
        )

    primary_owners: dict[str, str] = {}
    for profile in profiles:
        for prefix in profile.areas.get("primary", []):
            if prefix in primary_owners:
                raise ValueError(
                    f"Prefix '{prefix}' listed as primary by both "
                    f"'{primary_owners[prefix]}' and '{profile.team_id}'"
                )
            primary_owners[prefix] = profile.team_id

    no_team_set = set(no_team_prefixes)
    for profile in profiles:
        for prefix in profile.areas.get("primary", []) + profile.areas.get(
            "secondary", []
        ):
            if prefix in no_team_set:
                raise ValueError(
                    f"Prefix '{prefix}' is in no_team_prefixes but also "
                    f"appears in '{profile.team_id}' areas"
                )


def load_repo_config(name: str, profiles_dir: Path | None = None) -> RepoConfig:
    base = profiles_dir or PROFILES_DIR
    config_path = base / f"{name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Repo config not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    profiles = []
    for team_path_str in data["team_profiles"]:
        team_path = base / team_path_str
        if not team_path.exists():
            raise FileNotFoundError(f"Team profile not found: {team_path}")
        profiles.append(_load_team_profile(team_path))

    no_team_prefixes = data.get("no_team_prefixes", [])
    _validate_profiles(profiles, no_team_prefixes)

    return RepoConfig(
        repo=data["repo"],
        pinned_version=data.get("pinned_version", ""),
        team_profiles=profiles,
        no_team_prefixes=no_team_prefixes,
        none_examples=data.get("none_examples", []),
        confidence_thresholds=data.get("confidence_thresholds", {}),
        reporting=data.get("reporting", {}),
        codeowners=data.get("codeowners"),
    )
