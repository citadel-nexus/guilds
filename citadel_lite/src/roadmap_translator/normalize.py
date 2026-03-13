"""Normalization of status, phase, verify_status, revenue_gate, and readiness.

Implements Blueprint v1.1 §6 normalization rules.  Configuration is
read from ``config/roadmap_translate.toml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from src.roadmap_ir.types import (
    Item,
    RevenueGateEnum,
    StatusEnum,
    VerifyEnum,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_normalize"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
_CONFIG: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    config_path = Path(__file__).resolve().parents[2] / "config" / "roadmap_translate.toml"
    if config_path.exists():
        _CONFIG = tomllib.loads(config_path.read_text(encoding="utf-8"))
    else:
        _CONFIG = {}
    return _CONFIG


# ---------------------------------------------------------------------------
# Readiness calculation
# ---------------------------------------------------------------------------
_READINESS_TABLE: Dict[str, float] = {
    "done|verified": 1.0,
    "done|tested": 0.9,
    "done|not_tested": 0.8,
    "done|unknown": 0.8,
    "in_progress|verified": 0.6,
    "in_progress|tested": 0.55,
    "in_progress|not_tested": 0.5,
    "in_progress|unknown": 0.5,
    "blocked|verified": 0.3,
    "blocked|tested": 0.25,
    "blocked|not_tested": 0.2,
    "blocked|unknown": 0.2,
    "planned|verified": 0.15,
    "planned|tested": 0.12,
    "planned|not_tested": 0.1,
    "planned|unknown": 0.1,
    "unknown|unknown": 0.05,
}


def compute_readiness(status: StatusEnum, verify: VerifyEnum) -> float:
    """Deterministic readiness from status + verify_status."""
    key = f"{status.value}|{verify.value}"
    return _READINESS_TABLE.get(key, 0.05)


# ---------------------------------------------------------------------------
# Revenue gate mapping
# ---------------------------------------------------------------------------
def phase_to_revenue_gate(phase: Optional[int]) -> RevenueGateEnum:
    """Map a phase number to a revenue_gate enum value."""
    if phase is None:
        return RevenueGateEnum.unknown

    cfg = _load_config()
    gate_map = cfg.get("phase_revenue_gate", {})

    gate_str = gate_map.get(str(phase), gate_map.get(phase, "unknown"))
    try:
        return RevenueGateEnum(gate_str)
    except ValueError:
        return RevenueGateEnum.unknown


# ---------------------------------------------------------------------------
# Normalize items
# ---------------------------------------------------------------------------
def normalize_items(items: List[Item]) -> List[Item]:
    """Apply normalization to a list of Items (mutates in place)."""
    for item in items:
        # Readiness
        item.readiness = compute_readiness(item.status, item.verify_status)

        # Revenue gate (only override if currently unknown and phase present)
        if item.revenue_gate == RevenueGateEnum.unknown and item.phase is not None:
            item.revenue_gate = phase_to_revenue_gate(item.phase)

        # Confidence based on evidence quality
        if item.evidence:
            weights = [getattr(ev, "weight", 0.3) for ev in item.evidence]
            item.confidence = round(min(max(weights), 1.0), 2)
        else:
            item.confidence = 0.0

    return items
