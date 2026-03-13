"""Roadmap Tracker response models (MS-3).

Defines aggregate view models built on top of the existing
``roadmap_ir.types`` primitives.  Only models that do NOT already
exist in roadmap_ir are defined here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel, Field

from src.roadmap_ir.types import (
    PhaseCompletion,
    RevenueGateEnum,
    StatusEnum,
    ItemKindEnum,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_models"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Aggregate models
# ---------------------------------------------------------------------------
class FinancePhase(BaseModel):
    """Revenue-gate level completion summary for Finance Guild reporting."""

    revenue_gate: RevenueGateEnum
    total: int = Field(..., ge=0)
    done: int = Field(..., ge=0)
    in_progress: int = Field(default=0, ge=0)
    blocked: int = Field(default=0, ge=0)
    completion_pct: float = Field(..., ge=0.0, le=1.0)


class RoadmapSnapshot(BaseModel):
    """Point-in-time aggregate view of the entire Roadmap IR."""

    generated_at: datetime
    schema_version: str
    total_items: int = Field(..., ge=0)
    phase_completion: PhaseCompletion
    items_by_status: Dict[str, int] = Field(default_factory=dict)
    items_by_kind: Dict[str, int] = Field(default_factory=dict)
    finance_phases: List[FinancePhase] = Field(default_factory=list)
    health_score: float = Field(..., ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)
