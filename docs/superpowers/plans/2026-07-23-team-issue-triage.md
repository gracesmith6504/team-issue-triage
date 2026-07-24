# Team Issue Triage Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated agent that monitors GitHub repos (starting with NVIDIA/OpenShell), assesses each new issue for team relevance using an LLM, and surfaces actionable issues via tiered Slack notifications.

**Architecture:** Stateless CronJob reads a persistent state file, fetches new GitHub issues, scores them on three axes (Team Relevance, Urgency, Action Clarity) via Vertex AI, computes a verdict (ESCALATE/TRACK/WATCH/SKIP), and routes notifications accordingly. Profile YAML drives all team-specific configuration.

**Tech Stack:** Python 3.12, pytest, ruff, anthropic SDK (Vertex AI + direct), requests, PyYAML

## Global Constraints

- Python 3.12+
- NEVER include `Co-Authored-By` lines in commit messages
- Always run `make lint` before pushing
- No placeholders, no blue-tack fixes, think long-term architecture
- DRY, YAGNI, TDD — test-first for every module
- No `openai` dependency — use `anthropic` SDK for both Vertex and direct API
- Every component in `app/core/` must be pure (no I/O side effects)
- Spec: `docs/specs/2026-07-23-team-issue-triage-design.md`

---

## File Structure

```
team-issue-triage/
├── app/
│   ├── __init__.py
│   ├── __main__.py              # CLI entry point
│   ├── config.py                # Load config from env vars
│   ├── triage.py                # Main orchestrator
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py            # Verdict enum, IssueData, Assessment, DigestEntry
│   │   ├── truncation.py        # Body/comment truncation (copied from github-issue-monitor)
│   │   ├── llm.py               # LLMClientProtocol, AnthropicClient, VertexClient, factory
│   │   ├── profiles.py          # TeamProfile dataclass, YAML loader
│   │   ├── scoring.py           # Verdict computation, override rules
│   │   ├── prompt.py            # System + user prompt builders
│   │   └── assessment.py        # Orchestrates: issue → prompt → LLM → scored result
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── source.py            # IssueSource protocol
│   │   └── github.py            # GitHub API client
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── notifier.py          # Notifier protocol
│   │   ├── log.py               # LogNotifier (stdout)
│   │   └── slack.py             # SlackNotifier (webhook)
│   └── state/
│       ├── __init__.py
│       └── tracker.py           # JSON state file read/write
├── profiles/
│   └── openshell.yaml           # OpenShell team relevance profile
├── tests/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_models.py
│   │   ├── test_truncation.py
│   │   ├── test_llm.py
│   │   ├── test_profiles.py
│   │   ├── test_scoring.py
│   │   ├── test_prompt.py
│   │   └── test_assessment.py
│   ├── sources/
│   │   ├── __init__.py
│   │   └── test_github.py
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── test_log.py
│   │   └── test_slack.py
│   ├── state/
│   │   ├── __init__.py
│   │   └── test_tracker.py
│   ├── integration/
│   │   ├── __init__.py
│   │   └── test_triage.py
│   └── fixtures/
│       ├── protobuf_sync_failure.json
│       ├── openshift_scc_bug.json
│       ├── tui_styling_issue.json
│       └── helm_chart_regression.json
├── k8s/
│   ├── cronjob-triage.yaml
│   ├── cronjob-digest.yaml
│   ├── configmap.yaml
│   ├── pvc.yaml
│   └── kustomization.yaml
├── Dockerfile
├── Makefile
├── requirements.txt
├── requirements-dev.txt
├── conftest.py
└── README.md
```

---

### Task 1: Project Scaffolding, Data Models, and Truncation

**Files:**
- Create: `Makefile`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `conftest.py`
- Create: `app/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/core/models.py`
- Create: `app/core/truncation.py`
- Create: `tests/__init__.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_models.py`
- Create: `tests/core/test_truncation.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `Verdict` enum with values `ESCALATE`, `TRACK`, `WATCH`, `SKIP`
  - `IssueData` dataclass with fields: `repo: str`, `number: int`, `title: str`, `body: str`, `labels: list[str]`, `comments: list[dict]`, `url: str`, `created_at: str`
  - `Assessment` dataclass with fields: `repo: str`, `issue_number: int`, `issue_title: str`, `issue_url: str`, `relevance: int`, `relevance_reason: str`, `urgency: int`, `urgency_reason: str`, `action_clarity: int`, `action_clarity_reason: str`, `total: int`, `verdict: Verdict`, `override_applied: str | None`, `summary: str`, `recommendation: str`, `assessed_at: str`
  - `DigestEntry` dataclass with fields: `issue_number: int`, `title: str`, `repo: str`, `relevance: int`, `urgency: int`, `action_clarity: int`, `verdict: str`, `reason: str`, `url: str`, `assessed_at: str`
  - `truncate_body(text: str | None) -> str`
  - `truncate_comment(text: str | None) -> str`

- [ ] **Step 1: Create Makefile**

```makefile
.PHONY: test lint build

test:
	python -m pytest tests/ -v

lint:
	python -m ruff check app/ tests/
	python -m ruff format --check app/ tests/

format:
	python -m ruff format app/ tests/

build:
	docker build -t team-issue-triage .
```

- [ ] **Step 2: Create requirements.txt**

```
anthropic[vertex]>=0.49.0
requests>=2.31.0
PyYAML>=6.0
```

- [ ] **Step 3: Create requirements-dev.txt**

```
-r requirements.txt
pytest>=7.0.0
ruff>=0.4.0
```

- [ ] **Step 4: Create conftest.py**

```python
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: hits real APIs (LLM, GitHub)")


def pytest_collection_modifyitems(config, items):
    if config.option.markexpr:
        return
    skip_slow = __import__("pytest").mark.skip(reason="need -m slow to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
```

- [ ] **Step 5: Create empty __init__.py files**

Create these files with empty content:
- `app/__init__.py`
- `app/core/__init__.py`
- `tests/__init__.py`
- `tests/core/__init__.py`

- [ ] **Step 6: Write failing tests for data models**

File: `tests/core/test_models.py`

```python
from app.core.models import Assessment, DigestEntry, IssueData, Verdict


def test_verdict_values():
    assert Verdict.ESCALATE == "ESCALATE"
    assert Verdict.TRACK == "TRACK"
    assert Verdict.WATCH == "WATCH"
    assert Verdict.SKIP == "SKIP"


def test_verdict_ordering():
    ordered = [Verdict.ESCALATE, Verdict.TRACK, Verdict.WATCH, Verdict.SKIP]
    assert len(ordered) == 4


def test_issue_data_creation():
    issue = IssueData(
        repo="NVIDIA/OpenShell",
        number=2401,
        title="protobuf sync failed",
        body="The sync job failed with error...",
        labels=["kind/bug", "priority/critical"],
        comments=[{"user": "bot", "body": "Auto-created by sync action"}],
        url="https://github.com/NVIDIA/OpenShell/issues/2401",
        created_at="2026-07-23T14:00:00Z",
    )
    assert issue.repo == "NVIDIA/OpenShell"
    assert issue.number == 2401
    assert len(issue.labels) == 2
    assert len(issue.comments) == 1


def test_assessment_creation():
    assessment = Assessment(
        repo="NVIDIA/OpenShell",
        issue_number=2401,
        issue_title="protobuf sync failed",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2401",
        relevance=5,
        relevance_reason="Go SDK sync is team-owned",
        urgency=5,
        urgency_reason="Blocks releases",
        action_clarity=4,
        action_clarity_reason="Re-run sync after fixing protos",
        total=14,
        verdict=Verdict.ESCALATE,
        override_applied=None,
        summary="SDK sync failure blocks release",
        recommendation="Fix proto definitions and re-run sync",
        assessed_at="2026-07-23T14:05:00Z",
    )
    assert assessment.verdict == Verdict.ESCALATE
    assert assessment.total == 14
    assert assessment.override_applied is None


def test_digest_entry_creation():
    entry = DigestEntry(
        issue_number=2399,
        title="Helm values missing tolerations",
        repo="NVIDIA/OpenShell",
        relevance=4,
        urgency=2,
        action_clarity=5,
        verdict="TRACK",
        reason="OpenShift deployment gap",
        url="https://github.com/NVIDIA/OpenShell/issues/2399",
        assessed_at="2026-07-23T13:05:00Z",
    )
    assert entry.verdict == "TRACK"
    assert entry.relevance == 4
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.models'`

- [ ] **Step 8: Implement data models**

File: `app/core/models.py`

```python
from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    ESCALATE = "ESCALATE"
    TRACK = "TRACK"
    WATCH = "WATCH"
    SKIP = "SKIP"


@dataclass
class IssueData:
    repo: str
    number: int
    title: str
    body: str
    labels: list[str]
    comments: list[dict]
    url: str
    created_at: str


@dataclass
class Assessment:
    repo: str
    issue_number: int
    issue_title: str
    issue_url: str
    relevance: int
    relevance_reason: str
    urgency: int
    urgency_reason: str
    action_clarity: int
    action_clarity_reason: str
    total: int
    verdict: Verdict
    override_applied: str | None
    summary: str
    recommendation: str
    assessed_at: str


@dataclass
class DigestEntry:
    issue_number: int
    title: str
    repo: str
    relevance: int
    urgency: int
    action_clarity: int
    verdict: str
    reason: str
    url: str
    assessed_at: str
```

- [ ] **Step 9: Run model tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_models.py -v`
Expected: 4 passed

- [ ] **Step 10: Write failing tests for truncation**

File: `tests/core/test_truncation.py`

```python
from app.core.truncation import (
    BODY_MAX_CHARS,
    COMMENT_MAX_CHARS,
    truncate_body,
    truncate_comment,
)


def test_truncate_body_none():
    assert truncate_body(None) == "(no description provided)"


def test_truncate_body_empty():
    assert truncate_body("") == "(no description provided)"


def test_truncate_body_short():
    text = "This is a short body."
    assert truncate_body(text) == text


def test_truncate_body_long():
    text = "x" * (BODY_MAX_CHARS + 100)
    result = truncate_body(text)
    assert len(result) == BODY_MAX_CHARS


def test_truncate_comment_none():
    assert truncate_comment(None) == ""


def test_truncate_comment_empty():
    assert truncate_comment("") == ""


def test_truncate_comment_short():
    text = "Short comment."
    assert truncate_comment(text) == text


def test_truncate_comment_long():
    text = "y" * (COMMENT_MAX_CHARS + 50)
    result = truncate_comment(text)
    assert len(result) == COMMENT_MAX_CHARS
```

- [ ] **Step 11: Run truncation tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_truncation.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 12: Implement truncation module**

File: `app/core/truncation.py`

```python
BODY_MAX_CHARS = 3000
COMMENT_MAX_CHARS = 500


def truncate_body(text: str | None) -> str:
    if not text:
        return "(no description provided)"
    return text[:BODY_MAX_CHARS]


def truncate_comment(text: str | None) -> str:
    if not text:
        return ""
    return text[:COMMENT_MAX_CHARS]
```

- [ ] **Step 13: Run all tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/ -v`
Expected: 8 passed

- [ ] **Step 14: Install dev dependencies and run lint**

Run:
```bash
cd /Users/grasmith/github/team-issue-triage
pip install -r requirements-dev.txt
make lint
```
Expected: No lint errors

- [ ] **Step 15: Commit**

```bash
git add Makefile requirements.txt requirements-dev.txt conftest.py app/ tests/
git commit -m "feat: project scaffolding with data models and truncation"
```

---

### Task 2: LLM Client

**Files:**
- Create: `app/core/llm.py`
- Create: `tests/core/test_llm.py`

**Interfaces:**
- Consumes: nothing from prior tasks directly
- Produces:
  - `LLMClientProtocol` — Protocol with method `assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None`
  - `AnthropicClient(api_key: str)` — implements `LLMClientProtocol`
  - `VertexClient(project_id: str, region: str = "us-east5")` — implements `LLMClientProtocol`
  - `create_llm_client(provider: str = "vertex", **kwargs) -> LLMClientProtocol` — factory function
  - `resolve_model(provider: str, explicit_model: str | None) -> str` — returns default model for provider if none specified
  - Constants: `PROVIDERS = ("anthropic", "vertex")`, `DEFAULT_MODELS = {"anthropic": "claude-sonnet-4-6", "vertex": "claude-sonnet-4-6"}`

- [ ] **Step 1: Write failing tests for LLM client**

File: `tests/core/test_llm.py`

```python
from unittest.mock import MagicMock, patch

import pytest

from app.core.llm import (
    DEFAULT_MODELS,
    PROVIDERS,
    AnthropicClient,
    VertexClient,
    create_llm_client,
    resolve_model,
)


def test_providers_tuple():
    assert "vertex" in PROVIDERS
    assert "anthropic" in PROVIDERS


def test_default_models():
    assert "vertex" in DEFAULT_MODELS
    assert "anthropic" in DEFAULT_MODELS


def test_resolve_model_explicit():
    assert resolve_model("vertex", "claude-opus-4-6") == "claude-opus-4-6"


def test_resolve_model_default():
    assert resolve_model("vertex", None) == DEFAULT_MODELS["vertex"]


def test_resolve_model_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_model("openai", None)


@patch("app.core.llm.anthropic.Anthropic")
def test_create_anthropic_client(mock_cls):
    client = create_llm_client("anthropic", api_key="test-key")
    assert isinstance(client, AnthropicClient)


@patch("app.core.llm.AnthropicVertex")
def test_create_vertex_client(mock_cls):
    client = create_llm_client("vertex", project_id="test-project", region="us-east5")
    assert isinstance(client, VertexClient)


def test_create_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        create_llm_client("openai")


@patch("app.core.llm.anthropic.Anthropic")
def test_anthropic_assess_success(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = '{"relevance": 5, "urgency": 3}'
    mock_client.messages.create.return_value = mock_response

    client = AnthropicClient(api_key="test-key")
    result = client.assess("system prompt", "user prompt", "claude-sonnet-4-6")

    assert result == {"relevance": 5, "urgency": 3}
    mock_client.messages.create.assert_called_once()


@patch("app.core.llm.anthropic.Anthropic")
def test_anthropic_assess_invalid_json(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = "not json"
    mock_client.messages.create.return_value = mock_response

    client = AnthropicClient(api_key="test-key")
    result = client.assess("system", "user", "claude-sonnet-4-6")
    assert result is None


@patch("app.core.llm.AnthropicVertex")
def test_vertex_assess_success(mock_vertex_cls):
    mock_client = MagicMock()
    mock_vertex_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = '{"relevance": 4, "urgency": 5}'
    mock_client.messages.create.return_value = mock_response

    client = VertexClient(project_id="test-project", region="us-east5")
    result = client.assess("system", "user", "claude-sonnet-4-6")

    assert result == {"relevance": 4, "urgency": 5}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement LLM client**

File: `app/core/llm.py`

```python
import json
import logging
import time
from typing import Protocol

import anthropic
from anthropic import AnthropicVertex

logger = logging.getLogger(__name__)

PROVIDERS = ("anthropic", "vertex")

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "vertex": "claude-sonnet-4-6",
}

DEFAULT_VERTEX_REGION = "us-east5"


class LLMClientProtocol(Protocol):
    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None: ...


class AnthropicClient:
    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None:
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0,
                )
                content = response.content[0].text.strip()
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response: {e}")
                return None
            except Exception as e:
                if attempt < max_retries:
                    delay = 5 * (3 ** attempt)
                    logger.warning(
                        f"LLM failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"LLM failed after {max_retries + 1} attempts: {e}")
                    return None


class VertexClient:
    def __init__(self, project_id: str, region: str = DEFAULT_VERTEX_REGION):
        self._client = AnthropicVertex(project_id=project_id, region=region)

    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None:
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0,
                )
                content = response.content[0].text.strip()
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response: {e}")
                return None
            except Exception as e:
                if attempt < max_retries:
                    delay = 5 * (3 ** attempt)
                    logger.warning(
                        f"LLM failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"LLM failed after {max_retries + 1} attempts: {e}")
                    return None


def resolve_model(provider: str, explicit_model: str | None) -> str:
    if explicit_model:
        return explicit_model
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"Unknown provider: {provider}")
    return DEFAULT_MODELS[provider]


def create_llm_client(provider: str = "vertex", **kwargs) -> LLMClientProtocol:
    if provider == "anthropic":
        return AnthropicClient(api_key=kwargs["api_key"])
    if provider == "vertex":
        return VertexClient(
            project_id=kwargs.get("project_id", ""),
            region=kwargs.get("region", DEFAULT_VERTEX_REGION),
        )
    raise ValueError(f"Unknown provider: {provider}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_llm.py -v`
Expected: 11 passed

- [ ] **Step 5: Run lint**

Run: `cd /Users/grasmith/github/team-issue-triage && make lint`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add app/core/llm.py tests/core/test_llm.py
git commit -m "feat: LLM client with Anthropic and Vertex AI providers"
```

---

### Task 3: Profile System

**Files:**
- Create: `app/core/profiles.py`
- Create: `profiles/openshell.yaml`
- Create: `tests/core/test_profiles.py`

**Interfaces:**
- Consumes: nothing from prior tasks directly
- Produces:
  - `TeamProfile` dataclass with fields: `name: str`, `repos: list[str]`, `team_name: str`, `team_context: str`, `pinned_version: str`, `urgency_rules: str`, `calibration_examples: list[dict]`, `verdict_thresholds: dict[str, int] | None`
  - `load_profile(name: str, profiles_dir: Path | None = None) -> TeamProfile`
  - `find_profile_for_repo(repo: str, profiles_dir: Path | None = None) -> TeamProfile | None`

- [ ] **Step 1: Write failing tests for profile system**

File: `tests/core/test_profiles.py`

```python
from pathlib import Path

import pytest
import yaml

from app.core.profiles import TeamProfile, find_profile_for_repo, load_profile


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_profiles.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement profile system**

File: `app/core/profiles.py`

```python
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


def find_profile_for_repo(repo: str, profiles_dir: Path | None = None) -> TeamProfile | None:
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
```

- [ ] **Step 4: Create the OpenShell profile YAML**

File: `profiles/openshell.yaml`

```yaml
repos:
  - "NVIDIA/OpenShell"

team_name: "Agent Ops"
team_context: |
  The Agent Ops team at Red Hat is responsible for integrating OpenShell
  into Red Hat OpenShift AI (RHOAI) as a Dev Preview feature for the 3.5
  release. The team's focus areas are:

  1. Running OpenShell on OpenShift — Helm deployment, SCCs, RBAC,
     Routes, NetworkPolicies, pod security
  2. Sandbox operator design — CRDs for declarative sandbox management
  3. Inference routing — proxying LLM requests through OpenShell's
     gateway to model endpoints (vLLM, Vertex AI)
  4. Agent identity — SPIFFE/OIDC token exchange, AuthBridge integration
  5. Go SDK synchronization — protobuf codegen that must stay in sync
     with the server. Sync failures block releases.
  6. Midstream/downstream pipeline — syncing upstream changes into
     opendatahub-io/agents-operator and Red Hat builds

  The team does NOT own:
  - The TUI (openshell-tui) — terminal dashboard, cosmetic
  - Docker driver (openshell-driver-docker) — local dev only
  - MicroVM driver — not used on OpenShift
  - macOS-specific issues — team deploys on Linux/OpenShift
  - General documentation unless it's about OpenShift deployment

pinned_version: "v0.0.85"

urgency_rules: |
  RELEASE BLOCKERS (Urgency 5):
  - Go SDK protobuf sync failures (auto-created by GitHub Actions,
    title pattern: "protobuf sync failed" or "codegen sync")
  - Any issue with labels: priority/critical, kind/blocker
  - CI failures that affect the release pipeline

  REGRESSIONS (Urgency 4):
  - Bugs in v0.0.85 that worked in previous versions
  - Security vulnerabilities (CVE mentions, label: area/security)

  BUGS (Urgency 3):
  - Reproducible bugs in team-relevant areas with workarounds

  ENHANCEMENTS (Urgency 2):
  - Feature requests that would benefit OpenShift deployment
  - Improvements to areas the team actively works on

  DISCUSSIONS (Urgency 1):
  - RFCs, design proposals, architecture discussions
  - Feature requests outside team scope

calibration_examples:
  - summary: "Go SDK protobuf sync failed for v0.4.2"
    scores: "Relevance=5 Urgency=5 Action=4"
    verdict: "ESCALATE"
    reason: "SDK sync errors are release blockers. Clear action: re-run sync after fixing proto definitions."

  - summary: "Helm chart fails when SCC restricts runAsUser"
    scores: "Relevance=5 Urgency=4 Action=4"
    verdict: "ESCALATE"
    reason: "Directly affects OpenShift deployment — the team's primary focus area. Fix approach is apparent."

  - summary: "TUI crashes when terminal window is resized"
    scores: "Relevance=1 Urgency=3 Action=3"
    verdict: "SKIP"
    reason: "TUI is not team-owned. Bug is real but irrelevant to Agent Ops work."

  - summary: "Add GPU passthrough support for sandbox pods"
    scores: "Relevance=4 Urgency=2 Action=2"
    verdict: "TRACK"
    reason: "Relevant to OpenShift sandbox work but not urgent. Needs design discussion."

  - summary: "Landlock policy not enforced inside Docker containers"
    scores: "Relevance=1 Urgency=3 Action=3"
    verdict: "SKIP"
    reason: "Docker driver issue. Team deploys on OpenShift, not Docker."

  - summary: "Route TLS termination breaks with custom CA certificates"
    scores: "Relevance=5 Urgency=4 Action=3"
    verdict: "ESCALATE"
    reason: "TLS/mTLS on OpenShift is a team-owned area. Regression in deployment workflow."

  - summary: "RFC: SDK conformance testing framework"
    scores: "Relevance=3 Urgency=1 Action=1"
    verdict: "WATCH"
    reason: "Tangentially relevant but it's an open-ended design discussion. No action needed from the team."

  - summary: "openshell-core: refactor config parsing into separate module"
    scores: "Relevance=3 Urgency=1 Action=2"
    verdict: "WATCH"
    reason: "Core crate refactoring affects everyone but is not team-initiated. Watch for breaking changes."
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_profiles.py -v`
Expected: 9 passed

- [ ] **Step 6: Run lint**

Run: `cd /Users/grasmith/github/team-issue-triage && make lint`

- [ ] **Step 7: Commit**

```bash
git add app/core/profiles.py profiles/openshell.yaml tests/core/test_profiles.py
git commit -m "feat: team profile system with OpenShell YAML"
```

---

### Task 4: Scoring Engine

**Files:**
- Create: `app/core/scoring.py`
- Create: `tests/core/test_scoring.py`

**Interfaces:**
- Consumes: `Verdict` from `app.core.models`
- Produces:
  - `DEFAULT_THRESHOLDS = {"ESCALATE": 12, "TRACK": 8, "WATCH": 5}`
  - `AXIS_LABELS = {"relevance": "Team Relevance", "urgency": "Urgency", "action_clarity": "Action Clarity"}`
  - `clamp_score(value) -> int` — clamps to 1-5, defaults to 3 on parse failure
  - `compute_verdict(relevance: int, urgency: int, action_clarity: int, thresholds: dict[str, int] | None = None) -> tuple[Verdict, int, str | None]` — returns (verdict, total, override_applied)
  - `format_scores(relevance: int, urgency: int, action_clarity: int, relevance_reason: str, urgency_reason: str, action_clarity_reason: str) -> str`

- [ ] **Step 1: Write failing tests for scoring engine**

File: `tests/core/test_scoring.py`

```python
import pytest

from app.core.models import Verdict
from app.core.scoring import clamp_score, compute_verdict, format_scores


class TestClampScore:
    def test_valid_int(self):
        assert clamp_score(3) == 3

    def test_string_int(self):
        assert clamp_score("4") == 4

    def test_below_min(self):
        assert clamp_score(0) == 1

    def test_above_max(self):
        assert clamp_score(10) == 5

    def test_none(self):
        assert clamp_score(None) == 3

    def test_invalid_string(self):
        assert clamp_score("abc") == 3

    def test_boundary_1(self):
        assert clamp_score(1) == 1

    def test_boundary_5(self):
        assert clamp_score(5) == 5


class TestComputeVerdict:
    def test_escalate(self):
        verdict, total, override = compute_verdict(5, 5, 4)
        assert verdict == Verdict.ESCALATE
        assert total == 14
        assert override is None

    def test_track(self):
        verdict, total, override = compute_verdict(3, 3, 3)
        assert verdict == Verdict.TRACK
        assert total == 9

    def test_watch(self):
        verdict, total, override = compute_verdict(2, 2, 2)
        assert verdict == Verdict.WATCH
        assert total == 6

    def test_skip(self):
        verdict, total, override = compute_verdict(1, 1, 1)
        assert verdict == Verdict.SKIP
        assert total == 3

    def test_escalate_threshold_boundary(self):
        verdict, _, _ = compute_verdict(4, 4, 4)
        assert verdict == Verdict.ESCALATE

    def test_track_threshold_boundary(self):
        verdict, _, _ = compute_verdict(3, 3, 2)
        assert verdict == Verdict.TRACK

    def test_watch_threshold_boundary(self):
        verdict, _, _ = compute_verdict(2, 2, 1)
        assert verdict == Verdict.WATCH

    def test_override_urgency5_relevance3_forces_escalate(self):
        verdict, total, override = compute_verdict(3, 5, 1)
        assert verdict == Verdict.ESCALATE
        assert total == 9
        assert override == "Urgency=5 + Relevance>=3 forces ESCALATE"

    def test_override_urgency5_relevance2_no_force(self):
        verdict, _, override = compute_verdict(2, 5, 1)
        assert verdict == Verdict.TRACK
        assert override is None

    def test_override_relevance1_caps_at_watch(self):
        verdict, total, override = compute_verdict(1, 5, 5)
        assert verdict == Verdict.WATCH
        assert total == 11
        assert override == "Relevance=1 caps at WATCH"

    def test_override_relevance1_already_skip(self):
        verdict, _, override = compute_verdict(1, 1, 1)
        assert verdict == Verdict.SKIP
        assert override is None

    def test_custom_thresholds(self):
        custom = {"ESCALATE": 14, "TRACK": 10, "WATCH": 6}
        verdict, _, _ = compute_verdict(4, 4, 4, thresholds=custom)
        assert verdict == Verdict.TRACK

    def test_override_precedence_relevance1_over_urgency5(self):
        verdict, _, override = compute_verdict(1, 5, 5)
        assert verdict == Verdict.WATCH
        assert "Relevance=1" in override


class TestFormatScores:
    def test_format_with_reasons(self):
        result = format_scores(
            relevance=5, urgency=4, action_clarity=3,
            relevance_reason="Team-owned area",
            urgency_reason="Regression",
            action_clarity_reason="Needs investigation",
        )
        assert "Team Relevance: 5/5" in result
        assert "Urgency: 4/5" in result
        assert "Action Clarity: 3/5" in result
        assert "Team-owned area" in result

    def test_format_empty_reasons(self):
        result = format_scores(
            relevance=3, urgency=2, action_clarity=1,
            relevance_reason="", urgency_reason="", action_clarity_reason="",
        )
        assert "Team Relevance: 3/5" in result
        assert " — " not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement scoring engine**

File: `app/core/scoring.py`

```python
from app.core.models import Verdict

DEFAULT_THRESHOLDS = {
    "ESCALATE": 12,
    "TRACK": 8,
    "WATCH": 5,
}

AXIS_LABELS = {
    "relevance": "Team Relevance",
    "urgency": "Urgency",
    "action_clarity": "Action Clarity",
}


def clamp_score(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, n))


def compute_verdict(
    relevance: int,
    urgency: int,
    action_clarity: int,
    thresholds: dict[str, int] | None = None,
) -> tuple[Verdict, int, str | None]:
    t = thresholds or DEFAULT_THRESHOLDS
    total = relevance + urgency + action_clarity
    override = None

    verdict = Verdict.SKIP
    for v in (Verdict.ESCALATE, Verdict.TRACK, Verdict.WATCH):
        if total >= t[v.value]:
            verdict = v
            break

    if relevance == 1 and verdict in (Verdict.ESCALATE, Verdict.TRACK):
        verdict = Verdict.WATCH
        override = "Relevance=1 caps at WATCH"
    elif urgency == 5 and relevance >= 3 and verdict != Verdict.ESCALATE:
        verdict = Verdict.ESCALATE
        override = "Urgency=5 + Relevance>=3 forces ESCALATE"

    return verdict, total, override


def format_scores(
    relevance: int,
    urgency: int,
    action_clarity: int,
    relevance_reason: str,
    urgency_reason: str,
    action_clarity_reason: str,
) -> str:
    lines = []
    for axis, score, reason in [
        ("relevance", relevance, relevance_reason),
        ("urgency", urgency, urgency_reason),
        ("action_clarity", action_clarity, action_clarity_reason),
    ]:
        label = AXIS_LABELS[axis]
        sep = f" — {reason}" if reason else ""
        lines.append(f"{label}: {score}/5{sep}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_scoring.py -v`
Expected: 19 passed

- [ ] **Step 5: Run lint**

Run: `cd /Users/grasmith/github/team-issue-triage && make lint`

- [ ] **Step 6: Commit**

```bash
git add app/core/scoring.py tests/core/test_scoring.py
git commit -m "feat: scoring engine with verdict computation and override rules"
```

---

### Task 5: Prompt Builder and Assessment Orchestrator

**Files:**
- Create: `app/core/prompt.py`
- Create: `app/core/assessment.py`
- Create: `tests/core/test_prompt.py`
- Create: `tests/core/test_assessment.py`

**Interfaces:**
- Consumes:
  - `TeamProfile` from `app.core.profiles`
  - `IssueData`, `Assessment`, `Verdict` from `app.core.models`
  - `LLMClientProtocol` from `app.core.llm`
  - `clamp_score`, `compute_verdict` from `app.core.scoring`
  - `truncate_body`, `truncate_comment` from `app.core.truncation`
- Produces:
  - `build_system_prompt(profile: TeamProfile | None = None) -> str`
  - `build_user_prompt(issue: IssueData, profile: TeamProfile | None = None) -> str`
  - `assess_issue(issue: IssueData, llm_client: LLMClientProtocol, model: str, profile: TeamProfile | None = None) -> Assessment | None`

- [ ] **Step 1: Write failing tests for prompt builder**

File: `tests/core/test_prompt.py`

```python
from app.core.models import IssueData
from app.core.profiles import TeamProfile
from app.core.prompt import build_system_prompt, build_user_prompt


def _make_profile():
    return TeamProfile(
        name="test",
        repos=["NVIDIA/OpenShell"],
        team_name="Agent Ops",
        team_context="The team works on OpenShift integration.",
        pinned_version="v0.0.85",
        urgency_rules="Release blockers are urgency 5.",
        calibration_examples=[
            {
                "summary": "protobuf sync failed",
                "scores": "Relevance=5 Urgency=5 Action=4",
                "verdict": "ESCALATE",
                "reason": "Release blocker",
            }
        ],
    )


def _make_issue():
    return IssueData(
        repo="NVIDIA/OpenShell",
        number=2401,
        title="protobuf sync failed",
        body="The sync job failed with error code 1.",
        labels=["kind/bug"],
        comments=[{"user": "bot", "body": "Auto-created"}],
        url="https://github.com/NVIDIA/OpenShell/issues/2401",
        created_at="2026-07-23T14:00:00Z",
    )


def test_system_prompt_no_profile():
    prompt = build_system_prompt()
    assert "relevance" in prompt.lower()
    assert "urgency" in prompt.lower()
    assert "action_clarity" in prompt.lower() or "action clarity" in prompt.lower()
    assert "JSON" in prompt


def test_system_prompt_with_profile():
    profile = _make_profile()
    prompt = build_system_prompt(profile)
    assert "Agent Ops" in prompt
    assert "OpenShift integration" in prompt
    assert "v0.0.85" in prompt
    assert "Release blockers are urgency 5" in prompt
    assert "protobuf sync failed" in prompt


def test_user_prompt_includes_issue_data():
    issue = _make_issue()
    prompt = build_user_prompt(issue)
    assert "protobuf sync failed" in prompt
    assert "#2401" in prompt or "2401" in prompt
    assert "NVIDIA/OpenShell" in prompt
    assert "kind/bug" in prompt
    assert "Auto-created" in prompt


def test_user_prompt_no_comments():
    issue = _make_issue()
    issue.comments = []
    prompt = build_user_prompt(issue)
    assert "(no comments)" in prompt


def test_user_prompt_no_labels():
    issue = _make_issue()
    issue.labels = []
    prompt = build_user_prompt(issue)
    assert "none" in prompt.lower()
```

- [ ] **Step 2: Write failing tests for assessment orchestrator**

File: `tests/core/test_assessment.py`

```python
from unittest.mock import MagicMock

from app.core.assessment import assess_issue
from app.core.models import IssueData, Verdict
from app.core.profiles import TeamProfile


def _make_issue():
    return IssueData(
        repo="NVIDIA/OpenShell",
        number=2401,
        title="protobuf sync failed",
        body="The sync job failed.",
        labels=["kind/bug"],
        comments=[],
        url="https://github.com/NVIDIA/OpenShell/issues/2401",
        created_at="2026-07-23T14:00:00Z",
    )


def _make_profile():
    return TeamProfile(
        name="openshell",
        repos=["NVIDIA/OpenShell"],
        team_name="Agent Ops",
        team_context="OpenShift integration team.",
    )


def _mock_llm_response(relevance=5, urgency=5, action_clarity=4):
    return {
        "relevance": relevance,
        "relevance_reason": "Team-owned area",
        "urgency": urgency,
        "urgency_reason": "Blocks releases",
        "action_clarity": action_clarity,
        "action_clarity_reason": "Clear fix needed",
        "summary": "SDK sync failure",
        "recommendation": "Re-run sync",
    }


def test_assess_issue_escalate():
    issue = _make_issue()
    mock_llm = MagicMock()
    mock_llm.assess.return_value = _mock_llm_response(5, 5, 4)

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6", profile=_make_profile())

    assert result is not None
    assert result.verdict == Verdict.ESCALATE
    assert result.total == 14
    assert result.relevance == 5
    assert result.issue_number == 2401
    assert result.override_applied is None


def test_assess_issue_track():
    issue = _make_issue()
    mock_llm = MagicMock()
    mock_llm.assess.return_value = _mock_llm_response(3, 3, 3)

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is not None
    assert result.verdict == Verdict.TRACK
    assert result.total == 9


def test_assess_issue_skip_low_relevance():
    issue = _make_issue()
    mock_llm = MagicMock()
    mock_llm.assess.return_value = _mock_llm_response(1, 3, 3)

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is not None
    assert result.verdict == Verdict.WATCH
    assert result.override_applied == "Relevance=1 caps at WATCH"


def test_assess_issue_llm_returns_none():
    issue = _make_issue()
    mock_llm = MagicMock()
    mock_llm.assess.return_value = None

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is None


def test_assess_issue_clamps_scores():
    issue = _make_issue()
    mock_llm = MagicMock()
    response = _mock_llm_response()
    response["relevance"] = 10
    response["urgency"] = 0
    mock_llm.assess.return_value = response

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is not None
    assert result.relevance == 5
    assert result.urgency == 1


def test_assess_issue_override_urgency5_relevance3():
    issue = _make_issue()
    mock_llm = MagicMock()
    mock_llm.assess.return_value = _mock_llm_response(3, 5, 1)

    result = assess_issue(issue, mock_llm, "claude-sonnet-4-6")
    assert result is not None
    assert result.verdict == Verdict.ESCALATE
    assert result.override_applied == "Urgency=5 + Relevance>=3 forces ESCALATE"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_prompt.py tests/core/test_assessment.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement prompt builder**

File: `app/core/prompt.py`

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.truncation import truncate_body, truncate_comment

if TYPE_CHECKING:
    from app.core.models import IssueData
    from app.core.profiles import TeamProfile

BASE_SYSTEM_PROMPT = """You are a team issue triage agent. You assess GitHub issues to determine their relevance and urgency for a specific engineering team.

Score every issue on three axes, each from 1 to 5:

TEAM RELEVANCE — Does this issue touch an area the team owns or cares about?
  5: Directly in team-owned area
  4: Adjacent area the team actively contributes to
  3: Area the team uses but doesn't own
  2: Tangentially related
  1: Unrelated to team's work

URGENCY — How time-sensitive is this?
  5: Release blocker or CI failure that stops the team's work
  4: Regression in current pinned version or security vulnerability
  3: Bug affecting team workflows, but workaround exists
  2: Enhancement or improvement that would help the team
  1: Discussion, RFC, feature request, or nice-to-have

ACTION CLARITY — Is there something specific someone should do?
  5: Clear fix described, someone just needs to do it
  4: Problem is well-defined, fix approach is apparent
  3: Problem is clear but investigation needed to find the fix
  2: Problem is vague, needs reproduction or design discussion
  1: Open-ended discussion, RFC, or architectural question

When in doubt on any score, round DOWN.

Return a JSON object with these exact fields:
- "relevance": Integer 1-5
- "relevance_reason": One sentence explaining the score
- "urgency": Integer 1-5
- "urgency_reason": One sentence explaining the score
- "action_clarity": Integer 1-5
- "action_clarity_reason": One sentence explaining the score
- "summary": 1-2 sentence summary of what the issue is about
- "recommendation": One sentence — what should the team do about this?

Return ONLY the JSON object, no markdown fences or extra text."""


def build_system_prompt(profile: TeamProfile | None = None) -> str:
    if profile is None:
        return BASE_SYSTEM_PROMPT

    sections = [BASE_SYSTEM_PROMPT]

    if profile.team_context:
        sections.append(
            f"\n\n--- TEAM CONTEXT ({profile.team_name}) ---\n{profile.team_context.strip()}"
        )

    if profile.pinned_version:
        sections.append(
            f"\n\n--- PINNED VERSION ---\n"
            f"The team's current pinned version is {profile.pinned_version}. "
            f"Regressions against this version are Urgency 4."
        )

    if profile.urgency_rules:
        sections.append(
            f"\n\n--- URGENCY RULES ---\n{profile.urgency_rules.strip()}"
        )

    if profile.calibration_examples:
        lines = []
        for ex in profile.calibration_examples:
            lines.append(
                f"- \"{ex['summary']}\": {ex['scores']} → {ex['verdict']} — {ex['reason']}"
            )
        sections.append(
            f"\n\n--- CALIBRATION EXAMPLES ---\n"
            f"Use these as scoring anchors. For similar issues, start from the closest example:\n"
            + "\n".join(lines)
        )

    return "\n".join(sections)


def build_user_prompt(issue: IssueData, profile: TeamProfile | None = None) -> str:
    if issue.comments:
        comment_lines = []
        for c in issue.comments:
            comment_lines.append(f"@{c['user']}: {truncate_comment(c.get('body'))}")
        comments_section = "\n".join(comment_lines)
    else:
        comments_section = "(no comments)"

    labels_str = ", ".join(issue.labels) if issue.labels else "none"

    return f"""Issue from {issue.repo} (#{issue.number}):

Title: {issue.title}

Body:
{truncate_body(issue.body)}

Labels: {labels_str}

Comments (most recent):
{comments_section}"""
```

- [ ] **Step 5: Implement assessment orchestrator**

File: `app/core/assessment.py`

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.core.prompt import build_system_prompt, build_user_prompt
from app.core.scoring import clamp_score, compute_verdict

if TYPE_CHECKING:
    from app.core.llm import LLMClientProtocol
    from app.core.models import IssueData
    from app.core.profiles import TeamProfile

from app.core.models import Assessment

logger = logging.getLogger(__name__)


def assess_issue(
    issue: IssueData,
    llm_client: LLMClientProtocol,
    model: str,
    profile: TeamProfile | None = None,
) -> Assessment | None:
    system_prompt = build_system_prompt(profile)
    user_prompt = build_user_prompt(issue, profile=profile)
    analysis = llm_client.assess(system_prompt, user_prompt, model)
    if not analysis:
        return None

    relevance = clamp_score(analysis.get("relevance"))
    urgency = clamp_score(analysis.get("urgency"))
    action_clarity = clamp_score(analysis.get("action_clarity"))

    thresholds = profile.verdict_thresholds if profile else None
    verdict, total, override = compute_verdict(
        relevance, urgency, action_clarity, thresholds=thresholds
    )

    logger.info(
        f"[{issue.repo} #{issue.number}] "
        f"R={relevance} U={urgency} AC={action_clarity} Total={total} -> {verdict.value}"
    )

    return Assessment(
        repo=issue.repo,
        issue_number=issue.number,
        issue_title=issue.title,
        issue_url=issue.url,
        relevance=relevance,
        relevance_reason=analysis.get("relevance_reason", ""),
        urgency=urgency,
        urgency_reason=analysis.get("urgency_reason", ""),
        action_clarity=action_clarity,
        action_clarity_reason=analysis.get("action_clarity_reason", ""),
        total=total,
        verdict=verdict,
        override_applied=override,
        summary=analysis.get("summary", ""),
        recommendation=analysis.get("recommendation", ""),
        assessed_at=datetime.now(timezone.utc).isoformat(),
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/core/test_prompt.py tests/core/test_assessment.py -v`
Expected: 11 passed

- [ ] **Step 7: Run lint**

Run: `cd /Users/grasmith/github/team-issue-triage && make lint`

- [ ] **Step 8: Commit**

```bash
git add app/core/prompt.py app/core/assessment.py tests/core/test_prompt.py tests/core/test_assessment.py
git commit -m "feat: prompt builder and assessment orchestrator"
```

---

### Task 6: GitHub Source

**Files:**
- Create: `app/sources/__init__.py`
- Create: `app/sources/source.py`
- Create: `app/sources/github.py`
- Create: `tests/sources/__init__.py`
- Create: `tests/sources/test_github.py`
- Create: `tests/fixtures/protobuf_sync_failure.json`
- Create: `tests/fixtures/openshift_scc_bug.json`
- Create: `tests/fixtures/tui_styling_issue.json`
- Create: `tests/fixtures/helm_chart_regression.json`

**Interfaces:**
- Consumes: `IssueData` from `app.core.models`, `truncate_comment` from `app.core.truncation`
- Produces:
  - `IssueSource` protocol with method `fetch_new_issues(self, repos: list[str], since: str, seen_ids: set[int]) -> list[IssueData]`
  - `GitHubSource(token: str)` implementing `IssueSource`

- [ ] **Step 1: Write failing tests for GitHub source**

File: `tests/sources/test_github.py`

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import IssueData
from app.sources.github import GitHubSource

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def github_source():
    return GitHubSource(token="test-token")


@pytest.fixture()
def mock_issues_response():
    return [
        {
            "number": 2401,
            "title": "protobuf sync failed for v0.4.2",
            "body": "The sync job failed with error code 1.",
            "labels": [{"name": "kind/bug"}, {"name": "priority/critical"}],
            "html_url": "https://github.com/NVIDIA/OpenShell/issues/2401",
            "created_at": "2026-07-23T14:00:00Z",
            "pull_request": None,
        },
        {
            "number": 2400,
            "title": "Fix typo in README",
            "body": "Small typo fix.",
            "labels": [{"name": "docs"}],
            "html_url": "https://github.com/NVIDIA/OpenShell/issues/2400",
            "created_at": "2026-07-23T13:00:00Z",
        },
    ]


@patch("app.sources.github.requests.get")
def test_fetch_new_issues(mock_get, github_source, mock_issues_response):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_issues_response
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert len(issues) == 2
    assert issues[0].number == 2401
    assert issues[0].repo == "NVIDIA/OpenShell"
    assert issues[0].labels == ["kind/bug", "priority/critical"]


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_filters_seen(mock_get, github_source, mock_issues_response):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_issues_response
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids={2401},
    )

    assert len(issues) == 1
    assert issues[0].number == 2400


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_skips_pull_requests(mock_get, github_source):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "number": 100,
            "title": "PR: Fix something",
            "body": "A pull request.",
            "labels": [],
            "html_url": "https://github.com/NVIDIA/OpenShell/pull/100",
            "created_at": "2026-07-23T14:00:00Z",
            "pull_request": {"url": "https://api.github.com/..."},
        },
    ]
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert len(issues) == 0


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_api_error(mock_get, github_source):
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "Rate limited"
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert issues == []


@patch("app.sources.github.requests.get")
def test_fetch_new_issues_multiple_repos(mock_get, github_source):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "number": 1,
            "title": "Issue in repo",
            "body": "Test.",
            "labels": [],
            "html_url": "https://github.com/org/repo/issues/1",
            "created_at": "2026-07-23T14:00:00Z",
        },
    ]
    mock_get.return_value = mock_response

    issues = github_source.fetch_new_issues(
        repos=["NVIDIA/OpenShell", "opendatahub-io/agent-ops"],
        since="2026-07-23T12:00:00Z",
        seen_ids=set(),
    )

    assert mock_get.call_count == 2
```

- [ ] **Step 2: Create test fixture files**

File: `tests/fixtures/protobuf_sync_failure.json`

```json
{
  "number": 2401,
  "title": "Go SDK protobuf sync failed for v0.4.2",
  "body": "The automated protobuf sync GitHub Action failed.\n\nError: codegen output differs from checked-in Go files.\n\nFiles affected:\n- pkg/sdk/v1/agent.pb.go\n- pkg/sdk/v1/sandbox.pb.go\n\nThis blocks the v0.4.2 release.",
  "labels": ["kind/bug", "priority/critical", "area/sdk"],
  "comments": [
    {"user": "github-actions[bot]", "body": "Auto-created by protobuf sync workflow. Run ID: 12345"}
  ],
  "url": "https://github.com/NVIDIA/OpenShell/issues/2401",
  "created_at": "2026-07-23T14:00:00Z"
}
```

File: `tests/fixtures/openshift_scc_bug.json`

```json
{
  "number": 2399,
  "title": "Helm chart fails when SCC restricts runAsUser",
  "body": "When deploying on OpenShift with restricted SCCs, the Helm chart fails because the gateway pod spec hardcodes runAsUser: 1000.\n\nReproduction:\n1. Install on OpenShift with restricted SCC\n2. helm install openshell ./charts/openshell\n3. Pod fails with: unable to validate against any security context constraint\n\nExpected: Should use OpenShift-assigned UID range.",
  "labels": ["kind/bug", "area/deployment"],
  "comments": [],
  "url": "https://github.com/NVIDIA/OpenShell/issues/2399",
  "created_at": "2026-07-23T12:00:00Z"
}
```

File: `tests/fixtures/tui_styling_issue.json`

```json
{
  "number": 2395,
  "title": "TUI crashes when terminal window is resized below 80 columns",
  "body": "The TUI panics with an index out of bounds error when the terminal window is resized to less than 80 columns wide.\n\nStack trace:\n```\nthread 'main' panicked at 'index out of bounds: the len is 3 but the index is 5'\n```\n\nThis happens in the openshell-tui crate's render loop.",
  "labels": ["kind/bug", "area/tui"],
  "comments": [
    {"user": "tui-maintainer", "body": "I'll look into this. Probably need to add a minimum size check."}
  ],
  "url": "https://github.com/NVIDIA/OpenShell/issues/2395",
  "created_at": "2026-07-22T10:00:00Z"
}
```

File: `tests/fixtures/helm_chart_regression.json`

```json
{
  "number": 2398,
  "title": "Route TLS termination breaks with custom CA certificates",
  "body": "After upgrading to v0.0.85, OpenShift Routes configured with custom CA certificates fail TLS termination.\n\nThis worked in v0.0.84. The gateway now rejects the certificate chain with:\n```\ncertificate verify failed: unable to get local issuer certificate\n```\n\nWorkaround: Use passthrough TLS instead of edge termination.",
  "labels": ["kind/bug", "area/security", "area/deployment"],
  "comments": [
    {"user": "team-member", "body": "This is blocking our staging deployment. We can use passthrough for now but need a proper fix."}
  ],
  "url": "https://github.com/NVIDIA/OpenShell/issues/2398",
  "created_at": "2026-07-23T09:00:00Z"
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/sources/test_github.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement GitHub source**

File: `app/sources/__init__.py` — empty

File: `app/sources/source.py`

```python
from typing import Protocol

from app.core.models import IssueData


class IssueSource(Protocol):
    def fetch_new_issues(
        self, repos: list[str], since: str, seen_ids: set[int]
    ) -> list[IssueData]: ...
```

File: `app/sources/github.py`

```python
import logging

import requests

from app.core.models import IssueData
from app.core.truncation import truncate_comment

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubSource:
    def __init__(self, token: str):
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            }
        )

    def fetch_new_issues(
        self, repos: list[str], since: str, seen_ids: set[int]
    ) -> list[IssueData]:
        all_issues = []
        for repo in repos:
            issues = self._fetch_repo_issues(repo, since, seen_ids)
            all_issues.extend(issues)
        return all_issues

    def _fetch_repo_issues(
        self, repo: str, since: str, seen_ids: set[int]
    ) -> list[IssueData]:
        url = f"{GITHUB_API}/repos/{repo}/issues"
        params = {
            "since": since,
            "state": "open",
            "sort": "created",
            "direction": "desc",
            "per_page": 100,
        }

        response = self._session.get(url, params=params)
        if response.status_code != 200:
            logger.error(f"GitHub API error for {repo}: {response.status_code} {response.text}")
            return []

        issues = []
        for item in response.json():
            if item.get("pull_request"):
                continue
            if item["number"] in seen_ids:
                continue

            comments = self._fetch_comments(repo, item["number"])

            issues.append(
                IssueData(
                    repo=repo,
                    number=item["number"],
                    title=item["title"],
                    body=item.get("body") or "",
                    labels=[label["name"] for label in item.get("labels", [])],
                    comments=comments,
                    url=item["html_url"],
                    created_at=item["created_at"],
                )
            )

        logger.info(f"Fetched {len(issues)} new issues from {repo}")
        return issues

    def _fetch_comments(self, repo: str, issue_number: int) -> list[dict]:
        url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
        params = {"per_page": 5, "direction": "desc"}

        response = self._session.get(url, params=params)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch comments for {repo}#{issue_number}")
            return []

        return [
            {
                "user": comment.get("user", {}).get("login", "unknown"),
                "body": truncate_comment(comment.get("body")),
            }
            for comment in response.json()
        ]
```

- [ ] **Step 5: Create empty __init__.py files**

Create: `tests/sources/__init__.py` — empty
Create: `tests/fixtures/` directory (already exists from fixture files)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/sources/test_github.py -v`
Expected: 5 passed

- [ ] **Step 7: Run lint**

Run: `cd /Users/grasmith/github/team-issue-triage && make lint`

- [ ] **Step 8: Commit**

```bash
git add app/sources/ tests/sources/ tests/fixtures/
git commit -m "feat: GitHub issue source with protocol interface"
```

---

### Task 7: State Tracker

**Files:**
- Create: `app/state/__init__.py`
- Create: `app/state/tracker.py`
- Create: `tests/state/__init__.py`
- Create: `tests/state/test_tracker.py`

**Interfaces:**
- Consumes: `DigestEntry` from `app.core.models`
- Produces:
  - `StateTracker(state_path: Path)`
  - `StateTracker.load() -> dict` — returns `{"last_checked": str, "seen_issues": set[int], "digest_buffer": list[dict]}`
  - `StateTracker.save(state: dict) -> None`
  - `StateTracker.default_state(lookback_hours: int = 24) -> dict`

- [ ] **Step 1: Write failing tests for state tracker**

File: `tests/state/test_tracker.py`

```python
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.state.tracker import StateTracker


@pytest.fixture()
def state_path(tmp_path):
    return tmp_path / "state.json"


@pytest.fixture()
def tracker(state_path):
    return StateTracker(state_path)


def test_default_state(tracker):
    state = tracker.default_state()
    assert "last_checked" in state
    assert isinstance(state["seen_issues"], set)
    assert len(state["seen_issues"]) == 0
    assert state["digest_buffer"] == []


def test_default_state_lookback(tracker):
    state = tracker.default_state(lookback_hours=48)
    last_checked = datetime.fromisoformat(state["last_checked"])
    now = datetime.now(timezone.utc)
    diff = now - last_checked
    assert 47 < diff.total_seconds() / 3600 < 49


def test_load_missing_file(tracker):
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)
    assert state["digest_buffer"] == []


def test_save_and_load(tracker, state_path):
    state = {
        "last_checked": "2026-07-23T14:00:00+00:00",
        "seen_issues": {2401, 2399},
        "digest_buffer": [
            {
                "issue_number": 2399,
                "title": "Helm values missing tolerations",
                "repo": "NVIDIA/OpenShell",
                "relevance": 4,
                "urgency": 2,
                "action_clarity": 5,
                "verdict": "TRACK",
                "reason": "Clear fix, not urgent",
                "url": "https://github.com/NVIDIA/OpenShell/issues/2399",
                "assessed_at": "2026-07-23T13:05:00+00:00",
            }
        ],
    }
    tracker.save(state)

    loaded = tracker.load()
    assert loaded["last_checked"] == "2026-07-23T14:00:00+00:00"
    assert loaded["seen_issues"] == {2401, 2399}
    assert len(loaded["digest_buffer"]) == 1
    assert loaded["digest_buffer"][0]["issue_number"] == 2399


def test_load_corrupted_file(tracker, state_path):
    state_path.write_text("not valid json {{{")
    state = tracker.load()
    assert isinstance(state["seen_issues"], set)


def test_prune_old_issues(tracker):
    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(days=31)).isoformat()
    recent_time = (now - timedelta(days=1)).isoformat()

    state = {
        "last_checked": recent_time,
        "seen_issues": {100, 200, 300},
        "digest_buffer": [],
        "seen_timestamps": {
            "100": old_time,
            "200": old_time,
            "300": recent_time,
        },
    }
    tracker.save(state)

    loaded = tracker.load()
    pruned = tracker.prune_seen(loaded, max_age_days=30)
    assert 300 in pruned["seen_issues"]
    assert 100 not in pruned["seen_issues"]
    assert 200 not in pruned["seen_issues"]


def test_save_creates_parent_dirs(tmp_path):
    nested_path = tmp_path / "deep" / "nested" / "state.json"
    tracker = StateTracker(nested_path)
    state = tracker.default_state()
    tracker.save(state)
    assert nested_path.exists()


def test_seen_issues_serialized_as_list(tracker, state_path):
    state = {
        "last_checked": "2026-07-23T14:00:00+00:00",
        "seen_issues": {1, 2, 3},
        "digest_buffer": [],
    }
    tracker.save(state)

    raw = json.loads(state_path.read_text())
    assert isinstance(raw["seen_issues"], list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/state/test_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement state tracker**

File: `app/state/__init__.py` — empty

File: `app/state/tracker.py`

```python
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class StateTracker:
    def __init__(self, state_path: Path):
        self._path = state_path

    def load(self) -> dict:
        if not self._path.exists():
            logger.info("No state file found, using defaults")
            return self.default_state()

        try:
            with open(self._path) as f:
                raw = json.load(f)
            raw["seen_issues"] = set(raw.get("seen_issues", []))
            return raw
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Corrupted state file, using defaults: {e}")
            return self.default_state()

    def save(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            **state,
            "seen_issues": sorted(state.get("seen_issues", set())),
        }
        with open(self._path, "w") as f:
            json.dump(serializable, f, indent=2)

    @staticmethod
    def default_state(lookback_hours: int = 24) -> dict:
        last_checked = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        return {
            "last_checked": last_checked.isoformat(),
            "seen_issues": set(),
            "digest_buffer": [],
            "seen_timestamps": {},
        }

    @staticmethod
    def prune_seen(state: dict, max_age_days: int = 30) -> dict:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max_age_days)
        timestamps = state.get("seen_timestamps", {})

        kept = set()
        kept_timestamps = {}
        for issue_id in state["seen_issues"]:
            ts_str = timestamps.get(str(issue_id))
            if ts_str:
                ts = datetime.fromisoformat(ts_str)
                if ts > cutoff:
                    kept.add(issue_id)
                    kept_timestamps[str(issue_id)] = ts_str
            else:
                kept.add(issue_id)
                kept_timestamps[str(issue_id)] = now.isoformat()

        pruned_count = len(state["seen_issues"]) - len(kept)
        if pruned_count > 0:
            logger.info(f"Pruned {pruned_count} issues older than {max_age_days} days")

        state["seen_issues"] = kept
        state["seen_timestamps"] = kept_timestamps
        return state
```

- [ ] **Step 4: Create empty __init__.py**

Create: `tests/state/__init__.py` — empty

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/state/test_tracker.py -v`
Expected: 8 passed

- [ ] **Step 6: Run lint**

Run: `cd /Users/grasmith/github/team-issue-triage && make lint`

- [ ] **Step 7: Commit**

```bash
git add app/state/ tests/state/
git commit -m "feat: JSON state tracker with pruning and recovery"
```

---

### Task 8: Notification Backends

**Files:**
- Create: `app/notifications/__init__.py`
- Create: `app/notifications/notifier.py`
- Create: `app/notifications/log.py`
- Create: `app/notifications/slack.py`
- Create: `tests/notifications/__init__.py`
- Create: `tests/notifications/test_log.py`
- Create: `tests/notifications/test_slack.py`

**Interfaces:**
- Consumes: `Assessment`, `DigestEntry`, `Verdict` from `app.core.models`, `format_scores` from `app.core.scoring`
- Produces:
  - `Notifier` protocol with methods `send_escalation(self, assessment: Assessment) -> None` and `send_digest(self, entries: list[DigestEntry]) -> None`
  - `LogNotifier()` — prints to stdout
  - `SlackNotifier(webhook_url: str)` — sends via Slack webhook

- [ ] **Step 1: Write failing tests for log notifier**

File: `tests/notifications/test_log.py`

```python
from app.core.models import Assessment, DigestEntry, Verdict
from app.notifications.log import LogNotifier


def _make_assessment():
    return Assessment(
        repo="NVIDIA/OpenShell",
        issue_number=2401,
        issue_title="protobuf sync failed",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2401",
        relevance=5,
        relevance_reason="Team-owned",
        urgency=5,
        urgency_reason="Blocks releases",
        action_clarity=4,
        action_clarity_reason="Clear fix",
        total=14,
        verdict=Verdict.ESCALATE,
        override_applied=None,
        summary="SDK sync failure",
        recommendation="Re-run sync",
        assessed_at="2026-07-23T14:05:00+00:00",
    )


def _make_digest_entries():
    return [
        DigestEntry(
            issue_number=2399,
            title="Helm values missing tolerations",
            repo="NVIDIA/OpenShell",
            relevance=4,
            urgency=2,
            action_clarity=5,
            verdict="TRACK",
            reason="OpenShift gap",
            url="https://github.com/NVIDIA/OpenShell/issues/2399",
            assessed_at="2026-07-23T13:05:00+00:00",
        ),
    ]


def test_log_notifier_escalation(capsys):
    notifier = LogNotifier()
    notifier.send_escalation(_make_assessment())

    captured = capsys.readouterr()
    assert "ESCALATE" in captured.out
    assert "protobuf sync failed" in captured.out
    assert "#2401" in captured.out


def test_log_notifier_digest(capsys):
    notifier = LogNotifier()
    notifier.send_digest(_make_digest_entries())

    captured = capsys.readouterr()
    assert "DIGEST" in captured.out or "digest" in captured.out.lower()
    assert "Helm values" in captured.out


def test_log_notifier_empty_digest(capsys):
    notifier = LogNotifier()
    notifier.send_digest([])

    captured = capsys.readouterr()
    assert "empty" in captured.out.lower() or captured.out.strip() == ""
```

- [ ] **Step 2: Write failing tests for Slack notifier**

File: `tests/notifications/test_slack.py`

```python
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import Assessment, DigestEntry, Verdict
from app.notifications.slack import SlackNotifier


def _make_assessment():
    return Assessment(
        repo="NVIDIA/OpenShell",
        issue_number=2401,
        issue_title="protobuf sync failed",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2401",
        relevance=5,
        relevance_reason="Team-owned",
        urgency=5,
        urgency_reason="Blocks releases",
        action_clarity=4,
        action_clarity_reason="Clear fix",
        total=14,
        verdict=Verdict.ESCALATE,
        override_applied=None,
        summary="SDK sync failure",
        recommendation="Re-run sync",
        assessed_at="2026-07-23T14:05:00+00:00",
    )


def _make_digest_entries():
    return [
        DigestEntry(
            issue_number=2399,
            title="Helm values missing tolerations",
            repo="NVIDIA/OpenShell",
            relevance=4,
            urgency=2,
            action_clarity=5,
            verdict="TRACK",
            reason="OpenShift deployment gap",
            url="https://github.com/NVIDIA/OpenShell/issues/2399",
            assessed_at="2026-07-23T13:05:00+00:00",
        ),
        DigestEntry(
            issue_number=2397,
            title="Add NetworkPolicy templates to Helm chart",
            repo="NVIDIA/OpenShell",
            relevance=4,
            urgency=2,
            action_clarity=4,
            verdict="TRACK",
            reason="OpenShift network security enhancement",
            url="https://github.com/NVIDIA/OpenShell/issues/2397",
            assessed_at="2026-07-23T13:10:00+00:00",
        ),
    ]


@patch("app.notifications.slack.requests.post")
def test_slack_escalation(mock_post):
    mock_post.return_value = MagicMock(status_code=200)

    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    notifier.send_escalation(_make_assessment())

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    payload = call_args[1]["json"]

    assert "protobuf sync failed" in payload["text"]


@patch("app.notifications.slack.requests.post")
def test_slack_escalation_posts_thread(mock_post):
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ts": "123.456"})

    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    notifier.send_escalation(_make_assessment())

    assert mock_post.call_count >= 1


@patch("app.notifications.slack.requests.post")
def test_slack_digest(mock_post):
    mock_post.return_value = MagicMock(status_code=200)

    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    notifier.send_digest(_make_digest_entries())

    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "Helm values" in payload["text"]
    assert "NetworkPolicy" in payload["text"]


@patch("app.notifications.slack.requests.post")
def test_slack_empty_digest(mock_post):
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    notifier.send_digest([])

    mock_post.assert_not_called()


@patch("app.notifications.slack.requests.post")
def test_slack_digest_caps_at_10(mock_post):
    mock_post.return_value = MagicMock(status_code=200)

    entries = [
        DigestEntry(
            issue_number=i,
            title=f"Issue {i}",
            repo="NVIDIA/OpenShell",
            relevance=3,
            urgency=3,
            action_clarity=3,
            verdict="TRACK",
            reason="Test",
            url=f"https://github.com/NVIDIA/OpenShell/issues/{i}",
            assessed_at="2026-07-23T13:00:00+00:00",
        )
        for i in range(15)
    ]

    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
    notifier.send_digest(entries)

    payload = mock_post.call_args[1]["json"]
    assert "5 more" in payload["text"] or "omitted" in payload["text"].lower()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/notifications/ -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement notifier protocol**

File: `app/notifications/__init__.py` — empty

File: `app/notifications/notifier.py`

```python
from typing import Protocol

from app.core.models import Assessment, DigestEntry


class Notifier(Protocol):
    def send_escalation(self, assessment: Assessment) -> None: ...
    def send_digest(self, entries: list[DigestEntry]) -> None: ...
```

- [ ] **Step 5: Implement log notifier**

File: `app/notifications/log.py`

```python
import logging

from app.core.models import Assessment, DigestEntry
from app.core.scoring import format_scores

logger = logging.getLogger(__name__)

DIGEST_MAX_ITEMS = 10


class LogNotifier:
    def send_escalation(self, assessment: Assessment) -> None:
        scores = format_scores(
            relevance=assessment.relevance,
            urgency=assessment.urgency,
            action_clarity=assessment.action_clarity,
            relevance_reason=assessment.relevance_reason,
            urgency_reason=assessment.urgency_reason,
            action_clarity_reason=assessment.action_clarity_reason,
        )
        print(
            f"[ESCALATE] #{assessment.issue_number}: {assessment.issue_title}\n"
            f"  {assessment.issue_url}\n"
            f"  {assessment.summary}\n"
            f"  {scores}\n"
            f"  Recommendation: {assessment.recommendation}"
        )

    def send_digest(self, entries: list[DigestEntry]) -> None:
        if not entries:
            print("[DIGEST] Empty — no TRACK items to report.")
            return

        sorted_entries = sorted(entries, key=lambda e: e.urgency, reverse=True)
        shown = sorted_entries[:DIGEST_MAX_ITEMS]
        omitted = len(sorted_entries) - len(shown)

        print(f"[DIGEST] {len(sorted_entries)} items:")
        for entry in shown:
            print(
                f"  - #{entry.issue_number}: {entry.title} "
                f"(R={entry.relevance} U={entry.urgency} AC={entry.action_clarity}) "
                f"— {entry.reason}"
            )
        if omitted > 0:
            print(f"  ... and {omitted} more omitted")
```

- [ ] **Step 6: Implement Slack notifier**

File: `app/notifications/slack.py`

```python
import logging

import requests

from app.core.models import Assessment, DigestEntry
from app.core.scoring import format_scores

logger = logging.getLogger(__name__)

DIGEST_MAX_ITEMS = 10


class SlackNotifier:
    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    def send_escalation(self, assessment: Assessment) -> None:
        override_note = ""
        if assessment.override_applied:
            override_note = f"\n_Override: {assessment.override_applied}_"

        text = (
            f":rotating_light: *ESCALATE* — <{assessment.issue_url}|#{assessment.issue_number}: "
            f"{assessment.issue_title}>\n"
            f"{assessment.summary}{override_note}"
        )

        payload = {"text": text}
        self._post(payload)

    def send_digest(self, entries: list[DigestEntry]) -> None:
        if not entries:
            return

        sorted_entries = sorted(entries, key=lambda e: e.urgency, reverse=True)
        shown = sorted_entries[:DIGEST_MAX_ITEMS]
        omitted = len(sorted_entries) - len(shown)

        lines = [f":clipboard: *Daily Issue Digest* — {len(sorted_entries)} items\n"]
        for entry in shown:
            lines.append(
                f"• <{entry.url}|#{entry.issue_number}: {entry.title}> "
                f"(R={entry.relevance} U={entry.urgency} AC={entry.action_clarity}) "
                f"— {entry.reason}"
            )
        if omitted > 0:
            lines.append(f"\n_{omitted} more omitted_")

        payload = {"text": "\n".join(lines)}
        self._post(payload)

    def _post(self, payload: dict) -> None:
        try:
            response = requests.post(self._webhook_url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.error(f"Slack webhook failed: {response.status_code} {response.text}")
        except requests.RequestException as e:
            logger.error(f"Slack webhook error: {e}")
```

- [ ] **Step 7: Create empty __init__.py**

Create: `tests/notifications/__init__.py` — empty

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/notifications/ -v`
Expected: 8 passed

- [ ] **Step 9: Run lint**

Run: `cd /Users/grasmith/github/team-issue-triage && make lint`

- [ ] **Step 10: Commit**

```bash
git add app/notifications/ tests/notifications/
git commit -m "feat: notification backends with log and Slack webhook"
```

---

### Task 9: Config, Triage Orchestrator, and CLI Entry Point

**Files:**
- Create: `app/config.py`
- Create: `app/triage.py`
- Create: `app/__main__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_triage.py`

**Interfaces:**
- Consumes: everything from Tasks 1-8
  - `IssueData`, `Assessment`, `DigestEntry`, `Verdict` from `app.core.models`
  - `create_llm_client`, `resolve_model` from `app.core.llm`
  - `find_profile_for_repo` from `app.core.profiles`
  - `assess_issue` from `app.core.assessment`
  - `GitHubSource` from `app.sources.github`
  - `StateTracker` from `app.state.tracker`
  - `LogNotifier` from `app.notifications.log`
  - `SlackNotifier` from `app.notifications.slack`
- Produces:
  - `TriageConfig` dataclass with all config fields
  - `load_config() -> TriageConfig` — reads from env vars
  - `run_triage(config: TriageConfig) -> None` — hourly triage mode
  - `run_digest(config: TriageConfig) -> None` — daily digest mode
  - `app/__main__.py` — CLI entry point with `--mode triage|digest`

- [ ] **Step 1: Write failing tests for config and triage orchestrator**

File: `tests/integration/test_triage.py`

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import TriageConfig, load_config
from app.core.models import Verdict
from app.triage import run_digest, run_triage


@pytest.fixture()
def config(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    return TriageConfig(
        watch_repos=["NVIDIA/OpenShell"],
        llm_provider="vertex",
        llm_model=None,
        vertex_project_id="test-project",
        vertex_region="us-east5",
        anthropic_api_key=None,
        github_token="test-github-token",
        slack_webhook_url=None,
        state_path=tmp_path / "state.json",
        profiles_dir=profiles_dir,
        default_lookback_hours=24,
    )


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("WATCH_REPOS", "NVIDIA/OpenShell,opendatahub-io/agent-ops")
    monkeypatch.setenv("LLM_PROVIDER", "vertex")
    monkeypatch.setenv("VERTEX_PROJECT_ID", "my-project")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("STATE_PATH", "/tmp/state.json")

    config = load_config()
    assert config.watch_repos == ["NVIDIA/OpenShell", "opendatahub-io/agent-ops"]
    assert config.llm_provider == "vertex"
    assert config.vertex_project_id == "my-project"
    assert config.github_token == "ghp_test"


def test_load_config_defaults(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    config = load_config()
    assert config.llm_provider == "vertex"
    assert config.vertex_region == "us-east5"
    assert config.default_lookback_hours == 24


@patch("app.triage.GitHubSource")
@patch("app.triage.create_llm_client")
def test_run_triage_no_new_issues(mock_create_llm, mock_github_cls, config):
    mock_source = MagicMock()
    mock_source.fetch_new_issues.return_value = []
    mock_github_cls.return_value = mock_source

    mock_llm = MagicMock()
    mock_create_llm.return_value = mock_llm

    run_triage(config)

    mock_source.fetch_new_issues.assert_called_once()
    mock_llm.assess.assert_not_called()


@patch("app.triage.GitHubSource")
@patch("app.triage.create_llm_client")
@patch("app.triage.assess_issue")
def test_run_triage_with_escalation(mock_assess, mock_create_llm, mock_github_cls, config):
    from app.core.models import Assessment, IssueData

    mock_source = MagicMock()
    mock_source.fetch_new_issues.return_value = [
        IssueData(
            repo="NVIDIA/OpenShell",
            number=2401,
            title="protobuf sync failed",
            body="Sync failed.",
            labels=["kind/bug"],
            comments=[],
            url="https://github.com/NVIDIA/OpenShell/issues/2401",
            created_at="2026-07-23T14:00:00Z",
        )
    ]
    mock_github_cls.return_value = mock_source

    mock_assess.return_value = Assessment(
        repo="NVIDIA/OpenShell",
        issue_number=2401,
        issue_title="protobuf sync failed",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2401",
        relevance=5,
        relevance_reason="Team-owned",
        urgency=5,
        urgency_reason="Blocker",
        action_clarity=4,
        action_clarity_reason="Clear fix",
        total=14,
        verdict=Verdict.ESCALATE,
        override_applied=None,
        summary="SDK sync failure",
        recommendation="Re-run sync",
        assessed_at="2026-07-23T14:05:00+00:00",
    )

    run_triage(config)

    mock_assess.assert_called_once()
    state = json.loads(config.state_path.read_text())
    assert 2401 in state["seen_issues"]


@patch("app.triage.GitHubSource")
@patch("app.triage.create_llm_client")
@patch("app.triage.assess_issue")
def test_run_triage_track_goes_to_digest(mock_assess, mock_create_llm, mock_github_cls, config):
    from app.core.models import Assessment, IssueData

    mock_source = MagicMock()
    mock_source.fetch_new_issues.return_value = [
        IssueData(
            repo="NVIDIA/OpenShell",
            number=2399,
            title="Helm values issue",
            body="Missing tolerations.",
            labels=[],
            comments=[],
            url="https://github.com/NVIDIA/OpenShell/issues/2399",
            created_at="2026-07-23T12:00:00Z",
        )
    ]
    mock_github_cls.return_value = mock_source

    mock_assess.return_value = Assessment(
        repo="NVIDIA/OpenShell",
        issue_number=2399,
        issue_title="Helm values issue",
        issue_url="https://github.com/NVIDIA/OpenShell/issues/2399",
        relevance=4,
        urgency=2,
        action_clarity=5,
        total=11,
        verdict=Verdict.TRACK,
        override_applied=None,
        summary="Missing tolerations",
        recommendation="Add tolerations passthrough",
        relevance_reason="OpenShift area",
        urgency_reason="Not urgent",
        action_clarity_reason="Clear fix",
        assessed_at="2026-07-23T13:05:00+00:00",
    )

    run_triage(config)

    state = json.loads(config.state_path.read_text())
    assert len(state["digest_buffer"]) == 1
    assert state["digest_buffer"][0]["issue_number"] == 2399


def test_run_digest_flushes_buffer(config):
    state = {
        "last_checked": "2026-07-23T14:00:00+00:00",
        "seen_issues": [2399],
        "digest_buffer": [
            {
                "issue_number": 2399,
                "title": "Helm values issue",
                "repo": "NVIDIA/OpenShell",
                "relevance": 4,
                "urgency": 2,
                "action_clarity": 5,
                "verdict": "TRACK",
                "reason": "OpenShift gap",
                "url": "https://github.com/NVIDIA/OpenShell/issues/2399",
                "assessed_at": "2026-07-23T13:05:00+00:00",
            }
        ],
        "seen_timestamps": {},
    }
    config.state_path.write_text(json.dumps(state))

    run_digest(config)

    updated = json.loads(config.state_path.read_text())
    assert updated["digest_buffer"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/integration/test_triage.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement config module**

File: `app/config.py`

```python
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
```

- [ ] **Step 4: Implement triage orchestrator**

File: `app/triage.py`

```python
import json
import logging
from datetime import datetime, timezone

from app.config import TriageConfig
from app.core.assessment import assess_issue
from app.core.llm import create_llm_client, resolve_model
from app.core.models import DigestEntry, Verdict
from app.core.profiles import find_profile_for_repo
from app.notifications.log import LogNotifier
from app.notifications.slack import SlackNotifier
from app.sources.github import GitHubSource
from app.state.tracker import StateTracker

logger = logging.getLogger(__name__)


def _build_notifier(config: TriageConfig):
    if config.slack_webhook_url:
        return SlackNotifier(webhook_url=config.slack_webhook_url)
    return LogNotifier()


def _build_llm_client(config: TriageConfig):
    kwargs = {}
    if config.llm_provider == "anthropic":
        kwargs["api_key"] = config.anthropic_api_key
    elif config.llm_provider == "vertex":
        kwargs["project_id"] = config.vertex_project_id
        kwargs["region"] = config.vertex_region
    return create_llm_client(config.llm_provider, **kwargs)


def run_triage(config: TriageConfig) -> None:
    tracker = StateTracker(config.state_path)
    state = tracker.load()
    notifier = _build_notifier(config)
    source = GitHubSource(token=config.github_token)
    llm_client = _build_llm_client(config)
    model = resolve_model(config.llm_provider, config.llm_model)

    issues = source.fetch_new_issues(
        repos=config.watch_repos,
        since=state["last_checked"],
        seen_ids=state["seen_issues"],
    )

    logger.info(f"Found {len(issues)} new issues to assess")

    for issue in issues:
        profile = find_profile_for_repo(issue.repo, profiles_dir=config.profiles_dir)
        assessment = assess_issue(issue, llm_client, model, profile=profile)

        if assessment is None:
            logger.warning(f"Failed to assess {issue.repo}#{issue.number}")
            continue

        logger.info(
            f"Assessed {issue.repo}#{issue.number}: {assessment.verdict.value} "
            f"(total={assessment.total})"
        )

        if assessment.verdict == Verdict.ESCALATE:
            notifier.send_escalation(assessment)
        elif assessment.verdict == Verdict.TRACK:
            entry = DigestEntry(
                issue_number=assessment.issue_number,
                title=assessment.issue_title,
                repo=assessment.repo,
                relevance=assessment.relevance,
                urgency=assessment.urgency,
                action_clarity=assessment.action_clarity,
                verdict=assessment.verdict.value,
                reason=assessment.summary,
                url=assessment.issue_url,
                assessed_at=assessment.assessed_at,
            )
            state["digest_buffer"].append(
                {
                    "issue_number": entry.issue_number,
                    "title": entry.title,
                    "repo": entry.repo,
                    "relevance": entry.relevance,
                    "urgency": entry.urgency,
                    "action_clarity": entry.action_clarity,
                    "verdict": entry.verdict,
                    "reason": entry.reason,
                    "url": entry.url,
                    "assessed_at": entry.assessed_at,
                }
            )

        state["seen_issues"].add(issue.number)
        now_str = datetime.now(timezone.utc).isoformat()
        state.setdefault("seen_timestamps", {})[str(issue.number)] = now_str

    state["last_checked"] = datetime.now(timezone.utc).isoformat()
    state = tracker.prune_seen(state)
    tracker.save(state)
    logger.info("Triage run complete")


def run_digest(config: TriageConfig) -> None:
    tracker = StateTracker(config.state_path)
    state = tracker.load()
    notifier = _build_notifier(config)

    buffer = state.get("digest_buffer", [])
    if buffer:
        entries = [
            DigestEntry(
                issue_number=item["issue_number"],
                title=item["title"],
                repo=item["repo"],
                relevance=item["relevance"],
                urgency=item["urgency"],
                action_clarity=item["action_clarity"],
                verdict=item["verdict"],
                reason=item["reason"],
                url=item["url"],
                assessed_at=item["assessed_at"],
            )
            for item in buffer
        ]
        notifier.send_digest(entries)
        logger.info(f"Sent digest with {len(entries)} items")
    else:
        logger.info("Digest buffer empty, nothing to send")

    state["digest_buffer"] = []
    tracker.save(state)
```

- [ ] **Step 5: Implement CLI entry point**

File: `app/__main__.py`

```python
import argparse
import logging
import sys

from app.config import load_config
from app.triage import run_digest, run_triage


def main():
    parser = argparse.ArgumentParser(description="Team Issue Triage Agent")
    parser.add_argument(
        "--mode",
        choices=["triage", "digest"],
        default="triage",
        help="Run mode: triage (assess new issues) or digest (flush daily digest)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    config = load_config()

    if args.mode == "triage":
        run_triage(config)
    elif args.mode == "digest":
        run_digest(config)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Create empty __init__.py**

Create: `tests/integration/__init__.py` — empty

- [ ] **Step 7: Run all tests to verify they pass**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/ -v`
Expected: All tests pass (should be ~50+ tests total)

- [ ] **Step 8: Run lint**

Run: `cd /Users/grasmith/github/team-issue-triage && make lint`

- [ ] **Step 9: Commit**

```bash
git add app/config.py app/triage.py app/__main__.py tests/integration/
git commit -m "feat: triage orchestrator with config and CLI entry point"
```

---

### Task 10: Containerization and Deployment

**Files:**
- Create: `Dockerfile`
- Create: `k8s/cronjob-triage.yaml`
- Create: `k8s/cronjob-digest.yaml`
- Create: `k8s/configmap.yaml`
- Create: `k8s/pvc.yaml`
- Create: `k8s/kustomization.yaml`

**Interfaces:**
- Consumes: entire application from Tasks 1-9
- Produces: container image + Kubernetes deployment manifests

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY profiles/ profiles/

USER 1001

ENTRYPOINT ["python", "-m", "app"]
```

- [ ] **Step 2: Create PVC manifest**

File: `k8s/pvc.yaml`

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: triage-state
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Mi
```

- [ ] **Step 3: Create ConfigMap**

File: `k8s/configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: triage-config
data:
  WATCH_REPOS: "NVIDIA/OpenShell"
  LLM_PROVIDER: "vertex"
  VERTEX_REGION: "us-east5"
  STATE_PATH: "/data/state.json"
  PROFILES_DIR: "/app/profiles"
  DEFAULT_LOOKBACK_HOURS: "24"
```

- [ ] **Step 4: Create hourly triage CronJob**

File: `k8s/cronjob-triage.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: triage-hourly
spec:
  schedule: "0 * * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: triage
              image: quay.io/gracesmith6504/team-issue-triage:latest
              args: ["--mode", "triage"]
              envFrom:
                - configMapRef:
                    name: triage-config
                - secretRef:
                    name: triage-secrets
              volumeMounts:
                - name: state
                  mountPath: /data
          volumes:
            - name: state
              persistentVolumeClaim:
                claimName: triage-state
```

- [ ] **Step 5: Create daily digest CronJob**

File: `k8s/cronjob-digest.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: triage-digest
spec:
  schedule: "0 8 * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: digest
              image: quay.io/gracesmith6504/team-issue-triage:latest
              args: ["--mode", "digest"]
              envFrom:
                - configMapRef:
                    name: triage-config
                - secretRef:
                    name: triage-secrets
              volumeMounts:
                - name: state
                  mountPath: /data
          volumes:
            - name: state
              persistentVolumeClaim:
                claimName: triage-state
```

- [ ] **Step 6: Create Kustomization**

File: `k8s/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: team-issue-triage

resources:
  - pvc.yaml
  - configmap.yaml
  - cronjob-triage.yaml
  - cronjob-digest.yaml
```

- [ ] **Step 7: Test Docker build locally**

Run: `cd /Users/grasmith/github/team-issue-triage && docker build -t team-issue-triage:test .`
Expected: Build succeeds

- [ ] **Step 8: Run full test suite one final time**

Run: `cd /Users/grasmith/github/team-issue-triage && python -m pytest tests/ -v && make lint`
Expected: All tests pass, no lint errors

- [ ] **Step 9: Commit**

```bash
git add Dockerfile k8s/
git commit -m "feat: Dockerfile and Kubernetes CronJob manifests"
```
