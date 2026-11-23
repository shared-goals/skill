#!/usr/bin/env python3
"""Shared Shared-Goals platform helpers for status/update scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from daily_compass_shared import (
    COMPASS_CONTEXT_STATE_FILE,
    hunger_days,
    load_env_file,
    load_json_snapshot,
    make_line_context,
    render_next_steps_from_compass_snapshot,
    split_steps,
)
from daily_compass_shared import (
    render_shared_goals_section as shared_render_shared_goals_section,
)

DEFAULT_DIMENSIONS = ["faith", "will", "feeling", "mind"]
DIMENSION_HASHTAGS = {
    "faith": "#faith",
    "mind": "#mind",
    "will": "#will",
    "feeling": "#feel",
}


def _goal_dim_tags(goal: dict[str, Any], fallback_dimension: str) -> list[str]:
    raw = goal.get("dimensions")
    if not isinstance(raw, list):
        raw = goal.get("related_dimensions")
    if not isinstance(raw, list):
        raw = [fallback_dimension]

    tags: list[str] = []
    seen: set[str] = set()
    for item in raw:
        dim = str(item).strip().lower()
        tag = DIMENSION_HASHTAGS.get(dim)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    if not tags:
        fb = DIMENSION_HASHTAGS.get(str(fallback_dimension).strip().lower())
        if fb:
            tags.append(fb)
    return tags


def fetch_platform_shared_goals() -> dict[str, Any] | None:
    """Return the Compass payload, or None when the platform is unconfigured or unreachable."""
    load_env_file()
    base_url = os.environ.get("SHARED_GOALS_API_BASE_URL", "").strip()
    agent_key_id = os.environ.get("SHARED_GOALS_AGENT_KEY_ID", "").strip()
    if not base_url or not agent_key_id:
        return None

    url = urljoin(base_url.rstrip("/") + "/", "api/v1/compass/shared-goals")
    request = Request(url, headers={"X-Agent-Key-Id": agent_key_id})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError):
        return None

    if not isinstance(payload, dict) or not isinstance(payload.get("dimensions"), list):
        return None
    return payload


def fetch_active_contracts() -> dict[str, dict[str, Any]]:
    load_env_file()
    base_url = os.environ.get("SHARED_GOALS_API_BASE_URL", "").strip()
    agent_key_id = os.environ.get("SHARED_GOALS_AGENT_KEY_ID", "").strip()
    if not base_url or not agent_key_id:
        return {}

    url = urljoin(base_url.rstrip("/") + "/", "api/v1/contracts")
    request = Request(url, headers={"X-Agent-Key-Id": agent_key_id})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError):
        return {}

    contracts = payload.get("contracts") if isinstance(payload, dict) else None
    if not isinstance(contracts, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in contracts:
        if not isinstance(item, dict):
            continue
        goal_id = str(item.get("goal_id", "")).strip()
        if goal_id:
            out[goal_id] = item
    return out


def create_commit(
    contract_id: str,
    *,
    done: str,
    next_step: str | None,
    time_minutes: int | None,
    happy_moment: str | None,
    source_ref: str,
) -> dict[str, Any]:
    load_env_file()
    base_url = os.environ.get("SHARED_GOALS_API_BASE_URL", "").strip()
    agent_key_id = os.environ.get("SHARED_GOALS_AGENT_KEY_ID", "").strip()
    if not base_url or not agent_key_id:
        raise RuntimeError("Shared Goals API env vars are missing.")

    url = urljoin(base_url.rstrip("/") + "/", f"api/v1/contracts/{contract_id}/commits")
    body = json.dumps(
        {
            "time_minutes": time_minutes,
            "done": done,
            "next_step": next_step,
            "happy_moment": happy_moment,
            "is_public": False,
            "source_ref": source_ref,
            "user_approved": True,
        }
    ).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "X-Agent-Key-Id": agent_key_id,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Commit API failed: {exc.code} {detail}") from exc
    except (OSError, URLError, ValueError) as exc:
        raise RuntimeError(f"Commit API failed: {exc}") from exc


def _extract_markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    tail = text[match.end() :]
    next_heading = re.search(r"^##\s+", tail, re.MULTILINE)
    return tail[: next_heading.start()] if next_heading else tail


def _strip_goal_tag_suffix(task: str, goal_tag: str) -> str:
    text = str(task or "").strip()
    suffix = f" {goal_tag}"
    if goal_tag and text.endswith(suffix):
        return text[: -len(suffix)].rstrip()
    return text


def parse_completed_goals_from_compass_text(text: str) -> list[dict[str, Any]]:
    section = _extract_markdown_section(text, "Shared Goals")
    if not section:
        return []

    goal_pattern = re.compile(r"^-\s+(?P<title>.+?)\s+(?P<tag>#[A-Za-z0-9_.-]+)\s+hunger:(?P<hunger>\S+)\s*$")
    # The checkbox is optional: a plain dash line under a goal is an incomplete
    # task too (the checkbox only marks completion). `^\s*` (not `\s+`) so a
    # non-indented dash line matches as well.
    task_pattern = re.compile(r"^\s*-\s+(?:\[(?P<mark>[ xX])\]\s+)?(?P<task>.+?)\s*$")

    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in section.splitlines():
        line = raw.rstrip()
        if line.startswith("#"):
            # Any heading (dimension headings inside the section) ends the
            # current goal block: stray dash lines after it (e.g. the rendered
            # "- No goals in this dimension.") must not attach to the goal above.
            if current and (current["completed"] or current["incomplete"]):
                out.append(current)
            current = None
            continue
        goal_match = goal_pattern.match(line)
        if goal_match:
            # Keep any goal that owns at least one task line, including
            # planning-only goals (no completed items).
            if current and (current["completed"] or current["incomplete"]):
                out.append(current)
            goal_tag = goal_match.group("tag")
            current = {
                "goal_tag": goal_tag,
                "goal_id": goal_tag.removeprefix("#"),
                # Goal headlines are rendered bold (`- **Title #tag hunger:2d**`);
                # strip the markdown asterisks so prompts show a clean title.
                "goal_title": goal_match.group("title").strip().strip("*").strip(),
                "completed": [],
                "incomplete": [],
            }
            continue

        task_match = task_pattern.match(line)
        if task_match and current is not None:
            task = _strip_goal_tag_suffix(task_match.group("task"), current["goal_tag"])
            if not task:
                continue
            if (task_match.group("mark") or "").lower() == "x":
                current["completed"].append(task)
            else:
                current["incomplete"].append(task)

    if current and (current["completed"] or current["incomplete"]):
        out.append(current)
    return out


def detect_user_added_steps(goals: list[dict[str, Any]], payload: dict[str, Any]) -> dict[str, list[str]]:
    """Map goal_id -> task lines in the file that are not platform next steps.

    Both sides are normalized the same way (strip + goal-tag-suffix strip), so
    an appended `#sg-...` tag or line order does not create false positives.
    """
    platform_steps: dict[str, set[str]] = {}
    dims = payload.get("dimensions") if isinstance(payload, dict) else None
    if isinstance(dims, list):
        for block in dims:
            if not isinstance(block, dict):
                continue
            block_goals = block.get("goals")
            if not isinstance(block_goals, list):
                continue
            for goal in block_goals:
                if not isinstance(goal, dict):
                    continue
                goal_tag = str(goal.get("goal_tag", "")).strip()
                if not goal_tag:
                    gid = str(goal.get("goal_id", "")).strip().removeprefix("#")
                    if gid:
                        goal_tag = f"#{gid}"
                goal_id = goal_tag.removeprefix("#")
                if not goal_id:
                    continue
                steps = platform_steps.setdefault(goal_id, set())
                for step in split_steps(str(goal.get("next_step_text", ""))):
                    steps.add(_strip_goal_tag_suffix(step, goal_tag))

    out: dict[str, list[str]] = {}
    for goal in goals:
        if not isinstance(goal, dict):
            continue
        goal_id = str(goal.get("goal_id", "")).strip()
        if not goal_id:
            continue
        goal_tag = str(goal.get("goal_tag", "")).strip()
        known = platform_steps.get(goal_id, set())
        lines: list[str] = []
        for item in list(goal.get("completed", [])) + list(goal.get("incomplete", [])):
            text = _strip_goal_tag_suffix(str(item), goal_tag)
            if not text:
                continue
            # A goal absent from the payload cannot be classified against
            # platform steps, so it yields no user-added lines.
            if goal_id not in platform_steps or text in known or text in lines:
                continue
            lines.append(text)
        if lines:
            out[goal_id] = lines
    return out


def move_lines_to_quick_tasks(text: str, lines: list[str]) -> str:
    """Append `lines` as `- [ ] ` items under `## Quick Tasks` (created if absent).

    Returns `text` unchanged when `lines` is empty.
    """
    if not lines:
        return text

    headings = _iter_heading_positions(text)
    quick_index = next((i for i, (_, title) in enumerate(headings) if title == QUICK_TASKS_HEADING), None)
    if quick_index is not None:
        start, _ = headings[quick_index]
        end = headings[quick_index + 1][0] if quick_index + 1 < len(headings) else len(text)
        section = text[start:end]
        additions = "\n".join(f"- [ ] {str(line).strip()}" for line in lines if str(line).strip())
        stripped = section.rstrip("\n")
        if stripped.strip():
            rebuilt = f"{stripped}\n{additions}\n"
        else:
            rebuilt = f"{stripped}\n\n{additions}\n"
        if text[end:].startswith("##"):
            rebuilt += "\n"
        return text[:start] + rebuilt + text[end:]

    additions = "\n".join(f"- [ ] {str(line).strip()}" for line in lines if str(line).strip())
    block = f"\n## {QUICK_TASKS_HEADING}\n\n{additions}\n"
    return (text.rstrip("\n") + "\n" if text.strip() else "") + block


def commit_source_ref(goal_id: str, completed: list[str], incomplete: list[str]) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"goal_id": goal_id, "completed": completed, "incomplete": incomplete},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"compass-update:{goal_id}:{digest}"


def build_platform_lines(payload: dict[str, Any], *, append_goal_tag: bool = False) -> list[dict[str, str]]:
    dims = payload.get("dimensions") if isinstance(payload, dict) else None
    if not isinstance(dims, list):
        return []

    by_name: dict[str, dict[str, Any]] = {}
    for block in dims:
        if not isinstance(block, dict):
            continue
        name = str(block.get("dimension", "")).strip().lower()
        if name:
            by_name[name] = block

    order_raw = payload.get("dimension_order") if isinstance(payload, dict) else None
    order: list[str] = []
    if isinstance(order_raw, list):
        for item in order_raw:
            name = str(item).strip().lower()
            if name and name not in order:
                order.append(name)
    for item in DEFAULT_DIMENSIONS:
        if item in by_name and item not in order:
            order.append(item)
    for item in by_name:
        if item not in order:
            order.append(item)

    out: list[dict[str, str]] = []
    for dim in order:
        block = by_name.get(dim)
        if not isinstance(block, dict):
            continue
        goals = block.get("goals")
        if not isinstance(goals, list):
            continue
        hunger = hunger_days(block.get("last_fed_at"))

        for goal in goals:
            if not isinstance(goal, dict):
                continue
            goal_title = str(goal.get("goal_title", "")).strip()
            goal_tag = str(goal.get("goal_tag", "")).strip()
            if not goal_tag:
                gid = str(goal.get("goal_id", "")).strip().removeprefix("#")
                if gid:
                    goal_tag = f"#{gid}"
            dim_tags = " ".join(_goal_dim_tags(goal, dim))
            title = " ".join(part for part in [goal_title, goal_tag, dim_tags, f"hunger:{hunger}d"] if part).strip()
            if not title:
                continue

            steps = []
            for step in split_steps(str(goal.get("next_step_text", ""))):
                if append_goal_tag and goal_tag and goal_tag not in step:
                    step = f"{step} {goal_tag}".strip()
                steps.append(step)
            body = "\n".join(steps)
            out.append(make_line_context(title=title, body=body, signal=""))
    return out


def render_shared_goals_section(payload: dict[str, Any]) -> str:
    return shared_render_shared_goals_section(payload, DEFAULT_DIMENSIONS)


def _read_next_steps(path: Path) -> str:
    snapshot = load_json_snapshot(COMPASS_CONTEXT_STATE_FILE)
    if snapshot:
        next_steps = render_next_steps_from_compass_snapshot(snapshot)
        if next_steps.strip() and "No next steps yet." not in next_steps:
            return next_steps.split("\n\n", 1)[1].strip() if "\n\n" in next_steps else next_steps.strip()

    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    out: list[str] = []
    in_section = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            heading = s[3:].strip().lower()
            if in_section:
                break
            in_section = heading == "logos"
            continue
        if in_section:
            out.append(line.rstrip())
    return "\n".join(out).strip()


GENERATED_COMPASS_HEADINGS = ("Logos", "Shared Goals")
QUICK_TASKS_HEADING = "Quick Tasks"

_HEADING_RE = re.compile(r"^##\s+.*$", re.MULTILINE)


def _iter_heading_positions(text: str) -> list[tuple[int, str]]:
    """Return (offset, title) for every level-2 heading, in document order."""
    out: list[tuple[int, str]] = []
    for match in _HEADING_RE.finditer(text):
        title = text[match.start() : match.end()][2:].strip()
        out.append((match.start(), title))
    return out


def _render_generated_sections(payload: dict[str, Any], next_steps: str) -> dict[str, str]:
    return {
        "Logos": f"## Logos\n\n{next_steps}\n",
        "Shared Goals": f"{render_shared_goals_section(payload).strip()}\n",
    }


def _block_text(text: str, start: int, end: int | None) -> str:
    block = text[start:] if end is None else text[start:end]
    if not block.endswith("\n"):
        block += "\n"
    return block


def update_compass_markdown(payload: dict[str, Any], path: Path, *, logos_text: str | None = None) -> None:
    """Write generated Compass sections while preserving user-owned content.

    Generated headings are exactly `## Logos` and `## Shared Goals`. Everything
    else (preamble before the first heading, other `## ` sections with their
    bodies) is kept verbatim, in place. A generated heading that is missing from
    the file is inserted with the generated block at the top of the note —
    after any in-place generated sections, before the first user section —
    never below user content.
    A file that does not exist yet is bootstrapped with an extra, empty
    `## Quick Tasks` section after the generated ones.
    """
    existing = ""
    existed = False
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8", errors="replace")
            existed = True
        except OSError:
            existing = ""

    next_steps = str(logos_text or "").strip() or _read_next_steps(path)
    if not next_steps:
        next_steps = "- [ ] No next steps yet."
    generated = _render_generated_sections(payload, next_steps)

    if not existed:
        markdown = generated["Logos"] + "\n" + generated["Shared Goals"] + "\n## Quick Tasks\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return

    headings = _iter_heading_positions(existing)
    first_heading = headings[0][0] if headings else len(existing)
    preamble = existing[:first_heading]

    pieces: list[str] = []
    remaining = dict(generated)
    for index, (start, title) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(existing)
        if title in remaining:
            # The generated block replaces the existing one, in place. A
            # heading that merely resembles a generated one (e.g. `## Logos
            # Archive`) falls through to the user branch below.
            pieces.append(remaining.pop(title))
            if index + 1 < len(headings):
                pieces.append("\n")
            continue
        pieces.append(_block_text(existing, start, end))

    if remaining:
        # Not every generated heading was present in the file: insert the
        # missing ones (in canonical order) right after the preamble, before
        # the first user section.
        block = "".join(generated[name] + "\n" for name in ("Logos", "Shared Goals") if name in remaining)
        insert_at = next(
            (i for i, (_, title) in enumerate(headings) if title not in generated),
            len(headings),
        )
        pieces.insert(min(insert_at, len(pieces)), block.rstrip("\n") + "\n")

    if preamble and not preamble.endswith("\n"):
        preamble += "\n"
    markdown = preamble + "".join(pieces)
    if not markdown.endswith("\n"):
        markdown += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
