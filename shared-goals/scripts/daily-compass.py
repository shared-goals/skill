#!/usr/bin/env python3
"""Shared Goals Daily Compass runtime.

Pipeline:
1) Load active areas from references/*.yaml
2) Run boundary scripts in parallel and collect script JSON
3) Optionally run area/compass signal generation via hermes
4) Render final markdown from templates/daily-output.md

CLI:
  daily-compass.py [area1 area2 ...] [--verbose] [--fast]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from daily_compass_shared import (
	AREA_SIGNAL_VERIFICATION_BASE_LINES,
	COMPASS_CONTEXT_STATE_FILE,
	AreaContext,
	BOUNDARY_SCRIPT_TIMEOUT,
	BoundaryAreaContext,
	CompassContext,
	area_context_definition_text,
	build_numbered_lines,
	build_skill_index,
	resolve_hermes_argv,
	resolve_non_tui_cli_argv,
	sanitize_hermes_output,
	extract_section,
	normalize_text,
	parse_inline_list,
	parse_json_object,
	parse_top_level_yaml,
	run_subprocess_text,
	run_boundary_script,
	safe_str_key,
	serialize_area_base,
	serialize_boundary_area_base,
	serialize_line_item,
	project_boundary_to_area_context,
	save_json_snapshot,
	validate_json_response_strict,
)


HOME = Path.home()
HERMES_AGENT_DIR = HOME / ".hermes" / "hermes-agent"
HERMES_VENV_PY = HERMES_AGENT_DIR / "venv" / "bin" / "python"
HERMES_SKILLS_DIR = HOME / ".hermes" / "skills"
SHARED_GOALS_DIR = HERMES_SKILLS_DIR / "shared-goals" / "shared-goals"
SHARED_GOALS_SKILL = SHARED_GOALS_DIR / "SKILL.md"
AREAS_DIR = SHARED_GOALS_DIR / "references"
TEMPLATE_FILE = SHARED_GOALS_DIR / "templates" / "daily-output.md"
LOGS_DIR = SHARED_GOALS_DIR / "logs"
JOBS_FILE = HOME / ".hermes" / "cron" / "jobs.json"
SESSION_STATE_FILE = SHARED_GOALS_DIR / "state" / "daily-compass-session.json"

DEFAULT_DIMENSIONS = ["faith", "will", "feeling", "mind"]
VALID_DIMENSIONS = set(DEFAULT_DIMENSIONS)
DEFAULT_COMPASS_PROMPT = "Write one short phrase about today's Shared Goals direction based on area summaries."
DEFAULT_SESSION_TITLE = "Daily Compass"

PHASE_BOUNDARY = "Phase 1: boundary scripts"
PHASE_PROMPTS = "Phase 2: signal prompts"
PHASE_SIGNAL = "Phase 3: signal responses"
PHASE_RENDER = "Phase 4: render"
PHASE_FINAL = "Phase 5: final"

COMPASS_PROMPT_LABEL = "Compass signal prompt:"
AREA_PROMPT_LABEL = "Area signal prompt:"


@dataclass
class SignalJobResult:
	key: str
	area: BoundaryAreaContext | None
	reason: str
	ok: bool


@dataclass
class AreaSignalTask:
	index: int
	key: str
	label: str
	area: BoundaryAreaContext
	area_prompt: str
	prompt: str
	signal_max_chars: int = 50


@dataclass
class AreaSignalExecutionContext:
	model: str
	provider: str
	logger: TraceLogger
	session: HermesSessionState


@dataclass
class AreaConfig:
	key: str
	name: str
	dimensions: list[str]
	skill: str
	status: str
	path: Path
	signal_max_chars: int


@dataclass
class HermesSessionState:
	mode: str
	hermes_argv: list[str]
	chat_argv: list[str]
	session_id: str | None = None
	session_name: str = DEFAULT_SESSION_TITLE
	session_state_file: Path = SESSION_STATE_FILE
	rename_needed: bool = False
	renamed_session_ids: set[str] = field(default_factory=set)


def prune_expired_logs(logs_dir: Path) -> None:
	cutoff = datetime.now() - timedelta(days=7)
	for log_file in logs_dir.glob("*.log"):
		try:
			if log_file.is_file() and datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff:
				log_file.unlink()
		except FileNotFoundError:
			pass


class TraceLogger:
	def __init__(self, verbose: bool) -> None:
		self.verbose = verbose
		self.lines: list[str] = []
		LOGS_DIR.mkdir(parents=True, exist_ok=True)
		prune_expired_logs(LOGS_DIR)
		stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
		self.path = LOGS_DIR / f"{stamp}.log"
		self._fh = self.path.open("w", encoding="utf-8")

	def log(self, msg: str) -> None:
		line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
		self.lines.append(line)
		if self.verbose:
			print(line)
		else:
			self.write_chunk(line + "\n")

	def write_chunk(self, chunk: str) -> None:
		if not chunk:
			return
		self._fh.write(chunk)
		self._fh.flush()

	def write(self) -> Path:
		self._fh.flush()
		self._fh.close()
		return self.path

	def blank_line(self) -> None:
		if self.verbose:
			print()
		else:
			self.write_chunk("\n")

	def output(self, text: str, newline: bool = True) -> None:
		"""Output text respecting verbose mode."""
		final = text
		if newline and not final.endswith("\n"):
			final = final + "\n"
		if self.verbose:
			print(final, end="")
		else:
			self.write_chunk(final)


class TeeStream:
	def __init__(self, original: Any, logger: TraceLogger) -> None:
		self.original = original
		self.logger = logger

	def write(self, data: str) -> int:
		self.logger.write_chunk(data)
		return self.original.write(data)

	def flush(self) -> None:
		self.original.flush()

	def isatty(self) -> bool:
		return bool(getattr(self.original, "isatty", lambda: False)())


def print_phase(title: str) -> None:
	print()
	print("=" * 12 + f" {title} " + "=" * 12)
	print()


def emit_text_block(write_line: Any, label: str, body: str, default: str = "") -> None:
	write_line(label)
	write_line("")
	write_line(body or default)
	write_line("")


def log_text_block(logger: TraceLogger, label: str, text: str, elapsed: float | None = None) -> None:
	logger.blank_line()
	if elapsed is not None:
		logger.log(f"{label} ({elapsed:.0f}s)")
	else:
		logger.log(label)
	logger.blank_line()
	body = normalize_text(text)
	if logger.verbose:
		print(body)
	else:
		logger.write_chunk(body + "\n")
	logger.blank_line()


def log_json_response(logger: TraceLogger, label: str, json_text: str) -> None:
	"""Log JSON response with human-readable formatting."""
	logger.blank_line()
	logger.log(label)
	logger.blank_line()
	try:
		obj = parse_json_object(json_text)
		if obj:
			formatted = pretty_json(obj)
			logger.output(formatted)
		else:
			body = normalize_text(json_text)
			logger.output(body)
	except Exception:
		body = normalize_text(json_text)
		logger.output(body)
	logger.blank_line()


def pretty_json(value: Any) -> str:
	return json.dumps(value, ensure_ascii=False, indent=2)


def generated_prompt_blocks(runtime: CompassContext) -> list[tuple[str, str, str]]:
	blocks: list[tuple[str, str, str]] = []
	area_meta = runtime.get("area_meta", {}) if isinstance(runtime.get("area_meta"), dict) else {}
	areas_context: list[dict[str, Any]] = []
	for area in runtime.get("areas", []):
		if not isinstance(area, dict):
			continue
		area_payload = serialize_area_for_llm(area)
		areas_context.append(area_payload)
		key = str(area.get("key", "")).strip()
		meta = area_meta.get(key, {}) if isinstance(area_meta.get(key, {}), dict) else {}
		area_prompt = str(meta.get("area_prompt", "")).strip()
		generated = build_area_signal_prompt(area_prompt, area_payload)
		blocks.append((str(area.get("name", area.get("key", "area"))), AREA_PROMPT_LABEL, generated))

	compass_prompt = str(runtime.get("signal_prompt", DEFAULT_COMPASS_PROMPT))
	compass_generated = build_compass_signal_prompt(compass_prompt, areas_context)
	blocks.append(("", COMPASS_PROMPT_LABEL, compass_generated))
	return blocks


def emit_generated_prompts(runtime: CompassContext, write_line: Any) -> None:
	for heading, label, body in generated_prompt_blocks(runtime):
		if heading:
			write_line(f"[{heading}]")
		emit_text_block(write_line, label, body, "No")


def print_prompt_preview(runtime: CompassContext) -> None:
	print("Generated signal prompts")
	print()
	emit_generated_prompts(runtime, print)


def print_render_separator() -> None:
	print()


def runtime_json_snapshot(runtime: CompassContext) -> dict[str, Any]:
	snapshot: dict[str, Any] = {
		"compass": {
			"signal": str(runtime.get("signal", "")),
			"dimensions": runtime.get("dimensions", []),
		},
		"areas": [],
	}
	for area in runtime.get("areas", []):
		if not isinstance(area, dict):
			continue
		base = serialize_boundary_area_base(area)
		base["ts"] = area.get("ts", "")
		lines = area.get("lines", [])
		line_items: list[dict[str, Any]] = []
		if isinstance(lines, list):
			for line in lines:
				line_items.append(serialize_line_item(line))
		base["lines"] = line_items
		snapshot["areas"].append(base)
	return snapshot


def normalize_block(text: str) -> str:
	lines = [line.rstrip() for line in text.splitlines()]
	while lines and not lines[0].strip():
		lines.pop(0)
	while lines and not lines[-1].strip():
		lines.pop()
	return "\n".join(lines)


def parse_dimensions_order() -> list[str]:
	text = SHARED_GOALS_SKILL.read_text(encoding="utf-8", errors="replace")
	block = extract_section(text, "Dimensions order")
	if not block:
		return list(DEFAULT_DIMENSIONS)
	first = ""
	for ln in block.splitlines():
		if ln.strip() and not ln.strip().startswith("#"):
			first = ln.strip()
			break
	if not first:
		return list(DEFAULT_DIMENSIONS)
	dims = [d.strip() for d in first.split(",") if d.strip()]
	filtered: list[str] = []
	for dim in dims:
		if dim in VALID_DIMENSIONS and dim not in filtered:
			filtered.append(dim)
	if not filtered:
		return list(DEFAULT_DIMENSIONS)
	for dim in DEFAULT_DIMENSIONS:
		if dim not in filtered:
			filtered.append(dim)
	return filtered


def load_areas(selected: list[str], logger: TraceLogger) -> list[AreaConfig]:
	selected_set = {x.strip().lower() for x in selected if x.strip()}
	areas: list[AreaConfig] = []
	for path in sorted(AREAS_DIR.glob("*.yaml")):
		key = path.stem
		if selected_set and key.lower() not in selected_set:
			continue
		cfg = parse_top_level_yaml(path)
		status = cfg.get("status", "").strip()
		if status != "active":
			continue
		name = cfg.get("name", key).strip() or key
		dims = [d for d in parse_inline_list(cfg.get("dimensions", "[]")) if d in VALID_DIMENSIONS]
		if not dims:
			logger.log(f"Skip area '{key}': no valid dimensions")
			continue
		skill = cfg.get("skill", "").strip()
		if not skill:
			logger.log(f"Skip area '{key}': missing skill")
			continue
		try:
			signal_max_chars = max(50, int(cfg.get("signal_max_chars", "50")))
		except ValueError:
			signal_max_chars = 50
		areas.append(
			AreaConfig(
				key=key,
				name=name,
				dimensions=dims,
				skill=skill,
				status=status,
				path=path,
				signal_max_chars=signal_max_chars,
			)
		)
	logger.log(f"Loaded {len(areas)} active areas")
	return areas


def choose_primary_dimension(area_dimensions: list[str]) -> str:
	for dim in area_dimensions:
		if dim in VALID_DIMENSIONS:
			return dim
	return DEFAULT_DIMENSIONS[0]


def validate_runtime_or_raise(runtime: dict[str, Any]) -> None:
	if not isinstance(runtime, dict):
		raise ValueError("runtime_not_dict")
	dimensions = runtime.get("dimensions")
	if not isinstance(dimensions, list) or not dimensions:
		raise ValueError("runtime_compass_dimensions_invalid")
	areas = runtime.get("areas")
	if not isinstance(areas, list):
		raise ValueError("runtime_areas_not_list")
	for area in areas:
		if not isinstance(area, dict):
			raise ValueError("runtime_area_not_dict")
		if not str(area.get("key", "")).strip():
			raise ValueError("runtime_area_key_missing")
		if not str(area.get("name", "")).strip():
			raise ValueError("runtime_area_name_missing")
		if str(area.get("dimension", "")).strip() not in VALID_DIMENSIONS:
			raise ValueError("runtime_area_dimension_invalid")
		if str(area.get("status", "")).strip() not in {"ok", "TBD", "error"}:
			raise ValueError("runtime_area_status_invalid")
		lines = area.get("lines")
		if not isinstance(lines, list):
			raise ValueError("runtime_area_lines_not_list")
		for line in lines:
			if not isinstance(line, dict):
				raise ValueError("runtime_line_not_dict")
			if not str(line.get("title", "")).strip():
				raise ValueError("runtime_line_title_missing")


def build_error_area(area: AreaConfig, reason: str) -> BoundaryAreaContext:
	return {
		"name": area.name,
		"key": area.key,
		"dimension": choose_primary_dimension(area.dimensions),
		"status": "error",
		"reason": reason,
		"signal": "",
		"lines": [],
		"signal_max_chars": area.signal_max_chars,
	}


def hydrate_boundary_area(payload: dict[str, Any]) -> BoundaryAreaContext:
	area_obj = dict(payload)
	lines: list[dict[str, Any]] = []
	for raw_line in area_obj.get("lines", []):
		if not isinstance(raw_line, dict):
			continue
		line = dict(raw_line)
		line["title"] = str(line.get("title", ""))
		line["url"] = str(line.get("url", ""))
		line["body"] = str(line.get("body", ""))
		line["signal"] = str(line.get("signal", ""))
		lines.append(line)
	area_obj["lines"] = lines
	area_obj["name"] = str(area_obj.get("name", ""))
	area_obj["key"] = str(area_obj.get("key", ""))
	area_obj["dimension"] = str(area_obj.get("dimension", ""))
	area_obj["status"] = str(area_obj.get("status", ""))
	area_obj["reason"] = str(area_obj.get("reason", ""))
	area_obj["signal"] = str(area_obj.get("signal", ""))
	area_obj.pop("ts", None)
	return area_obj


def merge_area_signal_response(base_area: BoundaryAreaContext, response_area: AreaContext) -> BoundaryAreaContext:
	"""Apply lean AreaContext response onto boundary-rich runtime area."""
	updated: BoundaryAreaContext = hydrate_boundary_area(base_area)
	updated["name"] = str(response_area.get("name", updated.get("name", "")))
	updated["key"] = str(response_area.get("key", updated.get("key", "")))
	updated["dimension"] = str(response_area.get("dimension", updated.get("dimension", "")))
	updated["signal"] = str(response_area.get("signal", ""))
	response_lines = response_area.get("lines", []) if isinstance(response_area.get("lines", []), list) else []
	updated["lines"] = [serialize_line_item(line) for line in response_lines]
	return updated


def serialize_area_for_llm(area: BoundaryAreaContext) -> AreaContext:
	"""Canonical helper to serialize area payload for LLM round-trip."""
	return project_boundary_to_area_context(area)


def resolve_area_signal_prompt(skill_md: Path) -> str:
	text = skill_md.read_text(encoding="utf-8", errors="replace")
	return normalize_block(extract_section(text, "Area signal"))


def area_prompt_requests_json(prompt: str) -> bool:
	return bool(str(prompt or "").strip())


def json_area_signal_contract(area_payload: dict[str, Any]) -> str:
	"""Standardized guardrails for JSON area signal round-trip."""
	max_chars = int(area_payload.get("signal_max_chars", 50) or 50)
	checks = [
		line.replace("the configured area limit", f"{max_chars} chars")
		for line in AREA_SIGNAL_VERIFICATION_BASE_LINES
	]
	return (
		f"{area_context_definition_text()}\n\n"
		"VERIFICATION CHECKS:\n"
		f"{build_numbered_lines(checks)}"
	)


def build_area_signal_prompt(area_prompt: str, area_payload: dict[str, Any]) -> str:
	"""Compose a structured area prompt following GOAL→PROCEDURE→CONTRACT→INPUT hierarchy."""
	contract = (
		json_area_signal_contract(area_payload)
		if area_prompt_requests_json(area_prompt)
		else "Output requirement:\nReturn only one short phrase."
	)
	return (
		"GOAL:\n"
		"Return an updated AreaContext JSON object using SIGNAL GUIDANCE and VERIFICATION CHECKS.\n\n"
		"SIGNAL GUIDANCE:\n"
		f"{area_prompt}\n\n"
		f"{contract}\n\n"
		"Input AreaContext JSON:\n"
		f"{pretty_json(area_payload)}"
	)


def build_compass_signal_prompt(compass_prompt: str, areas_context: list[dict[str, Any]]) -> str:
	"""Compose a structured compass prompt with GOAL→INPUT hierarchy."""
	return (
		"GOAL (WHAT):\n"
		f"{compass_prompt}\n\n"
		"INPUT AreaContext list:\n"
		f"{pretty_json(areas_context)}\n\n"
		"Output requirement:\nReturn only one short phrase."
	)


def resolve_compass_signal_prompt() -> str:
	text = SHARED_GOALS_SKILL.read_text(encoding="utf-8", errors="replace")
	prompt = normalize_block(extract_section(text, "Compass signal"))
	return prompt or DEFAULT_COMPASS_PROMPT


def load_job_model_provider(job_name: str, logger: TraceLogger) -> tuple[str, str]:
	try:
		raw = JOBS_FILE.read_text(encoding="utf-8")
		payload = json.loads(raw)
	except (OSError, ValueError) as exc:
		logger.log(f"jobs.json read failed: {exc}")
		return "", ""

	jobs = payload.get("jobs") if isinstance(payload, dict) else None
	if not isinstance(jobs, list):
		return "", ""
	for job in jobs:
		if not isinstance(job, dict):
			continue
		if str(job.get("name", "")).strip() != job_name:
			continue
		model = str(job.get("model", "")).strip()
		provider = str(job.get("provider", "")).strip()
		logger.log(f"Using model/provider from jobs.json: model='{model}' provider='{provider}'")
		return model, provider
	logger.log(f"No matching job '{job_name}' in jobs.json")
	return "", ""


def resolve_chat_argv() -> list[str]:
	"""Resolve non-TUI CLI entrypoint for scripted chat calls."""
	return resolve_non_tui_cli_argv()


def extract_session_id(*texts: str) -> str | None:
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


def load_persistent_session_id(path: Path, logger: TraceLogger) -> str | None:
	if not path.exists():
		return None
	try:
		payload = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, ValueError) as exc:
		logger.log(f"Session state read failed: {exc}")
		return None
	if not isinstance(payload, dict):
		return None
	value = str(payload.get("session_id", "")).strip()
	return value or None


def save_persistent_session_id(path: Path, session_id: str, session_name: str, logger: TraceLogger) -> None:
	if not session_id:
		return
	payload = {
		"session_id": str(session_id),
		"session_name": str(session_name),
		"updated_at": datetime.now().isoformat(timespec="seconds"),
	}
	try:
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	except OSError as exc:
		logger.log(f"Session state write failed: {exc}")


def maybe_rename_session(session: HermesSessionState, logger: TraceLogger) -> None:
	if session.mode != "chat":
		return
	if not session.session_id:
		return
	if not session.session_name.strip():
		return
	if not session.rename_needed:
		return
	if session.session_id in session.renamed_session_ids:
		return
	if not session.hermes_argv:
		return

	cmd = list(session.hermes_argv)
	cmd.extend(["sessions", "rename", session.session_id, session.session_name])
	result = run_subprocess_text(cmd, timeout=60, env=os.environ.copy())
	if result.timed_out:
		logger.log(f"Session rename timed out for {session.session_id}")
		return
	if result.launch_error:
		logger.log(f"Session rename launch failed for {session.session_id}: {result.stderr[:300]}")
		return
	if result.returncode != 0:
		err = (result.stderr or result.stdout or "").strip()[:300]
		logger.log(f"Session rename failed for {session.session_id}: {err}")
		return
	logger.log(f"Session renamed: {session.session_id} -> '{session.session_name}'")
	session.renamed_session_ids.add(session.session_id)
	session.rename_needed = False


def build_hermes_cmd(prompt: str, model: str, provider: str, session: HermesSessionState) -> tuple[list[str], str]:
	if not session.hermes_argv:
		return [], "unavailable"

	if session.mode == "oneshot":
		cmd = list(session.hermes_argv)
		if model:
			cmd.extend(["-m", model])
		if provider:
			cmd.extend(["--provider", provider])
		cmd.extend(["-z", prompt])
		return cmd, "oneshot"

	chat_base = list(session.chat_argv) if session.chat_argv else []
	if chat_base:
		cmd = chat_base
		if session.session_id:
			cmd.extend(["--resume", session.session_id])
			mode = "chat_resume"
		else:
			mode = "chat_new"
		cmd.extend(["--query", prompt, "--quiet"])
		if model:
			cmd.extend(["--model", model])
		if provider:
			cmd.extend(["--provider", provider])
		return cmd, mode

	cmd = list(session.hermes_argv)
	cmd.append("chat")
	if model:
		cmd.extend(["-m", model])
	if provider:
		cmd.extend(["--provider", provider])
	if session.session_id:
		cmd.extend(["--resume", session.session_id])
		mode = "chat_resume"
	else:
		mode = "chat_new"
	cmd.extend(["-q", prompt, "-Q"])
	return cmd, mode


def run_hermes_raw(
	prompt: str,
	model: str,
	provider: str,
	logger: TraceLogger,
	label: str,
	session: HermesSessionState,
) -> tuple[str, float]:
	cmd, mode = build_hermes_cmd(prompt, model, provider, session)
	if not cmd:
		logger.log("Hermes command unavailable: neither PATH shim nor module fallback found")
		return "[ERR:hermes_unavailable]", 0.0
	started = datetime.now()
	logger.log(f"Hermes call start: {label} ({mode})")

	def run_cmd(argv: list[str], run_mode: str) -> tuple[int, str, str] | None:
		result = run_subprocess_text(argv, timeout=180, env=os.environ.copy())
		if result.timed_out:
			logger.log(f"Hermes call timed out for {label} ({run_mode})")
			return (-1, "", "")
		if result.launch_error:
			logger.log(f"Hermes call failed for {label}: {result.stderr}")
			return None
		return (result.returncode, result.stdout, result.stderr)

	result = run_cmd(cmd, mode)
	if result is None:
		return "[ERR:hermes_unavailable]", 0.0
	if result[0] == -1:
		return "[ERR:hermes_timeout]", 0.0

	returncode, stdout_text, stderr_text = result

	if returncode != 0 and mode == "chat_resume":
		err = (stderr_text or "").strip()[:300]
		logger.log(f"Hermes resume failed for {label} ({returncode}): {err}")
		logger.log(f"Hermes fallback start: {label} (chat_new)")
		session.session_id = None
		session.rename_needed = True
		fallback_cmd, fallback_mode = build_hermes_cmd(prompt, model, provider, session)
		result = run_cmd(fallback_cmd, fallback_mode)
		if result is None:
			return "[ERR:hermes_unavailable]", 0.0
		if result[0] == -1:
			return "[ERR:hermes_timeout]", 0.0
		returncode, stdout_text, stderr_text = result
		mode = fallback_mode

	if session.mode == "chat" and returncode == 0:
		session_id = extract_session_id(stderr_text, stdout_text)
		if session_id:
			if session.session_id != session_id:
				logger.log(f"Hermes session id: {session_id}")
			session.session_id = session_id
			save_persistent_session_id(session.session_state_file, session_id, session.session_name, logger)
			maybe_rename_session(session, logger)

	if returncode != 0:
		err = (stderr_text or "").strip()[:300]
		logger.log(f"Hermes non-zero exit for {label} ({returncode}): {err}")
		return f"[ERR:hermes_exit_{returncode}]", 0.0

	text = sanitize_hermes_output(stdout_text or "")
	elapsed = (datetime.now() - started).total_seconds()
	logger.log(f"Hermes call done: {label} ({mode}, {elapsed:.1f}s)")
	return text or "[ERR:hermes_empty]", elapsed


def run_hermes(
	prompt: str,
	model: str,
	provider: str,
	logger: TraceLogger,
	label: str,
	session: HermesSessionState,
	raw_response_label: str | None = None,
) -> str:
	text, elapsed = run_hermes_raw(prompt, model, provider, logger, label, session)
	log_text_block(logger, raw_response_label or f"Raw response [{label}]", text, elapsed=elapsed)
	obj = parse_json_object(text)
	result = ""
	if obj and len(obj) == 1:
		val = next(iter(obj.values()))
		if isinstance(val, str):
			out = val.strip()
			result = out if out else "[ERR:hermes_empty]"
	if not result:
		line = text.splitlines()[0].strip() if text else ""
		result = line if line else "[ERR:hermes_empty]"
	return result


def run_area_signal_job(
	task: AreaSignalTask,
	model: str,
	provider: str,
	logger: TraceLogger,
	session: HermesSessionState,
) -> SignalJobResult:
	area_key = task.key
	label = task.label
	area = task.area
	area_prompt = task.area_prompt
	prompt = task.prompt
	if not session.hermes_argv:
		return SignalJobResult(key=area_key, area=None, reason="hermes_unavailable", ok=False)

	if area_key == "shared-goals":
		return run_shared_goals_reflection(task, logger)

	if area_prompt_requests_json(area_prompt):
		response_text, elapsed = run_hermes_raw(prompt, model, provider, logger, label, session)
		log_text_block(logger, f"Raw area response [{label}]", response_text, elapsed=elapsed)
		response_payload, reason = validate_json_response_strict(response_text, area_key)
		second_try_used = False
		if should_retry_area_signal(reason, response_payload):
			logger.log(f"Invalid area signal JSON for {label}: {reason}; starting second try")
			logger.blank_line()
			logger.log(f"Retrying area signal for {label} due to {reason}")
			retry_delta = (
				f"Second try: previous response failed validation with reason '{reason}'. "
				"Return exactly one JSON object only."
			)
			log_text_block(logger, f"Retry prompt delta [{label}:second_try]", retry_delta)
			retry_prompt = f"{prompt}\n\n" + retry_delta
			response_text, elapsed = run_hermes_raw(retry_prompt, model, provider, logger, f"{label}:second_try", session)
			log_text_block(logger, f"Raw area response [{label}:second_try]", response_text, elapsed=elapsed)
			response_payload, reason = validate_json_response_strict(response_text, area_key)
			second_try_used = True
		if not response_payload:
			logger.log(f"Invalid area signal JSON for {label}; reason={reason}")
			return SignalJobResult(key=area_key, area=None, reason=reason, ok=False)
		updated_area = merge_area_signal_response(area, response_payload)
		if not safe_str_key(updated_area, "ts") and safe_str_key(area, "ts"):
			updated_area["ts"] = safe_str_key(area, "ts")
		if second_try_used:
			append_signal_note(updated_area, "(second try)")
		if reason == "valid_with_prose":
			logger.log(f"Accepted JSON for {label} after stripping wrapper prose")
			append_signal_note(updated_area, "(prose stripped)")
		log_json_response(logger, f"Processed area JSON [{label}]", pretty_json(serialize_area_for_llm(updated_area)))
		return SignalJobResult(key=area_key, area=updated_area, reason=reason, ok=True)

	area_signal = run_hermes(prompt, model, provider, logger, label, session, f"Raw area response [{label}]")
	updated_area = hydrate_boundary_area(area)
	updated_area["signal"] = area_signal
	return SignalJobResult(key=area_key, area=updated_area, reason="valid", ok=True)


def run_shared_goals_reflection(task: AreaSignalTask, logger: TraceLogger) -> SignalJobResult:
	"""Reflect once on the hungriest Shared Goal and store the prompt in signal."""
	lines = task.area.get("lines", [])
	if not isinstance(lines, list) or not lines:
		return SignalJobResult(key=task.key, area=None, reason="shared_goals_empty", ok=False)

	def hunger_days(line: dict[str, Any]) -> int:
		match = re.search(r"hunger:(\d+)d", str(line.get("title", "")))
		return int(match.group(1)) if match else -1

	candidates = [line for line in lines if isinstance(line, dict)]
	selected = max(enumerate(candidates), key=lambda item: (hunger_days(item[1]), -item[0]))
	selected_index, selected_line = selected
	goal_title = str(selected_line.get("title", "")).strip()
	goal_body = str(selected_line.get("body", "")).strip()
	query = (
		"Reflect on this Shared Goal and prepare one detailed English prompt for the next "
		"Hermes agent action. Use relevant memories about prior decisions, preferences, "
		"blockers, and current context, but keep the authoritative next steps as the task "
		"boundary. Return only the prompt, without analysis, citations, headings, or summary.\n\n"
		f"Selected goal: {goal_title}\n"
		f"Authoritative next steps:\n{goal_body}"
	)
	logger.log(f"Hindsight reflect start: {goal_title} (hunger={hunger_days(selected_line)}d)")
	try:
		response = run_hermes_hindsight_reflect(query, task, logger)
		try:
			payload = json.loads(response)
		except json.JSONDecodeError:
			payload = {"result": response}
		prompt = str(payload.get("result", payload.get("text", ""))).strip()
		if not prompt or prompt.startswith("[ERROR") or prompt.startswith("{"):
			raise RuntimeError(prompt or "empty reflection")
		prompt = prompt[: task.signal_max_chars].rstrip()
		updated_area = hydrate_boundary_area(task.area)
		updated_lines = [dict(line) for line in candidates]
		updated_lines[selected_index]["signal"] = prompt
		updated_area["lines"] = updated_lines
		logger.log(f"Hindsight reflect done: {len(prompt)} chars")
		return SignalJobResult(key=task.key, area=updated_area, reason="hindsight_reflected", ok=True)
	except Exception as exc:
		logger.log(f"Hindsight reflect failed: {exc}")
		return SignalJobResult(key=task.key, area=None, reason="hindsight_reflect_failed", ok=False)


def run_hermes_hindsight_reflect(query: str, task: AreaSignalTask, logger: TraceLogger) -> str:
	"""Ask Hermes to invoke hindsight_reflect exactly once, then return its result."""
	hermes_argv = resolve_hermes_argv()
	if not hermes_argv:
		raise RuntimeError("Hermes command unavailable")
	request = (
		"Use the `hindsight_reflect` tool exactly once with the query below. "
		"Do not answer from your own reasoning and do not call any other tool. "
		"After the tool returns, output only its result text.\n\n"
		f"{query}"
	)
	cmd = [*hermes_argv, "-t", "memory", "-z", request]
	logger.log("Hermes direct hindsight_reflect request start (toolset=memory)")
	result = run_subprocess_text(cmd, timeout=180, env=os.environ.copy())
	if result.returncode != 0:
		err = (result.stderr or result.stdout).strip()[:500]
		logger.log(f"Hermes direct hindsight_reflect failed: {err}")
		raise RuntimeError(err or "Hermes reflect request failed")
	logger.log("Hermes direct hindsight_reflect request done")
	return sanitize_hermes_output(result.stdout or "")


def build_area_signal_tasks(runtime: CompassContext) -> list[AreaSignalTask]:
	area_meta = runtime.get("area_meta", {}) if isinstance(runtime.get("area_meta"), dict) else {}
	tasks: list[AreaSignalTask] = []
	for index, area in enumerate(runtime.get("areas", [])):
		if not isinstance(area, dict):
			continue
		key = safe_str_key(area, "key")
		meta = area_meta.get(key, {}) if isinstance(area_meta.get(key, {}), dict) else {}
		area_prompt = str(meta.get("area_prompt", "")).strip()
		if not area_prompt:
			continue
		area_copy = hydrate_boundary_area(area)
		area_payload = serialize_area_for_llm(area_copy)
		area_payload["signal_max_chars"] = int(meta.get("signal_max_chars", 50) or 50)
		prompt = build_area_signal_prompt(area_prompt, area_payload)
		label = f"area:{key or 'unknown'}"
		tasks.append(
			AreaSignalTask(
				index=index,
				key=key,
				label=label,
				area=area_copy,
				area_prompt=area_prompt,
				prompt=prompt,
				signal_max_chars=int(meta.get("signal_max_chars", 50) or 50),
			)
		)
	return tasks


def prepare_area_signal_tasks(runtime: CompassContext) -> list[AreaSignalTask]:
	"""Prepare phase-3 area signal queue from current runtime state."""
	return build_area_signal_tasks(runtime)


def execute_area_signal_task(task: AreaSignalTask, context: AreaSignalExecutionContext) -> SignalJobResult:
	"""Execute one area signal task using shared execution context."""
	return run_area_signal_job(task, context.model, context.provider, context.logger, context.session)


def run_area_signal_batch(
	runtime: CompassContext,
	logger: TraceLogger,
	model: str,
	provider: str,
	session: HermesSessionState,
) -> None:
	tasks = prepare_area_signal_tasks(runtime)
	if not tasks:
		return

	context = AreaSignalExecutionContext(model=model, provider=provider, logger=logger, session=session)
	processed = 0
	failed = 0
	logger.log(f"Phase 3 area signal queue prepared: {len(tasks)} prompt(s)")
	for task in tasks:
		result = execute_area_signal_task(task, context)
		if not result.ok or not result.area:
			failed += 1
			logger.log(f"Phase 3 area signal failed: {task.label} ({result.reason})")
			continue
		runtime["areas"][task.index] = result.area
		processed += 1
	logger.log(f"Phase 3 area signal complete: processed={processed}, failed={failed}")


def should_retry_area_signal(reason: str, response_payload: AreaContext | None) -> bool:
	return response_payload is None and reason != "valid"


def append_signal_note(area: BoundaryAreaContext, note: str) -> None:
	note_clean = str(note or "").strip()
	if not note_clean:
		return
	current = str(area.get("signal", "")).strip()
	if note_clean in current:
		return
	if current:
		area["signal"] = f"{current} {note_clean}"
	else:
		area["signal"] = note_clean


def enrich_runtime(runtime: CompassContext, logger: TraceLogger, session: HermesSessionState) -> None:
	model, provider = load_job_model_provider("Daily Compass", logger)
	if session.mode == "oneshot":
		logger.log("Phase 3 session mode: oneshot (no shared chat context between prompts)")
	else:
		logger.log("Phase 3 session mode: chat (shared context across area and compass prompts)")
	run_area_signal_batch(runtime, logger, model, provider, session)

	compass_prompt = runtime.get("signal_prompt", DEFAULT_COMPASS_PROMPT)
	areas_context = []
	for area in runtime["areas"]:
		areas_context.append(serialize_area_for_llm(area))
	prompt = build_compass_signal_prompt(compass_prompt, areas_context)
	runtime["signal"] = run_hermes(prompt, model, provider, logger, "compass", session, "Raw compass response [compass]")


def build_runtime(
	areas: list[AreaConfig],
	skill_index: dict[str, Path],
	logger: TraceLogger,
) -> CompassContext:
	dimensions_order = parse_dimensions_order()
	compass_prompt = resolve_compass_signal_prompt()
	runtime: CompassContext = {
		"signal_prompt": compass_prompt,
		"signal": "",
		"dimensions": list(dimensions_order),
		"areas": [],
		"area_meta": {},
	}

	jobs: list[tuple[AreaConfig, Path, str, str]] = []
	for area in areas:
		skill_dir = skill_index.get(area.skill)
		if not skill_dir:
			logger.log(f"Area '{area.key}': skill '{area.skill}' not found")
			runtime["areas"].append(build_error_area(area, "skill_not_found"))
			continue

		skill_md = skill_dir / "SKILL.md"
		area_prompt = resolve_area_signal_prompt(skill_md)
		script = skill_dir / "scripts" / f"daily-{area.key}-status.py"
		if not script.exists():
			logger.log(f"Area '{area.key}': missing boundary script {script}")
			runtime["areas"].append(build_error_area(area, "boundary_script_missing"))
			runtime["area_meta"][area.key] = {
				"script_to_run": str(script),
				"area_prompt": area_prompt,
				"signal_max_chars": area.signal_max_chars,
			}
			continue

		jobs.append((area, script, area_prompt, str(script)))

	if jobs:
		with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as ex:
			futures = {
				ex.submit(run_boundary_script, area.key, script, BOUNDARY_SCRIPT_TIMEOUT, {
					**os.environ.copy(),
					"DAILY_COMPASS_RUN_ID": logger.path.stem,
					"DAILY_COMPASS_AREA_KEY": area.key,
				}): (area, area_prompt, script_s)
				for (area, script, area_prompt, script_s) in jobs
			}
			for fut in as_completed(futures):
				area, area_prompt, script_s = futures[fut]
				result = fut.result()
				runtime["area_meta"][area.key] = {
					"script_to_run": script_s,
					"area_prompt": area_prompt,
					"signal_max_chars": area.signal_max_chars,
				}
				logger.log(f"Run boundary: {area.key} -> {script_s}")
				logger.log(f"Area log: {LOGS_DIR / f'{logger.path.stem}.{area.key}.log'}")
				if not result.ok:
					runtime["areas"].append(build_error_area(area, result.stderr or "boundary_failed"))
					continue
				boundary_area = hydrate_boundary_area(result.payload)
				# Boundary scripts return minimal payload; metadata comes from YAML area config.
				boundary_area["name"] = area.name
				boundary_area["key"] = area.key
				boundary_area["dimension"] = choose_primary_dimension(area.dimensions)
				runtime["areas"].append(boundary_area)

	runtime["areas"].sort(key=lambda a: a["name"].lower())
	return runtime


def dimension_meta(dim: str) -> tuple[str, str]:
	if dim == "faith":
		return "🙏", "FAITH"
	if dim == "will":
		return "💪", "WILL"
	if dim == "feeling":
		return "🫶", "FEELING"
	if dim == "mind":
		return "🧠", "MIND"
	return "•", dim.upper()


def build_render_context(runtime: CompassContext) -> dict[str, Any]:
	order = runtime.get("dimensions", DEFAULT_DIMENSIONS)
	areas = runtime["areas"]
	grouped: dict[str, list[dict[str, Any]]] = {dim: [] for dim in order}
	for area in areas:
		dim = area.get("dimension", DEFAULT_DIMENSIONS[0])
		if dim not in grouped:
			grouped[dim] = []
		grouped[dim].append(area)

	dimensions_out: list[dict[str, Any]] = []
	for dim in order:
		emoji, name = dimension_meta(dim)
		dim_areas: list[dict[str, Any]] = []
		for area in grouped.get(dim, []):
			dim_areas.append(
				{
					"name": area["name"],
					"key": area.get("key", ""),
					"signal": area.get("signal", ""),
					"lines": [
						{
							**line,
							"display_signal": (
								"**> "
								+ line.get("signal", "").strip().replace("\n", "\n> ")
								+ "||"
								if area.get("key") == "shared-goals" and line.get("signal", "").strip()
								else f"*{line.get('signal', '')}*" if line.get("signal", "").strip() else ""
							),
						}
						for line in area.get("lines", [])
						if isinstance(line, dict)
					],
				}
			)
		dimensions_out.append({"emoji": emoji, "NAME": name, "areas": dim_areas})

	now = datetime.now()
	return {
		"weekday": now.strftime("%A"),
		"date": f"{now.strftime('%B')} {now.day}, {now.year}",
		"compass": {"signal": runtime.get("signal", "")},
		"dimensions": dimensions_out,
	}


def load_template() -> str:
	text = TEMPLATE_FILE.read_text(encoding="utf-8")
	sep = "\n---\n"
	if sep in text:
		text = text[text.index(sep) + len(sep) :]
	return text.strip()


def tpl_resolve(ctx: Any, path: str) -> Any:
	val = ctx
	for part in path.split("."):
		if isinstance(val, dict):
			val = val.get(part)
		else:
			return ""
		if val is None:
			return ""
	return val


def tpl_tokenize(text: str) -> list[tuple[str, Any]]:
	tokens: list[tuple[str, Any]] = []
	i = 0
	while i < len(text):
		j = text.find("{", i)
		if j == -1:
			if i < len(text):
				tokens.append(("TEXT", text[i:]))
			break
		if j > i:
			tokens.append(("TEXT", text[i:j]))
		k = text.find("}", j + 1)
		if k == -1:
			tokens.append(("TEXT", text[j:]))
			break
		tag = text[j + 1 : k].strip()
		if tag.startswith("foreach "):
			m = re.match(r"foreach\s+(\w+)\s+in\s+(\S+)", tag)
			tokens.append(("FOREACH", (m.group(1), m.group(2))) if m else ("TEXT", text[j : k + 1]))
		elif tag == "/foreach":
			tokens.append(("ENDFOREACH", ""))
		elif tag.startswith("if "):
			tokens.append(("IF", tag[3:].strip()))
		elif tag == "/if":
			tokens.append(("ENDIF", ""))
		elif tag == "else":
			tokens.append(("ELSE", ""))
		else:
			tokens.append(("VAR", tag))
		i = k + 1
	return tokens


def tpl_render(tokens: list[tuple[str, Any]], pos: int, ctx: dict[str, Any]) -> tuple[str, int]:
	out: list[str] = []
	while pos < len(tokens):
		typ, val = tokens[pos]
		if typ == "TEXT":
			out.append(val)
			pos += 1
		elif typ == "VAR":
			out.append(str(tpl_resolve(ctx, val)))
			pos += 1
		elif typ == "IF":
			cond = bool(tpl_resolve(ctx, val))
			pos += 1
			t_out, pos = tpl_render(tokens, pos, ctx)
			f_out = ""
			if pos < len(tokens) and tokens[pos][0] == "ELSE":
				pos += 1
				f_out, pos = tpl_render(tokens, pos, ctx)
			if pos < len(tokens) and tokens[pos][0] == "ENDIF":
				pos += 1
			out.append(t_out if cond else f_out)
		elif typ == "FOREACH":
			var_name, coll_path = val
			coll = tpl_resolve(ctx, coll_path)
			pos += 1
			body: list[tuple[str, Any]] = []
			depth = 0
			while pos < len(tokens):
				t, v = tokens[pos]
				if t == "FOREACH":
					depth += 1
				elif t == "ENDFOREACH":
					if depth == 0:
						pos += 1
						break
					depth -= 1
				body.append((t, v))
				pos += 1
			if isinstance(coll, list):
				for item in coll:
					sub = dict(ctx)
					sub[var_name] = item
					rendered, _ = tpl_render(body, 0, sub)
					out.append(rendered)
		elif typ in {"ELSE", "ENDIF", "ENDFOREACH"}:
			break
		else:
			pos += 1
	return "".join(out), pos


def render_template(context: dict[str, Any]) -> str:
	tokens = tpl_tokenize(load_template())
	out, _ = tpl_render(tokens, 0, context)
	out = re.sub(r"\n{3,}", "\n\n", out)
	return out.strip() + "\n"


def parse_args() -> argparse.Namespace:
	p = argparse.ArgumentParser(description="Shared Goals Daily Compass")
	p.add_argument("areas", nargs="*", help="Optional area keys, e.g. weather news")
	p.add_argument("--verbose", action="store_true", help="Print trace to stdout")
	p.add_argument("--fast", action="store_true", help="Skip signal phase")
	p.add_argument(
		"--session-title",
		default=DEFAULT_SESSION_TITLE,
		help="Stable Hermes session title used for Daily Compass runs",
	)
	p.add_argument(
		"--session-state-file",
		default=str(SESSION_STATE_FILE),
		help="Path to JSON state file that stores persistent Daily Compass session_id",
	)
	p.add_argument(
		"--session-mode",
		choices=["chat", "oneshot"],
		default="chat",
		help="Hermes invocation mode: chat reuses one session during this run",
	)
	return p.parse_args()


def main() -> int:
	args = parse_args()
	logger = TraceLogger(verbose=args.verbose)
	orig_stdout = sys.stdout
	orig_stderr = sys.stderr
	if args.verbose:
		sys.stdout = TeeStream(orig_stdout, logger)
		sys.stderr = TeeStream(orig_stderr, logger)
	logger.log("daily-compass start")
	session = HermesSessionState(
		mode=args.session_mode,
		hermes_argv=resolve_hermes_argv(),
		chat_argv=resolve_chat_argv(),
		session_name=str(args.session_title or DEFAULT_SESSION_TITLE).strip() or DEFAULT_SESSION_TITLE,
		session_state_file=Path(str(args.session_state_file)).expanduser(),
		rename_needed=args.session_mode == "chat",
	)
	if session.mode == "chat":
		logger.log("Hermes session mode: chat (single session for this run)")
		restored_session_id = load_persistent_session_id(session.session_state_file, logger)
		if restored_session_id:
			session.session_id = restored_session_id
			logger.log(f"Restored persistent session id: {restored_session_id}")
		else:
			logger.log("No persistent session id found; Daily Compass will create a new one")
	else:
		logger.log("Hermes session mode: oneshot")
	if not session.hermes_argv:
		logger.log("Hermes binary resolution failed")
	if session.mode == "chat" and not session.chat_argv and not session.hermes_argv:
		logger.log("Hermes chat command resolution failed")

	def log_phase(title: str) -> None:
		if args.verbose:
			print_phase(title)
		else:
			logger.write_chunk("\n")
			logger.write_chunk("=" * 12 + f" {title} " + "=" * 12 + "\n\n")

	def log_block(text: str) -> None:
		if args.verbose:
			print(text, end="")
		else:
			logger.write_chunk(text)

	def log_line(text: str) -> None:
		logger.output(text)

	try:
		log_phase(PHASE_BOUNDARY)
		skill_index = build_skill_index(HERMES_SKILLS_DIR)
		areas = load_areas(args.areas, logger)
		runtime = build_runtime(areas, skill_index, logger)
		validate_runtime_or_raise(runtime)
		
		script_chunks: list[str] = ["\n"]
		for area in runtime["areas"]:
			script_chunks.append(f"Area JSON [{area.get('key', 'unknown')}]:\n")
			script_chunks.append(json.dumps(area, ensure_ascii=False, indent=2) + "\n\n")
		log_block("".join(script_chunks))

		if args.fast:
			log_phase(PHASE_PROMPTS)
			if args.verbose:
				print_prompt_preview(runtime)
			else:
				logger.write_chunk("Generated signal prompts\n\n")
				emit_generated_prompts(runtime, log_line)
			logger.log("fast mode: signal requests skipped")
		else:
			log_phase(PHASE_PROMPTS)
			if args.verbose:
				print_prompt_preview(runtime)
			else:
				logger.write_chunk("Generated signal prompts\n\n")
				emit_generated_prompts(runtime, log_line)

		log_phase(PHASE_SIGNAL)
		if args.fast:
			log_block("Skipped in fast mode: Phase 3 runs hermes requests and JSON processing only in compass-run.\n")
		else:
			logger.log("phase 3 signal requests start")
			enrich_runtime(runtime, logger, session)
			validate_runtime_or_raise(runtime)

		save_json_snapshot(COMPASS_CONTEXT_STATE_FILE, runtime_json_snapshot(runtime), logger)

		log_phase(PHASE_RENDER)
		context = build_render_context(runtime)
		markdown = render_template(context)
		if args.verbose:
			print_render_separator()
		print(markdown, end="")
		if args.verbose:
			print_render_separator()
			print_phase(PHASE_FINAL)
		else:
			logger.write_chunk("\n")
			logger.write_chunk(markdown)
			if not markdown.endswith("\n"):
				logger.write_chunk("\n")
			logger.write_chunk("\n")
			logger.write_chunk("=" * 12 + f" {PHASE_FINAL} " + "=" * 12 + "\n\n")
		logger.log("render complete")
		return 0
	except ValueError as exc:
		logger.log(f"runtime schema error: {exc}")
		fallback = {
			"weekday": datetime.now().strftime("%A"),
			"date": f"{datetime.now().strftime('%B')} {datetime.now().day}, {datetime.now().year}",
			"compass": {"signal": ""},
			"dimensions": [
				{
					"emoji": "⚠️",
					"NAME": "ERROR",
					"areas": [
						{
							"name": "Daily Compass",
							"signal": "",
							"lines": [{"title": "Schema error", "url": "", "body": str(exc), "signal": ""}],
						}
					],
				}
			],
		}
		print(render_template(fallback), end="")
		return 1
	finally:
		if args.verbose:
			print_render_separator()
			print(f"[daily-compass] log written: {logger.path}")
		sys.stdout = orig_stdout
		sys.stderr = orig_stderr
		logger.write()


if __name__ == "__main__":
	raise SystemExit(main())
