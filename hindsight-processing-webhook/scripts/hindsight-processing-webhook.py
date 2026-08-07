#!/usr/bin/env python3
"""Deterministic completion hook for Hindsight retain/consolidation events.

Behavior:
- accepts global Hindsight webhook events
- exits silently unless shared status is processing
- while any retain/consolidation is pending/processing, exits silently
- when queue is quiet, switches state to completed and prints one completion message
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared-goals" / "scripts"
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))

from wtd_processing_state import load_state, save_state, utc_now_iso

STATE_PATH = Path(__file__).resolve().parents[2] / "shared-goals" / "runtime" / "wtd-processing-state.json"
WATCHED_EVENTS = {"retain.completed", "consolidation.completed"}


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else ""


def ensure_no_proxy() -> None:
    os.environ.setdefault("NO_PROXY", "*")
    os.environ.setdefault("no_proxy", "*")


def request_json(api_url: str, method: str, path: str, *, timeout: int = 120) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}",
        method=method,
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {detail}") from exc
    return json.loads(body) if body else {}


def count_operations(api_url: str, bank: str, status: str, op_type: str) -> int:
    query = urllib.parse.urlencode({"status": status, "type": op_type, "limit": 100})
    data = request_json(api_url, "GET", f"/v1/default/banks/{bank}/operations?{query}", timeout=120)
    items = data.get("items") if isinstance(data, dict) else None
    return len(items) if isinstance(items, list) else 0


def pending_or_processing_counts(api_url: str, bank: str) -> dict[str, int]:
    ensure_no_proxy()
    counts = {
        "retain_pending": count_operations(api_url, bank, "pending", "retain"),
        "retain_processing": count_operations(api_url, bank, "processing", "retain"),
        "consolidation_pending": count_operations(api_url, bank, "pending", "consolidation"),
        "consolidation_processing": count_operations(api_url, bank, "processing", "consolidation"),
    }
    counts["total"] = sum(counts.values())
    return counts


def run_for_event(
    payload: dict[str, Any],
    *,
    state_path: Path = STATE_PATH,
    counts_fn: Callable[[str, str], dict[str, int]] = pending_or_processing_counts,
) -> str | None:
    event = _safe_str(payload.get("event"))
    if event not in WATCHED_EVENTS:
        return None

    state = load_state(state_path)
    if _safe_str(state.get("status")) != "processing":
        return None

    api_url = os.environ.get("HINDSIGHT_API_URL", "http://rock.lan:8889")
    bank = os.environ.get("HINDSIGHT_BANK", "hermes")
    counts = counts_fn(api_url, bank)

    if counts.get("total", 0) > 0:
        return None

    state["status"] = "completed"
    state["completed_at"] = utc_now_iso()
    state["completion_event"] = event
    state["completion_operation_id"] = _safe_str(payload.get("operation_id"))
    state["queue_counts_at_completion"] = counts
    save_state(state_path, state)

    return (
        "WTD processing completed. Status: completed. "
        f"Event: {event}. Operation: {state['completion_operation_id'] or 'n/a'}."
    )


def main() -> None:
    try:
        raw = sys.stdin.read()
    except OSError:
        print("[SILENT]")
        return

    if not raw.strip():
        print("[SILENT]")
        return

    try:
        payload = json.loads(raw)
    except ValueError:
        print("[SILENT]")
        return

    if not isinstance(payload, dict):
        print("[SILENT]")
        return

    try:
        message = run_for_event(payload)
    except Exception as exc:
        print(f"Hindsight processing webhook error: {exc}")
        return

    print(message if message else "[SILENT]")


if __name__ == "__main__":
    main()
