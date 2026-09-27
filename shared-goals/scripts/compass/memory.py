"""Read-only Hindsight access for Daily Compass: reflect only, never retain."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

SIGNAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"signal": {"type": "string"}},
    "required": ["signal"],
    "additionalProperties": False,
}

TagsMatch = Literal["any", "all", "any_strict", "all_strict"]


class ReflectClient(Protocol):
    def reflect(self, bank_id: str, query: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class Reflection:
    signal: str
    memory_ids: tuple[str, ...]


class MemoryReader:
    """Wraps a Hindsight client without exposing it, so Compass cannot write memories."""

    def __init__(self, client: ReflectClient, bank_id: str) -> None:
        self.__client = client
        self.__bank_id = bank_id

    def reflect(
        self,
        query: str,
        *,
        max_tokens: int,
        tags: tuple[str, ...] = (),
        tags_match: TagsMatch = "any",
    ) -> Reflection:
        response = self.__client.reflect(
            self.__bank_id,
            query,
            budget="low",
            max_tokens=max_tokens,
            response_schema=SIGNAL_SCHEMA,
            tags=list(tags) or None,
            tags_match=tags_match,
            include_facts=True,
        )
        structured = getattr(response, "structured_output", None)
        signal = structured.get("signal") if isinstance(structured, dict) else None
        if not isinstance(signal, str) or not signal.strip():
            signal = str(getattr(response, "text", "") or "")
        based_on = getattr(response, "based_on", None)
        memories = getattr(based_on, "memories", None) or []
        memory_ids = tuple(str(fact.id) for fact in memories if getattr(fact, "id", None))
        return Reflection(signal=signal.strip(), memory_ids=memory_ids)


@contextmanager
def open_memory_reader(config_path: Path, *, timeout: float) -> Iterator[MemoryReader]:
    from hindsight_client import Hindsight

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = {}
    api_url = str(config.get("api_url") or os.environ.get("HINDSIGHT_API_URL", "http://rock.lan:8889")).rstrip("/")
    api_key = str(config.get("apiKey") or os.environ.get("HINDSIGHT_API_KEY", "")).strip() or None
    bank_id = str(config.get("bank_id") or "hermes").strip() or "hermes"
    client = Hindsight(base_url=api_url, api_key=api_key, timeout=timeout)
    try:
        yield MemoryReader(client, bank_id)
    finally:
        client.close()
