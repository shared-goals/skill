#!/usr/bin/env python3
"""Tests for sg-prd status script and WTD webhook triage script."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent
AREAS_DIR = Path.home() / ".hermes" / "skills" / "shared-goals" / "areas"
WEBHOOK_SKILL_DIR = Path.home() / ".hermes" / "skills" / "shared-goals" / "wtd-prd-webhook" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


SG_PRD_STATUS_PATH = AREAS_DIR / "sg-prd" / "scripts" / "daily-sg-prd-status.py"
WEBHOOK_PATH = WEBHOOK_SKILL_DIR / "wtd-prd-webhook.py"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


sg_prd_status = _load_module("sg_prd_status_module", SG_PRD_STATUS_PATH)
webhook_mod = _load_module("wtd_prd_webhook_module", WEBHOOK_PATH)


class SgPrdStatusTests(unittest.TestCase):
    def test_parse_open_questions_returns_one_line_per_section(self) -> None:
        text = """
# BACKLOG

## Приоритетные задачи

### 🔴 Partner service — who is first partner?
**Коммит:** abcdef1
**Вопрос:** Need concrete partner candidate.

### 🟡 Goal Discovery matching approach
- exact/fuzzy matching
- semantic search

## Feedback от Сергея
- done
""".strip()

        lines = sg_prd_status.parse_open_questions(text)
        self.assertEqual(len(lines), 2)
        self.assertIn("Partner service", lines[0]["title"])
        self.assertEqual(lines[0]["signal"], "")
        self.assertTrue(lines[0]["url"].startswith("https://github.com/shared-goals/prd/blob/main/BACKLOG.md#"))
        self.assertIn("Goal Discovery", lines[1]["title"])


class WtdPrdWebhookTests(unittest.TestCase):
    def test_decision_update_when_text_changed(self) -> None:
        payload = {
            "repository": {"full_name": "bongiozzo/whattodo"},
            "ref": "refs/heads/master",
            "before": "a" * 40,
            "after": "b" * 40,
            "commits": [
                {"added": ["text/p1-010-happiness.md"], "modified": [], "removed": []},
            ],
        }
        out = webhook_mod._decision_for_payload(payload)
        self.assertFalse(out["ignored"])
        self.assertTrue(out["should_update_prd"])
        self.assertEqual(out["decision"], "UPDATE_PRD")
        self.assertEqual(out["decision_hint"], "UPDATE_PRD")
        self.assertTrue(out["requires_memory_review"])
        self.assertEqual(out["memory_tags"], ["project:sg", "mvp", "wtd", "prd"])
        self.assertIn("Shared Goals MVP PRD maintenance context", out["memory_query"])
        self.assertIn("text/p1-010-happiness.md", out["relevant_paths"])

    def test_decision_no_update_for_noise_only(self) -> None:
        payload = {
            "repository": {"full_name": "bongiozzo/whattodo"},
            "ref": "refs/heads/master",
            "commits": [
                {"added": [], "modified": ["build/summary_source.md"], "removed": []},
            ],
        }
        out = webhook_mod._decision_for_payload(payload)
        self.assertFalse(out["ignored"])
        self.assertFalse(out["should_update_prd"])
        self.assertEqual(out["decision"], "NO_UPDATE")

    def test_ignored_for_other_repo(self) -> None:
        payload = {
            "repository": {"full_name": "someone/else"},
            "ref": "refs/heads/master",
            "commits": [],
        }
        out = webhook_mod._decision_for_payload(payload)
        self.assertTrue(out["ignored"])


if __name__ == "__main__":
    unittest.main()
