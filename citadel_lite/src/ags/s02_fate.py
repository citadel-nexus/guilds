"""
S02 FATE - Load policy gates, evaluate conditions, produce verdict.

Verdict outcomes:
- ALLOW:  Risk acceptable, proceed to execution
- REVIEW: Needs human review, override Guardian's auto-approve if needed
- DENY:   Blocked by AGS policy, override Guardian's approve if needed

The FATE stage can ESCALATE Guardian decisions (approve -> review, review -> deny)
but never DOWNGRADE them (deny -> review or review -> allow).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List

from src.types import SapientPacket
from src.ags.s01_definer import S01DefinerResult

logger = logging.getLogger(__name__)


class AGSVerdictEnum(Enum):
    """AGS verdict outcomes."""
    ALLOW = auto()
    REVIEW = auto()
    DENY = auto()


@dataclass
class FateGateResult:
    """Result of a single policy gate evaluation."""
    gate_id: str
    passed: bool
    reason: str = ""


@dataclass
class S02FateResult:
    """Complete FATE evaluation result."""
    verdict: AGSVerdictEnum = AGSVerdictEnum.ALLOW
    risk_score: float = 0.0
    gate_results: List[FateGateResult] = field(default_factory=list)
    rationale: str = ""
    escalated: bool = False
    original_guardian_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.name,
            "risk_score": self.risk_score,
            "gate_results": [
                {"gate_id": g.gate_id, "passed": g.passed, "reason": g.reason}
                for g in self.gate_results
            ],
            "rationale": self.rationale,
            "escalated": self.escalated,
            "original_guardian_action": self.original_guardian_action,
        }


class S02Fate:
    """
    Stage S02: Policy gate evaluation and verdict production.

    Input:  SapientPacket + S01DefinerResult + guardian_action
    Output: S02FateResult with verdict, risk score, and gate results
    """

    def __init__(self) -> None:
        self._policy_engine = self._load_policy_engine()

    @staticmethod
    def _load_policy_engine():
        try:
            from src.governance.policy_engine import PolicyEngine
            return PolicyEngine()
        except Exception:
            return None

    def run(
        self,
        sapient: SapientPacket,
        definer_result: S01DefinerResult,
        guardian_action: str,
    ) -> S02FateResult:
        """Evaluate policy gates and produce verdict."""
        result = S02FateResult(
            risk_score=sapient.guardian_risk_score,
            original_guardian_action=guardian_action,
        )

        # Gate 1: S01 Definer passed?
        gate1 = FateGateResult(
            gate_id="GATE-DEFINER",
            passed=definer_result.valid,
            reason="S01 definer validation" + (
                "" if definer_result.valid
                else f": {'; '.join(definer_result.violations)}"
            ),
        )
        result.gate_results.append(gate1)

        # Gate 2: CAPS tier eligibility
        gate2 = FateGateResult(
            gate_id="GATE-CAPS-TIER",
            passed=definer_result.caps_meets_tier,
            reason=f"CAPS {definer_result.caps_grade} for tier {definer_result.cgrf_tier}",
        )
        result.gate_results.append(gate2)

        # Gate 3: Risk score threshold
        risk = sapient.guardian_risk_score
        if risk < 0.25:
            gate3 = FateGateResult(
                gate_id="GATE-RISK-LOW", passed=True,
                reason=f"risk={risk:.3f} < 0.25",
            )
        elif risk < 0.65:
            gate3 = FateGateResult(
                gate_id="GATE-RISK-MED", passed=True,
                reason=f"risk={risk:.3f} in [0.25, 0.65)",
            )
        else:
            gate3 = FateGateResult(
                gate_id="GATE-RISK-HIGH", passed=False,
                reason=f"risk={risk:.3f} >= 0.65",
            )
        result.gate_results.append(gate3)

        # Gate 4: Security signal check
        has_security = any(
            f.get("factor") == "security_vulnerability"
            for f in sapient.risk_factors
        )
        gate4 = FateGateResult(
            gate_id="GATE-SECURITY",
            passed=not has_security,
            reason="security vulnerability detected" if has_security else "no security signals",
        )
        result.gate_results.append(gate4)

        # Gate 5: PolicyEngine compliance (if available)
        if self._policy_engine:
            try:
                compliance = self._policy_engine.check_compliance({
                    "risk_score": risk,
                    "action": guardian_action,
                    "policy_refs": [],
                })
                gate5 = FateGateResult(
                    gate_id="GATE-POLICY-ENGINE",
                    passed=compliance.get("compliant", True),
                    reason=(
                        f"violations: {compliance.get('violations', [])}"
                        if not compliance.get("compliant", True)
                        else "policy compliant"
                    ),
                )
                result.gate_results.append(gate5)
            except Exception as e:
                logger.debug("PolicyEngine check skipped: %s", e)

        # Verdict determination
        failed_gates = [g for g in result.gate_results if not g.passed]
        critical_failures = [
            g for g in failed_gates
            if g.gate_id in ("GATE-DEFINER", "GATE-RISK-HIGH")
        ]

        if critical_failures:
            result.verdict = AGSVerdictEnum.DENY
        elif failed_gates:
            result.verdict = AGSVerdictEnum.REVIEW
        elif risk < 0.25:
            result.verdict = AGSVerdictEnum.ALLOW
        elif risk < 0.65:
            result.verdict = AGSVerdictEnum.REVIEW
        else:
            result.verdict = AGSVerdictEnum.DENY

        # Escalation check: AGS can escalate but never downgrade
        verdict_level = {
            AGSVerdictEnum.ALLOW: 0,
            AGSVerdictEnum.REVIEW: 1,
            AGSVerdictEnum.DENY: 2,
        }
        guardian_level = {"approve": 0, "need_approval": 1, "block": 2}.get(guardian_action, 2)
        ags_level = verdict_level[result.verdict]

        if ags_level > guardian_level:
            result.escalated = True
            logger.warning(
                "AGS ESCALATION: Guardian said '%s' but AGS verdict is %s (gates: %s)",
                guardian_action, result.verdict.name,
                [g.gate_id for g in failed_gates],
            )

        # Build rationale
        rationale_parts = [f"AGS verdict: {result.verdict.name}"]
        if result.escalated:
            rationale_parts.append(f"ESCALATED from guardian={guardian_action}")
        passed = len(result.gate_results) - len(failed_gates)
        rationale_parts.append(f"gates passed: {passed}/{len(result.gate_results)}")
        if failed_gates:
            rationale_parts.append(f"failed: {[g.gate_id for g in failed_gates]}")
        result.rationale = " | ".join(rationale_parts)

        logger.debug("S02 FATE: verdict=%s escalated=%s", result.verdict.name, result.escalated)
        return result
