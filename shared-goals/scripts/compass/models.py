"""Contracts between boundary scripts, memory, the LLM and rendering."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Dimension = Literal["faith", "will", "feeling", "mind"]
DIMENSIONS: tuple[Dimension, ...] = ("faith", "will", "feeling", "mind")


class AreaConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    dimensions: tuple[Dimension, ...] = Field(min_length=1)
    skill: str = Field(min_length=1)
    status: str
    signal_max_chars: int = 50

    @field_validator("signal_max_chars")
    @classmethod
    def _at_least_50(cls, value: int) -> int:
        return max(50, value)

    @property
    def dimension(self) -> Dimension:
        return self.dimensions[0]


class Line(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    url: str
    body: str
    signal: str

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title is blank")
        return value


class BoundaryPayload(BaseModel):
    """What a `daily-<area>-status.py` script prints."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok", "TBD", "error"]
    reason: str
    lines: tuple[Line, ...]
    signal: str = ""
    ts: str = ""


class Evidence(BaseModel):
    """Immutable per-area facts; LLM output never edits these."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    name: str
    dimension: Dimension
    status: Literal["ok", "TBD", "error"]
    reason: str
    lines: tuple[Line, ...]
    signal_max_chars: int

    def line_id(self, index: int) -> str:
        return f"{self.key}:{index}"

    @property
    def line_ids(self) -> frozenset[str]:
        return frozenset(self.line_id(i) for i in range(len(self.lines)))

    def check_advice(self, advice: AreaAdvice, memory_ids: frozenset[str] = frozenset()) -> None:
        if advice.area != self.key:
            raise ValueError(f"advice for '{advice.area}' given to area '{self.key}'")
        if len(advice.signal) > self.signal_max_chars:
            raise ValueError(f"signal exceeds {self.signal_max_chars} chars")
        known = {"line": self.line_ids, "memory": memory_ids}
        unknown = [ref.id for ref in advice.source_refs if ref.id not in known[ref.kind]]
        if unknown:
            raise ValueError(f"unknown source_refs: {', '.join(unknown)}")


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["line", "memory"]
    id: str = Field(min_length=1)


class AreaAdvice(BaseModel):
    """LLM recommendation for one area, traceable to evidence lines or memories."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    area: str
    signal: str = Field(min_length=1)
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
