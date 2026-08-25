#!/usr/bin/env python3
"""Shared state helpers for deterministic Hindsight ingest completion."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STATE = {
    "status": "completed",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_STATE)
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return dict(DEFAULT_STATE)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(DEFAULT_STATE)
    if not isinstance(data, dict):
        return dict(DEFAULT_STATE)
    if "status" not in data:
        data["status"] = DEFAULT_STATE["status"]
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    state = dict(state)
    state["updated_at"] = utc_now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
