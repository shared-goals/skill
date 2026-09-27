"""Load area configs and the skill index from YAML."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from compass.models import AreaConfig


def read_frontmatter(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    try:
        meta = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


def build_skill_index(skills_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for skill_md in sorted(skills_root.glob("**/SKILL.md")):
        name = str(read_frontmatter(skill_md).get("name") or "").strip()
        if name and name not in index:
            index[name] = skill_md.parent
    return index


def load_area_config(path: Path) -> AreaConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("area file is not a mapping")
    return AreaConfig.model_validate({"name": path.stem, **raw, "key": path.stem})


def load_active_areas(areas_dir: Path, selected: list[str], log: Callable[[str], None]) -> list[AreaConfig]:
    wanted = {item.strip().lower() for item in selected if item.strip()}
    areas: list[AreaConfig] = []
    for path in sorted(areas_dir.glob("*.yaml")):
        if wanted and path.stem.lower() not in wanted:
            continue
        try:
            area = load_area_config(path)
        except (ValidationError, ValueError, yaml.YAMLError) as exc:
            log(f"Skip area '{path.stem}': {exc}")
            continue
        if area.status == "active":
            areas.append(area)
    log(f"Loaded {len(areas)} active areas")
    return areas
