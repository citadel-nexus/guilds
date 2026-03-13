"""
S01 DEFINER - Validate SapientPacket against CGRF tier + CAPS requirements.

Checks:
1. Required packet fields are populated
2. Risk score is in valid range [0, 1]
3. Agent CAPS grade meets the tier's minimum requirement
4. final_decision is a known value
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.types import SapientPacket
from src.ags.caps_stub import CAPSProfile, get_default_profile

logger = logging.getLogger(__name__)


class S01DefinerResult:
    """Result of S01 DEFINER validation."""

    def __init__(self) -> None:
        self.valid: bool = True
        self.violations: List[str] = []
        self.cgrf_tier: int = 0
        self.caps_grade: str = ""
        self.caps_meets_tier: bool = True

    def add_violation(self, msg: str) -> None:
        self.violations.append(msg)
        self.valid = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "violations": self.violations,
            "cgrf_tier": self.cgrf_tier,
            "caps_grade": self.caps_grade,
            "caps_meets_tier": self.caps_meets_tier,
        }


class S01Definer:
    """
    Stage S01: Validate packet schema, CGRF tier, and CAPS eligibility.

    Input:  SapientPacket + CGRF tier (from guardian metadata) + CAPSProfile
    Output: S01DefinerResult (valid/invalid + violations list)
    """

    REQUIRED_FIELDS = ["action_type", "intent_source", "intent_id", "fate_recommendation"]

    def run(
        self,
        sapient: SapientPacket,
        cgrf_tier: int = 0,
        caps_profile: Optional[CAPSProfile] = None,
    ) -> S01DefinerResult:
        """Validate the SapientPacket."""
        result = S01DefinerResult()
        result.cgrf_tier = cgrf_tier

        # 1. Schema validation: required fields
        for field_name in self.REQUIRED_FIELDS:
            value = getattr(sapient, field_name, None)
            if not value:
                result.add_violation(f"Missing required field: {field_name}")

        # 2. Risk score range check
        if not (0.0 <= sapient.guardian_risk_score <= 1.0):
            result.add_violation(
                f"guardian_risk_score out of range: {sapient.guardian_risk_score}"
            )

        # 3. CAPS eligibility for CGRF tier
        profile = caps_profile or get_default_profile("pipeline_agent")
        result.caps_grade = profile.grade.value

        if not profile.meets_tier(cgrf_tier):
            result.add_violation(
                f"CAPS grade {profile.grade.value} does not meet Tier {cgrf_tier} requirement"
            )
            result.caps_meets_tier = False
        else:
            result.caps_meets_tier = True

        # 4. Final decision consistency check
        valid_decisions = ("AUTO_MERGE", "HUMAN_REVIEW", "BLOCKED", "ROLLED_BACK", "")
        if sapient.final_decision not in valid_decisions:
            result.add_violation(f"Unknown final_decision: {sapient.final_decision}")

        logger.debug(
            "S01 DEFINER: valid=%s violations=%d tier=%d caps=%s",
            result.valid, len(result.violations), cgrf_tier, result.caps_grade,
        )
        return result
