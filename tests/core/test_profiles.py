import pytest
import yaml

from app.core.profiles import find_profile_for_repo, load_profile


@pytest.fixture()
def profiles_dir(tmp_path):
    profile = {
        "repos": ["NVIDIA/OpenShell"],
        "team_name": "Agent Ops",
        "team_context": "The team works on OpenShift integration.",
        "pinned_version": "v0.0.85",
        "urgency_rules": "Release blockers are urgency 5.",
        "calibration_examples": [
            {
                "summary": "protobuf sync failed",
                "scores": "Relevance=5 Urgency=5 Action=4",
                "verdict": "ESCALATE",
                "reason": "Release blocker",
            }
        ],
    }
    (tmp_path / "openshell.yaml").write_text(yaml.dump(profile))
    return tmp_path


def test_load_profile(profiles_dir):
    profile = load_profile("openshell", profiles_dir=profiles_dir)
    assert profile.name == "openshell"
    assert profile.repos == ["NVIDIA/OpenShell"]
    assert profile.team_name == "Agent Ops"
    assert profile.pinned_version == "v0.0.85"
    assert len(profile.calibration_examples) == 1
    assert profile.calibration_examples[0]["verdict"] == "ESCALATE"


def test_load_profile_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="Profile not found"):
        load_profile("nonexistent", profiles_dir=tmp_path)


def test_load_profile_empty(tmp_path):
    (tmp_path / "empty.yaml").write_text("")
    with pytest.raises(ValueError, match="empty or not a mapping"):
        load_profile("empty", profiles_dir=tmp_path)


def test_load_profile_missing_repos(tmp_path):
    (tmp_path / "bad.yaml").write_text(yaml.dump({"team_name": "Test"}))
    with pytest.raises(ValueError, match="non-empty 'repos'"):
        load_profile("bad", profiles_dir=tmp_path)


def test_find_profile_for_repo(profiles_dir):
    profile = find_profile_for_repo("NVIDIA/OpenShell", profiles_dir=profiles_dir)
    assert profile is not None
    assert profile.name == "openshell"


def test_find_profile_for_repo_case_insensitive(profiles_dir):
    profile = find_profile_for_repo("nvidia/openshell", profiles_dir=profiles_dir)
    assert profile is not None


def test_find_profile_for_repo_not_found(profiles_dir):
    profile = find_profile_for_repo("other/repo", profiles_dir=profiles_dir)
    assert profile is None


def test_find_profile_for_repo_no_dir(tmp_path):
    profile = find_profile_for_repo("any/repo", profiles_dir=tmp_path / "nope")
    assert profile is None


def test_load_profile_defaults(tmp_path):
    minimal = {"repos": ["org/repo"], "team_name": "Test"}
    (tmp_path / "minimal.yaml").write_text(yaml.dump(minimal))
    profile = load_profile("minimal", profiles_dir=tmp_path)
    assert profile.team_context == ""
    assert profile.pinned_version == ""
    assert profile.urgency_rules == ""
    assert profile.calibration_examples == []
    assert profile.verdict_thresholds is None
