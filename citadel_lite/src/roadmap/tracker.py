"""Roadmap Tracker — IR reader and snapshot builder (MS-3).

Reads a ``roadmap_ir.json`` produced by the Roadmap Translator
pipeline (MS-2) and builds aggregate snapshots used by the API
layer and, later, by the MCA feedback loop (MS-5).
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from src.roadmap_ir.types import (
    Item,
    PhaseCompletion,
    RevenueGateEnum,
    RoadmapIR,
    StatusEnum,
)
from src.roadmap_ir.validators import validate_ir

from .models import FinancePhase, RoadmapSnapshot

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_tracker"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# Safety: refuse files larger than 50 MB
_MAX_IR_FILE_BYTES = 50 * 1024 * 1024


class RoadmapTracker:
    """Reads a Roadmap IR file and produces aggregate views.

    Parameters
    ----------
    ir_path:
        Path to ``roadmap_ir.json``.  Must be an existing file under
        ``_MAX_IR_FILE_BYTES``.
    """

    def __init__(self, ir_path: Path) -> None:
        resolved = ir_path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"IR file not found: {resolved}")

        size = resolved.stat().st_size
        if size > _MAX_IR_FILE_BYTES:
            raise ValueError(
                f"IR file too large ({size} bytes, max {_MAX_IR_FILE_BYTES})"
            )

        raw = resolved.read_text(encoding="utf-8")
        self._ir: RoadmapIR = RoadmapIR.model_validate_json(raw)

        # Run semantic validation and collect warnings
        notes = validate_ir(self._ir)
        self._warnings: List[str] = [
            f"[{n.level.value}] {n.message}" for n in notes
        ]
        if self._warnings:
            logger.info(
                "IR validation produced %d note(s) for %s",
                len(self._warnings),
                resolved.name,
            )

    # -- public properties ---------------------------------------------------

    @property
    def ir(self) -> RoadmapIR:
        """Return the parsed Roadmap IR (read-only access)."""
        return self._ir

    @property
    def items(self) -> List[Item]:
        return self._ir.items

    # -- snapshot ------------------------------------------------------------

    def build_snapshot(self) -> RoadmapSnapshot:
        """Build a point-in-time aggregate snapshot of the Roadmap IR."""
        items = self._ir.items

        # Count by status
        status_counter: Counter[str] = Counter()
        for it in items:
            status_counter[it.status.value] += 1

        # Count by kind
        kind_counter: Counter[str] = Counter()
        for it in items:
            kind_counter[it.kind.value] += 1

        phase_completion = PhaseCompletion(
            done=status_counter.get(StatusEnum.done.value, 0),
            in_progress=status_counter.get(StatusEnum.in_progress.value, 0),
            blocked=status_counter.get(StatusEnum.blocked.value, 0),
            planned=status_counter.get(StatusEnum.planned.value, 0),
            unknown=status_counter.get(StatusEnum.unknown.value, 0),
        )

        finance = self.get_finance_guild_report()
        health = self._compute_health_score(items, phase_completion)

        return RoadmapSnapshot(
            generated_at=datetime.now(timezone.utc),
            schema_version=self._ir.schema_version,
            total_items=len(items),
            phase_completion=phase_completion,
            items_by_status=dict(status_counter),
            items_by_kind=dict(kind_counter),
            finance_phases=finance,
            health_score=health,
            warnings=list(self._warnings),
        )

    # -- finance guild -------------------------------------------------------

    def get_finance_guild_report(self) -> List[FinancePhase]:
        """Revenue-gate level completion for Finance Guild reporting."""
        gate_items: dict[RevenueGateEnum, List[Item]] = {}
        for it in self._ir.items:
            gate_items.setdefault(it.revenue_gate, []).append(it)

        result: List[FinancePhase] = []
        for gate in RevenueGateEnum:
            items = gate_items.get(gate, [])
            if not items:
                continue
            total = len(items)
            done = sum(1 for i in items if i.status == StatusEnum.done)
            in_prog = sum(
                1 for i in items if i.status == StatusEnum.in_progress
            )
            blocked = sum(1 for i in items if i.status == StatusEnum.blocked)

            result.append(
                FinancePhase(
                    revenue_gate=gate,
                    total=total,
                    done=done,
                    in_progress=in_prog,
                    blocked=blocked,
                    completion_pct=round(done / total, 4) if total else 0.0,
                )
            )
        return result

    # -- internal helpers ----------------------------------------------------

    @staticmethod
    def _compute_health_score(
        items: List[Item], pc: PhaseCompletion
    ) -> float:
        """Compute a 0.0–1.0 health score.

        Formula (interim — to be replaced by MCA professor in MS-5):
          health = (done * 1.0 + in_progress * 0.3) / total
        Blocked items contribute 0, penalising the score naturally.
        """
        total = len(items)
        if total == 0:
            return 1.0
        weighted = pc.done * 1.0 + pc.in_progress * 0.3
        return round(min(weighted / total, 1.0), 4)
