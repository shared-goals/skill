#!/usr/bin/env python3
"""Interactive Compass updater with Rich UI.

This script updates Compass.md with platform Shared Goals data and can optionally
create commit records for completed checklist items.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from daily_compass_shared import load_json_snapshot, render_next_steps_from_compass_snapshot
from shared_goals_platform import (
    fetch_platform_shared_goals,
    sync_compass_tasks,
    update_compass_markdown,
)

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


class RichUI:
    """UI adapter for the sync core: Rich rendering when available, plain otherwise.

    Owns the interactive prompting for compass-update: the sync loop itself lives
    in shared_goals_platform.sync_compass_tasks.
    """

    def __init__(self, console: Console | None) -> None:
        self.console = console

    def yes_no(self, prompt: str, default: bool = True) -> bool:
        if Confirm is not None:
            assert self.console is not None
            return Confirm.ask(prompt, default=default, console=self.console)
        suffix = "[Y/n]" if default else "[y/N]"
        raw = input(f"{prompt} {suffix} ").strip().lower()
        if not raw:
            return default
        return raw in {"y", "yes"}

    def optional_minutes(self, goal_title: str, *, default: int | None = None) -> int | None:
        """Ask for minutes. A blank answer means `default` (None => skip).

        Callers pick the blank semantics: the report flow passes None (skip),
        the planning flow passes 1 (a plan is worth one minute).
        """
        hint = "(blank to skip)" if default is None else f"(blank = {default})"
        if IntPrompt is not None:
            assert self.console is not None
            raw = Prompt.ask(f"Minutes for '{goal_title}' {hint}", default="", console=self.console)
            raw = raw.strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                if self.console:
                    self.console.print("[yellow]Please enter a whole number or leave blank.[/yellow]")
                return default
            return max(0, value)

        while True:
            raw = input(f"Minutes for '{goal_title}' {hint}: ").strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                print("Please enter a whole number or leave blank.")
                continue
            if value < 0:
                print("Minutes must be non-negative.")
                continue
            return value

    def happy_moment(self, goal_title: str) -> str | None:
        if Prompt is not None:
            assert self.console is not None
            raw = Prompt.ask(
                f"Happy moment for '{goal_title}' (blank if none)", default="", console=self.console
            ).strip()
            return raw or None
        raw = input(f"Happy moment for '{goal_title}' (blank if none): ").strip()
        return raw or None

    def commit_field_preview(
        self,
        goal_title: str,
        *,
        done: str,
        next_step: str | None,
    ) -> tuple[str, str | None]:
        if self.console and Table is not None:
            table = Table(title=f"Commit Preview: {goal_title}")
            table.add_column("Field", style="cyan", no_wrap=True)
            table.add_column("Value", style="white")
            table.add_row("done", done or "(empty)")
            table.add_row("next_step", next_step or "(none)")
            self.console.print(table)
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

        if self.yes_no("Edit done value?", default=False):
            if Prompt is not None:
                assert self.console is not None
                raw = Prompt.ask("New done value", default=done, console=self.console).strip()
            else:
                raw = input("New done value: ").strip()
            if raw:
                done = raw

        if self.yes_no("Edit next step value?", default=False):
            if Prompt is not None:
                assert self.console is not None
                raw = Prompt.ask("New next step value", default=next_step or "", console=self.console).strip()
            else:
                raw = input("New next step value: ").strip()
            next_step = raw or None

        return done, next_step

    def note(self, message: str) -> None:
        if self.console:
            self.console.print(f"[yellow]{message}[/yellow]")
        else:
            print(message)

    def show_completed(
        self, goal_title: str, goal_tag: str, completed: list[str], incomplete: list[str]
    ) -> None:
        if self.console and Table is not None:
            table = Table(title=f"Completed Tasks: {goal_title} {goal_tag}")
            table.add_column("Done")
            for item in completed:
                table.add_row(item)
            self.console.print(table)
            return
        print()
        print(f"Completed tasks for {goal_title} {goal_tag}:")
        for item in completed:
            print(f"- {item}")


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

    payload = fetch_platform_shared_goals()
    if payload is None:
        print("Shared Goals platform unavailable; Compass.md left unchanged.", file=sys.stderr)
        return 1

    if not args.no_sync_completed:
        created = sync_compass_tasks(path, payload, RichUI(console), planning=True)
        if console:
            console.print(f"[green]Created commits:[/green] {created}")
        else:
            print(f"Created commits: {created}")
        # Commits mutated the platform: re-fetch, or the file below is rendered
        # from a stale payload and freshly committed next steps vanish from it.
        if created:
            payload = fetch_platform_shared_goals() or payload

    update_compass_markdown(payload, path, logos_text=_read_logos_text(args))

    if console:
        console.print(f"[green]Updated[/green] {path}")
    else:
        print(f"Updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
