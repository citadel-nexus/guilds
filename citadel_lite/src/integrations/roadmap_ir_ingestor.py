"""Roadmap IR Ingestor — structured metric extraction for MCA (MS-5).

Delegates to ``RoadmapTracker`` for safe loading and validation, then
extracts the structured metric dict consumed by ``MetricsAggregator``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.roadmap.tracker import RoadmapTracker
from src.roadmap_ir.types import Item, RoadmapIR, StatusEnum

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_ir_ingestor"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)


def ingest_roadmap_ir(ir_path: Path) -> Dict[str, Any]:
    """Load a Roadmap IR file and return structured metrics for MCA.

    Delegates file-size checks, path validation, and semantic validation
    to ``RoadmapTracker``.

    Parameters
    ----------
    ir_path:
        Path to ``roadmap_ir.json``.

    Returns
    -------
    Dict with keys:
        ``items_total``, ``items_done``, ``items_blocked``,
        ``items_in_progress``, ``items_planned``,
        ``conflicts_count``, ``avg_confidence``,
        ``health_score``, ``schema_version``,
        ``phase_completion``, ``revenue_gate_coverage``,
        ``items_by_phase``, ``warnings``.
    """
    tracker = RoadmapTracker(ir_path)
    snapshot = tracker.build_snapshot()
    ir = tracker.ir

    # Phase-level breakdown (phase number → counts)
    items_by_phase = _group_items_by_phase(ir.items)

    # Revenue-gate coverage
    revenue_gate_coverage = _compute_revenue_gate_coverage(ir.items)

    # Average confidence across items
    avg_confidence = _compute_avg_confidence(ir.items)

    return {
        "items_total": snapshot.total_items,
        "items_done": snapshot.phase_completion.done,
        "items_blocked": snapshot.phase_completion.blocked,
        "items_in_progress": snapshot.phase_completion.in_progress,
        "items_planned": snapshot.phase_completion.planned,
        "conflicts_count": len(ir.conflicts),
        "avg_confidence": avg_confidence,
        "health_score": snapshot.health_score,
        "schema_version": snapshot.schema_version,
        "phase_completion": {
            "done": snapshot.phase_completion.done,
            "in_progress": snapshot.phase_completion.in_progress,
            "blocked": snapshot.phase_completion.blocked,
            "planned": snapshot.phase_completion.planned,
            "unknown": snapshot.phase_completion.unknown,
        },
        "revenue_gate_coverage": revenue_gate_coverage,
        "items_by_phase": items_by_phase,
        "warnings": snapshot.warnings,
    }


def get_roadmap_ir(ir_path: Path) -> RoadmapIR:
    """Load and return the full RoadmapIR model (for conflict routing).

    Parameters
    ----------
    ir_path:
        Path to ``roadmap_ir.json``.
    """
    tracker = RoadmapTracker(ir_path)
    return tracker.ir


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _group_items_by_phase(items: List[Item]) -> Dict[str, Dict[str, int]]:
    """Group items by their ``phase`` number and count by status."""
    phases: Dict[str, Dict[str, int]] = {}
    for item in items:
        key = str(item.phase) if item.phase is not None else "unassigned"
        bucket = phases.setdefault(key, {
            "total": 0, "done": 0, "in_progress": 0, "blocked": 0, "planned": 0,
        })
        bucket["total"] += 1
        if item.status == StatusEnum.done:
            bucket["done"] += 1
        elif item.status == StatusEnum.in_progress:
            bucket["in_progress"] += 1
        elif item.status == StatusEnum.blocked:
            bucket["blocked"] += 1
        elif item.status == StatusEnum.planned:
            bucket["planned"] += 1
    return phases


def _compute_revenue_gate_coverage(
    items: List[Item],
) -> Dict[str, Dict[str, Any]]:
    """Compute per-revenue-gate completion stats."""
    gates: Dict[str, Dict[str, Any]] = {}
    for item in items:
        gate = item.revenue_gate.value
        bucket = gates.setdefault(gate, {
            "total": 0, "done": 0, "in_progress": 0, "blocked": 0,
        })
        bucket["total"] += 1
        if item.status == StatusEnum.done:
            bucket["done"] += 1
        elif item.status == StatusEnum.in_progress:
            bucket["in_progress"] += 1
        elif item.status == StatusEnum.blocked:
            bucket["blocked"] += 1

    # Add completion_pct
    for bucket in gates.values():
        total = bucket["total"]
        bucket["completion_pct"] = round(bucket["done"] / total, 4) if total else 0.0

    return gates


def _compute_avg_confidence(items: List[Item]) -> float:
    """Average confidence across items that have a confidence score."""
    scores = [it.confidence for it in items if it.confidence is not None]
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)
