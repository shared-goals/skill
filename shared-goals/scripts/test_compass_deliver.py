from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from compass import deliver


def _run_ok() -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def _run_fail(detail: str) -> SimpleNamespace:
    return SimpleNamespace(returncode=1, stdout="", stderr=detail)


def test_delivers_each_area_then_status_with_pacing() -> None:
    messages = [("Calendar", "Calendar content"), ("Mail", "Mail content")]
    with (
        mock.patch.object(deliver, "hermes_executable", return_value="/hermes"),
        mock.patch.object(deliver.subprocess, "run", return_value=_run_ok()) as run,
        mock.patch.object(deliver.time, "sleep") as sleep,
    ):
        deliver.deliver_area_messages(messages)

    sent = [call.args[0][-1] for call in run.call_args_list]
    assert sent == ["Calendar content", "Mail content", "Daily Compass sent 2/2 area messages: Calendar, Mail"]
    assert all(call.args[0][:5] == ["/hermes", "send", "--to", "telegram", "--quiet"] for call in run.call_args_list)
    assert sleep.call_args_list == [mock.call(deliver.SEND_INTERVAL_SECONDS)] * 2


def test_failed_send_continues_and_errors_reach_status() -> None:
    def side_effect(argv, **kwargs):
        return _run_fail("bot blocked") if "Calendar content" in argv[-1] else _run_ok()

    with (
        mock.patch.object(deliver, "hermes_executable", return_value="/hermes"),
        mock.patch.object(deliver.subprocess, "run", side_effect=side_effect) as run,
        mock.patch.object(deliver.time, "sleep"),
    ):
        deliver.deliver_area_messages([("Calendar", "Calendar content"), ("Mail", "Mail content")])

    sent = [call.args[0][-1] for call in run.call_args_list]
    assert sent == [
        "Calendar content",
        "Mail content",
        "Daily Compass sent 1/2 area messages: Mail | errors: Calendar: Telegram send failed for "
        "area 'Calendar': bot blocked",
    ]
    assert run.call_count == 3


def test_oversized_area_is_clamped_and_delivered_with_note_in_status() -> None:
    messages = [("Big", "x" * (deliver.MAX_SAFE_MESSAGE_UNITS + 100)), ("Small", "ok")]
    with (
        mock.patch.object(deliver, "hermes_executable", return_value="/hermes"),
        mock.patch.object(deliver.subprocess, "run", return_value=_run_ok()) as run,
        mock.patch.object(deliver.time, "sleep"),
    ):
        deliver.deliver_area_messages(messages)

    sent = [call.args[0][-1] for call in run.call_args_list]
    assert deliver.utf16_units(sent[0]) <= deliver.MAX_SAFE_MESSAGE_UNITS
    assert sent[0].endswith(deliver.TRUNCATION_MARKER)
    assert sent[1] == "ok"
    assert "sent 2/2" in sent[2] and "Big: clamped to Telegram safe size" in sent[2]


def test_status_message_is_clamped_when_errors_pile_up() -> None:
    failures = [(f"Area{i}", f"body{i}") for i in range(120)]
    def side_effect(argv, **kwargs):
        return _run_ok() if argv[-1].startswith("Daily Compass sent") else _run_fail("bot blocked")

    with (
        mock.patch.object(deliver, "hermes_executable", return_value="/hermes"),
        mock.patch.object(deliver.subprocess, "run", side_effect=side_effect) as run,
        mock.patch.object(deliver.time, "sleep"),
    ):
        deliver.deliver_area_messages(failures)

    status = run.call_args_list[-1].args[0][-1]
    assert deliver.utf16_units(status) <= deliver.MAX_SAFE_MESSAGE_UNITS
    assert status.endswith(deliver.TRUNCATION_MARKER)
    assert "sent 0/120" in status and "Area0: Telegram send failed" in status


@pytest.mark.parametrize(
    ("messages", "error"),
    [([], "no area messages")],
)
def test_rejects_empty_messages_before_sending(messages, error) -> None:
    with mock.patch.object(deliver.subprocess, "run") as run, pytest.raises(ValueError, match=error):
        deliver.deliver_area_messages(messages)
    run.assert_not_called()
