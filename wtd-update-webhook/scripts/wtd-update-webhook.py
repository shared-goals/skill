#!/usr/bin/env python3
"""Deterministic starter hook for WTD update processing.

Behavior:
- validates GitHub push payload for the target repo/branch
- derives changed chapter slugs from text/*.md paths
- starts async reingest via text-forge wrapper
- writes status=processing to shared state
- prints one processing message, or [SILENT]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared-goals" / "scripts"
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))

from wtd_processing_state import load_state, save_state, utc_now_iso

TARGET_REPO = "bongiozzo/whattodo"
TARGET_REF = "refs/heads/master"
STATE_PATH = Path(__file__).resolve().parents[2] / "shared-goals" / "runtime" / "wtd-processing-state.json"

UV_CANDIDATE_PATHS = (
    Path("/opt/homebrew/bin/uv"),
    Path("/usr/local/bin/uv"),
)


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else ""


def collect_changed_paths(commits: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for commit in commits:
        for key in ("added", "modified", "removed"):
            for raw in _safe_list(commit.get(key)):
                path = _safe_str(raw).strip()
                if not path or path in seen:
                    continue
                seen.add(path)
                paths.append(path)
    return sorted(paths)


def chapters_from_paths(paths: list[str]) -> list[str]:
    chapters: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if not path.startswith("text/") or not path.endswith(".md"):
            continue
        slug = Path(path).stem
        if slug in seen:
            continue
        seen.add(slug)
        chapters.append(slug)
    return chapters


def resolve_uv_bin() -> str | None:
    override = os.environ.get("UV_BIN", "").strip()
    if override:
        p = Path(override).expanduser()
        if p.exists() and p.is_file() and os.access(p, os.X_OK):
            return str(p)

    discovered = shutil.which("uv")
    if discovered:
        return discovered

    for candidate in UV_CANDIDATE_PATHS:
        if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    return None


def start_reingest(chapters: list[str], from_commit: str | None = None) -> dict[str, Any]:
    text_forge = Path(os.environ.get("TEXT_FORGE_ROOT", "/Users/shag/Work/text-forge"))
    wtd_root = Path(os.environ.get("WTD_ROOT", "/Users/shag/Work/whattodo"))
    api_url = os.environ.get("HINDSIGHT_API_URL", "http://rock.lan:8889")
    bank = os.environ.get("HINDSIGHT_BANK", "hermes")
    wrapper = text_forge / "scripts" / "hindsight-wtd-ingest-wrapper.py"

    if not wrapper.exists():
        raise RuntimeError(f"missing ingest wrapper: {wrapper}")

    # Gateway environments may not have uv on PATH; prefer uv when available,
    # then fall back to text-forge venv python, then current interpreter.
    uv_bin = resolve_uv_bin()
    venv_python = text_forge / ".venv" / "bin" / "python"
    legacy_venv_python = text_forge / "venv" / "bin" / "python"
    if uv_bin:
        base_cmd = [uv_bin, "run", "python", str(wrapper)]
        runtime_mode = "uv"
    elif venv_python.exists():
        base_cmd = [str(venv_python), str(wrapper)]
        runtime_mode = "venv"
    elif legacy_venv_python.exists():
        base_cmd = [str(legacy_venv_python), str(wrapper)]
        runtime_mode = "legacy_venv"
    else:
        base_cmd = [sys.executable, str(wrapper)]
        runtime_mode = "system_python"

    cmd = [
        *base_cmd,
        "--root",
        str(wtd_root),
        "--api-url",
        api_url,
        "--bank",
        bank,
        "--yes",
        "--delta",
    ]
    if from_commit:
        cmd.extend(["--from-commit", from_commit])
        ingest_mode = "diff_sections"
    else:
        # Fallback to chapter-level ingest when commit range is unavailable.
        for chapter in chapters:
            one = [*cmd, "--chapter", chapter]
            subprocess.run(one, cwd=text_forge, check=True)
        return {
            "chapters": chapters,
            "api_url": api_url,
            "bank": bank,
            "text_forge": str(text_forge),
            "wtd_root": str(wtd_root),
            "runtime_mode": runtime_mode,
            "ingest_mode": "chapter_fallback",
        }

    subprocess.run(cmd, cwd=text_forge, check=True)

    return {
        "chapters": chapters,
        "api_url": api_url,
        "bank": bank,
        "text_forge": str(text_forge),
        "wtd_root": str(wtd_root),
        "runtime_mode": runtime_mode,
        "ingest_mode": ingest_mode,
        "from_commit": from_commit,
    }


def invoke_start_reingest(
    start_reingest_fn: Callable[..., dict[str, Any]], chapters: list[str], from_commit: str | None
) -> dict[str, Any]:
    try:
        return start_reingest_fn(chapters, from_commit)
    except TypeError:
        # Backwards-compatible fallback for tests or older callables.
        return start_reingest_fn(chapters)


def run_for_payload(
    payload: dict[str, Any],
    *,
    state_path: Path = STATE_PATH,
    start_reingest_fn: Callable[..., dict[str, Any]] = start_reingest,
) -> str | None:
    repo = _safe_str(payload.get("repository", {}).get("full_name"))
    ref = _safe_str(payload.get("ref"))
    if repo != TARGET_REPO:
        return None
    if ref and ref != TARGET_REF:
        return None

    commits = [c for c in _safe_list(payload.get("commits")) if isinstance(c, dict)]
    changed_paths = collect_changed_paths(commits)
    chapters = chapters_from_paths(changed_paths)
    if not chapters:
        return None

    before = _safe_str(payload.get("before"))
    after = _safe_str(payload.get("after"))
    commit_range = f"{before[:7]}..{after[:7]}" if before and after else "unknown"

    ingest_meta = invoke_start_reingest(start_reingest_fn, chapters, after or None)

    previous = load_state(state_path)
    state = {
        "status": "processing",
        "started_at": utc_now_iso(),
        "previous_status": previous.get("status"),
        "repo": repo,
        "ref": ref or TARGET_REF,
        "commit_range": commit_range,
        "chapters": chapters,
        "retain_operation_id": None,
        "consolidation_operation_id": None,
        "ingest": ingest_meta,
    }
    save_state(state_path, state)

    return (
        f"WTD processing started. Status: processing. "
        f"Commit range: {commit_range}. Chapters: {len(chapters)} ({', '.join(chapters)})."
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
        message = run_for_payload(payload)
    except Exception as exc:
        print(f"WTD processing failed to start: {exc}")
        return

    print(message if message else "[SILENT]")


if __name__ == "__main__":
    main()
