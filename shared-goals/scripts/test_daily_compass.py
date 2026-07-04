#!/usr/bin/env python3
"""Small unittest suite for pure daily-compass logic."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from unittest import mock
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
    def test_enrich_runtime_runs_area_batch_before_compass_with_shared_session(self) -> None:
        runtime = {
            "signal_prompt": "Compass prompt",
            "signal": "",
            "dimensions": ["mind"],
            "areas": [
                {
                    "name": "News",
                    "key": "news",
                    "dimension": "mind",
                    "status": "ok",
                    "reason": "",
                    "signal": "",
                    "lines": [{"title": "HN", "url": "", "body": "item", "signal": ""}],
                }
            ],
            "area_meta": {"news": {"area_prompt": "Signal news."}},
        }
        logger = module.TraceLogger(verbose=False)
        session = module.HermesSessionState(mode="chat", hermes_argv=["hermes"], chat_argv=["cli.py"])
        calls: list[tuple[str, object]] = []

        def fake_batch(rt, _logger, _model, _provider, passed_session):
            calls.append(("batch", passed_session))
            rt["areas"][0]["signal"] = "area-done"

        def fake_run_hermes(_prompt, _model, _provider, _logger, label, passed_session, _raw_label=None):
            calls.append((label, passed_session))
            return "compass-done"

        try:
            with mock.patch.object(module, "load_job_model_provider", return_value=("", "")), mock.patch.object(
                module, "run_area_signal_batch", side_effect=fake_batch
            ), mock.patch.object(module, "run_hermes", side_effect=fake_run_hermes):
                module.enrich_runtime(runtime, logger, session)
        finally:
            if hasattr(logger, "_fh") and not logger._fh.closed:
                logger._fh.close()

        self.assertEqual([c[0] for c in calls], ["batch", "compass"])
        self.assertIs(calls[0][1], session)
        self.assertIs(calls[1][1], session)
        self.assertEqual(runtime["areas"][0]["signal"], "area-done")
        self.assertEqual(runtime["signal"], "compass-done")

    def test_build_area_signal_tasks_preserves_runtime_order(self) -> None:
        runtime = {
            "areas": [
                {
                    "name": "Weather",
                    "key": "weather",
                    "dimension": "feeling",
                    "status": "ok",
                    "reason": "",
                    "signal": "",
                    "lines": [{"title": "SPb", "url": "", "body": "rain", "signal": ""}],
                },
                {
                    "name": "News",
                    "key": "news",
                    "dimension": "mind",
                    "status": "ok",
                    "reason": "",
                    "signal": "",
                    "lines": [{"title": "HN", "url": "", "body": "item", "signal": ""}],
                },
            ],
            "area_meta": {
                "weather": {"area_prompt": "Signal weather."},
                "news": {"area_prompt": "Signal news."},
            },
        }
        tasks = module.prepare_area_signal_tasks(runtime)
        self.assertEqual([t.key for t in tasks], ["weather", "news"])
        self.assertEqual([t.index for t in tasks], [0, 1])

    def test_run_area_signal_batch_executes_tasks_sequentially(self) -> None:
        runtime = {
            "areas": [
                {
                    "name": "News",
                    "key": "news",
                    "dimension": "mind",
                    "status": "ok",
                    "reason": "",
                    "signal": "",
                    "lines": [{"title": "HN", "url": "", "body": "item", "signal": ""}],
                },
                {
                    "name": "Weather",
                    "key": "weather",
                    "dimension": "feeling",
                    "status": "ok",
                    "reason": "",
                    "signal": "",
                    "lines": [{"title": "SPb", "url": "", "body": "rain", "signal": ""}],
                },
            ],
            "area_meta": {},
        }

        tasks = [
            module.AreaSignalTask(
                index=0,
                key="news",
                label="area:news",
                area=module.hydrate_boundary_area(runtime["areas"][0]),
                area_prompt="Signal news.",
                prompt="GOAL:\nNews",
            ),
            module.AreaSignalTask(
                index=1,
                key="weather",
                label="area:weather",
                area=module.hydrate_boundary_area(runtime["areas"][1]),
                area_prompt="Signal weather.",
                prompt="GOAL:\nWeather",
            ),
        ]

        called: list[str] = []

        def fake_execute(task, _context):
            called.append(task.key)
            updated = module.hydrate_boundary_area(task.area)
            updated["signal"] = f"{task.key}-done"
            return module.SignalJobResult(key=task.key, area=updated, reason="valid", ok=True)

        logger = module.TraceLogger(verbose=False)
        session = module.HermesSessionState(mode="chat", hermes_argv=["hermes"], chat_argv=["cli.py"])
        try:
            with mock.patch.object(module, "prepare_area_signal_tasks", return_value=tasks), mock.patch.object(
                module, "execute_area_signal_task", side_effect=fake_execute
            ):
                module.run_area_signal_batch(runtime, logger, "", "", session)
        finally:
            if hasattr(logger, "_fh") and not logger._fh.closed:
                logger._fh.close()

        self.assertEqual(called, ["news", "weather"])
        self.assertEqual(runtime["areas"][0]["signal"], "news-done")
        self.assertEqual(runtime["areas"][1]["signal"], "weather-done")

    def test_build_area_signal_tasks_includes_only_prompted_areas(self) -> None:
        runtime = {
            "areas": [
                {
                    "name": "News",
                    "key": "news",
                    "dimension": "mind",
                    "status": "ok",
                    "reason": "",
                    "signal": "",
                    "lines": [{"title": "HN", "url": "", "body": "item", "signal": ""}],
                },
                {
                    "name": "Weather",
                    "key": "weather",
                    "dimension": "feeling",
                    "status": "ok",
                    "reason": "",
                    "signal": "",
                    "lines": [{"title": "Samara", "url": "", "body": "rain", "signal": ""}],
                },
            ],
            "area_meta": {
                "news": {"area_prompt": "Summarize as JSON."},
                "weather": {"area_prompt": ""},
            },
        }
        tasks = module.build_area_signal_tasks(runtime)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].key, "news")
        self.assertEqual(tasks[0].index, 0)
        self.assertTrue(tasks[0].prompt.startswith("GOAL:"))

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
            "status": "ok",
            "reason": "",
            "signal": "ok",
            "lines": [{"title": "Samara", "url": "", "body": "", "signal": ""}],
        }
        self.assertTrue(shared.is_valid_boundary_area_context(payload, "weather"))

    def test_boundary_area_context_validation_accepts_empty_signals(self) -> None:
        payload = {
            "status": "ok",
            "reason": "",
            "signal": "",
            "lines": [
                {"title": "Samara", "url": "", "body": "Clear", "signal": ""},
                {"title": "Humidity", "url": "", "body": "40%", "signal": ""},
            ],
        }
        self.assertTrue(shared.is_valid_boundary_area_context(payload, "weather"))
        self.assertEqual(payload["signal"], "")
        self.assertTrue(all(line["signal"] == "" for line in payload["lines"]))

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
