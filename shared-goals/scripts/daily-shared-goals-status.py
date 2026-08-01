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

from daily_compass_shared import (
    load_env_file,
    make_boundary_payload,
)
from shared_goals_platform import (
    build_platform_lines,
    commit_source_ref,
    create_commit,
    fetch_active_contracts,
    fetch_platform_shared_goals,
    parse_completed_goals_from_compass_text,
    update_compass_markdown,
)
from shared_goals_platform import (
    render_shared_goals_section as _render_shared_goals_section,
)


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


def maybe_sync_completed_tasks(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    goals = parse_completed_goals_from_compass_text(text)
    if not goals:
        return 0
    if not sys.stdin.isatty():
        print("Completed Shared Goals tasks detected, but prompts require an interactive terminal.")
        return 0

    contracts = fetch_active_contracts()
    created = 0
    for goal in goals:
        goal_id = str(goal["goal_id"])
        contract = contracts.get(goal_id)
        if not contract:
            print(f"Skipping {goal['goal_title']}: no active contract found for {goal['goal_tag']}")
            continue

        print()
        print(f"Completed tasks for {goal['goal_title']} {goal['goal_tag']}:")
        for item in goal["completed"]:
            print(f"- {item}")

        if not _prompt_yes_no("Create commit for this goal?", default=True):
            continue

        minutes = _prompt_optional_minutes(goal["goal_title"])
        happy_moment = _prompt_happy_moment(goal["goal_title"])
        done = "\n".join(goal["completed"]).strip()
        next_step = "\n".join(goal["incomplete"]).strip() or None
        done, next_step = _prompt_commit_field_preview(goal["goal_title"], done=done, next_step=next_step)
        create_commit(
            str(contract.get("contract_id", "")).strip(),
            done=done,
            next_step=next_step,
            time_minutes=minutes,
            happy_moment=happy_moment,
            source_ref=commit_source_ref(goal_id, goal["completed"], goal["incomplete"]),
        )
        created += 1
    return created


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
