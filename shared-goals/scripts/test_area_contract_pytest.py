#!/usr/bin/env python3
"""Pytest integration check for Shared Goals area contract.

This test runs area-test.py as a subprocess and captures output so successful
runs stay quiet in pytest output.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent
AREA_TEST = SCRIPTS_DIR / "area-test.py"


def _tail(text: str, lines: int = 80) -> str:
    items = (text or "").splitlines()
    if len(items) <= lines:
        return "\n".join(items)
    return "\n".join(items[-lines:])


def test_shared_goals_area_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(AREA_TEST), "shared-goals"],
        cwd=str(SCRIPTS_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "area-test shared-goals failed\n"
        f"exit={result.returncode}\n"
        "--- stdout tail ---\n"
        f"{_tail(result.stdout)}\n"
        "--- stderr tail ---\n"
        f"{_tail(result.stderr)}"
    )
