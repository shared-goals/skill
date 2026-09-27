#!/usr/bin/env python3
"""Contract tests for compass.models and compass.config (T-CON-2..4)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from compass.config import build_skill_index, load_active_areas
from compass.models import AreaAdvice, Evidence, Line, SourceRef


def _evidence(**overrides) -> Evidence:
    data = {
        "key": "photo",
        "name": "Photos",
        "dimension": "feeling",
        "status": "ok",
        "reason": "",
        "lines": (Line(title="Album", url="https://example.com/a", body="20 new photos", signal=""),),
        "signal_max_chars": 80,
    }
    return Evidence(**{**data, **overrides})


def _advice(signal: str = "Pick five photos.", refs=(("line", "photo:0"),)) -> AreaAdvice:
    return AreaAdvice(area="photo", signal=signal, source_refs=tuple(SourceRef(kind=k, id=i) for k, i in refs))


# T-CON-2 ---------------------------------------------------------------------


def test_advice_requires_source_refs() -> None:
    with pytest.raises(ValidationError):
        AreaAdvice(area="photo", signal="Pick five photos.", source_refs=())


def test_advice_with_known_line_and_memory_refs_is_accepted() -> None:
    _evidence().check_advice(_advice(refs=(("line", "photo:0"), ("memory", "mem-1"))), memory_ids=frozenset({"mem-1"}))


@pytest.mark.parametrize("refs", [(("line", "photo:1"),), (("memory", "mem-unknown"),), (("line", "news:0"),)])
def test_advice_with_unknown_refs_is_rejected(refs) -> None:
    with pytest.raises(ValueError, match="unknown source_refs"):
        _evidence().check_advice(_advice(refs=refs), memory_ids=frozenset({"mem-1"}))


def test_advice_over_signal_limit_is_rejected() -> None:
    evidence = _evidence()
    with pytest.raises(ValueError, match="exceeds"):
        evidence.check_advice(_advice(signal="x" * (evidence.signal_max_chars + 1)))


def test_advice_for_another_area_is_rejected() -> None:
    advice = AreaAdvice(area="news", signal="Read it.", source_refs=(SourceRef(kind="line", id="photo:0"),))
    with pytest.raises(ValueError, match="given to area"):
        _evidence().check_advice(advice)


# T-CON-3 ---------------------------------------------------------------------


def test_evidence_cannot_be_modified() -> None:
    evidence = _evidence()
    snapshot = evidence.model_dump()
    with pytest.raises(ValidationError):
        evidence.lines[0].title = "Rewritten"
    with pytest.raises(ValidationError):
        evidence.dimension = "mind"
    evidence.check_advice(_advice())
    assert evidence.model_dump() == snapshot


# T-CON-4 ---------------------------------------------------------------------


def _write_area(areas_dir: Path, key: str, body: str) -> None:
    (areas_dir / f"{key}.yaml").write_text(body, encoding="utf-8")


def test_load_active_areas_skips_invalid_configs_with_reason(tmp_path: Path) -> None:
    _write_area(tmp_path, "news", "name: News\ndimensions: [mind]\nskill: news\nstatus: active\nnotes: x\n")
    _write_area(tmp_path, "bogus-dim", "name: Bogus\ndimensions: [mind, luck]\nskill: bogus\nstatus: active\n")
    _write_area(tmp_path, "no-skill", "name: No Skill\ndimensions: [will]\nstatus: active\n")
    _write_area(tmp_path, "paused", "name: Paused\ndimensions: [faith]\nskill: paused\nstatus: TBD\n")
    logs: list[str] = []

    areas = load_active_areas(tmp_path, [], logs.append)

    assert [area.key for area in areas] == ["news"]
    assert areas[0].dimension == "mind"
    assert areas[0].signal_max_chars == 50
    skipped = {line.split("'")[1] for line in logs if line.startswith("Skip area")}
    assert skipped == {"bogus-dim", "no-skill"}


def test_load_active_areas_honours_selection(tmp_path: Path) -> None:
    _write_area(tmp_path, "news", "name: News\ndimensions: [mind]\nskill: news\nstatus: active\n")
    _write_area(tmp_path, "weather", "name: Weather\ndimensions: [feeling]\nskill: weather\nstatus: active\n")
    assert [a.key for a in load_active_areas(tmp_path, ["Weather"], lambda _msg: None)] == ["weather"]


def test_skill_index_reads_frontmatter_name(tmp_path: Path) -> None:
    good = tmp_path / "a" / "news"
    good.mkdir(parents=True)
    (good / "SKILL.md").write_text('---\nname: "news"\ndescription: "x: y"\n---\n# News\n', encoding="utf-8")
    broken = tmp_path / "b"
    broken.mkdir()
    (broken / "SKILL.md").write_text("---\nname: [unclosed\n---\n", encoding="utf-8")
    assert build_skill_index(tmp_path) == {"news": good}
