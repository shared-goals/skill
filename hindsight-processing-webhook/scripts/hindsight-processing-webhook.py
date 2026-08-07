#!/usr/bin/env python3
"""Deterministic completion hook for Hindsight retain/consolidation events.

Behavior:
- accepts global Hindsight webhook events
- exits silently unless shared status is processing
- while any non-delivery operation is pending/processing/running, exits silently
- when the operation queue is truly quiet, switches state to completed and prints one completion message
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared-goals" / "scripts"
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))

from wtd_processing_state import load_state, save_state, utc_now_iso

STATE_PATH = Path(__file__).resolve().parents[2] / "shared-goals" / "runtime" / "wtd-processing-state.json"
LOG_PATH = Path.home() / ".hermes" / "logs" / "hindsight-processing-webhook.log"
ACTIVE_STATUSES = ("pending", "processing", "running")
IGNORED_ACTIVE_TYPES = tuple(
    t.strip()
    for t in os.environ.get("WTD_COMPLETION_IGNORE_TYPES", "webhook_delivery").split(",")
    if t.strip()
)
MAX_OPERATIONS_LIMIT = 100


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _local_ts() -> str:
    # Match Hermes log wall-clock style: YYYY-MM-DD HH:MM:SS,mmm
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]


def ensure_no_proxy() -> None:
    os.environ.setdefault("NO_PROXY", "*")
    os.environ.setdefault("no_proxy", "*")


def _log_decision(
    decision: str,
    *,
    event: str,
    operation_id: str,
    state_status: str,
    counts: dict[str, int] | None = None,
    note: str = "",
) -> None:
    parts = [
        f"decision={decision}",
        f"event={event or 'n/a'}",
        f"operation_id={operation_id or 'n/a'}",
        f"state_status={state_status or 'n/a'}",
    ]
    if counts is not None:
        parts.append("counts=" + ",".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if note:
        parts.append(f"note={note}")
    line = f"{_local_ts()} INFO hindsight_processing_webhook: " + " ".join(parts)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


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


def list_operations(api_url: str, bank: str, status: str, limit: int = MAX_OPERATIONS_LIMIT) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, MAX_OPERATIONS_LIMIT))
    query = urllib.parse.urlencode({"status": status, "limit": safe_limit})
    data = request_json(api_url, "GET", f"/v1/default/banks/{bank}/operations?{query}", timeout=120)
    items = data.get("items") if isinstance(data, dict) else None
    return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []


def pending_or_processing_counts(api_url: str, bank: str) -> dict[str, int]:
    ensure_no_proxy()
    counts: dict[str, int] = {}
    by_type: dict[str, int] = {}
    total = 0
    for status in ACTIVE_STATUSES:
        items = list_operations(api_url, bank, status)
        active_items = []
        for item in items:
            op_type = _safe_str(item.get("type"))
            if op_type in IGNORED_ACTIVE_TYPES:
                continue
            active_items.append(item)
            by_type[op_type or "unknown"] = by_type.get(op_type or "unknown", 0) + 1
        counts[f"active_{status}"] = len(active_items)
        total += len(active_items)
    counts["total"] = total
    for op_type, count in sorted(by_type.items()):
        counts[f"type_{op_type}"] = count
    return counts


def run_for_event(
    payload: dict[str, Any],
    *,
    state_path: Path = STATE_PATH,
    counts_fn: Callable[[str, str], dict[str, int]] = pending_or_processing_counts,
) -> str | None:
    event = _safe_str(payload.get("event"))
    operation_id = _safe_str(payload.get("operation_id"))

    state = load_state(state_path)
    state_status = _safe_str(state.get("status"))
    if state_status != "processing":
        _log_decision(
            "ignore_not_processing",
            event=event,
            operation_id=operation_id,
            state_status=state_status,
        )
        return None

    api_url = os.environ.get("HINDSIGHT_API_URL", "http://rock.lan:8889")
    bank = os.environ.get("HINDSIGHT_BANK", "hermes")
    counts = counts_fn(api_url, bank)

    if counts.get("total", 0) > 0:
        _log_decision(
            "ignore_queue_busy",
            event=event,
            operation_id=operation_id,
            state_status=state_status,
            counts=counts,
        )
        return None

    # Only complete on terminal webhook events.
    if not event.endswith(".completed"):
        _log_decision(
            "ignore_not_completed_event",
            event=event,
            operation_id=operation_id,
            state_status=state_status,
            counts=counts,
        )
        return None

    state["status"] = "completed"
    state["completed_at"] = utc_now_iso()
    state["completion_event"] = event
    state["completion_operation_id"] = operation_id
    state["queue_counts_at_completion"] = counts
    save_state(state_path, state)
    _log_decision(
        "complete",
        event=event,
        operation_id=operation_id,
        state_status="completed",
        counts=counts,
    )

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
