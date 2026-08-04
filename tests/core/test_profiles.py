import pytest
import yaml

from app.core.profiles import load_repo_config


@pytest.fixture()
def profiles_dir(tmp_path):
    teams_dir = tmp_path / "teams"
    teams_dir.mkdir()

    team_a = {
        "team_id": "team-a",
        "team_name": "Team A",
        "description": "Team A does stuff",
        "areas": {"primary": ["cli", "sdk"], "secondary": ["gateway"]},
        "urgency_overrides": {"critical": ["SDK sync failures"]},
        "examples": [
            {
                "title": "SDK sync failed",
                "urgency": "critical",
                "reasoning": "Blocks release",
            }
        ],
        "notifications": {
            "receive_secondary": True,
            "secondary_min_urgency": "high",
            "channels": [],
        },
    }
    team_b = {
        "team_id": "team-b",
        "team_name": "Team B",
        "description": "Team B does other stuff",
        "areas": {"primary": ["gateway"], "secondary": []},
        "urgency_overrides": {},
        "examples": [],
        "notifications": {"receive_secondary": False, "channels": []},
    }

    (teams_dir / "team-a.yaml").write_text(yaml.dump(team_a))
    (teams_dir / "team-b.yaml").write_text(yaml.dump(team_b))

    repo_config = {
        "repo": "NVIDIA/OpenShell",
        "pinned_version": "v0.0.92",
        "team_profiles": ["teams/team-a.yaml", "teams/team-b.yaml"],
        "no_team_prefixes": ["build", "tui"],
        "none_examples": [
            {
                "title": "feat(build): evaluate Bazel",
                "reasoning": "No team owns builds",
            },
        ],
        "confidence_thresholds": {
            "auto_assign": 0.8,
            "multi_team_gap": 0.2,
            "uncertain": 0.5,
            "none_min": 0.75,
        },
        "reporting": {"period": "weekly", "period_start": "monday", "timezone": "UTC"},
    }
    (tmp_path / "test-repo.yaml").write_text(yaml.dump(repo_config))
    return tmp_path


def test_load_repo_config(profiles_dir):
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    assert config.repo == "NVIDIA/OpenShell"
    assert config.pinned_version == "v0.0.92"
    assert len(config.team_profiles) == 2
    assert config.team_profiles[0].team_id == "team-a"
    assert config.team_profiles[1].team_id == "team-b"
    assert config.no_team_prefixes == ["build", "tui"]
    assert config.confidence_thresholds["none_min"] == 0.75
    assert len(config.none_examples) == 1


def test_load_repo_config_team_fields(profiles_dir):
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    team_a = config.team_profiles[0]
    assert team_a.team_name == "Team A"
    assert team_a.description == "Team A does stuff"
    assert team_a.areas["primary"] == ["cli", "sdk"]
    assert team_a.areas["secondary"] == ["gateway"]
    assert len(team_a.examples) == 1
    assert team_a.notifications["receive_secondary"] is True


def test_load_repo_config_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_repo_config("nonexistent", profiles_dir=tmp_path)


def test_load_repo_config_missing_team_file(profiles_dir):
    repo_yaml = profiles_dir / "test-repo.yaml"
    data = yaml.safe_load(repo_yaml.read_text())
    data["team_profiles"].append("teams/missing.yaml")
    repo_yaml.write_text(yaml.dump(data))
    with pytest.raises(FileNotFoundError):
        load_repo_config("test-repo", profiles_dir=profiles_dir)


def test_validation_primary_uniqueness(profiles_dir):
    team_b_path = profiles_dir / "teams" / "team-b.yaml"
    team_b = yaml.safe_load(team_b_path.read_text())
    team_b["areas"]["primary"] = ["cli"]  # conflict: team-a also has cli as primary
    team_b_path.write_text(yaml.dump(team_b))
    with pytest.raises(ValueError, match="cli.*primary"):
        load_repo_config("test-repo", profiles_dir=profiles_dir)


def test_validation_no_team_overlap(profiles_dir):
    team_a_path = profiles_dir / "teams" / "team-a.yaml"
    team_a = yaml.safe_load(team_a_path.read_text())
    team_a["areas"]["primary"].append("build")  # conflict: build is in no_team_prefixes
    team_a_path.write_text(yaml.dump(team_a))
    with pytest.raises(ValueError, match="build.*no_team_prefixes"):
        load_repo_config("test-repo", profiles_dir=profiles_dir)


def test_validation_team_id_uniqueness(profiles_dir):
    team_b_path = profiles_dir / "teams" / "team-b.yaml"
    team_b = yaml.safe_load(team_b_path.read_text())
    team_b["team_id"] = "team-a"  # duplicate
    team_b_path.write_text(yaml.dump(team_b))
    with pytest.raises(ValueError, match="team-a.*duplicate"):
        load_repo_config("test-repo", profiles_dir=profiles_dir)


def test_secondary_can_overlap(profiles_dir):
    """Multiple teams listing the same prefix as secondary is allowed."""
    team_b_path = profiles_dir / "teams" / "team-b.yaml"
    team_b = yaml.safe_load(team_b_path.read_text())
    team_b["areas"]["secondary"] = [
        "cli"
    ]  # team-a has cli as primary, team-b as secondary — OK
    team_b_path.write_text(yaml.dump(team_b))
    config = load_repo_config("test-repo", profiles_dir=profiles_dir)
    assert len(config.team_profiles) == 2


def test_load_real_profiles():
    """Smoke test: the actual profiles/ directory loads without errors."""
    config = load_repo_config("openshell")
    assert config.repo == "NVIDIA/OpenShell"
    assert len(config.team_profiles) == 6
