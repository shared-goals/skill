#!/usr/bin/env python3
"""Tests for deterministic hindsight-processing-webhook finisher flow."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


HOOK_PATH = Path.home() / ".hermes" / "skills" / "shared-goals" / "hindsight-processing-webhook" / "scripts" / "hindsight-processing-webhook.py"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


mod = _load_module("hindsight_processing_webhook_det", HOOK_PATH)


class HindsightProcessingWebhookTests(unittest.TestCase):
    def test_silent_for_unwatched_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps({"status": "processing"}), encoding="utf-8")
            out = mod.run_for_event({"event": "other.event"}, state_path=state_path, counts_fn=lambda *_: {"total": 0})
        self.assertIsNone(out)

    def test_silent_when_not_processing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            out = mod.run_for_event(
                {"event": "consolidation.completed", "operation_id": "op-1"},
                state_path=state_path,
                counts_fn=lambda *_: {"total": 0},
            )
        self.assertIsNone(out)

    def test_silent_when_queue_not_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps({"status": "processing"}), encoding="utf-8")
            out = mod.run_for_event(
                {"event": "retain.completed", "operation_id": "op-1"},
                state_path=state_path,
                counts_fn=lambda *_: {"retain_pending": 1, "retain_processing": 0, "consolidation_pending": 0, "consolidation_processing": 0, "total": 1},
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIsNone(out)
        self.assertEqual(state["status"], "processing")

    def test_retain_completed_finalizes_when_queue_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps({"status": "processing", "started_at": "t0"}), encoding="utf-8")
            out = mod.run_for_event(
                {"event": "retain.completed", "operation_id": "op-retain"},
                state_path=state_path,
                counts_fn=lambda *_: {
                    "retain_pending": 0,
                    "retain_processing": 0,
                    "consolidation_pending": 0,
                    "consolidation_processing": 0,
                    "total": 0,
                },
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertIsInstance(out, str)
        self.assertIn("completed", out)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["completion_event"], "retain.completed")
        self.assertEqual(state["completion_operation_id"], "op-retain")

    def test_marks_completed_when_queue_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps({"status": "processing", "started_at": "t0"}), encoding="utf-8")
            out = mod.run_for_event(
                {"event": "consolidation.completed", "operation_id": "op-2"},
                state_path=state_path,
                counts_fn=lambda *_: {"retain_pending": 0, "retain_processing": 0, "consolidation_pending": 0, "consolidation_processing": 0, "total": 0},
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertIsInstance(out, str)
        self.assertIn("completed", out)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["completion_event"], "consolidation.completed")
        self.assertEqual(state["completion_operation_id"], "op-2")


if __name__ == "__main__":
    unittest.main()
