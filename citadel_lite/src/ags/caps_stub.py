"""
Simplified CAPS (Citadel Agent Performance Score) stub for Phase 24.

Phase 25 (AIS integration) will replace this with the full XP/TP economy.
Until then, all agents start at CAPS grade B with 1000 XP and 50 TP.

CAPS grades: D(0-100 XP) -> C(101-500) -> B(501-2000) -> A(2001-10000) -> S(10000+)
Tier requirements: Tier 0=D+, Tier 1=C+, Tier 2=B+, Tier 3=A+
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class CAPSGrade(Enum):
    """CAPS performance grades."""
    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


# XP thresholds for each grade (lower bound inclusive)
_XP_THRESHOLDS: Dict[str, int] = {
    "S": 10001,
    "A": 2001,
    "B": 501,
    "C": 101,
    "D": 0,
}

# Minimum CAPS grade required for each CGRF tier
_TIER_MIN_GRADE: Dict[int, CAPSGrade] = {
    0: CAPSGrade.D,   # Tier 0 (experimental): any grade
    1: CAPSGrade.C,   # Tier 1 (dev): C+
    2: CAPSGrade.B,   # Tier 2 (production): B+
    3: CAPSGrade.A,   # Tier 3 (mission-critical): A+
}

# Grade ordering for comparison
_GRADE_ORDER = {
    CAPSGrade.D: 0,
    CAPSGrade.C: 1,
    CAPSGrade.B: 2,
    CAPSGrade.A: 3,
    CAPSGrade.S: 4,
}


@dataclass
class CAPSProfile:
    """Agent CAPS profile with XP/TP economy metrics."""
    agent_id: str
    xp: int = 1000
    tp: int = 50
    grade: CAPSGrade = CAPSGrade.B

    def meets_tier(self, tier: int) -> bool:
        """Check if this agent's CAPS grade meets the minimum for the given CGRF tier."""
        min_grade = _TIER_MIN_GRADE.get(tier, CAPSGrade.D)
        return _GRADE_ORDER[self.grade] >= _GRADE_ORDER[min_grade]


def resolve_caps_grade(xp: int) -> CAPSGrade:
    """Resolve CAPS grade from XP value."""
    for grade_name, threshold in sorted(_XP_THRESHOLDS.items(), key=lambda x: -x[1]):
        if xp >= threshold:
            return CAPSGrade(grade_name)
    return CAPSGrade.D


def get_default_profile(agent_id: str) -> CAPSProfile:
    """Return the default CAPS profile (Phase 25 stub). All agents start at B-grade."""
    return CAPSProfile(agent_id=agent_id, xp=1000, tp=50, grade=CAPSGrade.B)


def get_ais_profile(agent_id: str) -> CAPSProfile:
    """Return CAPS profile from AIS engine if available, otherwise fall back to stub.

    This is the Phase 25 integration point between AIS and AGS.
    """
    try:
        from src.ais.engine import AISEngine
        engine = AISEngine()
        return engine.get_caps_profile(agent_id)
    except Exception:
        import logging
        logging.getLogger(__name__).debug(
            "AIS not available for %s, using stub default", agent_id,
        )
        return get_default_profile(agent_id)
