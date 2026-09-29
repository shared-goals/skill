#!/usr/bin/env python3
"""Behaviour-lock harness for the Daily Compass refactor (T-CON-1, T-RANK-*, T-REN-1).

Strict xfails mark target behaviour not built yet; they flip to failures once fixed,
so remove the marker in the task that implements them.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from urllib.error import URLError

import pytest
import yaml
from pydantic import ValidationError

SCRIPTS_DIR = Path(__file__).parent
FIXTURES = SCRIPTS_DIR / "fixtures"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import shared_goals_platform as platform
from compass.collect import run_boundary
from compass.config import build_skill_index
from compass.models import BoundaryPayload


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


compass = _load("harness_daily_compass", "daily-compass.py")
sg_status = _load("harness_sg_status", "daily-shared-goals-status.py")

FROZEN_NOW = datetime(2026, 9, 27, 8, 0, 0)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW if tz is None else FROZEN_NOW.replace(tzinfo=tz)


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def logger(tmp_path, monkeypatch):
    monkeypatch.setattr(compass, "LOGS_DIR", tmp_path)
    trace = compass.TraceLogger(verbose=False)
    yield trace
    trace._fh.close()


def _shared_goals_task(lines: list[dict]) -> object:
    return compass.AreaSignalTask(
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
            "lines": lines,
        },
        area_prompt="",
        prompt="",
        signal_max_chars=2000,
    )


def _selected_goal_title(lines: list[dict], logger, monkeypatch) -> str:
    monkeypatch.setattr(compass, "run_hindsight_recall", lambda *_: compass.Recall(memories=()))
    monkeypatch.setattr(compass, "run_hermes_raw", lambda *_args, **_kwargs: ('{"signal":"Do the next step."}', 0.1))
    result = compass.run_shared_goals_signal(
        _shared_goals_task(lines), "test-model", "test-provider", logger, compass.HermesSessionState("chat", [], [])
    )
    return result.area["lines"][0]["title"]


# T-CON-1 ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_fixture("boundary_payloads.json")["valid"]))
def test_boundary_payload_contract_accepts_valid(name: str) -> None:
    payload = _fixture("boundary_payloads.json")["valid"][name]
    BoundaryPayload.model_validate(payload)


@pytest.mark.parametrize("reason", sorted(_fixture("boundary_payloads.json")["invalid"]))
def test_boundary_payload_contract_rejects_invalid(reason: str) -> None:
    payload = _fixture("boundary_payloads.json")["invalid"][reason]
    with pytest.raises(ValidationError):
        BoundaryPayload.model_validate(payload)


def _active_area_scripts() -> list[tuple[str, Path]]:
    skill_index = build_skill_index(compass.HERMES_SKILLS_DIR)
    out: list[tuple[str, Path]] = []
    for path in sorted(compass.AREAS_DIR.glob("*.yaml")):
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        # shag runs a git-sync preflight; not safe for a test run.
        if cfg.get("status") != "active" or path.stem == "shag":
            continue
        skill_dir = skill_index.get(str(cfg.get("skill", "")))
        if skill_dir:
            out.append((path.stem, skill_dir / "scripts" / f"daily-{path.stem}-status.py"))
    return out


@pytest.mark.live
@pytest.mark.parametrize(("key", "script"), _active_area_scripts())
def test_live_boundary_script_output_matches_contract(key: str, script: Path) -> None:
    assert script.exists(), f"{key}: missing {script}"
    run_boundary(script)


# T-RANK ----------------------------------------------------------------------


def test_platform_lines_follow_platform_dimension_order() -> None:
    payload = _fixture("platform_shared_goals.json")
    tags = [re.search(r"#sg-\S+", line["title"]).group(0) for line in platform.build_platform_lines(payload)]
    assert tags == ["#sg-music", "#sg-photo", "#sg-run", "#sg-read"]


def test_rendered_dimension_order_follows_platform(logger, monkeypatch) -> None:
    payload = _fixture("platform_shared_goals.json")
    monkeypatch.setattr(platform, "fetch_platform_shared_goals", lambda: payload)
    runtime = compass.build_runtime([], {}, logger)
    assert runtime["dimensions"] == payload["dimension_order"]
    assert runtime["ranking_fallback"] is False


def test_platform_outage_falls_back_to_skill_order_and_is_flagged(logger, monkeypatch) -> None:
    monkeypatch.setattr(platform, "fetch_platform_shared_goals", lambda: None)
    monkeypatch.setattr(compass, "datetime", FrozenDatetime)
    runtime = compass.build_runtime([], {}, logger)
    assert runtime["dimensions"] == ["faith", "will", "feeling", "mind"]
    assert runtime["ranking_fallback"] is True
    rendered = compass.render_template(compass.build_render_context(runtime))
    assert "platform unavailable" in rendered


def test_never_fed_goal_is_selected_first(logger, monkeypatch) -> None:
    lines = platform.build_platform_lines(_fixture("platform_shared_goals.json"))
    assert "#sg-music" in _selected_goal_title(lines, logger, monkeypatch)


def test_equal_hunger_keeps_platform_order(logger, monkeypatch) -> None:
    payload = _fixture("platform_shared_goals.json")
    payload["dimension_order"] = ["faith", "will", "mind"]
    payload["dimensions"] = [block for block in payload["dimensions"] if block["dimension"] != "feeling"]
    lines = platform.build_platform_lines(payload)
    assert "#sg-photo" in _selected_goal_title(lines, logger, monkeypatch)


@pytest.mark.parametrize("update_compass", [False, True])
def test_platform_unavailable_is_flagged(update_compass: bool, tmp_path, monkeypatch) -> None:
    def refuse(*_args, **_kwargs):
        raise URLError("connection refused")

    compass_md = tmp_path / "Compass.md"
    compass_md.write_text(
        "## Logos\n\n- [ ] keep me\n\n## Shared Goals\n\n- Photo #sg-photo hunger:3d\n", encoding="utf-8"
    )
    before = compass_md.read_text(encoding="utf-8")
    argv = ["daily-shared-goals-status.py"]
    if update_compass:
        argv += ["--update-compass", "--compass-path", str(compass_md)]

    monkeypatch.setenv("SHARED_GOALS_API_BASE_URL", "http://platform.test")
    monkeypatch.setenv("SHARED_GOALS_AGENT_KEY_ID", "test-key")
    monkeypatch.setattr(platform, "load_env_file", lambda *_: None)
    monkeypatch.setattr(sg_status, "load_env_file", lambda *_: None)
    monkeypatch.setattr(platform, "urlopen", refuse)
    monkeypatch.setattr(sys, "argv", argv)
    out = io.StringIO()
    with redirect_stdout(out):
        assert sg_status.main() == 0
    payload = BoundaryPayload.model_validate_json(out.getvalue())
    assert (payload.status, payload.reason) == ("error", "platform_unavailable")
    assert compass_md.read_text(encoding="utf-8") == before


# T-REN-1 ---------------------------------------------------------------------


def test_render_matches_golden_output(monkeypatch) -> None:
    monkeypatch.setattr(compass, "datetime", FrozenDatetime)
    context = compass.build_render_context(_fixture("runtime_render.json"))
    golden = (FIXTURES / "golden_daily_output.md").read_text(encoding="utf-8")
    assert compass.render_template(context) == golden
