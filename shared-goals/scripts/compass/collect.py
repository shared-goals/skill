"""Run area boundary scripts in parallel and turn their output into immutable Evidence."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from daily_compass_shared import BOUNDARY_SCRIPT_TIMEOUT_SECONDS, parse_json_object
from pydantic import ValidationError

from compass.models import AreaConfig, BoundaryPayload, Evidence, Line

MAX_WORKERS = 4


class BoundaryError(RuntimeError):
    """A boundary run failed; the message is the area's error reason."""


def boundary_script(skill_dir: Path, area_key: str) -> Path:
    return skill_dir / "scripts" / f"daily-{area_key}-status.py"


def run_boundary(
    script: Path, *, timeout: int = BOUNDARY_SCRIPT_TIMEOUT_SECONDS, env: Mapping[str, str] | None = None
) -> BoundaryPayload:
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=dict(env) if env is not None else None,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BoundaryError("boundary_timeout") from exc
    except OSError as exc:
        raise BoundaryError(f"boundary_exec_failed: {exc}") from exc
    if proc.returncode != 0:
        raise BoundaryError((proc.stderr or "").strip()[:400] or f"boundary_exit_{proc.returncode}")
    data = parse_json_object(proc.stdout or "")
    if data is None:
        raise BoundaryError("boundary_non_json")
    try:
        return BoundaryPayload.model_validate(data)
    except ValidationError as exc:
        raise BoundaryError("boundary_schema_invalid") from exc


def _evidence(area: AreaConfig, status: str, reason: str, lines: tuple[Line, ...] = ()) -> Evidence:
    return Evidence(
        key=area.key,
        name=area.name,
        dimension=area.dimension,
        status=status,
        reason=reason,
        lines=lines,
        signal_max_chars=area.signal_max_chars,
    )


def collect_area(area: AreaConfig, skill_dir: Path | None, *, timeout: int, env: Mapping[str, str]) -> Evidence:
    if skill_dir is None:
        return _evidence(area, "error", "skill_not_found")
    script = boundary_script(skill_dir, area.key)
    if not script.exists():
        return _evidence(area, "error", "boundary_script_missing")
    try:
        payload = run_boundary(script, timeout=timeout, env=env)
    except BoundaryError as exc:
        return _evidence(area, "error", str(exc))
    return _evidence(area, payload.status, payload.reason, payload.lines)


def collect_areas(
    areas: list[AreaConfig],
    skill_index: Mapping[str, Path],
    *,
    run_id: str,
    log: Callable[[str], None],
    timeout: int = BOUNDARY_SCRIPT_TIMEOUT_SECONDS,
) -> list[Evidence]:
    """One area failing never affects the others; results are sorted by area name."""

    def run_one(area: AreaConfig) -> Evidence:
        env = {**os.environ, "DAILY_COMPASS_RUN_ID": run_id, "DAILY_COMPASS_AREA_KEY": area.key}
        evidence = collect_area(area, skill_index.get(area.skill), timeout=timeout, env=env)
        log(f"Boundary {area.key}: {evidence.status}" + (f" ({evidence.reason})" if evidence.reason else ""))
        return evidence

    if not areas:
        return []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(areas))) as pool:
        results = list(pool.map(run_one, areas))
    return sorted(results, key=lambda evidence: evidence.name.lower())
