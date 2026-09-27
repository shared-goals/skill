"""Deterministic hunger ranking; the platform's `dimension_order` is the only hunger source."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from compass.models import DIMENSIONS, Dimension


def dimension_order(platform_payload: dict[str, Any] | None, fallback: Sequence[str]) -> tuple[list[Dimension], bool]:
    """Return (order, from_platform). Unknown or repeated names are dropped; missing ones are appended."""
    raw = platform_payload.get("dimension_order") if isinstance(platform_payload, dict) else None
    from_platform = isinstance(raw, list) and any(str(item).strip().lower() in DIMENSIONS for item in raw)
    order: list[Dimension] = []
    for item in [*(raw if from_platform else []), *fallback, *DIMENSIONS]:
        name = str(item).strip().lower()
        if name in DIMENSIONS and name not in order:
            order.append(name)  # type: ignore[arg-type]
    return order, from_platform


def hungriest_line(lines: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """Shared Goals lines arrive in platform hunger order (never-fed first), so the first line wins."""
    return next((line for line in lines if isinstance(line, dict)), None)
