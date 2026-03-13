"""
AGS Pipeline Runner - chains S00 GENERATOR -> S01 DEFINER -> S02 FATE -> S03 ARCHIVIST.

Public API:
    pipeline = AGSPipeline(audit=audit_logger)
    verdict = pipeline.run(packet, decision, cgrf_tier=2)
    # verdict.action -> "approve" | "need_approval" | "block"
    # verdict.escalated -> True if AGS overrode Guardian
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from src.types import Decision, HandoffPacket
from src.audit.logger import AuditLogger
from src.ags.caps_stub import CAPSProfile, get_default_profile, get_ais_profile
from src.ags.s00_generator import S00Generator
from src.ags.s01_definer import S01Definer
from src.ags.s02_fate import S02Fate, AGSVerdictEnum
from src.ags.s03_archivist import S03Archivist

logger = logging.getLogger(__name__)


@dataclass
class AGSVerdict:
    """
    Final AGS pipeline output.

    If escalated is True, the orchestrator should use this verdict's action
    instead of the original Guardian decision.
    """
    action: str                          # "approve" | "need_approval" | "block"
    verdict: str                         # "ALLOW" | "REVIEW" | "DENY"
    risk_score: float
    escalated: bool
    original_guardian_action: str
    sapient_packet_id: str
    rationale: str
    gate_results: List[Dict[str, Any]] = field(default_factory=list)
    definer_violations: List[str] = field(default_factory=list)
    archive_record: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Map AGS verdict enum to Guardian-compatible action strings
_VERDICT_TO_ACTION = {
    AGSVerdictEnum.ALLOW: "approve",
    AGSVerdictEnum.REVIEW: "need_approval",
    AGSVerdictEnum.DENY: "block",
}


class AGSPipeline:
    """
    AGS 4-stage constitutional judiciary pipeline.

    Usage:
        pipeline = AGSPipeline(audit=audit_logger)
        verdict = pipeline.run(packet, decision, cgrf_tier=2)
    """

    def __init__(
        self,
        audit: Optional[AuditLogger] = None,
        caps_profile: Optional[CAPSProfile] = None,
    ) -> None:
        self.audit = audit
        self.caps_profile = caps_profile
        self._s00 = S00Generator()
        self._s01 = S01Definer()
        self._s02 = S02Fate()
        self._s03 = S03Archivist()

    def run(
        self,
        packet: HandoffPacket,
        decision: Decision,
        cgrf_tier: int = 0,
    ) -> AGSVerdict:
        """
        Run the full AGS pipeline.

        Args:
            packet: HandoffPacket from the A2A pipeline
            decision: Guardian Decision
            cgrf_tier: CGRF tier from guardian metadata (default 0)

        Returns:
            AGSVerdict with the final action, verdict, and escalation info
        """
        # S00: Generate SapientPacket
        sapient = self._s00.run(packet, decision)

        # S01: Validate against CGRF tier + CAPS
        profile = self.caps_profile or get_ais_profile("pipeline_agent")
        definer_result = self._s01.run(sapient, cgrf_tier=cgrf_tier, caps_profile=profile)

        # S02: Policy gates + verdict
        fate_result = self._s02.run(sapient, definer_result, decision.action)

        # S03: Archive to audit trail
        archive_record = self._s03.run(sapient, fate_result, audit=self.audit)

        # Build final verdict
        ags_action = _VERDICT_TO_ACTION.get(fate_result.verdict, "block")

        verdict = AGSVerdict(
            action=ags_action,
            verdict=fate_result.verdict.name,
            risk_score=fate_result.risk_score,
            escalated=fate_result.escalated,
            original_guardian_action=decision.action,
            sapient_packet_id=sapient.packet_id,
            rationale=fate_result.rationale,
            gate_results=[
                {"gate_id": g.gate_id, "passed": g.passed, "reason": g.reason}
                for g in fate_result.gate_results
            ],
            definer_violations=definer_result.violations,
            archive_record=archive_record,
        )

        # Stash AGS results on packet.artifacts for downstream audit/report
        if not isinstance(getattr(packet, "artifacts", None), dict):
            packet.artifacts = {}
        packet.artifacts["ags_verdict"] = verdict.to_dict()

        logger.info(
            "AGS Pipeline: verdict=%s action=%s escalated=%s (guardian=%s)",
            verdict.verdict, verdict.action, verdict.escalated, verdict.original_guardian_action,
        )

        return verdict
