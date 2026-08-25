#!/usr/bin/env python3
"""Prepare deterministic inputs for a WTD content comparison.

This script does not interpret the material. It refreshes the local WTD checkout
when safe, optionally fetches a timestamped YouTube transcript, and inventories
Markdown source files for the LLM/Hindsight comparison stage.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def git_state(repo: Path) -> dict:
    before = run(["git", "status", "--short", "--branch"], repo)
    dirty = bool(before.stdout and any(line and not line.startswith("##") for line in before.stdout.splitlines()))
    pull: dict[str, object]
    if dirty:
        pull = {
            "attempted": False,
            "ok": False,
            "reason": "working tree is not clean; pull skipped",
            "stdout": "",
            "stderr": "",
        }
    else:
        result = run(["git", "pull", "--ff-only"], repo)
        pull = {
            "attempted": True,
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    after = run(["git", "status", "--short", "--branch"], repo)
    commit = run(["git", "rev-parse", "HEAD"], repo)
    return {
        "repo": str(repo),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "before": before.stdout.strip(),
        "dirty_before_pull": dirty,
        "pull": pull,
        "after": after.stdout.strip(),
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
    }


def source_inventory(repo: Path) -> list[dict[str, object]]:
    files = []
    for path in sorted(repo.rglob("*.md")):
        if any(part == ".git" for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        headings = [line.strip() for line in text.splitlines() if line.lstrip().startswith("#")]
        files.append({
            "path": str(path.relative_to(repo)),
            "bytes": path.stat().st_size,
            "headings": headings[:100],
        })
    return files


def fetch_transcript(url: str, output_dir: Path, language: str | None) -> dict:
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    helper = hermes_home / "skills/media/youtube-content/scripts/fetch_transcript.py"
    if not helper.exists():
        raise FileNotFoundError(f"youtube transcript helper not found: {helper}")

    hermes_python = hermes_home / "hermes-agent/venv/bin/python"
    runner = str(hermes_python) if hermes_python.exists() else sys.executable
    command = [runner, str(helper), url, "--timestamps"]
    if language:
        command.extend(["--language", language])
    result = run(command)
    raw = result.stdout.strip()
    if result.returncode != 0:
        raise RuntimeError((result.stderr or raw or "transcript helper failed").strip())

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"raw": raw, "parse_error": "helper output was not JSON"}

    (output_dir / "transcript.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if isinstance(payload, dict) and payload.get("timestamped_text"):
        transcript_text = str(payload["timestamped_text"])
    elif isinstance(payload, dict) and payload.get("full_text"):
        transcript_text = str(payload["full_text"])
    else:
        text = payload.get("transcript") if isinstance(payload, dict) else None
        if isinstance(text, list):
            lines = []
            for item in text:
                if isinstance(item, dict):
                    start = item.get("start", item.get("offset", ""))
                    content = item.get("text", "")
                    lines.append(f"[{start}] {content}".strip())
                else:
                    lines.append(str(item))
            transcript_text = "\n".join(lines)
        else:
            transcript_text = str(text or payload.get("raw", "")) if isinstance(payload, dict) else str(payload)
    (output_dir / "transcript.md").write_text(transcript_text + "\n", encoding="utf-8")
    return {
        "ok": bool(transcript_text.strip()),
        "language_requested": language,
        "helper": str(helper),
        "returncode": result.returncode,
        "characters": len(transcript_text),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Content URL, such as a web page or YouTube URL")
    parser.add_argument("--wtd-repo", default=os.environ.get("WTD_REPO_PATH", "~/Work/whattodo"), type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--language", default="ru,en")
    args = parser.parse_args()

    output_dir = args.output_dir or Path.cwd() / "video_comparison_packet"
    output_dir.mkdir(parents=True, exist_ok=True)
    wtd_repo = args.wtd_repo.expanduser()
    if not wtd_repo.is_dir():
        print(f"WTD repository not found: {wtd_repo}", file=sys.stderr)
        return 2

    state = git_state(wtd_repo)
    (output_dir / "git_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inventory = source_inventory(wtd_repo)
    (output_dir / "wtd_source_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        transcript = fetch_transcript(args.url, output_dir, args.language)
    except (FileNotFoundError, RuntimeError) as exc:
        transcript = {"ok": False, "error": str(exc)}
        (output_dir / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output_dir / "transcript.md").write_text("", encoding="utf-8")

    metadata = {
        "url": args.url,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "wtd_repo": str(wtd_repo),
        "git_commit": state.get("commit"),
        "git_pull_ok": state.get("pull", {}).get("ok", False),
        "transcript": transcript,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "metadata": metadata}, ensure_ascii=False, indent=2))
    return 0 if transcript.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]

# End of file
