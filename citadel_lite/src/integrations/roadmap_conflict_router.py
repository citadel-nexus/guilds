"""Roadmap Conflict Router — convert IR conflicts for Government (MS-5).

Converts Pydantic ``Conflict`` models from the Roadmap IR into plain
dicts that ``ProfGovernment.analyze()`` can consume.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.roadmap_ir.types import Conflict, RoadmapIR

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_conflict_router"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# Safety cap — prevent unbounded conflict lists from overwhelming the LLM
_MAX_CONFLICTS = 500

# Severity mapping: field name → severity level
_SEVERITY_MAP: Dict[str, str] = {
    "status": "HIGH",
    "readiness": "MEDIUM",
    "confidence": "MEDIUM",
    "verify_status": "MEDIUM",
    "revenue_gate": "HIGH",
}
_DEFAULT_SEVERITY = "LOW"


def route_conflicts(ir: RoadmapIR) -> List[Dict[str, Any]]:
    """Convert IR Conflict models to Government-friendly dicts.

    Parameters
    ----------
    ir:
        Parsed ``RoadmapIR`` containing a ``conflicts`` list.

    Returns
    -------
    List of dicts sorted by severity (HIGH first), capped at
    ``_MAX_CONFLICTS``.  Each dict has keys:
        ``item_id``, ``field``, ``values``, ``resolution``,
        ``action_hint``, ``severity``.
    """
    if not ir.conflicts:
        return []

    conflicts = ir.conflicts[:_MAX_CONFLICTS]
    if len(ir.conflicts) > _MAX_CONFLICTS:
        logger.warning(
            "Conflict list truncated: %d → %d",
            len(ir.conflicts), _MAX_CONFLICTS,
        )

    result = [_conflict_to_dict(c) for c in conflicts]

    # Sort by severity: HIGH > MEDIUM > LOW
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    result.sort(key=lambda d: severity_order.get(d["severity"], 3))

    return result


def _conflict_to_dict(conflict: Conflict) -> Dict[str, Any]:
    """Convert a single Conflict model to a plain dict."""
    return {
        "item_id": conflict.item_id,
        "field": conflict.field,
        "values": [
            {"source_id": cv.source_id, "value": cv.value}
            for cv in conflict.values
        ],
        "resolution": conflict.resolution,
        "action_hint": conflict.action_hint,
        "severity": _SEVERITY_MAP.get(conflict.field, _DEFAULT_SEVERITY),
    }
