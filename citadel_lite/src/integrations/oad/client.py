"""
OADClient — thin adapter for OAD (Oracle Augmented Diagnostics).

Repair requests dispatch missions to OAD via NATS and wait for completion.
In dry_run mode no external calls are made.

CGRF compliance
---------------
_MODULE_NAME    = "oad_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from src.contracts.diagnostics import RepairRequest, RepairResult, Signal
from src.integrations.oad.signal_router import OADSignalRouter

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "oad_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


class OADClient:
    """
    Adapter that mediates between OrchestratorV3 and the OAD system.

    Parameters
    ----------
    nats_client : optional NATSBridgeClient
    dry_run : bool
    """

    def __init__(self, nats_client=None, dry_run: bool = True):
        self._nats = nats_client
        self._dry_run = dry_run
        self._signal_router = OADSignalRouter(dry_run=dry_run)

    # ── Public API ───────────────────────────────────────────────────────────

    def repair(self, request: RepairRequest) -> RepairResult:
        """
        Request OAD to repair a failed build/test cycle.

        Publishes ``citadel.oad.mission.dispatched`` and waits for
        ``citadel.oad.mission.completed``.
        """
        if self._nats is None:
            logger.info("OADClient: stub mode — returning stub RepairResult")
            return RepairResult(order_id=request.order_id, status="stub")

        if self._dry_run:
            logger.info("OADClient: dry_run=True — returning dry_run RepairResult")
            return RepairResult(order_id=request.order_id, status="dry_run")

        return self.dispatch_mission(
            order_id=request.order_id,
            mission_type="reflex",
            payload=request.to_dict(),
        )

    def dispatch_mission(
        self,
        order_id: str,
        mission_type: str = "cognition",
        payload: Optional[dict] = None,
        rig_target: str = "rig1",
        priority: str = "high",
    ) -> RepairResult:
        """
        Dispatch an OAD mission and wait for its completion.

        This is the only method that publishes ``citadel.oad.mission.dispatched``.
        """
        if self._nats is None or self._dry_run:
            logger.debug("OADClient.dispatch_mission: stub/dry_run")
            return RepairResult(order_id=order_id, status="stub" if self._nats is None else "dry_run")

        mission_id = f"MISSION-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        logger.info("OADClient: dispatching mission %s (type=%s)", mission_id, mission_type)

        self._nats.publish(
            "citadel.oad.mission.dispatched",
            {
                "mission_id": mission_id,
                "rig_target": rig_target,
                "mission_type": mission_type,
                "payload": payload or {},
                "priority": priority,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        event = self._nats.wait_for("citadel.oad.mission.completed", timeout=120)
        if event is None:
            logger.warning("OADClient: timed out waiting for mission.completed")
            return RepairResult(order_id=order_id, status="error",
                                notes="Timed out waiting for OAD mission.completed")

        return RepairResult(
            order_id=order_id,
            status=event.get("status", "ok"),
            patches_applied=event.get("result", {}).get("patches", []),
        )

    def pull_latest_signals(self) -> List[Signal]:
        """Delegate to OADSignalRouter.pull_latest_signals()."""
        return self._signal_router.pull_latest_signals()
