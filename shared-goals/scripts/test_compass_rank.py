#!/usr/bin/env python3
"""Hunger ranking (T-RANK-1..4)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from compass.rank import dimension_order, hungriest_line

FALLBACK = ["faith", "will", "feeling", "mind"]


def test_platform_order_wins() -> None:
    payload = {"dimension_order": ["feeling", "faith", "will", "mind"]}
    assert dimension_order(payload, FALLBACK) == (["feeling", "faith", "will", "mind"], True)


def test_partial_platform_order_is_completed_from_fallback() -> None:
    payload = {"dimension_order": ["Mind", "luck", "mind"]}
    assert dimension_order(payload, ["will", "faith"]) == (["mind", "will", "faith", "feeling"], True)


@pytest.mark.parametrize("payload", [None, {}, {"dimension_order": []}, {"dimension_order": ["luck"]}, []])
def test_missing_platform_order_uses_fallback_and_is_flagged(payload) -> None:
    assert dimension_order(payload, ["mind", "bogus", "faith"]) == (["mind", "faith", "will", "feeling"], False)


def test_hungriest_line_is_first_platform_line() -> None:
    lines = [{"title": "Never fed hunger:neverd"}, {"title": "Fed long ago hunger:40d"}]
    assert hungriest_line(lines) == lines[0]


def test_hungriest_line_skips_junk_and_handles_empty() -> None:
    assert hungriest_line(["junk", {"title": "A"}]) == {"title": "A"}
    assert hungriest_line([]) is None
