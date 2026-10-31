"""
Provider adapters (Spec 08, OD-54 / OD-55): request building and response parsing only.
No retries, no fallbacks, no I/O. Exactly one adapter is used per process.
"""
from __future__ import annotations

import json
from typing import Any

from settings.model import DEFAULT_LLM_MODELS as DEFAULT_MODELS
from settings.model import LLM_PROVIDERS as PROVIDERS
from settings.model import llm_model_mismatch as model_mismatch

from .errors import MalformedResponse
from .types import LLMRequest, Usage

__all__ = ["ADAPTERS", "DEFAULT_MODELS", "PROVIDERS", "AnthropicAdapter", "GroqAdapter", "model_mismatch",
           "normalise_model", "parse_json_object"]


def normalise_model(provider: str, model: str) -> str:
    """Drop a leading '<provider>/' prefix that names the selected provider (e.g. 'groq/...')."""
    prefix = f"{provider}/"
    return model[len(prefix):] if model.lower().startswith(prefix) else model


def _usage(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("usage")
    return raw if isinstance(raw, dict) else {}


def _json_body(response_json: Any, provider: str) -> dict[str, Any]:
    if not isinstance(response_json, dict):
        raise MalformedResponse(f"{provider} response is not a JSON object (malformed_response)")
    return response_json


class GroqAdapter:
    """Groq's OpenAI-compatible chat completions API."""

    name = "groq"
    url = "https://api.groq.com/openai/v1/chat/completions"

    def headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def body(self, request: LLMRequest, model: str, max_tokens: int, temperature: float) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": request.system},
                         {"role": "user", "content": request.user}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if request.response_format == "json":
            body["response_format"] = {"type": "json_object"}
        return body

    def parse(self, response_json: Any) -> tuple[str, Usage]:
        data = _json_body(response_json, self.name)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise MalformedResponse("groq response has no message content (malformed_response)") from None
        if not isinstance(content, str):
            raise MalformedResponse("groq message content is not text (malformed_response)")
        usage = _usage(data)
        return content, Usage(input_tokens=int(usage.get("prompt_tokens") or 0),
                              output_tokens=int(usage.get("completion_tokens") or 0))


class AnthropicAdapter:
    """Anthropic Messages API."""

    name = "anthropic"
    url = "https://api.anthropic.com/v1/messages"

    def headers(self, api_key: str) -> dict[str, str]:
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    def body(self, request: LLMRequest, model: str, max_tokens: int, temperature: float) -> dict[str, Any]:
        return {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
        }

    def parse(self, response_json: Any) -> tuple[str, Usage]:
        data = _json_body(response_json, self.name)
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise MalformedResponse("anthropic response has no content blocks (malformed_response)")
        raw = [b.get("text") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
        texts = [t for t in raw if isinstance(t, str)]
        if not raw or len(texts) != len(raw):
            raise MalformedResponse("anthropic response has no text block (malformed_response)")
        usage = _usage(data)
        return "".join(texts), Usage(input_tokens=int(usage.get("input_tokens") or 0),
                                     output_tokens=int(usage.get("output_tokens") or 0))


ADAPTERS: dict[str, Any] = {"groq": GroqAdapter(), "anthropic": AnthropicAdapter()}


def parse_json_object(text: str, provider: str) -> dict[str, Any]:
    """JSON mode result: one JSON object, optionally wrapped in a markdown fence."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else ""
        clean = clean.rstrip().removesuffix("```").strip()
    try:
        value = json.loads(clean)
    except (ValueError, RecursionError):
        raise MalformedResponse(f"{provider} returned text that is not JSON (malformed_response)") from None
    if not isinstance(value, dict):
        raise MalformedResponse(f"{provider} returned JSON that is not an object (malformed_response)")
    return value
