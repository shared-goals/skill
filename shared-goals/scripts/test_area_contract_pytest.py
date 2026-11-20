#!/usr/bin/env python3
"""Pytest integration check for Shared Goals area contract.

This test runs area-test.py as a subprocess and captures output so successful
runs stay quiet in pytest output.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent
AREA_TEST = SCRIPTS_DIR / "area-test.py"


@pytest.mark.live
def test_shared_goals_area_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(AREA_TEST), "shared-goals"],
        cwd=str(SCRIPTS_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        pytest.fail(f"area contract failed (exit {result.returncode})", pytrace=False)
