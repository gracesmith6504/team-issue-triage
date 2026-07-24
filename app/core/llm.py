import json
import logging
import re
import time
from typing import Protocol

import anthropic
from anthropic import AnthropicVertex

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def _assess_with_retry(
    client, system_prompt: str, user_prompt: str, model: str
) -> dict | None:
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0,
            )
            content = response.content[0].text.strip()
            return _extract_json(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return None
        except Exception as e:
            if attempt < max_retries:
                delay = 5 * (3**attempt)
                logger.warning(
                    f"LLM failed (attempt {attempt + 1}/{max_retries + 1}), "
                    f"retrying in {delay}s: {e}"
                )
                time.sleep(delay)
            else:
                logger.error(f"LLM failed after {max_retries + 1} attempts: {e}")
                return None
    return None


PROVIDERS = ("anthropic", "vertex")

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "vertex": "claude-sonnet-4-6",
}

DEFAULT_VERTEX_REGION = "us-east5"


class LLMClientProtocol(Protocol):
    def assess(
        self, system_prompt: str, user_prompt: str, model: str
    ) -> dict | None: ...


class AnthropicClient:
    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None:
        return _assess_with_retry(self._client, system_prompt, user_prompt, model)


class VertexClient:
    def __init__(self, project_id: str, region: str = DEFAULT_VERTEX_REGION):
        self._client = AnthropicVertex(project_id=project_id, region=region)

    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None:
        return _assess_with_retry(self._client, system_prompt, user_prompt, model)


def resolve_model(provider: str, explicit_model: str | None) -> str:
    if explicit_model:
        return explicit_model
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"Unknown provider: {provider}")
    return DEFAULT_MODELS[provider]


def create_llm_client(provider: str = "vertex", **kwargs: str) -> LLMClientProtocol:
    if provider == "anthropic":
        return AnthropicClient(api_key=kwargs["api_key"])
    if provider == "vertex":
        return VertexClient(
            project_id=kwargs.get("project_id", ""),
            region=kwargs.get("region", DEFAULT_VERTEX_REGION),
        )
    raise ValueError(f"Unknown provider: {provider}")
