"""Send rendered Daily Compass area messages to Telegram via the Hermes CLI.

Delivery never goes silent: every area message is sent (oversized bodies are
clamped, not dropped), one failed send never blocks the rest, and any problem
is reported in the final status message.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

MAX_SAFE_MESSAGE_UNITS = 3500
TRUNCATION_MARKER = "\n\n… (truncated)"
SEND_INTERVAL_SECONDS = 1.1
SEND_TIMEOUT_SECONDS = 120


def hermes_executable() -> str:
    executable = shutil.which("hermes")
    if executable:
        return executable
    fallback = Path.home() / ".local" / "bin" / "hermes"
    if fallback.is_file():
        return str(fallback)
    raise RuntimeError("Hermes CLI was not found on PATH or in ~/.local/bin")


def utf16_units(text: str) -> int:
    """Telegram counts message length in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def _safe_prefix(body: str, max_units: int) -> str:
    """Largest body prefix whose UTF-16 length fits max_units."""
    if max_units <= 0:
        return ""
    lo, hi = 0, len(body)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if utf16_units(body[:mid]) <= max_units:
            lo = mid
        else:
            hi = mid - 1
    return body[:lo]


def clamp_message_body(body: str) -> str:
    """Clamp a body to Telegram's safe size; oversized bodies are truncated, never dropped."""
    if utf16_units(body) <= MAX_SAFE_MESSAGE_UNITS:
        return body
    clipped = _safe_prefix(body, MAX_SAFE_MESSAGE_UNITS - utf16_units(TRUNCATION_MARKER)).rstrip()
    return clipped + TRUNCATION_MARKER


def send_telegram_text(executable: str, body: str, purpose: str) -> None:
    result = subprocess.run(
        [executable, "send", "--to", "telegram", "--quiet", body],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=SEND_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise RuntimeError(f"Telegram send failed for {purpose}: {detail}")


def deliver_area_messages(messages: list[tuple[str, str]]) -> None:
    """Send one message per area, then a status listing delivered areas and errors."""
    if not messages:
        raise ValueError("Daily Compass rendered no area messages")
    executable = hermes_executable()
    delivered: list[str] = []
    errors: list[str] = []
    for name, body in messages:
        clamped = clamp_message_body(body)
        if clamped != body:
            errors.append(f"{name}: clamped to Telegram safe size")
        try:
            send_telegram_text(executable, clamped, f"area '{name}'")
            delivered.append(name)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{name}: {exc}")
        time.sleep(SEND_INTERVAL_SECONDS)
    listing = ", ".join(delivered) or "none"
    status = f"Daily Compass sent {len(delivered)}/{len(messages)} area messages: {listing}"
    if errors:
        status += " | errors: " + "; ".join(errors)
    send_telegram_text(executable, clamp_message_body(status), "delivery status")
