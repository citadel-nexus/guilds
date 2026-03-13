"""
S00 GENERATOR - Normalize mutation intent into SapientPacket format.

Reads the HandoffPacket and Guardian Decision to populate the SapientPacket
sections S00-S06 with available pipeline context.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from src.types import Decision, HandoffPacket, SapientPacket

logger = logging.getLogger(__name__)


class S00Generator:
    """
    Stage S00: Generate a SapientPacket from pipeline context.

    Input:  HandoffPacket + Decision (from Guardian)
    Output: SapientPacket with sections S00-S06 populated from context
    """

    def run(self, packet: HandoffPacket, decision: Decision) -> SapientPacket:
        """Build a SapientPacket from the current pipeline state."""
        event = packet.event
        sentinel_out = self._get_agent_payload(packet, "sentinel")
        fixer_out = self._get_agent_payload(packet, "fixer")

        final_decision_map = {
            "approve": "AUTO_MERGE",
            "need_approval": "HUMAN_REVIEW",
            "block": "BLOCKED",
        }

        sapient = SapientPacket(
            # S00: Decision metadata
            action_type=self._infer_action_type(event.event_type),
            autonomy_budget_at_decision=1.0 - decision.risk_score,

            # S01: Intent provenance
            intent_source=event.source or "unknown",
            intent_id=event.event_id,
            intent_priority=sentinel_out.get("severity_weight", 0.5),

            # S04: Risk assessment
            guardian_risk_score=decision.risk_score,
            risk_factors=self._extract_risk_factors(decision, sentinel_out),
            fate_recommendation=self._map_action_to_fate(decision.action),

            # S05: Execution record (partial - execution hasn't happened yet)
            generation_mode=fixer_out.get("generation_mode", "rule"),

            # S06: Outcome
            final_decision=final_decision_map.get(decision.action, "BLOCKED"),
        )

        # S03: Council deliberation (from guardian)
        sapient.council_votes = {"guardian": decision.action}
        sapient.council_confidence = 1.0 - decision.risk_score
        if decision.action == "block":
            sapient.dissent_reasons = [decision.rationale]

        logger.debug("S00 GENERATOR produced packet_id=%s", sapient.packet_id)
        return sapient

    @staticmethod
    def _get_agent_payload(packet: HandoffPacket, agent_name: str) -> Dict[str, Any]:
        out = packet.agent_outputs.get(agent_name)
        if out is None:
            return {}
        return out.payload if hasattr(out, "payload") else {}

    @staticmethod
    def _infer_action_type(event_type: str) -> str:
        mapping = {
            "ci_failed": "code_generation",
            "deploy_failed": "deploy",
            "security_alert": "code_generation",
            "test_regression": "code_generation",
            "config_drift": "code_generation",
        }
        return mapping.get(event_type, "code_generation")

    @staticmethod
    def _map_action_to_fate(action: str) -> str:
        return {"approve": "proceed", "need_approval": "review", "block": "block"}.get(action, "block")

    @staticmethod
    def _extract_risk_factors(decision: Decision, sentinel_out: Dict[str, Any]) -> list:
        factors = []
        if decision.risk_score >= 0.65:
            factors.append({"factor": "high_risk_score", "value": decision.risk_score})
        signals = sentinel_out.get("signals", [])
        if "security_vulnerability" in signals:
            factors.append({"factor": "security_vulnerability", "value": True})
        severity = sentinel_out.get("severity", "medium")
        if severity in ("high", "critical"):
            factors.append({"factor": f"severity_{severity}", "value": True})
        return factors
