#!/usr/bin/env python3
"""Shared helpers for Daily Compass runtime and area contract tests."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict


VALID_DIMENSIONS = {"faith", "will", "feeling", "mind"}

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
	"LineContext `signal` is not more than 50 chars.",
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
class BoundaryExecResult:
	ok: bool
	returncode: int
	stdout: str
	stderr: str
	payload: dict[str, Any]
	timed_out: bool = False


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
	areas: list[BoundaryAreaContext]
	area_meta: dict[str, dict[str, str]]


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


def parse_top_level_yaml(path: Path) -> dict[str, str]:
	data: dict[str, str] = {}
	for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
		line = raw.strip()
		if not line or line.startswith("#") or line.startswith("-"):
			continue
		m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
		if not m:
			continue
		key = m.group(1)
		value = m.group(2).strip()
		if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
			value = value[1:-1]
		data[key] = value
	return data


def parse_inline_list(value: str) -> list[str]:
	v = value.strip()
	if not (v.startswith("[") and v.endswith("]")):
		return []
	inner = v[1:-1].strip()
	if not inner:
		return []
	out: list[str] = []
	for item in inner.split(","):
		d = item.strip().strip('"').strip("'")
		if d:
			out.append(d)
	return out


def parse_frontmatter_name(skill_md: Path) -> str | None:
	text = skill_md.read_text(encoding="utf-8", errors="replace")
	if not text.startswith("---\n"):
		return None
	end = text.find("\n---", 4)
	if end < 0:
		return None
	for raw in text[4:end].splitlines():
		m = re.match(r"^name:\s*(.+)$", raw.strip())
		if m:
			return m.group(1).strip().strip('"').strip("'")
	return None


def find_skill_dir(skill_name: str, skills_root: Path) -> Path | None:
	for md in skills_root.glob("**/SKILL.md"):
		if parse_frontmatter_name(md) == skill_name:
			return md.parent
	return None


def build_skill_index(skills_root: Path) -> dict[str, Path]:
	index: dict[str, Path] = {}
	for skill_md in skills_root.glob("**/SKILL.md"):
		name = parse_frontmatter_name(skill_md)
		if name and name not in index:
			index[name] = skill_md.parent
	return index


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


def is_valid_boundary_area_context(payload: dict[str, Any], expected_key: str = "") -> bool:
	if set(payload.keys()) != {"name", "key", "dimension", "status", "reason", "signal", "lines"}:
		return False

	if not is_valid_area_context(
		{
			"name": payload.get("name", ""),
			"key": payload.get("key", ""),
			"dimension": payload.get("dimension", ""),
			"signal": payload.get("signal", ""),
			"lines": payload.get("lines", []),
		},
		expected_key,
	):
		return False

	status = str(payload.get("status", "")).strip()
	reason = payload.get("reason")
	if status not in {"ok", "TBD", "error"}:
		return False
	if not isinstance(reason, str):
		return False
	return True


def is_valid_boundary_area_payload(payload: dict[str, Any], expected_key: str = "") -> bool:
	allowed_keys = {"name", "key", "dimension", "status", "reason", "signal", "lines", "ts"}
	if not set(payload.keys()).issubset(allowed_keys):
		return False
	for required in ("name", "key", "dimension", "status", "reason", "lines"):
		if required not in payload:
			return False

	key = str(payload.get("key", "")).strip()
	name = str(payload.get("name", "")).strip()
	dimension = str(payload.get("dimension", "")).strip()
	status = str(payload.get("status", "")).strip()
	reason = payload.get("reason")
	lines = payload.get("lines")

	if expected_key and key != expected_key:
		return False
	if not key:
		return False
	if not name:
		return False
	if dimension not in VALID_DIMENSIONS:
		return False
	if status not in {"ok", "TBD", "error"}:
		return False
	if not isinstance(reason, str):
		return False
	if not isinstance(lines, list):
		return False

	for line in lines:
		if not isinstance(line, dict):
			return False
		title = str(line.get("title", "")).strip()
		if not title:
			return False
		for optional_key in ("url", "body", "signal"):
			if optional_key in line and not isinstance(line.get(optional_key), str):
				return False
	if "ts" in payload and not isinstance(payload.get("ts"), str):
		return False
	if "signal" in payload and not isinstance(payload.get("signal"), str):
		return False
	return True


def run_boundary_script(area_key: str, script: Path, timeout: int = 60, env: dict[str, str] | None = None) -> BoundaryExecResult:
	try:
		proc = subprocess.run(
			[sys.executable, str(script)],
			capture_output=True,
			text=True,
			timeout=timeout,
			env=env,
		)
	except subprocess.TimeoutExpired:
		return BoundaryExecResult(ok=False, returncode=124, stdout="", stderr="boundary_timeout", payload={}, timed_out=True)

	if proc.returncode != 0:
		reason = (proc.stderr or "boundary_exec_failed").strip()[:400]
		return BoundaryExecResult(ok=False, returncode=proc.returncode, stdout=proc.stdout or "", stderr=reason or "boundary_exec_failed", payload={})

	payload = parse_json_object(proc.stdout or "")
	if not payload:
		return BoundaryExecResult(ok=False, returncode=proc.returncode, stdout=proc.stdout or "", stderr="boundary_non_json", payload={})

	if not is_valid_boundary_area_payload(payload, area_key):
		return BoundaryExecResult(ok=False, returncode=proc.returncode, stdout=proc.stdout or "", stderr="boundary_schema_invalid", payload=payload)

	return BoundaryExecResult(ok=True, returncode=proc.returncode, stdout=proc.stdout or "", stderr=proc.stderr or "", payload=payload)


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
