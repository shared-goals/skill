#!/usr/bin/env python3
"""Small unittest suite for pure daily-compass logic."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).parent / "daily-compass.py"
SHARED_GOALS_MODULE_PATH = Path(__file__).parent / "daily-shared-goals-status.py"
SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_compass_shared as shared

spec = importlib.util.spec_from_file_location("daily_compass_module", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)  # type: ignore[attr-defined]

sg_spec = importlib.util.spec_from_file_location("daily_shared_goals_module", SHARED_GOALS_MODULE_PATH)
assert sg_spec and sg_spec.loader
sg_module = importlib.util.module_from_spec(sg_spec)
sys.modules[sg_spec.name] = sg_module
sg_spec.loader.exec_module(sg_module)  # type: ignore[attr-defined]


class DailyCompassPureTests(unittest.TestCase):
    def test_shared_goals_reflection_runs_once_for_hungriest_goal(self) -> None:
        calls: list[tuple[str, dict[str, str]]] = []
        prompt = "Work on the selected goal with the next concrete action first. #sg-photo"

        def fake_reflect(query: str, _task: object, _logger: object) -> str:
            calls.append(("hindsight_reflect", {"query": query}))
            return json.dumps({"result": prompt})

        task = module.AreaSignalTask(
            index=0,
            key="shared-goals",
            label="area:shared-goals",
            area={
                "name": "Shared Goals",
                "key": "shared-goals",
                "dimension": "faith",
                "status": "ok",
                "reason": "",
                "signal": "",
                "lines": [
                    {"title": "Less hungry #sg-less hunger:6d", "body": "Later", "signal": ""},
                    {"title": "Hungry #sg-photo hunger:14d", "body": "Do photos", "signal": ""},
                ],
            },
            area_prompt="",
            prompt="",
            signal_max_chars=2000,
        )
        logger = module.TraceLogger(verbose=False)
        try:
            with mock.patch.object(
                module,
                "run_hermes_hindsight_reflect",
                side_effect=fake_reflect,
            ):
                result = module.run_shared_goals_reflection(task, logger)
        finally:
            if hasattr(logger, "_fh") and not logger._fh.closed:
                logger._fh.close()

        self.assertTrue(result.ok)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "hindsight_reflect")
        self.assertIn("Hungry #sg-photo hunger:14d", calls[0][1]["query"])
        self.assertEqual(result.area["lines"][1]["signal"], prompt)

    def test_json_area_signal_contract_uses_area_limit(self) -> None:
        contract = module.json_area_signal_contract({"signal_max_chars": 2000})
        self.assertIn("LineContext `signal` is not more than 2000 chars.", contract)

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

    def test_build_platform_next_steps_area_preserves_goal_tags(self) -> None:
        payload = {
            "dimension_order": ["faith", "will", "feeling", "mind"],
            "dimensions": [
                {
                    "dimension": "faith",
                    "last_fed_at": "2026-07-27T14:00:00+00:00",
                    "goals": [
                        {
                            "goal_tag": "#sg-sharedgoals-dev",
                            "goal_title": "Shared Goals Development",
                            "dimensions": ["faith", "mind"],
                            "next_step_text": "Run Plavdom pilot as the first concrete partner-style goal experiment",
                        }
                    ],
                }
            ],
        }
        lines = sg_module.build_platform_lines(payload)

        self.assertEqual(len(lines), 1)
        self.assertIn("Shared Goals Development", lines[0]["title"])
        self.assertIn("#sg-sharedgoals-dev", lines[0]["title"])
        self.assertIn("#faith", lines[0]["title"])
        self.assertIn("#mind", lines[0]["title"])
        self.assertIn("hunger:", lines[0]["title"])
        self.assertNotIn("#sg-sharedgoals-dev", lines[0]["body"])

    def test_build_runtime_skips_platform_feed_by_default(self) -> None:
        logger = module.TraceLogger(verbose=False)
        try:
            runtime = module.build_runtime([], {}, logger)
        finally:
            if hasattr(logger, "_fh") and not logger._fh.closed:
                logger._fh.close()

        self.assertEqual(runtime["areas"], [])

    def test_run_next_steps_recommendation_mode_uses_area_signal_pipeline(self) -> None:
        payload = {
            "dimension_order": ["will", "faith"],
            "dimensions": [
                {
                    "dimension": "will",
                    "goals": [
                        {
                            "goal_title": "Will Goal",
                            "goal_tag": "#sg-will",
                            "next_step_text": "Step will",
                        }
                    ],
                }
            ],
        }
        lines = sg_module.build_platform_lines(payload)
        self.assertEqual(len(lines), 1)
        self.assertIn("Will Goal", lines[0]["title"])

    def test_render_shared_goals_section_formats_dimensions_goals_and_steps(self) -> None:
        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                return datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

        with mock.patch.object(shared, "datetime", FrozenDateTime):
            text = sg_module.render_shared_goals_section(
                {
                    "dimension_order": ["mind", "faith", "will", "feeling"],
                    "hunger_diagnostics": [
                        {"dimension": "mind", "last_fed_at": None},
                        {"dimension": "faith", "last_fed_at": "2026-07-26T12:00:00+00:00"},
                        {"dimension": "will", "last_fed_at": None},
                        {"dimension": "feeling", "last_fed_at": None},
                    ],
                    "dimensions": [
                        {
                            "dimension": "faith",
                            "last_fed_at": "2026-07-26T12:00:00+00:00",
                            "goals": [
                                {
                                    "goal_tag": "#sg-homelab",
                                    "goal_title": "Homelab",
                                    "next_step_text": "Configure stable homelab infrastructure",
                                },
                                {
                                    "goal_tag": "#sg-music",
                                    "goal_title": "Music",
                                    "next_step_text": "Develop Music autodiscovery and organization with SoulBeets",
                                }
                            ],
                        }
                    ],
                }
            )
        self.assertIn("## Shared Goals", text)
        self.assertIn("### Mind (never)", text)
        self.assertIn("### Faith (2d)", text)
        self.assertIn("### Will (never)", text)
        self.assertIn("### Feeling (never)", text)
        self.assertLess(text.index("### Mind"), text.index("### Faith"))
        self.assertLess(text.index("### Faith"), text.index("### Will"))
        self.assertLess(text.index("### Will"), text.index("### Feeling"))
        self.assertIn("- **Homelab #sg-homelab hunger:2d**", text)
        self.assertIn("- [ ] Configure stable homelab infrastructure #sg-homelab", text)
        self.assertIn("- **Music #sg-music hunger:2d**", text)
        self.assertIn("- [ ] Develop Music autodiscovery and organization with SoulBeets #sg-music", text)
        self.assertIn("  - [ ] Configure stable homelab infrastructure #sg-homelab\n- **Music #sg-music hunger:2d**", text)
        self.assertNotIn("\n\n- **Music #sg-music hunger:2d**", text)
        self.assertIn("No goals in this dimension.", text)
        self.assertIn("\n\n- **Homelab", text)

    def test_render_shared_goals_section_handles_empty(self) -> None:
        text = sg_module.render_shared_goals_section({"dimensions": []})
        self.assertIn("## Shared Goals", text)
        self.assertIn("### Faith (never)", text)
        self.assertIn("### Will (never)", text)
        self.assertIn("### Feeling (never)", text)
        self.assertIn("### Mind (never)", text)
        self.assertIn("No goals in this dimension.", text)

    def test_preview_commit_fields_allows_editing_done_and_next_step(self) -> None:
        with mock.patch("builtins.input", side_effect=["y", "Updated done", "y", "Updated next step"]):
            done, next_step = sg_module._prompt_commit_field_preview(
                goal_title="Shared Goals Development",
                done="Original done",
                next_step="Original next step",
            )

        self.assertEqual(done, "Updated done")
        self.assertEqual(next_step, "Updated next step")

    def test_render_next_steps_from_compass_snapshot_uses_shared_goals_line_signals(self) -> None:
        text = shared.render_next_steps_from_compass_snapshot(
            {
                "areas": [
                    {
                        "key": "shared-goals",
                        "lines": [
                            {
                                "title": "Shared Goals Development #sg-sharedgoals-dev",
                                "url": "",
                                "body": "Run Plavdom pilot\nUpdate sg-prd README",
                                "signal": "Run Plavdom pilot with one concrete partner",
                            },
                            {
                                "title": "Music #sg-music",
                                "url": "",
                                "body": "Choose tracks",
                                "signal": "",
                            },
                            {
                                "title": "Photo #sg-photo",
                                "url": "",
                                "body": "Develop workflow",
                                "signal": "Build Photos workflow for this week",
                            },
                            {
                                "title": "Homelab #sg-homelab",
                                "url": "",
                                "body": "Configure infrastructure",
                                "signal": "Stabilize Homelab core infrastructure",
                            },
                            {
                                "title": "Extra #sg-extra",
                                "url": "",
                                "body": "Should be hidden",
                                "signal": "",
                            },
                            {
                                "title": "Overflow #sg-overflow",
                                "url": "",
                                "body": "Too many",
                                "signal": "Must be trimmed by cap",
                            },
                        ],
                    }
                ]
            }
        )

        self.assertIn("## Logos", text)
        self.assertIn("- [ ] Run Plavdom pilot with one concrete partner", text)
        self.assertNotIn("- [ ] Choose tracks", text)
        self.assertNotIn("- [ ] Build Photos workflow for this week", text)
        self.assertNotIn("- [ ] Stabilize Homelab core infrastructure", text)
        self.assertNotIn("- [ ] Should be hidden", text)
        self.assertNotIn("- [ ] Overflow #sg-overflow", text)
        self.assertNotIn("Must be trimmed by cap", text)

        next_step_lines = [line for line in text.splitlines() if line.startswith("- [ ] ")]
        self.assertEqual(len(next_step_lines), 1)

    def test_build_area_signal_prompt_uses_area_guidance_without_special_cases(self) -> None:
        prompt = module.build_area_signal_prompt(
            "Select one hungry goal and prepare a prompt.",
            {
                "name": "Shared Goals",
                "key": "shared-goals",
                "dimension": "faith",
                "signal": "",
                "lines": [],
            },
        )

        self.assertIn("Select one hungry goal and prepare a prompt.", prompt)
        self.assertNotIn("Shared Goals Logos requirements", prompt)

    def test_parse_completed_goals_from_compass_text_groups_tasks_by_goal(self) -> None:
        text = """## Next Steps

- [ ] Placeholder

## Shared Goals

### Will (never)

- Shared Goals Development #sg-sharedgoals-dev hunger:neverd
    - [x] Unite Daily Compass with Shared Goals MVP development loop #sg-sharedgoals-dev
    - [x] Make Recommended Next Steps and Balanced Shared Goals as view of Compass in Markdown and Telegram #sg-sharedgoals-dev
    - [ ] Update sg-prd skill README to satisfy the current use case #sg-sharedgoals-dev

### Faith (0d)

- Writing Personal WTD text #sg-wtd-writing hunger:0d
    - [ ] Rename WTD context to project:wtd for Shared Goals development memory and PRD workflows #sg-wtd-writing
"""
        parsed = sg_module.parse_completed_goals_from_compass_text(text)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["goal_id"], "sg-sharedgoals-dev")
        self.assertEqual(
            parsed[0]["completed"],
            [
                "Unite Daily Compass with Shared Goals MVP development loop",
                "Make Recommended Next Steps and Balanced Shared Goals as view of Compass in Markdown and Telegram",
            ],
        )
        self.assertEqual(
            parsed[0]["incomplete"],
            ["Update sg-prd skill README to satisfy the current use case"],
        )

    def test_build_platform_shared_goals_lines_uses_hunger_order(self) -> None:
        lines = sg_module.build_platform_lines(
            {
                "dimension_order": ["will", "faith"],
                "dimensions": [
                    {
                        "dimension": "faith",
                        "goals": [
                            {
                                "goal_title": "Faith Goal",
                                "goal_tag": "#sg-faith",
                                "next_step_text": "Step faith",
                            }
                        ],
                    },
                    {
                        "dimension": "will",
                        "goals": [
                            {
                                "goal_title": "Will Goal",
                                "goal_tag": "#sg-will",
                                "next_step_text": "Step will",
                            }
                        ],
                    },
                ],
            }
        )

        self.assertEqual(len(lines), 2)
        self.assertIn("Will Goal", lines[0]["title"])
        self.assertIn("Faith Goal", lines[1]["title"])

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

    def test_extract_session_id_accepts_multiple_formats(self) -> None:
        self.assertEqual(
            module.extract_session_id("session_id: 20260713_080052_9ee155"),
            "20260713_080052_9ee155",
        )
        self.assertEqual(
            module.extract_session_id("**Session ID:** `20260713_080052_9ee155`"),
            "20260713_080052_9ee155",
        )
        self.assertEqual(
            module.extract_session_id("no match", "session id = 20260713_080052_9ee155"),
            "20260713_080052_9ee155",
        )

    def test_persistent_session_state_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state" / "daily-compass-session.json"
            logger = module.TraceLogger(verbose=False)
            try:
                self.assertIsNone(module.load_persistent_session_id(state_path, logger))
                module.save_persistent_session_id(
                    state_path,
                    "20260713_080052_9ee155",
                    "Daily Compass",
                    logger,
                )
                restored = module.load_persistent_session_id(state_path, logger)
                self.assertEqual(restored, "20260713_080052_9ee155")
                saved = state_path.read_text(encoding="utf-8")
                self.assertIn('"session_name": "Daily Compass"', saved)
            finally:
                if hasattr(logger, "_fh") and not logger._fh.closed:
                    logger._fh.close()

if __name__ == "__main__":
    unittest.main(verbosity=2)
