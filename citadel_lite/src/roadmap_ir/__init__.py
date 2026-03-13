"""roadmap_ir — Roadmap IR schema, types, and validators.

Provides the canonical Pydantic v2 data model for the Citadel Lite
Roadmap IR (Intermediate Representation) as defined in the Roadmap
Translator Blueprint v1.1.
"""

from __future__ import annotations

from .types import (
    Blocker,
    Catalog,
    Conflict,
    ConflictValue,
    CommitByDay,
    CommitVelocity,
    Evidence,
    EvidenceFileLoc,
    EvidenceGit,
    EvidenceText,
    Item,
    ItemKindEnum,
    Loc,
    Metrics,
    Note,
    NoteLevelEnum,
    Output,
    OutputTypeEnum,
    PhaseCompletion,
    RevenueGateEnum,
    RoadmapIR,
    Source,
    SourceTypeEnum,
    StatusEnum,
    VerifyEnum,
)
from .validators import validate_ir

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_ir"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

__all__ = [
    "Blocker",
    "Catalog",
    "Conflict",
    "ConflictValue",
    "CommitByDay",
    "CommitVelocity",
    "Evidence",
    "EvidenceFileLoc",
    "EvidenceGit",
    "EvidenceText",
    "Item",
    "ItemKindEnum",
    "Loc",
    "Metrics",
    "Note",
    "NoteLevelEnum",
    "Output",
    "OutputTypeEnum",
    "PhaseCompletion",
    "RevenueGateEnum",
    "RoadmapIR",
    "Source",
    "SourceTypeEnum",
    "StatusEnum",
    "VerifyEnum",
    "validate_ir",
]
