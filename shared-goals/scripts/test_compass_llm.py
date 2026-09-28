from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from compass.llm import AREA_CONTEXT_SCHEMA, complete, resolve_endpoint


def _response(content: str, finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content=content))]
    )


class FakeClient:
    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


REQUEST = httpx.Request("POST", "http://tf.test/v1/chat/completions")


def test_complete_disables_thinking_and_enforces_schema() -> None:
    client = FakeClient(_response('{"ok": true}'))
    text = complete(client, "agent", "prompt", log=lambda _: None, schema=AREA_CONTEXT_SCHEMA)

    assert text == '{"ok": true}'
    call = client.calls[0]
    assert call["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert call["response_format"]["json_schema"]["schema"] is AREA_CONTEXT_SCHEMA


def test_complete_retries_transient_errors_then_succeeds() -> None:
    client = FakeClient(openai.APIConnectionError(request=REQUEST), _response("done"))
    delays: list[float] = []
    assert complete(client, "agent", "p", log=lambda _: None, sleep=delays.append) == "done"
    assert len(client.calls) == 2
    assert delays == [10.0]


def test_complete_does_not_retry_timeouts() -> None:
    client = FakeClient(openai.APITimeoutError(request=REQUEST), _response("never"))
    with pytest.raises(openai.APITimeoutError):
        complete(client, "agent", "p", log=lambda _: None, sleep=lambda _: None)
    assert len(client.calls) == 1


def test_complete_logs_truncation() -> None:
    logs: list[str] = []
    complete(FakeClient(_response("partial", "length")), "agent", "p", log=logs.append)
    assert any("truncated" in line for line in logs)


def test_resolve_endpoint_reads_named_custom_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TF_TEST_KEY", "secret")
    config = {
        "custom_providers": [
            {"name": "tf", "base_url": "http://tf.test/v1/", "key_env": "TF_TEST_KEY", "model": "agent"}
        ]
    }

    endpoint = resolve_endpoint(config, "custom:tf", "")

    assert endpoint is not None
    assert (endpoint.base_url, endpoint.api_key, endpoint.model) == ("http://tf.test/v1", "secret", "agent")
    assert resolve_endpoint(config, "nous", "m") is None
    with pytest.raises(ValueError):
        resolve_endpoint(config, "custom:missing", "")
