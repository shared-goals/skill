#!/usr/bin/env python3
"""Tests for deterministic wtd-update-webhook starter flow."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


WEBHOOK_PATH = Path.home() / ".hermes" / "skills" / "shared-goals" / "wtd-update-webhook" / "scripts" / "wtd-update-webhook.py"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


mod = _load_module("wtd_update_webhook_det", WEBHOOK_PATH)


class WtdUpdateWebhookDeterministicTests(unittest.TestCase):
    def test_silent_for_non_target_repo(self) -> None:
        payload = {
            "repository": {"full_name": "someone/else"},
            "ref": "refs/heads/master",
            "commits": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = mod.run_for_payload(payload, state_path=Path(tmp) / "state.json", start_reingest_fn=lambda c: {})
        self.assertIsNone(out)

    def test_silent_when_no_text_changes(self) -> None:
        payload = {
            "repository": {"full_name": "bongiozzo/whattodo"},
            "ref": "refs/heads/master",
            "commits": [{"added": ["build/x.md"], "modified": [], "removed": []}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = mod.run_for_payload(payload, state_path=Path(tmp) / "state.json", start_reingest_fn=lambda c: {})
        self.assertIsNone(out)

    def test_sets_processing_state_and_calls_reingest(self) -> None:
        payload = {
            "repository": {"full_name": "bongiozzo/whattodo"},
            "ref": "refs/heads/master",
            "before": "a" * 40,
            "after": "b" * 40,
            "commits": [
                {
                    "added": ["text/p1-010-happiness.md"],
                    "modified": ["text/p2-020-x.md"],
                    "removed": [],
                }
            ],
        }
        called: list[list[str]] = []

        def fake_start(chapters: list[str]) -> dict:
            called.append(chapters)
            return {"chapters": chapters}

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            out = mod.run_for_payload(payload, state_path=state_path, start_reingest_fn=fake_start)
            self.assertIsInstance(out, str)
            self.assertIn("processing", out)
            state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(called, [["p1-010-happiness", "p2-020-x"]])
        self.assertEqual(state["status"], "processing")
        self.assertEqual(state["commit_range"], "aaaaaaa..bbbbbbb")
        self.assertEqual(state["chapters"], ["p1-010-happiness", "p2-020-x"])


if __name__ == "__main__":
    unittest.main()
