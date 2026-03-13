"""
PerplexityControlLoopClient — adapter for the Perplexity Control Loop v2.

Executes the READ → THINK → WRITE → ASSESS pipeline and returns a
DiagnosticsReport.  In dry_run mode (default) no external APIs are called.

CGRF compliance
---------------
_MODULE_NAME    = "control_loop_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from src.contracts.diagnostics import DiagnosticsReport, DiagnosticsRequest

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "control_loop_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


class PerplexityControlLoopClient:
    """
    Thin adapter for the external Perplexity Control Loop v2.

    Parameters
    ----------
    dry_run : bool
        If True no external API calls are made (returns stub report).
    """

    def __init__(self, dry_run: bool = True):
        self._dry_run = dry_run
        self._api_key: Optional[str] = os.getenv("PPLX_API_KEY")

    # ── Public API ───────────────────────────────────────────────────────────

    def run(self, request: DiagnosticsRequest) -> DiagnosticsReport:
        """
        Execute a full READ→THINK→WRITE→ASSESS diagnostic cycle.

        Returns a stub report when dry_run=True or PPLX_API_KEY is not set.
        """
        if self._dry_run or not self._api_key:
            logger.info(
                "PerplexityControlLoopClient: %s — returning stub DiagnosticsReport",
                "dry_run" if self._dry_run else "PPLX_API_KEY unset",
            )
            return DiagnosticsReport(
                order_id=request.order_id,
                verdict="UNKNOWN",
                risk=0,
                blockers=[],
                outputs={"mode": "stub"},
            )

        # Live path: delegate to the external perplexity_control_loop_v2 process
        # (vault_loader dependency is intentionally NOT imported here — MS-A3 wires this in)
        logger.info(
            "PerplexityControlLoopClient: running live diagnostic for order %s",
            request.order_id,
        )
        return self._run_live(request)

    def _run_live(self, request: DiagnosticsRequest) -> DiagnosticsReport:
        """Placeholder for live Perplexity Loop invocation (wired in MS-A3)."""
        logger.warning("PerplexityControlLoopClient._run_live: not yet wired — returning stub")
        return DiagnosticsReport(
            order_id=request.order_id,
            verdict="UNKNOWN",
            risk=0,
            outputs={"mode": "live_stub"},
        )
