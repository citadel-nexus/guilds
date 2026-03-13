"""Roadmap-to-MCA Mapper — revenue gate / ZES tier mapping (MS-5).

Maps ``RevenueGateEnum`` values to ZES pricing tiers and computes
per-gate completion coverage for Oracle/Mirror consumption.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.roadmap_ir.types import Item, RevenueGateEnum, StatusEnum

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_to_mca_mapper"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# Revenue-gate → ZES tier mapping (from config/mca_meta_001.yaml)
_GATE_TO_ZES: Dict[RevenueGateEnum, str] = {
    RevenueGateEnum.tradebuilder: "premium",
    RevenueGateEnum.zes_agent: "zes_agent",
    RevenueGateEnum.platform_saas: "platform",
    RevenueGateEnum.data_products: "data",
    RevenueGateEnum.upsell: "upsell",
    RevenueGateEnum.unknown: "core",
}


def map_revenue_gate_to_zes_tier(gate: RevenueGateEnum) -> str:
    """Return the ZES tier string for a given revenue gate.

    Parameters
    ----------
    gate:
        Revenue gate enum value.

    Returns
    -------
    ZES tier string (e.g. ``"premium"``, ``"zes_agent"``).
    """
    return _GATE_TO_ZES.get(gate, "core")


def compute_revenue_gate_coverage(
    items: List[Item],
) -> Dict[str, Dict[str, Any]]:
    """Group items by revenue gate and compute completion per gate.

    Parameters
    ----------
    items:
        List of Roadmap IR ``Item`` models.

    Returns
    -------
    Dict keyed by gate value string:
        ``{gate: {total, done, in_progress, blocked, completion_pct, zes_tier}}``.
    """
    gates: Dict[str, Dict[str, Any]] = {}

    for item in items:
        gate = item.revenue_gate
        key = gate.value
        bucket = gates.setdefault(key, {
            "total": 0,
            "done": 0,
            "in_progress": 0,
            "blocked": 0,
            "completion_pct": 0.0,
            "zes_tier": map_revenue_gate_to_zes_tier(gate),
        })
        bucket["total"] += 1
        if item.status == StatusEnum.done:
            bucket["done"] += 1
        elif item.status == StatusEnum.in_progress:
            bucket["in_progress"] += 1
        elif item.status == StatusEnum.blocked:
            bucket["blocked"] += 1

    # Compute completion percentages
    for bucket in gates.values():
        total = bucket["total"]
        bucket["completion_pct"] = round(bucket["done"] / total, 4) if total else 0.0

    return gates
