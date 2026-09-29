"""Read-only Hindsight recall for Daily Compass; never retain or reflect."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

TagsMatch = Literal["any", "all", "any_strict", "all_strict"]


class RecallClient(Protocol):
    def recall(self, bank_id: str, query: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class RecalledMemory:
    id: str
    text: str


@dataclass(frozen=True)
class Recall:
    memories: tuple[RecalledMemory, ...]


class MemoryReader:
    """Wraps a Hindsight client without exposing it, so Compass cannot write memories."""

    def __init__(self, client: RecallClient, bank_id: str) -> None:
        self.__client = client
        self.__bank_id = bank_id

    def recall(
        self,
        query: str,
        *,
        max_tokens: int,
        tags: tuple[str, ...] = (),
        tags_match: TagsMatch = "any",
    ) -> Recall:
        response = self.__client.recall(
            self.__bank_id,
            query,
            budget="low",
            max_tokens=max_tokens,
            tags=list(tags) or None,
            tags_match=tags_match,
        )
        results = getattr(response, "results", None) or []
        memories = tuple(
            RecalledMemory(id=memory.id, text=memory.text.strip())
            for memory in results
            if isinstance(getattr(memory, "id", None), str)
            and isinstance(getattr(memory, "text", None), str)
            and memory.id.strip()
            and memory.text.strip()
        )
        return Recall(memories=memories)


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
