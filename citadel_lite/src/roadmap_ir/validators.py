"""Roadmap IR v1 — semantic validators.

Validates a RoadmapIR instance beyond what the JSON Schema / Pydantic
type system can express.  Returns a list of Note objects so results
can be folded back into the IR's ``notes`` array.
"""

from __future__ import annotations

from typing import List

from .types import (
    Item,
    Note,
    NoteLevelEnum,
    RoadmapIR,
    StatusEnum,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_ir_validators"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def validate_ir(ir: RoadmapIR) -> List[Note]:
    """Run all semantic checks and return generated notes."""
    notes: List[Note] = []
    notes.extend(_check_item_id_uniqueness(ir))
    notes.extend(_check_evidence_without_status(ir))
    notes.extend(_check_phase_id_pattern(ir))
    notes.extend(_check_source_refs(ir))
    notes.extend(_check_dependency_refs(ir))
    notes.extend(_check_dependency_cycles(ir))
    return notes


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
def _check_item_id_uniqueness(ir: RoadmapIR) -> List[Note]:
    """Error if any item_id appears more than once."""
    seen: dict[str, int] = {}
    notes: List[Note] = []
    for item in ir.items:
        seen[item.item_id] = seen.get(item.item_id, 0) + 1
    for item_id, count in seen.items():
        if count > 1:
            notes.append(
                Note(
                    level=NoteLevelEnum.error,
                    message=f"Duplicate item_id '{item_id}' appears {count} times",
                    item_id=item_id,
                )
            )
    return notes


def _check_evidence_without_status(ir: RoadmapIR) -> List[Note]:
    """Error if status is 'unknown' but evidence list is non-empty."""
    notes: List[Note] = []
    for item in ir.items:
        if item.status == StatusEnum.unknown and len(item.evidence) > 0:
            notes.append(
                Note(
                    level=NoteLevelEnum.warning,
                    message=(
                        f"Item '{item.item_id}' has evidence but status is "
                        f"'unknown'; consider updating status"
                    ),
                    item_id=item.item_id,
                )
            )
    return notes


def _check_phase_id_pattern(ir: RoadmapIR) -> List[Note]:
    """Warn if item has a phase number but item_id doesn't start with 'phase-'."""
    notes: List[Note] = []
    for item in ir.items:
        if item.phase is not None and not item.item_id.startswith("phase-"):
            notes.append(
                Note(
                    level=NoteLevelEnum.warning,
                    message=(
                        f"Item '{item.item_id}' has phase={item.phase} but "
                        f"item_id does not start with 'phase-'"
                    ),
                    item_id=item.item_id,
                )
            )
    return notes


def _check_source_refs(ir: RoadmapIR) -> List[Note]:
    """Error if evidence references a source_id not in sources list."""
    source_ids = {s.source_id for s in ir.sources}
    notes: List[Note] = []
    for item in ir.items:
        for ev in item.evidence:
            if ev.source_id not in source_ids:
                notes.append(
                    Note(
                        level=NoteLevelEnum.error,
                        message=(
                            f"Item '{item.item_id}' evidence references "
                            f"unknown source_id '{ev.source_id}'"
                        ),
                        item_id=item.item_id,
                        source_id=ev.source_id,
                    )
                )
    return notes


def _check_dependency_refs(ir: RoadmapIR) -> List[Note]:
    """Error if a dependency references a non-existent item_id."""
    all_ids = {item.item_id for item in ir.items}
    notes: List[Note] = []
    for item in ir.items:
        if not item.dependencies:
            continue
        for dep_id in item.dependencies:
            if dep_id not in all_ids:
                notes.append(
                    Note(
                        level=NoteLevelEnum.error,
                        message=(
                            f"Item '{item.item_id}' depends on "
                            f"'{dep_id}' which does not exist"
                        ),
                        item_id=item.item_id,
                    )
                )
    return notes


def _check_dependency_cycles(ir: RoadmapIR) -> List[Note]:
    """Warn if the dependency graph contains cycles (DFS-based)."""
    graph: dict[str, list[str]] = {}
    for item in ir.items:
        graph[item.item_id] = list(item.dependencies or [])

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {k: WHITE for k in graph}
    notes: List[Note] = []

    def dfs(node: str, path: list[str]) -> None:
        if node not in color:
            return
        color[node] = GRAY
        path.append(node)
        for dep in graph.get(node, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                cycle_start = path.index(dep)
                cycle = path[cycle_start:] + [dep]
                notes.append(
                    Note(
                        level=NoteLevelEnum.warning,
                        message=(
                            f"Dependency cycle detected: "
                            f"{' -> '.join(cycle)}"
                        ),
                    )
                )
            elif color[dep] == WHITE:
                dfs(dep, path)
        path.pop()
        color[node] = BLACK

    for node in list(graph.keys()):
        if color.get(node) == WHITE:
            dfs(node, [])

    return notes
