#!/usr/bin/env python3
"""Interactive Compass updater with Rich UI.

This script updates Compass.md with platform Shared Goals data and can optionally
create commit records for completed checklist items.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from shared_goals_platform import (
    commit_source_ref,
    create_commit,
    fetch_active_contracts,
    fetch_platform_shared_goals,
    parse_completed_goals_from_compass_text,
    update_compass_markdown,
)
from daily_compass_shared import load_json_snapshot, render_next_steps_from_compass_snapshot

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


def _default_compass_path() -> Path:
    obsidian_root = Path.home()
    env_vault = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    if env_vault:
        obsidian_root = Path(env_vault).expanduser()
    return obsidian_root / "Compass.md"


def _resolve_compass_path(path_arg: str) -> Path:
    candidate = Path(path_arg).expanduser()
    if candidate.exists() or candidate.parent.exists():
        return candidate
    return Path.home() / "Compass.md"


def _prompt_yes_no(console: Console | None, prompt: str, default: bool = True) -> bool:
    if Confirm is not None:
        assert console is not None
        return Confirm.ask(prompt, default=default, console=console)
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {suffix} ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def _prompt_optional_minutes(console: Console | None, goal_title: str) -> int | None:
    if IntPrompt is not None:
        assert console is not None
        raw = Prompt.ask(f"Minutes for '{goal_title}' (blank to skip)", default="", console=console)
        raw = raw.strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            if console:
                console.print("[yellow]Please enter a whole number or leave blank.[/yellow]")
            return None
        return max(0, value)

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


def _prompt_happy_moment(console: Console | None, goal_title: str) -> str | None:
    if Prompt is not None:
        assert console is not None
        raw = Prompt.ask(f"Happy moment for '{goal_title}' (blank if none)", default="", console=console).strip()
        return raw or None
    raw = input(f"Happy moment for '{goal_title}' (blank if none): ").strip()
    return raw or None


def _prompt_commit_field_preview(
    console: Console | None,
    goal_title: str,
    *,
    done: str,
    next_step: str | None,
) -> tuple[str, str | None]:
    if console and Table is not None:
        table = Table(title=f"Commit Preview: {goal_title}")
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        table.add_row("done", done or "(empty)")
        table.add_row("next_step", next_step or "(none)")
        console.print(table)
    else:
        print("-" * 60)
        print(f"Commit preview for '{goal_title}':")
        print("-" * 60)
        print("done:")
        print((done or "(empty)").strip())
        print()
        print("next step:")
        print((next_step or "(none)").strip())
        print("-" * 60)

    if _prompt_yes_no(console, "Edit done value?", default=False):
        if Prompt is not None:
            assert console is not None
            raw = Prompt.ask("New done value", default=done, console=console).strip()
        else:
            raw = input("New done value: ").strip()
        if raw:
            done = raw

    if _prompt_yes_no(console, "Edit next step value?", default=False):
        if Prompt is not None:
            assert console is not None
            raw = Prompt.ask("New next step value", default=next_step or "", console=console).strip()
        else:
            raw = input("New next step value: ").strip()
        next_step = raw or None

    return done, next_step


def _sync_completed_tasks(console: Console | None, path: Path) -> int:
    if not path.exists():
        return 0

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    goals = parse_completed_goals_from_compass_text(text)
    if not goals:
        return 0

    contracts = fetch_active_contracts()
    created = 0
    for goal in goals:
        goal_id = str(goal["goal_id"])
        contract = contracts.get(goal_id)
        if not contract:
            message = f"Skipping {goal['goal_title']}: no active contract for {goal['goal_tag']}"
            if console:
                console.print(f"[yellow]{message}[/yellow]")
            else:
                print(message)
            continue

        if console and Table is not None:
            table = Table(title=f"Completed Tasks: {goal['goal_title']} {goal['goal_tag']}")
            table.add_column("Done")
            for item in goal["completed"]:
                table.add_row(item)
            console.print(table)
        else:
            print()
            print(f"Completed tasks for {goal['goal_title']} {goal['goal_tag']}:")
            for item in goal["completed"]:
                print(f"- {item}")

        if not _prompt_yes_no(console, "Create commit for this goal?", default=True):
            continue

        minutes = _prompt_optional_minutes(console, goal["goal_title"])
        happy_moment = _prompt_happy_moment(console, goal["goal_title"])
        done = "\n".join(goal["completed"]).strip()
        next_step = "\n".join(goal["incomplete"]).strip() or None
        done, next_step = _prompt_commit_field_preview(
            console,
            goal["goal_title"],
            done=done,
            next_step=next_step,
        )

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Shared Goals Compass updater")
    parser.add_argument(
        "--compass-path",
        default=str(_default_compass_path()),
        help="Compass markdown path",
    )
    parser.add_argument(
        "--no-sync-completed",
        action="store_true",
        help="Do not prompt for commit creation from completed tasks",
    )
    parser.add_argument(
        "--logos-context",
        default="",
        help="Daily Compass context JSON to render into the Logos section",
    )
    return parser.parse_args()


def _read_logos_text(args: argparse.Namespace) -> str | None:
    if args.logos_context:
        snapshot = load_json_snapshot(Path(args.logos_context).expanduser())
        if snapshot:
            rendered = render_next_steps_from_compass_snapshot(snapshot).strip()
            if rendered.startswith("## Logos"):
                return rendered.split("\n", 2)[2].strip() if "\n" in rendered else ""
            return rendered

    return None


def main() -> int:
    args = parse_args()
    console = Console() if Console is not None else None

    requested_path = Path(args.compass_path).expanduser()
    path = _resolve_compass_path(args.compass_path)
    if requested_path != path and console:
        console.print(f"[yellow]Using fallback path:[/yellow] {path}")

    if not args.no_sync_completed:
        created = _sync_completed_tasks(console, path)
        if console:
            console.print(f"[green]Created commits:[/green] {created}")
        else:
            print(f"Created commits: {created}")

    payload = fetch_platform_shared_goals()
    update_compass_markdown(payload, path, logos_text=_read_logos_text(args))

    if console:
        console.print(f"[green]Updated[/green] {path}")
    else:
        print(f"Updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
