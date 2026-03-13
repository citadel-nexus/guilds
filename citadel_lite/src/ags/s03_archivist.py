"""
S03 ARCHIVIST - Record AGS verdict in the hash-chained guardian audit log.

Uses the existing AuditLogger (SHA-256 hash-chaining) so that AGS verdicts
are tamper-evident and form part of the same audit chain as the pipeline.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.types import SapientPacket
from src.audit.logger import AuditLogger
from src.ags.s02_fate import S02FateResult

logger = logging.getLogger(__name__)


class S03Archivist:
    """
    Stage S03: Archive the AGS verdict into the audit trail.

    Input:  SapientPacket + S02FateResult + AuditLogger
    Output: Dict with archive record (packet_id, verdict, hash)
    """

    def run(
        self,
        sapient: SapientPacket,
        fate_result: S02FateResult,
        audit: Optional[AuditLogger] = None,
    ) -> Dict[str, Any]:
        """Record AGS verdict in audit trail and return the archive record."""
        record = {
            "packet_id": sapient.packet_id,
            "verdict": fate_result.verdict.name,
            "risk_score": fate_result.risk_score,
            "escalated": fate_result.escalated,
            "original_guardian_action": fate_result.original_guardian_action,
            "gate_results": [
                {"gate_id": g.gate_id, "passed": g.passed, "reason": g.reason}
                for g in fate_result.gate_results
            ],
            "rationale": fate_result.rationale,
            "intent_source": sapient.intent_source,
            "intent_id": sapient.intent_id,
            "action_type": sapient.action_type,
            "timestamp": sapient.timestamp,
        }

        if audit is not None:
            audit.log("ags.verdict", record)
            logger.info(
                "S03 ARCHIVIST: recorded verdict=%s for packet=%s (escalated=%s)",
                fate_result.verdict.name,
                sapient.packet_id,
                fate_result.escalated,
            )
        else:
            logger.warning("S03 ARCHIVIST: no audit logger provided, verdict not recorded")

        return record
