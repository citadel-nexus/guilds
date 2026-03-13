"""
VCCClient — thin adapter for the Virtual Construction Crew.

In dry_run mode (default) all methods return stub results without
touching NATS or any external system.  When ``nats_client`` is provided
and ``dry_run=False`` the client publishes to / subscribes from NATS.

CGRF compliance
---------------
_MODULE_NAME    = "vcc_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.contracts.orders import BuildRequest, BuildResult

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "vcc_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


class VCCClient:
    """
    Thin adapter that mediates between OrchestratorV3 and the VCC.

    Parameters
    ----------
    nats_client : optional NATSBridgeClient
        If None the client operates in stub mode regardless of dry_run.
    dry_run : bool
        When True no NATS publishes are sent (returns ``dry_run`` status).
    """

    def __init__(self, nats_client=None, dry_run: bool = True):
        self._nats = nats_client
        self._dry_run = dry_run

    # ── Public API ───────────────────────────────────────────────────────────

    def build(self, request: BuildRequest) -> BuildResult:
        """
        Request a VCC build cycle and return the result.

        In stub/dry_run mode the result is returned immediately.
        In live mode this publishes a build request to NATS and waits
        for ``citadel.vcc.cycle.completed``.
        """
        if self._nats is None:
            logger.info("VCCClient: NATSBridgeClient not set — returning stub BuildResult")
            return BuildResult(order_id=request.order_id, status="stub")

        if self._dry_run:
            logger.info("VCCClient: dry_run=True — returning dry_run BuildResult")
            return BuildResult(order_id=request.order_id, status="dry_run")

        # Live mode: publish build request and wait for CRP cycle completion
        logger.info("VCCClient: publishing build request for order %s", request.order_id)
        self._nats.publish(
            "citadel.vcc.build.request",
            request.to_dict(),
        )
        event = self._nats.wait_for(
            "citadel.vcc.cycle.completed",
            timeout=120,
        )
        if event is None:
            logger.warning("VCCClient: timed out waiting for cycle.completed")
            return BuildResult(order_id=request.order_id, status="error",
                               notes="Timed out waiting for VCC cycle.completed")
        return BuildResult.from_dict({
            "order_id": request.order_id,
            "status": "ok",
            "crp_cycle_id": event.get("cycle_id", ""),
            "metrics": {
                "vcc_test_passed": event.get("vcc_test_passed", 0),
                "vcc_test_failed": event.get("vcc_test_failed", 0),
            },
            "build_checks_passed": event.get("guardrail_pass", True),
        })

    def get_latest_crp(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve the most recent CRP cycle state from Supabase/NATS.

        Returns None in stub/dry_run mode.
        """
        if self._nats is None or self._dry_run:
            logger.debug("VCCClient.get_latest_crp: stub mode — returning None")
            return None

        # Live: query Supabase vcc_loop_state for latest CRP row
        logger.info("VCCClient: fetching latest CRP state")
        return None  # placeholder until Supabase query is wired in MS-A3
