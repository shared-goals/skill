"""Test a synthetic boundary, or pass --boundary-script PATH to test one reviewed local script."""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from compass.models import BoundaryPayload

from daily_compass_shared import (
    BOUNDARY_SCRIPT_TIMEOUT_SECONDS,
    SCRIPT_DIR as SHARED_GOALS_SCRIPTS_DIR,
    parse_json_object,
)

@pytest.fixture
def script(request, tmp_path):
    selected = request.config.getoption("--boundary-script")
    if selected:
        path = Path(selected).resolve()
        if not path.is_file():
            pytest.fail("selected boundary script does not exist", pytrace=False)
        return path
    sample = json.loads((SHARED_GOALS_SCRIPTS_DIR / "fixtures/boundary_payloads.json").read_text())
    path = tmp_path / "daily-example-status.py"
    path.write_text(f"print({json.dumps(sample['valid']['ok'])!r})\n", encoding="utf-8")
    return path


def _base_env() -> dict[str, str]:
    return dict(os.environ)


def _uv_env() -> dict[str, str]:
    """Simulate the compass runtime: `uv run` exports UV=<path>."""
    env = dict(os.environ)
    env["UV"] = "/usr/local/bin/uv"
    env["VIRTUAL_ENV"] = str(SHARED_GOALS_SCRIPTS_DIR / ".venv")
    return env


def _stripped_env(home: Path) -> dict[str, str]:
    """No credentials, no config — only the minimum to run python."""
    keep = {"PATH", "HOME", "LANG", "LC_ALL", "TERM", "VIRTUAL_ENV"}
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["HOME"] = str(home)
    return env


def run_boundary(script: Path, env: dict[str, str]) -> tuple[int, str, str]:
    child_env = dict(env)
    pythonpath = os.pathsep.join(
        part for part in (str(SHARED_GOALS_SCRIPTS_DIR), child_env.get("PYTHONPATH", "")) if part
    )
    child_env["PYTHONPATH"] = pythonpath
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=BOUNDARY_SCRIPT_TIMEOUT_SECONDS,
        env=child_env,
        stdin=subprocess.DEVNULL,
    )
    return proc.returncode, proc.stdout, proc.stderr


def validate_output(rc: int, output: str) -> None:
    if rc:
        pytest.fail(f"boundary exited with status {rc}", pytrace=False)
    data = parse_json_object(output)
    if data is None:
        pytest.fail("boundary stdout is not a JSON object", pytrace=False)
    try:
        payload = BoundaryPayload.model_validate(data)
    except ValidationError:
        pytest.fail("boundary payload does not match schema", pytrace=False)
    if not payload.lines or any(not line.title or not line.body.strip() for line in payload.lines):
        pytest.fail("each boundary needs a line with a title and non-empty body", pytrace=False)
    if payload.reason == "not_implemented" and not any(
        "not implemented" in line.body.lower() or "tbd" in line.body.lower() for line in payload.lines
    ):
        pytest.fail("stub boundary must explain that it is not implemented", pytrace=False)


# --- Contract: valid payload in the normal environment -----------------------

def test_payload_valid_normal_env(script):
    rc, out, _ = run_boundary(script, _base_env())
    validate_output(rc, out)


# --- UV hygiene: nested-uv env must not break the boundary -------------------

def test_payload_valid_under_uv_env(script):
    rc, out, _ = run_boundary(script, _uv_env())
    validate_output(rc, out)


# --- Degradation: no credentials -> valid payload with error lines, exit 0 ---

def test_payload_valid_without_credentials(script, tmp_path):
    rc, out, _ = run_boundary(script, _stripped_env(tmp_path))
    validate_output(rc, out)


# --- Static hygiene: timeouts everywhere, no bare ssh ------------------------

def _walk_calls(tree: ast.AST) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _kw(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def test_subprocess_calls_have_timeout(script):
    source = script.read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = []
    for call in _walk_calls(tree):
        if _call_name(call) == "run" and not _kw(call, "timeout"):
            offenders.append(call.lineno)
    assert not offenders, f"subprocess.run without timeout at lines {offenders}"


def test_urlopen_calls_have_timeout(script):
    source = script.read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = []
    for call in _walk_calls(tree):
        if _call_name(call) in {"urlopen", "open"} and not _kw(call, "timeout"):
            # urllib opener.open(...) / urlopen(...) need explicit timeout
            if isinstance(call.func, ast.Attribute) and call.func.attr == "open":
                offenders.append(call.lineno)
            elif _call_name(call) == "urlopen":
                offenders.append(call.lineno)
    assert not offenders, f"urlopen/open without timeout at lines {offenders}"


def test_no_bare_ssh_subprocess(script):
    """ssh children must fail fast, never prompt for a password in cron."""
    source = script.read_text(encoding="utf-8")
    if '"ssh"' not in source and "'ssh'" not in source:
        return
    tree = ast.parse(source)
    for call in _walk_calls(tree):
        if _call_name(call) != "run":
            continue
        for arg in call.args:
            if isinstance(arg, ast.List):
                first = arg.elts[0] if arg.elts else None
                if isinstance(first, ast.Constant) and first.value == "ssh":
                    if "BatchMode" not in ast.unparse(call):
                        pytest.fail(f"SSH without BatchMode at line {call.lineno}", pytrace=False)
