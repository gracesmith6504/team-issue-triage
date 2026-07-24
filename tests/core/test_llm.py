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


@patch("app.core.llm.AnthropicVertex")
def test_vertex_assess_invalid_json(mock_vertex_cls):
    mock_client = MagicMock()
    mock_vertex_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = "not valid json either"
    mock_client.messages.create.return_value = mock_response

    client = VertexClient(project_id="test-project", region="us-east5")
    result = client.assess("system", "user", "claude-sonnet-4-6")
    assert result is None


@patch("app.core.llm.anthropic.Anthropic")
def test_anthropic_assess_api_error_returns_none(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = RuntimeError("API down")

    client = AnthropicClient(api_key="test-key")
    with patch("app.core.llm.time.sleep"):
        result = client.assess("system", "user", "claude-sonnet-4-6")
    assert result is None


@patch("app.core.llm.AnthropicVertex")
def test_vertex_assess_api_error_returns_none(mock_vertex_cls):
    mock_client = MagicMock()
    mock_vertex_cls.return_value = mock_client
    mock_client.messages.create.side_effect = RuntimeError("API down")

    client = VertexClient(project_id="test-project", region="us-east5")
    with patch("app.core.llm.time.sleep"):
        result = client.assess("system", "user", "claude-sonnet-4-6")
    assert result is None


@patch("app.core.llm.anthropic.Anthropic")
def test_anthropic_assess_calls_with_correct_params(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = "{}"
    mock_client.messages.create.return_value = mock_response

    client = AnthropicClient(api_key="test-key")
    client.assess("sys prompt", "usr prompt", "claude-sonnet-4-6")

    mock_client.messages.create.assert_called_once_with(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system="sys prompt",
        messages=[{"role": "user", "content": "usr prompt"}],
        temperature=0,
    )


@patch("app.core.llm.anthropic.Anthropic")
def test_anthropic_retries_on_transient_error(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = '{"ok": true}'

    mock_client.messages.create.side_effect = [
        RuntimeError("transient"),
        mock_response,
    ]

    client = AnthropicClient(api_key="test-key")
    with patch("app.core.llm.time.sleep"):
        result = client.assess("system", "user", "claude-sonnet-4-6")

    assert result == {"ok": True}
    assert mock_client.messages.create.call_count == 2
