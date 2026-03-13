"""Roadmap IR v1 — Pydantic v2 type definitions.

Defines the complete Roadmap IR data model as specified in the
Roadmap Translator Blueprint v1.1 §2.5.  All roadmap inputs are
translated into this intermediate JSON format.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_ir_types"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class StatusEnum(str, Enum):
    """Item completion status."""
    unknown = "unknown"
    planned = "planned"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"


class VerifyEnum(str, Enum):
    """Verification / test status."""
    unknown = "unknown"
    not_tested = "not_tested"
    tested = "tested"
    verified = "verified"


class RevenueGateEnum(str, Enum):
    """Revenue gate that an item contributes to."""
    tradebuilder = "tradebuilder"
    zes_agent = "zes_agent"
    platform_saas = "platform_saas"
    data_products = "data_products"
    upsell = "upsell"
    unknown = "unknown"


class SourceTypeEnum(str, Enum):
    """Type of ingested source document."""
    markdown = "markdown"
    plaintext = "plaintext"
    gitlog = "gitlog"
    json = "json"
    other = "other"


class ItemKindEnum(str, Enum):
    """Kind of roadmap item."""
    phase = "phase"
    feature = "feature"
    milestone = "milestone"
    task = "task"


class OutputTypeEnum(str, Enum):
    """Type of item output / artifact."""
    endpoint = "endpoint"
    module = "module"
    path = "path"
    command = "command"
    artifact = "artifact"
    doc = "doc"
    test = "test"


class NoteLevelEnum(str, Enum):
    """Severity level for notes."""
    info = "info"
    warning = "warning"
    error = "error"


# ---------------------------------------------------------------------------
# Evidence models
# ---------------------------------------------------------------------------
class Loc(BaseModel):
    """File location (path + line range)."""
    path: str = Field(..., min_length=1, max_length=500)
    line_start: int = Field(..., ge=1)
    line_end: int = Field(..., ge=1)


class EvidenceFileLoc(BaseModel):
    """Evidence pointing to a file location."""
    source_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_\-]{1,63}$")
    loc: Loc
    quote: Optional[str] = Field(default=None, max_length=800)
    weight: float = Field(..., ge=0.0, le=1.0)


class EvidenceGit(BaseModel):
    """Evidence from a git commit."""
    source_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_\-]{1,63}$")
    commit: str = Field(..., pattern=r"^[0-9a-f]{7,40}$")
    date: Optional[datetime] = None
    author: Optional[str] = Field(default=None, max_length=200)
    files: Optional[List[str]] = None
    message: Optional[str] = Field(default=None, max_length=500)
    weight: float = Field(..., ge=0.0, le=1.0)


class EvidenceText(BaseModel):
    """Free-text evidence."""
    source_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_\-]{1,63}$")
    text: str = Field(..., min_length=1, max_length=800)
    weight: float = Field(..., ge=0.0, le=1.0)


Evidence = Union[EvidenceFileLoc, EvidenceGit, EvidenceText]


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------
class Blocker(BaseModel):
    """An item-level blocker."""
    text: str = Field(..., min_length=1, max_length=500)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_refs: Optional[List[int]] = None


class Output(BaseModel):
    """An output / artifact produced by an item."""
    type: OutputTypeEnum
    value: str = Field(..., min_length=1, max_length=500)
    extra: Optional[dict[str, Any]] = None


class Source(BaseModel):
    """Describes one ingested source document."""
    source_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_\-]{1,63}$")
    type: SourceTypeEnum
    label: str = Field(..., min_length=1, max_length=200)
    fingerprint: str = Field(..., pattern=r"^(sha256):[0-9a-f]{64}$")
    path_hint: Optional[str] = Field(default=None, max_length=500)
    collected_at: datetime


class Catalog(BaseModel):
    """Enumerates the allowed enum values for this IR instance."""
    status_enum: List[StatusEnum] = Field(
        default_factory=lambda: list(StatusEnum),
        min_length=5,
        max_length=5,
    )
    verify_enum: List[VerifyEnum] = Field(
        default_factory=lambda: list(VerifyEnum),
        min_length=4,
        max_length=4,
    )
    revenue_gates: List[RevenueGateEnum] = Field(
        default_factory=lambda: list(RevenueGateEnum),
        min_length=6,
        max_length=6,
    )


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------
class Item(BaseModel):
    """A single roadmap item (phase / feature / milestone / task)."""
    item_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_\-]{2,80}$")
    kind: ItemKindEnum
    phase: Optional[int] = Field(default=None, ge=0, le=999)
    title: str = Field(..., min_length=1, max_length=300)
    status: StatusEnum
    verify_status: VerifyEnum = VerifyEnum.unknown
    readiness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    revenue_gate: RevenueGateEnum = RevenueGateEnum.unknown
    tags: Optional[List[str]] = None
    owners: Optional[List[str]] = None
    updated_at: Optional[date] = None
    dependencies: Optional[List[str]] = None
    blockers: Optional[List[Blocker]] = None
    outputs: Optional[List[Output]] = None
    evidence: List[Evidence] = Field(..., min_length=1)
    raw: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
class CommitByDay(BaseModel):
    """Single day commit count."""
    date: date
    count: int = Field(..., ge=0)


class CommitVelocity(BaseModel):
    """Git commit velocity over a sliding window."""
    window_days: int = Field(..., ge=1, le=365)
    commits_total: int = Field(..., ge=0)
    commits_by_day: List[CommitByDay] = Field(default_factory=list)


class PhaseCompletion(BaseModel):
    """Aggregate item counts by status."""
    done: int = Field(default=0, ge=0)
    in_progress: int = Field(default=0, ge=0)
    blocked: int = Field(default=0, ge=0)
    planned: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)


class Metrics(BaseModel):
    """Top-level metrics section."""
    commit_velocity: Optional[CommitVelocity] = None
    phase_completion: Optional[PhaseCompletion] = None
    generated_warnings: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Conflict & Note
# ---------------------------------------------------------------------------
class ConflictValue(BaseModel):
    """One side of a conflict."""
    source_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_\-]{1,63}$")
    value: Any


class Conflict(BaseModel):
    """Records a disagreement between sources for a given item field."""
    item_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_\-]{2,80}$")
    field: str = Field(..., min_length=1, max_length=64)
    values: List[ConflictValue] = Field(..., min_length=2)
    resolution: str = Field(..., min_length=1, max_length=120)
    action_hint: str = Field(..., min_length=1, max_length=300)


class Note(BaseModel):
    """A translator-generated note (info / warning / error)."""
    level: NoteLevelEnum
    message: str = Field(..., min_length=1, max_length=600)
    source_id: Optional[str] = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9_\-]{1,63}$"
    )
    item_id: Optional[str] = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9_\-]{2,80}$"
    )


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------
class RoadmapIR(BaseModel):
    """Root Roadmap IR document."""
    schema_: str = Field("citadel.roadmap_ir", alias="schema")
    schema_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    generated_at: datetime
    sources: List[Source] = Field(..., min_length=1)
    catalog: Catalog = Field(default_factory=Catalog)
    items: List[Item] = Field(default_factory=list)
    metrics: Metrics = Field(default_factory=Metrics)
    conflicts: List[Conflict] = Field(default_factory=list)
    notes: List[Note] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @field_validator("schema_")
    @classmethod
    def _check_schema_const(cls, v: str) -> str:
        if v != "citadel.roadmap_ir":
            raise ValueError("schema must be 'citadel.roadmap_ir'")
        return v
