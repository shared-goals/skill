#!/usr/bin/env python3
"""Area compatibility test runner for Shared Goals Daily Compass.

Usage:
  area-test.py <area>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
HOME = Path.home()
HERMES_SKILLS_DIR = HOME / ".hermes" / "skills"
SHARED_GOALS_DIR = HERMES_SKILLS_DIR / "shared-goals" / "shared-goals"
SHARED_GOALS_SCRIPTS_DIR = SHARED_GOALS_DIR / "scripts"
AREA_REFS_DIR = SHARED_GOALS_DIR / "references"

if str(SHARED_GOALS_SCRIPTS_DIR) not in sys.path:
	sys.path.insert(0, str(SHARED_GOALS_SCRIPTS_DIR))

from daily_compass_shared import (
	ACTION_VERBS,
	COMMON_JSON_CONTRACT_PHRASES,
	VALID_DIMENSIONS,
	extract_section,
	find_skill_dir,
	is_valid_area_context,
	is_valid_boundary_area_context,
	is_valid_line_context,
	project_boundary_to_area_context,
	parse_inline_list,
	parse_top_level_yaml,
	run_boundary_script,
)


@dataclass
class CheckResult:
	name: str
	ok: bool
	detail: str
	group: str


DAILY_COMPASS_MODULE_PATH = SHARED_GOALS_SCRIPTS_DIR / "daily-compass.py"


def checkmark(ok: bool) -> str:
	return "PASS" if ok else "FAIL"


def clean_block(text: str) -> str:
	lines = [line.rstrip() for line in text.splitlines()]
	return "\n".join(line for line in lines if line.strip())


def check_signal_guidance_duplication(area_guidance_section: str) -> tuple[bool, str]:
	"""Check that area signal guidance doesn't duplicate common JSON contract phrases."""
	area_lower = area_guidance_section.lower()
	found = [p for p in COMMON_JSON_CONTRACT_PHRASES if p in area_lower]
	if found:
		return False, f"duplicates common contract: {', '.join(repr(p) for p in found)}"
	return True, "no duplication with common contract"


def check_signal_guidance_enumeration(area_guidance_section: str) -> tuple[bool, str]:
	"""Require area signal guidance to use actionable, enumerated steps (1., 2., ...)."""
	lines = [ln.strip() for ln in area_guidance_section.splitlines() if ln.strip()]
	step_nums: list[int] = []
	for ln in lines:
		m = re.match(r"^(\d+)\.\s+", ln)
		if m:
			step_nums.append(int(m.group(1)))

	if not step_nums:
		return False, "missing enumerated steps (expected lines like '1. ...')"

	if step_nums[0] != 1:
		return False, f"enumeration must start at 1 (found start={step_nums[0]})"

	expected = list(range(1, len(step_nums) + 1))
	if step_nums != expected:
		return False, f"non-sequential enumeration (found={step_nums}, expected={expected})"

	return True, f"sequential enumeration found: {step_nums}"


def check_signal_directive_verbs(area_guidance_section: str) -> tuple[bool, str]:
	"""Require each enumerated step to start with a concrete action verb."""
	lines = [ln.strip() for ln in area_guidance_section.splitlines() if ln.strip()]
	bad: list[str] = []
	for ln in lines:
		m = re.match(r"^(\d+)\.\s+([A-Za-z][A-Za-z-]*)\b", ln)
		if not m:
			continue
		verb = m.group(2).lower()
		if verb not in ACTION_VERBS:
			bad.append(f"{m.group(1)}:{verb}")

	if bad:
		verbs = ", ".join(sorted(ACTION_VERBS))
		return False, f"steps must start with allowed action verbs ({verbs}); found invalid: {', '.join(bad)}"

	return True, "all enumerated steps start with allowed action verbs"


def check_signal_scope_addresses(area_guidance_section: str) -> tuple[bool, str]:
	"""Require explicit signal scope references (AreaContext/LineContext) and reject ambiguous wording."""
	lines = [ln.strip() for ln in area_guidance_section.splitlines() if ln.strip()]
	ambiguous: list[str] = []
	has_area_context_signal = False
	has_line_context_signal = False

	for ln in lines:
		low = ln.lower()
		if "areacontext `signal`" in low:
			has_area_context_signal = True
		if "linecontext `signal`" in low:
			has_line_context_signal = True
		if "`signal`" in ln and "AreaContext `signal`" not in ln and "LineContext `signal`" not in ln:
			ambiguous.append(ln)

	if ambiguous:
		return False, "ambiguous `signal` references; use explicit `AreaContext `signal`` or `LineContext `signal``: " + " | ".join(ambiguous)

	if not has_area_context_signal:
		return False, "missing explicit `AreaContext `signal`` reference"
	if not has_line_context_signal:
		return False, "missing explicit `LineContext `signal`` reference"

	return True, "signal references are explicitly scoped to AreaContext/LineContext"


def add_check(checks: list[CheckResult], name: str, ok: bool, detail: str, group: str) -> None:
	checks.append(CheckResult(name=name, ok=ok, detail=detail, group=group))


def load_daily_compass_module() -> object:
	spec = importlib.util.spec_from_file_location("daily_compass_module_for_area_test", DAILY_COMPASS_MODULE_PATH)
	if spec is None or spec.loader is None:
		raise RuntimeError(f"failed to load daily-compass module from {DAILY_COMPASS_MODULE_PATH}")
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)  # type: ignore[attr-defined]
	return module


def run_runtime_preflight_tests() -> tuple[bool, str]:
	"""Run daily-compass unit tests before area-specific checks."""
	test_script = SHARED_GOALS_SCRIPTS_DIR / "test_daily_compass.py"
	if not test_script.exists():
		return False, f"missing test script: {test_script}"
	try:
		proc = subprocess.run(
			[sys.executable, str(test_script)],
			capture_output=True,
			text=True,
			timeout=120,
		)
	except subprocess.TimeoutExpired:
		return False, "test_daily_compass timeout"
	if proc.returncode != 0:
		out = (proc.stdout or "").strip()
		err = (proc.stderr or "").strip()
		detail = err or out or "test_daily_compass failed"
		return False, detail.splitlines()[-1]

	combined = "\n".join([proc.stdout or "", proc.stderr or ""])
	lines = [ln.strip() for ln in combined.splitlines() if ln.strip()]
	test_rows = [ln for ln in lines if ln.startswith("test_") and " ... " in ln]
	test_names = [ln.split(" ... ", 1)[0] for ln in test_rows]
	ran_line = next((ln for ln in lines if ln.startswith("Ran ")), "")
	ok_line = next((ln for ln in reversed(lines) if ln == "OK"), "OK")
	if test_names:
		return True, f"{ran_line or 'Ran tests'}; {ok_line}; tests: {', '.join(test_names)}"
	if ran_line:
		return True, f"{ran_line}; {ok_line}"
	return True, "runtime tests passed"


def collect_area_test_checks(area_key: str) -> list[CheckResult]:
	area_file = AREA_REFS_DIR / f"{area_key}.yaml"
	checks: list[CheckResult] = []

	preflight_ok, preflight_detail = run_runtime_preflight_tests()
	add_check(checks, "daily_compass_unit_tests", preflight_ok, preflight_detail, "preflight")
	if not preflight_ok:
		return checks

	exists = area_file.exists()
	add_check(checks, "yaml_exists", exists, str(area_file), "skill")
	if not exists:
		return checks

	cfg = parse_top_level_yaml(area_file)
	name_val = cfg.get("name", "").strip()
	dims = parse_inline_list(cfg.get("dimensions", "[]"))
	skill_name = cfg.get("skill", "").strip()
	status = cfg.get("status", "").strip()

	add_check(checks, "yaml_name", bool(name_val), name_val or "missing", "skill")
	add_check(checks, "yaml_dimensions", bool(dims), str(dims), "skill")
	add_check(checks, "yaml_dimensions_valid", all(d in VALID_DIMENSIONS for d in dims), str(dims), "skill")
	add_check(checks, "yaml_status", status in {"active", "TBD"}, status or "missing", "skill")
	add_check(checks, "yaml_skill", bool(skill_name), skill_name or "missing", "skill")

	skill_dir = find_skill_dir(skill_name, HERMES_SKILLS_DIR) if skill_name else None
	add_check(checks, "skill_found", skill_dir is not None, str(skill_dir) if skill_dir else "not found", "skill")

	skill_text = ""
	if skill_dir:
		daily_compass_module = load_daily_compass_module()
		skill_md = skill_dir / "SKILL.md"
		if skill_md.exists():
			skill_text = skill_md.read_text(encoding="utf-8", errors="replace")
		area_sec = extract_section(skill_text, "Area signal")
		line_sec = extract_section(skill_text, "Line signal") or extract_section(skill_text, "Line signal (optional)")
		area_signal_guidance_ok = bool(area_sec)
		area_signal_guidance_detail = clean_block(area_sec) if area_sec else "missing"
		if area_sec:
			enum_ok, enum_detail = check_signal_guidance_enumeration(area_sec)
			add_check(checks, "area_signal_guidance_enumerated", enum_ok, enum_detail, "signal_guidance")
			verb_ok, verb_detail = check_signal_directive_verbs(area_sec)
			add_check(checks, "area_signal_directive_verbs", verb_ok, verb_detail, "signal_guidance")
			scope_ok, scope_detail = check_signal_scope_addresses(area_sec)
			add_check(checks, "area_signal_scope_addresses", scope_ok, scope_detail, "signal_guidance")
		else:
			add_check(checks, "area_signal_guidance_enumerated", False, "missing area signal section", "signal_guidance")
			add_check(checks, "area_signal_directive_verbs", False, "missing area signal section", "signal_guidance")
			add_check(checks, "area_signal_scope_addresses", False, "missing area signal section", "signal_guidance")
		add_check(checks, "line_signal_section_removed", not bool(line_sec), clean_block(line_sec) if line_sec else "absent", "signal_guidance")
		
		# Check for duplication with common contract
		if area_sec:
			dup_ok, dup_detail = check_signal_guidance_duplication(area_sec)
			add_check(checks, "area_signal_guidance_no_duplication", dup_ok, dup_detail, "signal_guidance")

		boundary = skill_dir / "scripts" / f"daily-{area_key}-status.py"
		add_check(checks, "boundary_exists", boundary.exists(), str(boundary), "infrastructure")

		if boundary.exists():
			result = run_boundary_script(area_key, boundary, 60, os.environ.copy())
			add_check(checks, "boundary_exec", result.ok, f"exit={result.returncode}", "infrastructure")
			if not result.ok:
				add_check(checks, "boundary_area_context_validated", False, "invalid AreaContext JSON", "infrastructure")
			if result.ok:
				payload = result.payload
				key_match = str(payload.get("key", "")).strip() == area_key
				add_check(checks, "boundary_key_match", key_match, str(payload.get("key", "")), "infrastructure")
				name_match = str(payload.get("name", "")).strip() == name_val
				add_check(checks, "boundary_name_match", name_match, str(payload.get("name", "")), "infrastructure")
				dim = str(payload.get("dimension", "")).strip()
				dim_ok = dim in dims if dims else dim in VALID_DIMENSIONS
				add_check(checks, "boundary_dimension_match", dim_ok, dim or "missing", "infrastructure")
				status_val = str(payload.get("status", "")).strip()
				status_ok = status_val in {"ok", "TBD", "error"}
				add_check(checks, "boundary_status_valid", status_ok, status_val or "missing", "infrastructure")
				lines = payload.get("lines", [])

				boundary_candidate = {
					"name": str(payload.get("name", "")),
					"key": str(payload.get("key", "")),
					"dimension": str(payload.get("dimension", "")),
					"status": str(payload.get("status", "")),
					"reason": str(payload.get("reason", "")),
					"signal": str(payload.get("signal", "")),
					"lines": [
						{
							"title": str(x.get("title", "")),
							"url": str(x.get("url", "")),
							"body": str(x.get("body", "")),
							"signal": str(x.get("signal", "")),
						}
						for x in (lines if isinstance(lines, list) else [])
					],
				}
				boundary_ctx_ok = is_valid_boundary_area_context(boundary_candidate, area_key)
				projected_area = project_boundary_to_area_context(boundary_candidate)
				area_ctx_ok = is_valid_area_context(projected_area, area_key)
				line_ctx_ok = all(is_valid_line_context(x) for x in projected_area["lines"])
				add_check(checks, "boundary_area_context_validated", boundary_ctx_ok, "BoundaryAreaContext JSON + strict schema", "infrastructure")
				add_check(checks, "boundary_to_area_projection", area_ctx_ok, "BoundaryAreaContext -> AreaContext projection schema", "infrastructure")
				add_check(checks, "boundary_line_context_schema", line_ctx_ok, f"LineContext strict schema; lines={len(projected_area['lines'])}", "infrastructure")
				if area_sec:
					area_signal_guidance_detail = daily_compass_module.build_area_signal_prompt(area_sec, projected_area)

		add_check(checks, "area_signal_guidance_section", area_signal_guidance_ok, area_signal_guidance_detail, "signal_guidance")

	return checks


def render_area_test_checks(checks: list[CheckResult]) -> None:
	def print_group(title: str, group_name: str, render_multiline: bool = False) -> None:
		rows = [check for check in checks if check.group == group_name]
		if not rows:
			return
		print(title)
		print("")
		for check in rows:
			if render_multiline and isinstance(check.detail, str) and "\n" in check.detail:
				print(f"{checkmark(check.ok)} {check.name}:")
				print("")
				for line in check.detail.splitlines():
					print(line)
				print("")
			else:
				print(f"{checkmark(check.ok)} {check.name}: {check.detail}")
		print("")

	print_group("PREFLIGHT:", "preflight")
	print_group("SKILL:", "skill")
	print_group("INFRASTRUCTURE:", "infrastructure", render_multiline=True)
	print_group("SIGNAL GUIDANCE:", "signal_guidance", render_multiline=True)


def run() -> int:
	parser = argparse.ArgumentParser(description="Test area compatibility with daily-compass")
	parser.add_argument("area", help="Area key, e.g. weather")
	args = parser.parse_args()

	area_key = args.area.strip().lower()
	checks = collect_area_test_checks(area_key)
	render_area_test_checks(checks)
	return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
	raise SystemExit(run())
