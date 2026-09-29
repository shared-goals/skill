"""Stateless chat completions against an OpenAI-compatible `custom:<name>` provider."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import openai

from compass.models import DIMENSIONS

DEFAULT_MAX_TOKENS = 4096
DEFAULT_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 10.0
TRANSIENT_ERRORS = (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError)

LINE_CONTEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {name: {"type": "string"} for name in ("title", "url", "body", "signal")},
    "required": ["title", "url", "body", "signal"],
    "additionalProperties": False,
}

SIGNAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"signal": {"type": "string"}},
    "required": ["signal"],
    "additionalProperties": False,
}

AREA_CONTEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "key": {"type": "string"},
        "dimension": {"type": "string", "enum": list(DIMENSIONS)},
        "signal": {"type": "string"},
        "lines": {"type": "array", "items": LINE_CONTEXT_SCHEMA},
    },
    "required": ["name", "key", "dimension", "signal", "lines"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    api_key: str
    model: str


def resolve_endpoint(config: Mapping[str, Any], provider: str, model: str) -> Endpoint | None:
    """Endpoint for a `custom:<name>` provider from Hermes `custom_providers`; None for other providers."""
    if not provider.startswith("custom:"):
        return None
    name = provider.split(":", 1)[1]
    for entry in config.get("custom_providers") or []:
        if isinstance(entry, dict) and entry.get("name") == name:
            key_env = str(entry.get("key_env") or "").strip()
            api_key = os.environ.get(key_env, "") if key_env else str(entry.get("api_key") or "")
            return Endpoint(
                base_url=str(entry.get("base_url") or "").rstrip("/"),
                api_key=api_key,
                model=model or str(entry.get("model") or ""),
            )
    raise ValueError(f"custom provider '{name}' not found in custom_providers")


def open_client(endpoint: Endpoint, *, timeout: float) -> Any:
    return openai.OpenAI(
        base_url=endpoint.base_url, api_key=endpoint.api_key or "no-key", max_retries=0, timeout=timeout
    )


def complete(
    client: Any,
    model: str,
    prompt: str,
    *,
    log: Callable[[str], None],
    schema: dict[str, Any] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    attempts: int = DEFAULT_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        # Reasoning models otherwise spend the whole budget thinking inside `content`.
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }
    if schema is not None:
        kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "response", "schema": schema}}

    for attempt in range(1, attempts):
        try:
            return _content(client.chat.completions.create(**kwargs), max_tokens, log)
        except openai.APITimeoutError:
            raise
        except TRANSIENT_ERRORS as exc:
            delay = RETRY_BACKOFF_SECONDS * attempt
            log(f"LLM transient error (attempt {attempt}/{attempts}): {exc!r}; retrying in {delay:.0f}s")
            sleep(delay)
    return _content(client.chat.completions.create(**kwargs), max_tokens, log)


def _content(response: Any, max_tokens: int, log: Callable[[str], None]) -> str:
    choice = response.choices[0]
    if choice.finish_reason == "length":
        log(f"LLM response truncated at max_tokens={max_tokens}")
    return choice.message.content or ""
