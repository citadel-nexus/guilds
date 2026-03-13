"""Emit the final Roadmap IR JSON and optional Markdown report.

Produces ``roadmap_ir.json`` and ``roadmap_ir.report.md``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.roadmap_ir.types import (
    Conflict,
    Item,
    Metrics,
    Note,
    PhaseCompletion,
    RoadmapIR,
    Source,
    StatusEnum,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_emit"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


def build_ir(
    sources: List[Source],
    items: List[Item],
    conflicts: List[Conflict],
    notes: List[Note],
) -> RoadmapIR:
    """Assemble a complete RoadmapIR document."""
    phase_comp = _compute_phase_completion(items)
    metrics = Metrics(phase_completion=phase_comp)

    return RoadmapIR(
        schema="citadel.roadmap_ir",
        schema_version="1.0.0",
        generated_at=datetime.now(timezone.utc),
        sources=sources,
        items=items,
        metrics=metrics,
        conflicts=conflicts,
        notes=notes,
    )


def emit_json(ir: RoadmapIR, out_path: Path) -> None:
    """Write RoadmapIR as JSON."""
    data = ir.model_dump(by_alias=True, mode="json")
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def emit_report(ir: RoadmapIR, out_path: Path) -> None:
    """Write a human-readable Markdown summary report."""
    lines: List[str] = []
    lines.append("# Roadmap IR Report")
    lines.append("")
    lines.append(f"Generated: {ir.generated_at.isoformat()}")
    lines.append(f"Sources: {len(ir.sources)}")
    lines.append(f"Items: {len(ir.items)}")
    lines.append(f"Conflicts: {len(ir.conflicts)}")
    lines.append(f"Notes: {len(ir.notes)}")
    lines.append("")

    # Phase completion
    pc = ir.metrics.phase_completion
    if pc:
        lines.append("## Phase Completion")
        lines.append("")
        lines.append(f"| Status | Count |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Done | {pc.done} |")
        lines.append(f"| In Progress | {pc.in_progress} |")
        lines.append(f"| Blocked | {pc.blocked} |")
        lines.append(f"| Planned | {pc.planned} |")
        lines.append(f"| Unknown | {pc.unknown} |")
        total = pc.done + pc.in_progress + pc.blocked + pc.planned + pc.unknown
        if total > 0:
            lines.append(f"| **Total** | **{total}** |")
            pct = round(pc.done / total * 100, 1)
            lines.append(f"\nCompletion: {pct}%")
        lines.append("")

    # Items by phase
    phases = sorted(set(it.phase for it in ir.items if it.phase is not None))
    if phases:
        lines.append("## Items by Phase")
        lines.append("")
        for p in phases:
            p_items = [it for it in ir.items if it.phase == p]
            done_count = sum(1 for it in p_items if it.status == StatusEnum.done)
            lines.append(f"### Phase {p} ({done_count}/{len(p_items)} done)")
            for it in p_items:
                mark = "✅" if it.status == StatusEnum.done else "⬜"
                lines.append(f"- {mark} `{it.item_id}`: {it.title}")
            lines.append("")

    # Conflicts
    if ir.conflicts:
        lines.append("## Conflicts")
        lines.append("")
        for c in ir.conflicts:
            lines.append(f"- **{c.item_id}**.{c.field}: {c.resolution}")
        lines.append("")

    # Notes
    if ir.notes:
        lines.append("## Notes")
        lines.append("")
        for n in ir.notes:
            lines.append(f"- [{n.level.value.upper()}] {n.message}")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def _compute_phase_completion(items: List[Item]) -> PhaseCompletion:
    """Count items by status."""
    counts = {s: 0 for s in StatusEnum}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return PhaseCompletion(
        done=counts[StatusEnum.done],
        in_progress=counts[StatusEnum.in_progress],
        blocked=counts[StatusEnum.blocked],
        planned=counts[StatusEnum.planned],
        unknown=counts[StatusEnum.unknown],
    )
