"""Merge items from multiple translators and generate conflicts.

Implements Blueprint v1.1 §7 merge rules.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.roadmap_ir.types import (
    Conflict,
    ConflictValue,
    Evidence,
    Item,
    StatusEnum,
    VerifyEnum,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_merge"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Priority orderings (Blueprint v1.1 §7.1)
# ---------------------------------------------------------------------------
_STATUS_PRIORITY = {
    StatusEnum.done: 4,
    StatusEnum.blocked: 3,
    StatusEnum.in_progress: 2,
    StatusEnum.planned: 1,
    StatusEnum.unknown: 0,
}

_VERIFY_PRIORITY = {
    VerifyEnum.verified: 3,
    VerifyEnum.tested: 2,
    VerifyEnum.not_tested: 1,
    VerifyEnum.unknown: 0,
}


def merge_items(
    patches_items: List[Tuple[str, List[Item]]],
) -> Tuple[List[Item], List[Conflict]]:
    """Merge item lists from multiple translators.

    Args:
        patches_items: list of ``(source_id, items)`` tuples.

    Returns:
        ``(merged_items, conflicts)`` — deduplicated items and any
        field-level conflicts detected during merging.
    """
    bucket: Dict[str, List[Tuple[str, Item]]] = {}
    for source_id, items in patches_items:
        for item in items:
            bucket.setdefault(item.item_id, []).append((source_id, item))

    merged: List[Item] = []
    conflicts: List[Conflict] = []

    for item_id, entries in bucket.items():
        if len(entries) == 1:
            merged.append(entries[0][1])
            continue

        # Multiple sources for same item_id → merge
        m_item, m_conflicts = _merge_group(item_id, entries)
        merged.append(m_item)
        conflicts.extend(m_conflicts)

    return merged, conflicts


def _merge_group(
    item_id: str,
    entries: List[Tuple[str, Item]],
) -> Tuple[Item, List[Conflict]]:
    """Merge multiple Items with the same item_id."""
    conflicts: List[Conflict] = []

    # Pick winning status
    statuses = [(sid, it.status) for sid, it in entries]
    best_status = max(statuses, key=lambda x: _STATUS_PRIORITY.get(x[1], 0))
    if len(set(s for _, s in statuses)) > 1:
        conflicts.append(
            Conflict(
                item_id=item_id,
                field="status",
                values=[ConflictValue(source_id=s, value=v.value) for s, v in statuses],
                resolution=f"Chose '{best_status[1].value}' (highest priority)",
                action_hint="Verify status with source documents",
            )
        )

    # Pick winning verify_status
    verifies = [(sid, it.verify_status) for sid, it in entries]
    best_verify = max(verifies, key=lambda x: _VERIFY_PRIORITY.get(x[1], 0))

    # Pick best title (longest concrete)
    titles = [(sid, it.title) for sid, it in entries]
    best_title = max(titles, key=lambda x: len(x[1]))

    # Union evidence
    all_evidence: List[Evidence] = []
    for _, it in entries:
        all_evidence.extend(it.evidence)

    # Union tags
    all_tags: List[str] = []
    for _, it in entries:
        if it.tags:
            all_tags.extend(it.tags)
    unique_tags = list(dict.fromkeys(all_tags)) if all_tags else None

    # Union blockers
    all_blockers = []
    for _, it in entries:
        if it.blockers:
            all_blockers.extend(it.blockers)

    # Union outputs
    all_outputs = []
    for _, it in entries:
        if it.outputs:
            all_outputs.extend(it.outputs)

    # Union dependencies
    all_deps: List[str] = []
    for _, it in entries:
        if it.dependencies:
            all_deps.extend(it.dependencies)
    unique_deps = list(dict.fromkeys(all_deps)) if all_deps else None

    # Take first non-None phase
    phase = None
    for _, it in entries:
        if it.phase is not None:
            phase = it.phase
            break

    # Max updated_at
    dates = [it.updated_at for _, it in entries if it.updated_at]
    best_date = max(dates) if dates else None

    # Build merged item
    base = entries[0][1]
    merged = Item(
        item_id=item_id,
        kind=base.kind,
        phase=phase,
        title=best_title[1],
        status=best_status[1],
        verify_status=best_verify[1],
        revenue_gate=base.revenue_gate,
        tags=unique_tags,
        owners=base.owners,
        updated_at=best_date,
        dependencies=unique_deps,
        blockers=all_blockers or None,
        outputs=all_outputs or None,
        evidence=all_evidence,
    )

    return merged, conflicts
