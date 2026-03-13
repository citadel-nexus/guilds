"""MCA MetricsAggregator — code analysis + Roadmap IR + project metrics.

Extends the data models from ``citadel_progression_assessment.py``
(``Status``, ``Deliverable``, ``Phase``, ``Component``) to provide
a unified metrics snapshot for MCA professor analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "metrics_aggregator"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)


# ── Re-use Status enum pattern from citadel_progression_assessment.py ──────
class MetricStatus(str, Enum):
    """Status for MCA metric items — mirrors citadel Status with weights."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    COMPLETE = "complete"

    @property
    def weight(self) -> float:
        weights = {
            "not_started": 0.0,
            "in_progress": 0.3,
            "blocked": 0.1,
            "review": 0.7,
            "complete": 1.0,
        }
        return weights[self.value]


@dataclass
class MetricItem:
    """A single metric data point — modelled after Deliverable."""

    item_id: str
    name: str
    status: MetricStatus = MetricStatus.NOT_STARTED
    phase: Optional[str] = None
    completion_pct: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseMetrics:
    """Aggregated metrics for a phase — modelled after Phase."""

    phase_id: str
    name: str
    items_total: int = 0
    items_done: int = 0
    items_blocked: int = 0
    completion_pct: float = 0.0
    revenue_gate: str = "core"


class MetricsAggregator:
    """Aggregates code, project, and roadmap metrics into a unified snapshot.

    The snapshot is consumed by MCA professors during analysis.
    """

    def __init__(self) -> None:
        self._code_metrics: Dict[str, Any] = {}
        self._phase_metrics: List[PhaseMetrics] = []
        self._items: List[MetricItem] = []
        self._roadmap_ir_metrics: Optional[Dict[str, Any]] = None
        self._custom: Dict[str, Any] = {}

    # ── Code metrics ───────────────────────────────────────────────────────
    def set_code_metrics(
        self,
        total_files: int = 0,
        total_lines: int = 0,
        test_files: int = 0,
        test_count: int = 0,
        coverage_pct: float = 0.0,
        **extras: Any,
    ) -> None:
        """Set code-level metrics."""
        self._code_metrics = {
            "total_files": total_files,
            "total_lines": total_lines,
            "test_files": test_files,
            "test_count": test_count,
            "coverage_pct": coverage_pct,
            **extras,
        }

    # ── Phase metrics ──────────────────────────────────────────────────────
    def add_phase(self, phase: PhaseMetrics) -> None:
        """Add a phase metrics entry."""
        self._phase_metrics.append(phase)

    def add_phases_from_dicts(self, phases: List[Dict[str, Any]]) -> None:
        """Bulk add phases from dicts (e.g. from Roadmap IR)."""
        for p in phases:
            self._phase_metrics.append(PhaseMetrics(
                phase_id=p.get("phase_id", p.get("id", "")),
                name=p.get("name", ""),
                items_total=p.get("items_total", 0),
                items_done=p.get("items_done", 0),
                items_blocked=p.get("items_blocked", 0),
                completion_pct=p.get("completion_pct", 0.0),
                revenue_gate=p.get("revenue_gate", "core"),
            ))

    # ── Item metrics ───────────────────────────────────────────────────────
    def add_item(self, item: MetricItem) -> None:
        """Add an individual metric item."""
        self._items.append(item)

    # ── Roadmap IR (MS-5) ────────────────────────────────────────────────
    def add_roadmap_ir_metrics(self, ir_metrics: Dict[str, Any]) -> None:
        """Inject structured Roadmap IR metrics from the ingestor.

        Extracts phase-level breakdown into ``PhaseMetrics`` objects and
        stores revenue-gate coverage and conflict data for professor
        consumption.

        Parameters
        ----------
        ir_metrics:
            Dict produced by ``ingest_roadmap_ir()`` with keys like
            ``items_by_phase``, ``revenue_gate_coverage``, etc.
        """
        self._roadmap_ir_metrics = ir_metrics

        # Extract items_by_phase → PhaseMetrics
        items_by_phase = ir_metrics.get("items_by_phase", {})
        for phase_key, counts in items_by_phase.items():
            total = counts.get("total", 0)
            done = counts.get("done", 0)
            self.add_phase(PhaseMetrics(
                phase_id=f"phase_{phase_key}",
                name=f"Phase {phase_key}",
                items_total=total,
                items_done=done,
                items_blocked=counts.get("blocked", 0),
                completion_pct=round(done / total * 100, 1) if total else 0.0,
            ))

        # Store conflict and confidence as custom metrics
        if "conflicts_count" in ir_metrics:
            self.set_custom("conflicts_count", ir_metrics["conflicts_count"])
        if "avg_confidence" in ir_metrics:
            self.set_custom("avg_confidence", ir_metrics["avg_confidence"])
        if "health_score" in ir_metrics:
            self.set_custom("health_score", ir_metrics["health_score"])

    # ── Code structure metrics (MS-5: from Compiler professor) ────────────
    def add_code_structure_metrics(self, compiler_output: Dict[str, Any]) -> None:
        """Inject code structure metrics from ProfCodeCompiler.

        Parameters
        ----------
        compiler_output:
            Dict with keys ``enums``, ``functions``, ``schemas``,
            ``dependencies``, ``complexity_tags``, ``fingerprints``.
        """
        self.set_custom("code_structure", compiler_output)

    # ── Custom data ────────────────────────────────────────────────────────
    def set_custom(self, key: str, value: Any) -> None:
        """Set an arbitrary custom metric."""
        self._custom[key] = value

    # ── Aggregation ────────────────────────────────────────────────────────
    def aggregate(self) -> Dict[str, Any]:
        """Produce a unified metrics snapshot for professor consumption.

        Returns
        -------
        Dict with keys: ``code_summary``, ``plan_summary``,
        ``phase_details``, ``roadmap_ir``, ``custom``.
        """
        total_items = len(self._items)
        done_items = sum(1 for i in self._items if i.status == MetricStatus.COMPLETE)
        blocked_items = sum(1 for i in self._items if i.status == MetricStatus.BLOCKED)

        # Phase-level aggregation
        total_phases = len(self._phase_metrics)
        phases_done = sum(1 for p in self._phase_metrics if p.completion_pct >= 100.0)

        # Weighted completion
        weighted_completion = 0.0
        if total_items > 0:
            weighted_completion = sum(i.status.weight for i in self._items) / total_items * 100.0

        plan_summary = {
            "total_items": total_items,
            "items_done": done_items,
            "items_blocked": blocked_items,
            "total_phases": total_phases,
            "phases_done": phases_done,
            "weighted_completion_pct": round(weighted_completion, 1),
        }

        phase_details = [
            {
                "phase_id": p.phase_id,
                "name": p.name,
                "items_total": p.items_total,
                "items_done": p.items_done,
                "items_blocked": p.items_blocked,
                "completion_pct": p.completion_pct,
                "revenue_gate": p.revenue_gate,
            }
            for p in self._phase_metrics
        ]

        snapshot: Dict[str, Any] = {
            "code_summary": self._code_metrics or {},
            "plan_summary": plan_summary,
            "phase_details": phase_details,
            "custom": self._custom,
        }

        if self._roadmap_ir_metrics:
            snapshot["roadmap_ir"] = self._roadmap_ir_metrics

        return snapshot
