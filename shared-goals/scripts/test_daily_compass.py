#!/usr/bin/env python3
"""Small unittest suite for pure daily-compass logic."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "daily-compass.py"
SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_compass_shared as shared

spec = importlib.util.spec_from_file_location("daily_compass_module", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)  # type: ignore[attr-defined]


class DailyCompassPureTests(unittest.TestCase):
    def test_choose_primary_dimension(self) -> None:
        self.assertEqual(module.choose_primary_dimension(["mind", "faith"]), "mind")
        self.assertEqual(module.choose_primary_dimension(["unknown", "will"]), "will")

    def test_inline_list_parser(self) -> None:
        self.assertEqual(module.parse_inline_list("[faith, will]"), ["faith", "will"])
        self.assertEqual(module.parse_inline_list("[]"), [])
        self.assertEqual(module.parse_inline_list("not-list"), [])

    def test_template_tokenize_minimal(self) -> None:
        toks = module.tpl_tokenize("Hello {name}")
        self.assertTrue(any(t[0] == "VAR" for t in toks))

    def test_trace_logger_creates_file_immediately(self) -> None:
        logger = module.TraceLogger(verbose=False)
        try:
            self.assertTrue(logger.path.exists())
            logger.log("unit-test-line")
            log_path = logger.write()
            text = log_path.read_text(encoding="utf-8")
            self.assertIn("unit-test-line", text)
        finally:
            try:
                if hasattr(logger, "_fh") and not logger._fh.closed:
                    logger._fh.close()
            except OSError:
                pass

    def test_resolve_area_signal_prompt_extracts_area_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            skill_md = Path(tmp_dir) / "SKILL.md"
            skill_md.write_text(
                """
## Area signal

1. Do one thing.
2. Do second thing.

## Other section

Ignore.
""".strip()
                + "\n",
                encoding="utf-8",
            )
            area_prompt = module.resolve_area_signal_prompt(skill_md)
            self.assertEqual(area_prompt, "1. Do one thing.\n2. Do second thing.")

    def test_validate_json_response_strict_accepts_clean_json(self) -> None:
        text = (
            '{"name":"Weather","key":"weather","dimension":"feeling",'
            '"signal":"ok","lines":[{"title":"Samara","url":"","body":"","signal":""}]}'
        )
        payload, reason = shared.validate_json_response_strict(text, "weather")
        self.assertEqual(reason, "valid")
        self.assertIsNotNone(payload)

    def test_validate_json_response_strict_accepts_markdown_fence(self) -> None:
        text = (
            "```json\n"
            '{"name":"Weather","key":"weather","dimension":"feeling",'
            '"signal":"ok","lines":[{"title":"Samara","url":"","body":"","signal":""}]}'
            "\n```"
        )
        payload, reason = shared.validate_json_response_strict(text, "weather")
        self.assertIsNotNone(payload)
        self.assertEqual(reason, "valid")

    def test_validate_json_response_strict_accepts_wrapper_prose_by_extracting_json(self) -> None:
        text = (
            "Done. Final result:\n"
            '{"name":"Weather","key":"weather","dimension":"feeling",'
            '"signal":"ok","lines":[{"title":"Samara","url":"","body":"","signal":""}]}'
        )
        payload, reason = shared.validate_json_response_strict(text, "weather")
        self.assertIsNotNone(payload)
        self.assertEqual(reason, "valid_with_prose")

    def test_validate_json_response_strict_rejects_schema_error(self) -> None:
        text = '{"name":"Weather","key":"wrong","dimension":"feeling","signal":"","lines":[]}'
        payload, reason = shared.validate_json_response_strict(text, "weather")
        self.assertIsNone(payload)
        self.assertEqual(reason, "schema_error")

    def test_validate_json_response_strict_rejects_extra_area_key(self) -> None:
        text = (
            '{"name":"Weather","key":"weather","dimension":"feeling",'
            '"signal":"ok","lines":[{"title":"Samara","url":"","body":"","signal":""}],'
            '"extra":"not-allowed"}'
        )
        payload, reason = shared.validate_json_response_strict(text, "weather")
        self.assertIsNone(payload)
        self.assertEqual(reason, "schema_error")

    def test_validate_json_response_strict_rejects_extra_line_key(self) -> None:
        text = (
            '{"name":"Weather","key":"weather","dimension":"feeling",'
            '"signal":"ok","lines":[{"title":"Samara","url":"","body":"","signal":"","extra":"x"}]}'
        )
        payload, reason = shared.validate_json_response_strict(text, "weather")
        self.assertIsNone(payload)
        self.assertEqual(reason, "schema_error")

    def test_should_retry_area_signal_for_failed_validation_reasons(self) -> None:
        self.assertTrue(module.should_retry_area_signal("schema_error", None))
        self.assertTrue(module.should_retry_area_signal("not_dict", None))
        self.assertTrue(module.should_retry_area_signal("empty", None))
        self.assertFalse(module.should_retry_area_signal("valid", {"key": "weather"}))

    def test_append_signal_note_idempotent(self) -> None:
        area = {
            "name": "Weather",
            "key": "weather",
            "dimension": "feeling",
            "status": "ok",
            "reason": "",
            "signal": "initial",
            "lines": [{"title": "Samara", "url": "", "body": "", "signal": ""}],
        }
        module.append_signal_note(area, "(prose stripped)")
        module.append_signal_note(area, "(prose stripped)")
        self.assertEqual(area["signal"], "initial (prose stripped)")

    def test_boundary_area_context_validation_accepts_metadata(self) -> None:
        payload = {
            "name": "Weather",
            "key": "weather",
            "dimension": "feeling",
            "status": "ok",
            "reason": "",
            "signal": "ok",
            "lines": [{"title": "Samara", "url": "", "body": "", "signal": ""}],
        }
        self.assertTrue(shared.is_valid_boundary_area_context(payload, "weather"))

    def test_project_boundary_to_area_context_drops_metadata(self) -> None:
        payload = {
            "name": "Weather",
            "key": "weather",
            "dimension": "feeling",
            "status": "ok",
            "reason": "",
            "signal": "ok",
            "lines": [{"title": "Samara", "url": "", "body": "", "signal": ""}],
        }
        projected = shared.project_boundary_to_area_context(payload)
        self.assertEqual(set(projected.keys()), {"name", "key", "dimension", "signal", "lines"})

if __name__ == "__main__":
    unittest.main(verbosity=2)
