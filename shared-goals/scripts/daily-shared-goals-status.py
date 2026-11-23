#!/usr/bin/env python3
"""Shared Goals platform boundary/status script.

Default mode prints boundary JSON for the `shared-goals` area.
Optional mode updates Compass.md using platform-generated Shared Goals section.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from daily_compass_shared import (
    load_env_file,
    make_boundary_payload,
)
# NOTE: the four names below (`commit_source_ref`, `create_commit`,
# `fetch_active_contracts`, `parse_completed_goals_from_compass_text`) are not
# called in this module: the sync core resolves them in
# shared_goals_platform's namespace. They stay re-exported here so callers and
# tests that steered them through this script keep working.
from shared_goals_platform import (  # noqa: F401
    build_platform_lines,
    commit_source_ref,
    create_commit,
    fetch_active_contracts,
    fetch_platform_shared_goals,
    parse_completed_goals_from_compass_text,
    sync_compass_tasks,
    update_compass_markdown,
)
from shared_goals_platform import (
    render_shared_goals_section as _render_shared_goals_section,
)

# Rich is optional on this host; the flags mirror compass-update.py's probe, so a
# caller can tell which prompting branch the interpreter really supports.
try:
    from rich.console import Console
    from rich.prompt import Confirm, IntPrompt, Prompt
    from rich.table import Table
except Exception:  # pragma: no cover - graceful fallback when rich is absent.
    Console = None
    Confirm = None
    IntPrompt = None
    Prompt = None
    Table = None


class PlainUI:
    """UI adapter for the sync core: plain input/print, no Rich dependency.

    Prompts delegate to the module-level `_prompt_*` helpers, so a caller that
    used to steer those still reaches the same code path.
    """

    def yes_no(self, prompt: str, default: bool = True) -> bool:
        return _prompt_yes_no(prompt, default)

    def optional_minutes(self, goal_title: str) -> int | None:
        return _prompt_optional_minutes(goal_title)

    def happy_moment(self, goal_title: str) -> str | None:
        return _prompt_happy_moment(goal_title)

    def commit_field_preview(self, goal_title: str, *, done: str, next_step: str | None) -> tuple[str, str | None]:
        return _prompt_commit_field_preview(goal_title, done=done, next_step=next_step)

    def note(self, message: str) -> None:
        print(message)

    def show_completed(self, goal_title: str, goal_tag: str, completed: list[str], incomplete: list[str]) -> None:
        print()
        print(f"Completed tasks for {goal_title} {goal_tag}:")
        for item in completed:
            print(f"- {item}")


def _prompt_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix} ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def _prompt_optional_minutes(goal_title: str) -> int | None:
    while True:
        raw = input(f"Minutes for '{goal_title}' (blank to skip): ").strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            print("Please enter a whole number or leave blank.")
            continue
        if value < 0:
            print("Minutes must be non-negative.")
            continue
        return value


def _prompt_happy_moment(goal_title: str) -> str | None:
    raw = input(f"Happy moment for '{goal_title}' (blank if none): ").strip()
    return raw or None


def _prompt_commit_field_preview(goal_title: str, *, done: str, next_step: str | None) -> tuple[str, str | None]:
    print()
    print(f"{'-' * 60}")
    print(f"Commit preview for '{goal_title}':")
    print(f"{'-' * 60}")
    print("done:")
    print((done or "(empty)").strip())
    print()
    print("next step:")
    print((next_step or "(none)").strip())
    print(f"{'-' * 60}")
    print()

    if _prompt_yes_no("Edit done value?", default=False):
        raw = input("New done value: ").strip()
        if raw:
            done = raw
    if _prompt_yes_no("Edit next step value?", default=False):
        raw = input("New next step value: ").strip()
        next_step = raw or None
    return done, next_step


def maybe_sync_completed_tasks(path: Path, *, ui: Any = None, payload: dict[str, Any] | None = None) -> int:
    """Offer commits for goals with completed items (planning-less sync pass).

    `ui` / `payload` are injectable for tests; the CLI path passes neither and
    behaves exactly as before.
    """
    if ui is None:
        ui = PlainUI()
    if payload is None:
        payload = fetch_platform_shared_goals() or {}
    return sync_compass_tasks(path, payload, ui, planning=False)


def _default_compass_path() -> str:
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    if vault_path:
        return str(Path(vault_path).expanduser() / "Compass.md")
    return str(Path.home() / "Compass.md")


def render_shared_goals_section(payload: dict[str, object]) -> str:
    """Compatibility wrapper for callers importing from this script."""
    return _render_shared_goals_section(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shared Goals platform boundary script")
    parser.add_argument(
        "--update-compass",
        action="store_true",
        help="Update Compass.md using fetched Shared Goals payload",
    )
    parser.add_argument(
        "--compass-path",
        default=_default_compass_path(),
        help="Compass markdown path for --update-compass",
    )
    return parser.parse_args()


def main() -> int:
    load_env_file()
    args = parse_args()

    if args.update_compass:
        maybe_sync_completed_tasks(Path(args.compass_path).expanduser())
    payload = fetch_platform_shared_goals()
    if payload is None:
        print(json.dumps(make_boundary_payload(status="error", reason="platform_unavailable", include_ts=True)))
        return 0

    if args.update_compass:
        update_compass_markdown(payload, Path(args.compass_path).expanduser())

    lines = build_platform_lines(payload)
    out = make_boundary_payload(
        status="ok" if lines else "TBD",
        reason="" if lines else "shared_goals_empty",
        lines=lines,
        include_ts=True,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
