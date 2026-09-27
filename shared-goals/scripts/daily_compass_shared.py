#!/usr/bin/env python3
"""Shared helpers for Daily Compass runtime and area contract tests."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Protocol, TypedDict

VALID_DIMENSIONS = {"faith", "will", "feeling", "mind"}

BOUNDARY_SCRIPT_TIMEOUT_SECONDS = 180
HERMES_SIGNAL_TIMEOUT_SECONDS = 180
HERMES_REFLECT_TIMEOUT_SECONDS = 300
SESSION_COMMAND_TIMEOUT_SECONDS = 60

ACTION_VERBS = {
    "add",
    "analyze",
    "classify",
    "delete",
    "derive",
    "drop",
    "keep",
    "map",
    "preserve",
    "prioritize",
    "rank",
    "remove",
    "rewrite",
    "set",
    "summarize",
    "trim",
    "update",
    "write",
}

AREA_SIGNAL_VERIFICATION_BASE_LINES = [
    "Exactly one AreaContext JSON object.",
    "No prose before or after output AreaContext JSON.",
    "No markdown fences or comments.",
    "AreaContext `signal` is not more than 70 chars.",
    "LineContext `signal` is not more than the configured area limit.",
    "Do not invent facts outside input AreaContext.",
]

COMMON_JSON_CONTRACT_PHRASES = [
    "json object",
    "top-level keys",
    "source of truth",
    "do not invent",
    "exactly one valid json",
    "schema-preserving",
    "markdown fences",
    "extra fields",
    "preserve status",
    "preserve reason",
    "line facts",
]

HERMES_AGENT_DIR = Path.home() / ".hermes" / "hermes-agent"
HERMES_CLI_PY = HERMES_AGENT_DIR / "cli.py"
HERMES_VENV_PY = HERMES_AGENT_DIR / "venv" / "bin" / "python"
SHARED_GOALS_DIR = Path.home() / ".hermes" / "skills" / "shared-goals" / "shared-goals"
SHARED_GOALS_LOGS_DIR = SHARED_GOALS_DIR / "logs"
SHARED_GOALS_STATE_DIR = SHARED_GOALS_DIR / "state"
COMPASS_CONTEXT_STATE_FILE = SHARED_GOALS_STATE_DIR / "daily-compass-context.json"
NEXT_STEPS_MAX_ITEMS = 5


def load_env_file(env_path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ when missing."""
    import os

    path = env_path or (Path.home() / ".hermes" / ".env")
    if not path.exists():
        return

    try:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return


def resolve_hermes_argv() -> list[str]:
    """Resolve hermes command argv with PATH and module fallback."""
    env_bin = os.environ.get("HERMES_BIN", "").strip()
    if env_bin:
        if any(sep in env_bin for sep in ("/", "\\")):
            return [str(Path(env_bin).expanduser())]
        resolved_env = shutil.which(env_bin)
        if resolved_env:
            return [resolved_env]

    hermes_bin = shutil.which("hermes")
    if hermes_bin:
        return [hermes_bin]

    if importlib.util.find_spec("hermes_cli") is not None:
        return [sys.executable, "-m", "hermes_cli.main"]

    return []


def resolve_non_tui_cli_argv() -> list[str]:
    """Resolve non-TUI CLI entrypoint for scripted query/chat calls."""
    if HERMES_CLI_PY.exists() and HERMES_VENV_PY.exists():
        return [str(HERMES_VENV_PY), str(HERMES_CLI_PY)]
    if HERMES_CLI_PY.exists():
        return [sys.executable, str(HERMES_CLI_PY)]
    return []


def resolve_chat_cli_argv() -> list[str]:
    """Resolve `hermes chat`; only this entrypoint supports title-keyed sessions."""
    hermes_argv = resolve_hermes_argv()
    return [*hermes_argv, "chat"] if hermes_argv else []


def build_hermes_query_cmd(prompt: str) -> list[str]:
    """Build robust query command that avoids TUI wrappers when available."""
    cli_argv = resolve_non_tui_cli_argv()
    if cli_argv:
        return [*cli_argv, "--query", prompt, "--quiet"]
    hermes_argv = resolve_hermes_argv()
    if hermes_argv:
        return [*hermes_argv, "-z", prompt]
    return []


CLI_BANNER_PREFIXES = ("Warning: Unknown toolsets:", "↪ restored workspace dir:")


def sanitize_hermes_output(text: str) -> str:
    """Strip known non-semantic CLI prefixes from scripted output."""
    lines = (text or "").splitlines()
    while lines and lines[0].startswith(CLI_BANNER_PREFIXES):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip()


def resolve_shared_goals_logs_dir() -> Path:
    """Return shared-goals logs directory, creating it when needed."""
    SHARED_GOALS_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return SHARED_GOALS_LOGS_DIR


def resolve_area_log_path(area_key: str, run_id: str | None = None) -> Path:
    """Return per-area log path in shared-goals logs directory."""
    safe_area = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(area_key or "area").strip()) or "area"
    run = str(run_id or os.environ.get("DAILY_COMPASS_RUN_ID", "")).strip()
    if not run:
        run = datetime.now().strftime("%Y%m%d-%H%M%S")
        # Reuse one process-local run id when area scripts run standalone.
        os.environ["DAILY_COMPASS_RUN_ID"] = run
    return resolve_shared_goals_logs_dir() / f"{run}.{safe_area}.log"


def append_area_log_line(area_key: str, message: str, level: str = "INFO", run_id: str | None = None) -> Path:
    """Append one timestamped line to a per-area log file and return its path."""
    path = resolve_area_log_path(area_key, run_id=run_id)
    stamp = datetime.now().isoformat(timespec="seconds")
    entry = f"[{stamp}] [{str(level or 'INFO').upper()}] {str(message or '').strip()}\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    return path


def now_iso_utc() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def save_json_snapshot(path: Path, payload: dict[str, Any], logger: LoggerLike | None = None) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        if logger is not None:
            logger.log(f"Snapshot write failed: {exc}")
        else:
            raise


def load_json_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def sanitize_logos_task_text(text: str) -> str:
    """Make free-form LLM signal text safe to embed as one Markdown checklist line.

    Renders as a single `- [ ] ...` line, so any embedded newline (e.g. from a
    truncated or multi-paragraph reflection) would otherwise split the list item
    and any code-fence marker (```) placed at the start of a resulting line would
    open a fenced code block that swallows the rest of Compass.md if it never
    closes. Collapsing to one line neutralizes both failure modes at the source.
    """
    collapsed = " ".join(str(text or "").split())
    plain = collapsed.replace("```", "").replace("**", "")
    plain = re.sub(r"^(?:(?:>+|#{1,6})\s*|[-*]\s*(?:\[[ xX]\]\s*)?)+", "", plain)
    return re.sub(r"\|{2,}$", "", plain).strip()


def render_next_steps_from_compass_snapshot(snapshot: dict[str, Any]) -> str:
    areas = snapshot.get("areas") if isinstance(snapshot, dict) else None
    if not isinstance(areas, list):
        areas = []

    shared_area: dict[str, Any] | None = None
    for area in areas:
        if not isinstance(area, dict):
            continue
        if str(area.get("key", "")).strip() == "shared-goals":
            shared_area = area
            break

    lines = ["## Logos", ""]
    if not shared_area:
        lines.append("- [ ] No next steps yet.")
        return "\n".join(lines) + "\n"

    shared_lines = shared_area.get("lines") if isinstance(shared_area, dict) else None
    if not isinstance(shared_lines, list) or not shared_lines:
        lines.append("- [ ] No next steps yet.")
        return "\n".join(lines) + "\n"

    shown = 0
    for item in shared_lines:
        if shown >= 1:
            break
        if not isinstance(item, dict):
            continue

        # Prefer explicit line signal as the actionable task.
        task = str(item.get("signal", "")).strip()
        if not task:
            body = str(item.get("body", "")).strip()
            steps = split_steps(body)
            if steps:
                task = steps[0]
        if not task:
            task = str(item.get("title", "")).strip()

        if task:
            lines.append(f"- [ ] {sanitize_logos_task_text(task)}")
            shown += 1
    return "\n".join(lines).rstrip() + "\n"


def format_dim_label(value: str) -> str:
    v = str(value or "").strip().lower()
    return v[:1].upper() + v[1:] if v else "Unknown"


def hunger_days(last_fed_at: Any) -> str:
    text = str(last_fed_at or "").strip()
    if not text:
        return "never"
    try:
        ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "never"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return str(max(0, (datetime.now(timezone.utc) - ts).days))


def split_steps(text: str) -> list[str]:
    steps: list[str] = []
    for raw in str(text or "").splitlines():
        item = re.sub(r"^[-*]\s+", "", raw.strip())
        if item:
            steps.append(item)
    if not steps and str(text or "").strip():
        steps.append(str(text).strip())
    return steps


def render_shared_goals_section(payload: dict[str, Any], default_dimensions: list[str]) -> str:
    dims = payload.get("dimensions") if isinstance(payload, dict) else None
    if not isinstance(dims, list):
        dims = []

    by_name: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for block in dims:
        if not isinstance(block, dict):
            continue
        name = str(block.get("dimension", "")).strip().lower()
        if not name:
            continue
        by_name[name] = block

    raw_order = payload.get("dimension_order") if isinstance(payload, dict) else None
    if isinstance(raw_order, list):
        for item in raw_order:
            name = str(item).strip().lower()
            if name and name not in order:
                order.append(name)
    for dim in default_dimensions:
        if dim not in order:
            order.append(dim)

    lines = ["## Shared Goals", ""]
    for dim in order:
        block = by_name.get(dim, {})
        fed = block.get("last_fed_at") if isinstance(block, dict) else None
        fed_label = f"{hunger_days(fed)}d" if fed else "never"
        lines.append(f"### {format_dim_label(dim)} ({fed_label})")
        lines.append("")
        goals = block.get("goals") if isinstance(block, dict) else None
        if not isinstance(goals, list) or not goals:
            lines.append("- No goals in this dimension.")
            lines.append("")
            continue

        for goal in goals:
            if not isinstance(goal, dict):
                continue
            goal_tag = str(goal.get("goal_tag", "")).strip()
            goal_title = str(goal.get("goal_title", "")).strip()
            headline_parts = [goal_title, goal_tag, f"hunger:{hunger_days(block.get('last_fed_at'))}d"]
            headline = " ".join(part for part in headline_parts if part).strip()
            if headline:
                lines.append(f"- **{headline}**")
            for step in split_steps(str(goal.get("next_step_text", ""))):
                if goal_tag and goal_tag not in step:
                    step = f"{step} {goal_tag}".strip()
                lines.append(f"  - [ ] {step}")
        lines.append("")

    if lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def make_line_context(title: str, url: str = "", body: str = "", signal: str = "") -> dict[str, str]:
    """Create a strict LineContext dict."""
    return {
        "title": str(title),
        "url": str(url),
        "body": str(body),
        "signal": str(signal),
    }


def make_boundary_payload(
    *,
    status: str,
    reason: str,
    lines: list[dict[str, str]] | None = None,
    include_ts: bool = False,
) -> dict[str, Any]:
    """Create a minimal boundary payload with only status, reason, lines, and optional ts."""
    payload: dict[str, Any] = {
        "status": status,
        "reason": reason,
        "lines": lines or [],
    }
    if include_ts:
        payload["ts"] = now_iso_utc()
    return payload


def build_numbered_lines(lines: list[str], start: int = 1) -> str:
    out: list[str] = []
    for index, line in enumerate(lines, start=start):
        out.append(f"{index}. {line}")
    return "\n".join(out)


def area_context_definition_text() -> str:
    return (
        "LineContext definition:\n"
        "LineContext = { title: string, url: string, body: string, signal: string }\n\n"
        "AreaContext definition:\n"
        "AreaContext = { name: string, key: string, dimension: string, signal: string, lines: LineContext[] }\n"
    )


@dataclass
class SubprocessTextResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    launch_error: bool = False


class LoggerLike(Protocol):
    def log(self, msg: str) -> None: ...


@dataclass(frozen=True)
class HermesCallProfile:
    key: str
    session_name: str
    model: str
    provider: str
    toolsets: tuple[str, ...]
    timeout_seconds: int
    oneshot: bool = False
    skip_memory: bool = False


@dataclass
class HermesCallResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    session_id: str | None
    resumed: bool
    timed_out: bool = False
    launch_error: bool = False


def run_subprocess_text(argv: list[str], *, timeout: int, env: dict[str, str] | None = None) -> SubprocessTextResult:
    """Run a subprocess and return normalized text outputs and status."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return SubprocessTextResult(returncode=124, stdout=stdout, stderr=stderr, timed_out=True, launch_error=False)
    except OSError as exc:
        return SubprocessTextResult(returncode=127, stdout="", stderr=str(exc), timed_out=False, launch_error=True)

    return SubprocessTextResult(
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        timed_out=False,
        launch_error=False,
    )


def extract_session_id(*texts: str) -> str | None:
    """Find a Hermes session id in CLI stdout/stderr text."""
    patterns = [
        r"session[_\s-]*id\s*[:=]\s*`?([A-Za-z0-9_.:-]+)`?",
        r"\b([0-9]{8}_[0-9]{6}_[a-f0-9]{6,})\b",
    ]
    for text in texts:
        blob = str(text or "")
        if not blob:
            continue
        for pattern in patterns:
            match = re.search(pattern, blob, flags=re.IGNORECASE)
            if not match:
                continue
            value = str(match.group(1)).strip()
            if value:
                return value
    return None


def load_session_registry(path: Path, logger: LoggerLike | None = None) -> dict[str, Any]:
    if not path.exists():
        return {"sessions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        if logger is not None:
            logger.log(f"Hermes session registry read failed: {exc}")
        return {"sessions": {}}
    sessions = payload.get("sessions") if isinstance(payload, dict) else None
    return payload if isinstance(sessions, dict) else {"sessions": {}}


def load_named_session_id(path: Path, profile: HermesCallProfile, logger: LoggerLike | None = None) -> str | None:
    """Return the last observed session id for a profile (informational only)."""
    payload = load_session_registry(path, logger)
    record = payload["sessions"].get(profile.key)
    if not isinstance(record, dict):
        return None
    return str(record.get("session_id", "")).strip() or None


def save_named_session(
    path: Path, profile: HermesCallProfile, session_id: str, logger: LoggerLike | None = None
) -> None:
    if not session_id:
        return
    payload = load_session_registry(path, logger)
    existing = payload["sessions"].get(profile.key)
    record = dict(existing) if isinstance(existing, dict) else {}
    record.update(
        {
            "session_id": session_id,
            "session_name": profile.session_name,
            "effective_model": profile.model,
            "effective_provider": profile.provider,
            "toolsets": list(profile.toolsets),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    payload["sessions"][profile.key] = record
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        if logger is not None:
            logger.log(f"Hermes session registry write failed: {exc}")


def run_hermes_call(
    *,
    cli_argv: list[str],
    prompt: str,
    profile: HermesCallProfile,
    registry_path: Path,
    logger: LoggerLike,
    label: str,
) -> HermesCallResult:
    """Execute one policy-complete Hermes call against the profile's named session."""
    known_id = None if profile.oneshot else load_named_session_id(registry_path, profile, logger)

    def build() -> list[str]:
        cmd = [*cli_argv]
        if not profile.oneshot:
            cmd.extend(["--continue", profile.session_name, "--create-if-missing"])
        cmd.extend(["--model", profile.model, "--provider", profile.provider])
        if profile.toolsets:
            cmd.extend(["--toolsets", ",".join(profile.toolsets)])
        if profile.skip_memory:
            cmd.append("--ignore-rules")
        if profile.oneshot:
            cmd.extend(["--oneshot", prompt])
        else:
            cmd.extend(["--query", prompt, "--quiet"])
        return cmd

    logger.log(
        f"Hermes call start: label={label} session={profile.key} "
        f"title='{profile.session_name}' id={known_id or 'unknown'} "
        f"model={profile.model} provider={profile.provider} "
        f"toolsets={','.join(profile.toolsets) or 'default'} timeout={profile.timeout_seconds}s"
    )
    started = monotonic()
    result = run_subprocess_text(build(), timeout=profile.timeout_seconds, env=os.environ.copy())
    elapsed = monotonic() - started
    new_id = extract_session_id(result.stderr) if result.returncode == 0 else None
    if new_id and not profile.oneshot:
        save_named_session(registry_path, profile, new_id, logger)
    resumed = bool(new_id) and new_id == known_id
    logger.log(
        f"Hermes call finish: label={label} session={profile.key} id={new_id or known_id or 'unknown'} "
        f"elapsed={elapsed:.1f}s resumed={resumed} returncode={result.returncode} "
        f"timed_out={result.timed_out} launch_error={result.launch_error}"
    )
    return HermesCallResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        elapsed_seconds=elapsed,
        session_id=new_id or known_id,
        resumed=resumed,
        timed_out=result.timed_out,
        launch_error=result.launch_error,
    )


class LineContext(TypedDict):
    title: str
    url: str
    body: str
    signal: str


class AreaContext(TypedDict):
    name: str
    key: str
    dimension: str
    signal: str
    lines: list[LineContext]


class BoundaryAreaContext(AreaContext):
    status: str
    reason: str


class CompassContext(TypedDict):
    signal_prompt: str
    signal: str
    dimensions: list[str]
    ranking_fallback: bool
    areas: list[BoundaryAreaContext]
    area_meta: dict[str, dict[str, str]]
    advice: dict[str, dict[str, Any]]


def parse_json_object(text: str) -> dict[str, Any] | None:
    left = text.find("{")
    right = text.rfind("}")
    if left < 0 or right <= left:
        return None
    try:
        payload = json.loads(text[left : right + 1])
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def extract_section(skill_text: str, heading: str) -> str:
    pat = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.M)
    m = pat.search(skill_text)
    if not m:
        return ""
    start = m.end()
    tail = skill_text[start:]
    next_h = re.search(r"^##\s+", tail, re.M)
    return (tail[: next_h.start()] if next_h else tail).strip()


def strip_wrapping_fences(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return body

    if body.startswith("```"):
        lines = body.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()

    if body.startswith("~~~"):
        lines = body.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "~~~":
            return "\n".join(lines[1:-1]).strip()

    return body


def validate_json_response_strict(text: str, expected_key: str = "") -> tuple[AreaContext | None, str]:
    """Validate JSON output with strict no-wrapper policy.

    Returns (payload, reason) where reason is one of:
    - valid
    - valid_with_prose
    - empty
    - invalid_json
    - has_prose
    - not_dict
    - schema_error
    """
    body = strip_wrapping_fences(text)
    if not body:
        return None, "empty"

    left = body.find("{")
    right = body.rfind("}")
    if left < 0 or right <= left:
        return None, "invalid_json"

    has_wrapper_prose = bool(body[:left].strip() or body[right + 1 :].strip())

    try:
        payload = json.loads(body[left : right + 1])
    except ValueError:
        return None, "invalid_json"

    if not isinstance(payload, dict):
        return None, "not_dict"

    if not is_valid_area_context(payload, expected_key):
        return None, "schema_error"

    if has_wrapper_prose:
        return payload, "valid_with_prose"

    return payload, "valid"


def is_valid_line_context(line: dict[str, Any]) -> bool:
    if set(line.keys()) != {"title", "url", "body", "signal"}:
        return False
    title = str(line.get("title", "")).strip()
    if not title:
        return False
    return all(isinstance(line.get(key), str) for key in ("title", "url", "body", "signal"))


def is_valid_area_context(payload: dict[str, Any], expected_key: str = "") -> bool:
    if set(payload.keys()) != {"name", "key", "dimension", "signal", "lines"}:
        return False

    key = str(payload.get("key", "")).strip()
    name = str(payload.get("name", "")).strip()
    dimension = str(payload.get("dimension", "")).strip()
    signal = payload.get("signal")
    lines = payload.get("lines")

    if expected_key and key != expected_key:
        return False
    if not key:
        return False
    if not name:
        return False
    if dimension not in VALID_DIMENSIONS:
        return False
    if not isinstance(signal, str):
        return False
    if not isinstance(lines, list):
        return False

    for line in lines:
        if not isinstance(line, dict):
            return False
        if not is_valid_line_context(line):
            return False
    return True


# Output and serialization helpers


def normalize_text(text: str) -> str:
    """Normalize newlines: CRLF/CR → LF for consistent output."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def serialize_line_item(line: dict[str, Any]) -> LineContext:
    """Extract line to LLM-safe schema (title, url, body, signal)."""
    if not isinstance(line, dict):
        return {"title": "", "url": "", "body": "", "signal": ""}
    return {
        "title": str(line.get("title", "")),
        "url": str(line.get("url", "")),
        "body": str(line.get("body", "")),
        "signal": str(line.get("signal", "")),
    }


def serialize_area_base(area: dict[str, Any]) -> AreaContext:
    """Extract lean prompt-safe AreaContext fields."""
    if not isinstance(area, dict):
        return {"name": "", "key": "", "dimension": "", "signal": "", "lines": []}
    return {
        "name": str(area.get("name", "")),
        "key": str(area.get("key", "")),
        "dimension": str(area.get("dimension", "")),
        "signal": str(area.get("signal", "")),
        "lines": [],
    }


def serialize_boundary_area_base(area: dict[str, Any]) -> BoundaryAreaContext:
    """Extract boundary/runtime area fields including operational metadata."""
    base = serialize_area_base(area)
    return {
        "name": base["name"],
        "key": base["key"],
        "dimension": base["dimension"],
        "status": str(area.get("status", "")),
        "reason": str(area.get("reason", "")),
        "signal": base["signal"],
        "lines": [],
    }


def project_boundary_to_area_context(area: dict[str, Any]) -> AreaContext:
    """Project boundary-rich area into lean AreaContext for prompt builders."""
    base = serialize_area_base(area)
    lines = area.get("lines", []) if isinstance(area.get("lines", []), list) else []
    base["lines"] = [serialize_line_item(line) for line in lines]
    return base


def safe_str_key(obj: dict[str, Any], key: str) -> str:
    """Safely extract and coerce dict value to stripped string."""
    return str(obj.get(key, "")).strip()
