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

from compass.memory import SIGNAL_SCHEMA, MemoryReader, open_memory_reader


class FakeClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.calls: list[tuple[tuple, dict]] = []
        self.response = response
        self.error = error

    def reflect(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.response

    def retain(self, *_args, **_kwargs):
        raise AssertionError("Compass must never retain")


def _response(text: str = "", structured=None, memory_ids=()):
    memories = [SimpleNamespace(id=mid) for mid in memory_ids]
    return SimpleNamespace(text=text, structured_output=structured, based_on=SimpleNamespace(memories=memories))


# T-MEM-1 ---------------------------------------------------------------------


def test_reader_exposes_reflect_only() -> None:
    reader = MemoryReader(FakeClient(), "bank")
    public = {name for name in dir(reader) if not name.startswith("_")}
    assert public == {"reflect"}
    assert not any(hasattr(reader, name) for name in ("retain", "learn", "create_mental_model", "client"))


def test_reflect_request_is_scoped_and_asks_for_sources() -> None:
    client = FakeClient(_response(structured={"signal": "ok"}))
    MemoryReader(client, "hermes").reflect("q", max_tokens=256, tags=("project:sg",), tags_match="all_strict")
    (args, kwargs) = client.calls[0]
    assert args == ("hermes", "q")
    assert kwargs["tags"] == ["project:sg"]
    assert kwargs["tags_match"] == "all_strict"
    assert kwargs["include_facts"] is True
    assert kwargs["response_schema"] == SIGNAL_SCHEMA
    assert kwargs["max_tokens"] == 256


def test_reflect_without_tags_sends_none() -> None:
    client = FakeClient(_response(text="x"))
    MemoryReader(client, "hermes").reflect("q", max_tokens=10)
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
        raise RuntimeError("reflect failed")
    assert seen == {"base_url": "http://h.test", "api_key": "k", "timeout": 5, "closed": True}


# T-LLM-3 ---------------------------------------------------------------------


def test_structured_signal_and_memory_ids_are_returned() -> None:
    fixture = json.loads((FIXTURES / "reflect_response.json").read_text(encoding="utf-8"))
    memory_ids = [m["id"] for m in fixture["based_on"]["memories"]]
    client = FakeClient(_response(text="ignored", structured={"signal": " Pick 20. "}, memory_ids=memory_ids))
    reflection = MemoryReader(client, "hermes").reflect("q", max_tokens=256)
    assert reflection.signal == "Pick 20."
    assert reflection.memory_ids == ("mem-photo-1", "mem-photo-2")


@pytest.mark.parametrize("structured", [None, {}, {"signal": ""}, {"signal": 3}, "not-a-dict"])
def test_missing_structured_output_falls_back_to_text(structured) -> None:
    client = FakeClient(_response(text=" Plain answer ", structured=structured))
    assert MemoryReader(client, "hermes").reflect("q", max_tokens=256).signal == "Plain answer"


def test_reflect_errors_propagate_to_caller() -> None:
    client = FakeClient(error=TimeoutError("hindsight down"))
    with pytest.raises(TimeoutError):
        MemoryReader(client, "hermes").reflect("q", max_tokens=256)
