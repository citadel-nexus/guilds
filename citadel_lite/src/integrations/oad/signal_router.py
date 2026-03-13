"""
OADSignalRouter — normalises raw events into Signal dataclasses.

This corresponds to the OBSERVE stage of the REFLEX pipeline.
Each ``pull_*`` method maps a raw event source into a ``Signal`` with a
consistent schema.  Callers (DiagnosticsLoop, OADClient) consume the
normalised signals to decide whether to trigger a Reflex repair.

CGRF compliance
---------------
_MODULE_NAME    = "signal_router"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from src.contracts.diagnostics import Signal

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "signal_router"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


class OADSignalRouter:
    """
    Collects and normalises signals from GitLab, Datadog, etc.

    In stub mode (no credentials) all methods return an empty list.
    """

    def __init__(self, dry_run: bool = True):
        self._dry_run = dry_run
        self._gitlab_token: Optional[str] = (
            os.getenv("OAD_PAT") or os.getenv("GITLAB_TOKEN")
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def pull_latest_signals(self) -> List[Signal]:
        """
        Collect signals from all configured sources.

        Returns an empty list when dry_run=True or no credentials set.
        """
        signals: List[Signal] = []
        signals.extend(self._pull_gitlab())
        return signals

    # ── Source handlers ──────────────────────────────────────────────────────

    def _pull_gitlab(self) -> List[Signal]:
        if self._dry_run or not self._gitlab_token:
            logger.debug("OADSignalRouter: GitLab stub — no signals")
            return []

        # Placeholder: real implementation queries GitLab pipelines API
        # and maps failed pipelines to Signal(event_type="pipeline_failed")
        logger.info("OADSignalRouter: pulling GitLab signals")
        return []

    # ── Normalisation helpers ────────────────────────────────────────────────

    @staticmethod
    def _make_signal(
        source: str,
        event_type: str,
        signal_class: str = "technical",
        priority: str = "medium",
        should_trigger_reflex: bool = False,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Signal:
        return Signal(
            signal_id=f"sig-{uuid.uuid4().hex[:8]}",
            source=source,
            event_type=event_type,
            signal_class=signal_class,
            priority=priority,
            should_trigger_reflex=should_trigger_reflex,
            raw=raw or {},
        )
