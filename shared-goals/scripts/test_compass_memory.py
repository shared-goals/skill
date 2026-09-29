#!/usr/bin/env python3
"""Read-only memory adapter (T-MEM-1, T-LLM-3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).parent
FIXTURES = SCRIPTS_DIR / "fixtures"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from compass.memory import MemoryReader, Recall, RecalledMemory, open_memory_reader


class FakeClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.calls: list[tuple[tuple, dict]] = []
        self.response = response
        self.error = error

    def recall(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.response

    def retain(self, *_args, **_kwargs):
        raise AssertionError("Compass must never retain")


def _response(memories=()):
    results = [SimpleNamespace(id=memory_id, text=text) for memory_id, text in memories]
    return SimpleNamespace(results=results)


# T-MEM-1 ---------------------------------------------------------------------


def test_reader_exposes_recall_only() -> None:
    reader = MemoryReader(FakeClient(), "bank")
    public = {name for name in dir(reader) if not name.startswith("_")}
    assert public == {"recall"}
    assert not any(hasattr(reader, name) for name in ("reflect", "retain", "learn", "create_mental_model", "client"))


def test_recall_request_is_scoped() -> None:
    client = FakeClient(_response())
    MemoryReader(client, "hermes").recall("q", max_tokens=256, tags=("project:sg",), tags_match="all_strict")
    (args, kwargs) = client.calls[0]
    assert args == ("hermes", "q")
    assert kwargs["tags"] == ["project:sg"]
    assert kwargs["tags_match"] == "all_strict"
    assert kwargs["budget"] == "low"
    assert kwargs["max_tokens"] == 256


def test_recall_without_tags_sends_none() -> None:
    client = FakeClient(_response())
    MemoryReader(client, "hermes").recall("q", max_tokens=10)
    assert client.calls[0][1]["tags"] is None


def test_open_memory_reader_reads_config_and_closes_client(tmp_path: Path, monkeypatch) -> None:
    seen: dict = {}

    class FakeHindsight:
        def __init__(self, **kwargs) -> None:
            seen.update(kwargs)

        def close(self) -> None:
            seen["closed"] = True

    monkeypatch.setitem(sys.modules, "hindsight_client", SimpleNamespace(Hindsight=FakeHindsight))
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"api_url": "http://h.test/", "bank_id": "b1", "apiKey": "k"}), encoding="utf-8")
    with pytest.raises(RuntimeError), open_memory_reader(config, timeout=5):
        assert "closed" not in seen
        raise RuntimeError("recall failed")
    assert seen == {"base_url": "http://h.test", "api_key": "k", "timeout": 5, "closed": True}


# T-LLM-3 ---------------------------------------------------------------------


def test_recall_returns_memory_text_and_ids() -> None:
    client = FakeClient(_response((("mem-1", "First fact"), ("mem-2", "Second fact"))))
    recall = MemoryReader(client, "hermes").recall("q", max_tokens=256)
    assert recall == Recall(
        memories=(RecalledMemory(id="mem-1", text="First fact"), RecalledMemory(id="mem-2", text="Second fact"))
    )


def test_recall_with_no_results_is_empty() -> None:
    assert MemoryReader(FakeClient(_response()), "hermes").recall("q", max_tokens=256) == Recall(memories=())


def test_recall_errors_propagate_to_caller() -> None:
    client = FakeClient(error=TimeoutError("hindsight down"))
    with pytest.raises(TimeoutError):
        MemoryReader(client, "hermes").recall("q", max_tokens=256)
