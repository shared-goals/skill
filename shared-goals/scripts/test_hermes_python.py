"""Tests for the shared hermes-python resolver in daily_compass_shared.

hermes-agent is a uv project (no venv/); scripts needing hermes_cli /
hermes_state must resolve the interpreter through uv. This is the single
owner of that resolution (DRY) — see the pitfall in sg-area-craft SKILL.md.
"""
from __future__ import annotations

import json
import sys

import pytest

from daily_compass_shared import get_hermes_python, run_hermes_python


@pytest.fixture
def install(tmp_path, monkeypatch):
    project = tmp_path / ".hermes/hermes-agent"
    project.mkdir(parents=True)
    (project / "pyproject.toml").touch()
    uv = tmp_path / "uv"
    uv.write_text(f'#!/bin/sh\ncd "$2" || exit 1\nshift 4\nexec "{sys.executable}" "$@"\n')
    uv.chmod(0o700)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))
    return project


def test_get_hermes_python_resolves_uv_run(install):
    cmd = get_hermes_python()
    assert cmd is not None
    assert "uv" in cmd and "--directory" in cmd and "run python" in cmd


def test_run_hermes_python_can_import_hermes_state(install):
    (install / "hermes_state.py").touch()
    result = run_hermes_python("import hermes_state; print('ok')")
    assert result is not None, "hermes python must be available"
    rc, out, err = result
    assert rc == 0, f"exit={rc} stderr={err[-300:]}"
    assert "ok" in out


def test_run_hermes_python_returns_none_without_hermes_agent(monkeypatch, tmp_path):
    import daily_compass_shared as shared

    monkeypatch.setattr(shared.Path, "home", lambda: tmp_path)
    assert shared.get_hermes_python() is None
    assert shared.run_hermes_python("print('x')") is None


def test_run_hermes_python_roundtrip_json(install):
    result = run_hermes_python("import json; print(json.dumps({'a': 1}))")
    assert result is not None
    rc, out, _ = result
    assert rc == 0
    assert json.loads(out) == {"a": 1}
