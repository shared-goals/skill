#!/usr/bin/env python3
"""Failure isolation for boundary collection (T-FAIL-1)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from compass.collect import BoundaryError, collect_areas, run_boundary
from compass.models import AreaConfig

OK_PAYLOAD = {"status": "ok", "reason": "", "lines": [{"title": "T", "url": "", "body": "B", "signal": ""}]}

SCRIPTS = {
    "good": f"import json; print('log noise'); print(json.dumps({OK_PAYLOAD!r}))",
    "crash": "import sys; sys.stderr.write('boom'); sys.exit(3)",
    "silent-crash": "raise SystemExit(2)",
    "slow": "import time; time.sleep(30)",
    "prose": "print('no json here')",
    "bad-schema": "import json; print(json.dumps({'status': 'done', 'reason': '', 'lines': []}))",
    "env": textwrap.dedent(
        """
        import json, os
        title = os.environ['DAILY_COMPASS_RUN_ID'] + '/' + os.environ['DAILY_COMPASS_AREA_KEY']
        print(json.dumps({'status': 'ok', 'reason': '', 'lines': [{'title': title, 'url': '', 'body': '', 'signal': ''}]}))
        """
    ),
}


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("crash", "boom"),
        ("silent-crash", "boundary_exit_2"),
        ("slow", "boundary_timeout"),
        ("prose", "boundary_non_json"),
        ("bad-schema", "boundary_schema_invalid"),
    ],
)
def test_run_boundary_failures_raise_reason(name: str, reason: str, tmp_path: Path) -> None:
    script = _write(tmp_path / f"{name}.py", SCRIPTS[name])
    with pytest.raises(BoundaryError, match=reason):
        run_boundary(script, timeout=2)


def test_run_boundary_tolerates_log_noise_around_json(tmp_path: Path) -> None:
    payload = run_boundary(_write(tmp_path / "good.py", SCRIPTS["good"]), timeout=10)
    assert payload.model_dump(exclude={"signal", "ts"}) == {**OK_PAYLOAD, "lines": tuple(OK_PAYLOAD["lines"])}


def test_one_failing_area_does_not_affect_others(tmp_path: Path) -> None:
    skills: dict[str, Path] = {}
    areas: list[AreaConfig] = []
    for key in ("good", "crash", "slow", "env"):
        skill_dir = tmp_path / key
        _write(skill_dir / "scripts" / f"daily-{key}-status.py", SCRIPTS[key])
        skills[key] = skill_dir
        areas.append(AreaConfig(key=key, name=key.title(), dimensions=("mind",), skill=key, status="active"))
    areas.append(AreaConfig(key="nomatch", name="Nomatch", dimensions=("will",), skill="missing", status="active"))
    skills["noscript"] = tmp_path / "noscript"
    areas.append(AreaConfig(key="noscript", name="Noscript", dimensions=("faith",), skill="noscript", status="active"))
    logs: list[str] = []

    evidence = collect_areas(areas, skills, run_id="run-1", log=logs.append, timeout=3)

    by_key = {item.key: item for item in evidence}
    assert [item.name for item in evidence] == sorted(item.name for item in evidence)
    assert (by_key["good"].status, by_key["good"].lines[0].title) == ("ok", "T")
    assert by_key["env"].lines[0].title == "run-1/env"
    assert (by_key["crash"].status, by_key["crash"].reason) == ("error", "boom")
    assert (by_key["slow"].status, by_key["slow"].reason) == ("error", "boundary_timeout")
    assert (by_key["nomatch"].status, by_key["nomatch"].reason) == ("error", "skill_not_found")
    assert (by_key["noscript"].status, by_key["noscript"].reason) == ("error", "boundary_script_missing")
    assert by_key["noscript"].dimension == "faith"
    assert len(logs) == len(areas)


def test_collect_areas_with_no_areas_is_empty() -> None:
    assert collect_areas([], {}, run_id="r", log=lambda _msg: None) == []
