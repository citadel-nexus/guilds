"""
DiagnosticsLoop — READ → THINK → WRITE → ASSESS pipeline.

Aggregates telemetry from Supabase, Notion, GitLab, Datadog and Perplexity
into a CitadelHealthSnapshot, emits a DiagnosticsReport, and writes audit
artefacts to Notion/Linear/GitLab (when dry_run=False).

Health gate logic (from BLUEPRINT v9.0):
  If health_grade in ("CRITICAL", "DEGRADING") AND health_score < 60:
    → write go_no_go = "NO-GO" to Supabase vcc_loop_state
    → loop_orchestrator polls and issues pause (Citadel Lite does NOT issue pause)

CGRF compliance
---------------
_MODULE_NAME    = "diagnostics_loop"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "BACKEND_SERVICE"
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.contracts.diagnostics import (
    CitadelHealthSnapshot,
    DiagnosticsReport,
    DiagnosticsRequest,
    HealthCodeMetrics,
    HealthInfraMetrics,
    HealthRevenueMetrics,
    Signal,
)

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "diagnostics_loop"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "BACKEND_SERVICE"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# DEGRADING grade alias used in Blueprint health gate
_CRITICAL_GRADES = {"CRITICAL", "DEGRADING"}


class DiagnosticsLoop:
    """
    Orchestrates the 4-step diagnostic cycle for OrchestratorV3.

    Parameters
    ----------
    perplexity_client : optional PerplexityControlLoopClient
    oad_signal_router : optional OADSignalRouter
    datadog_adapter : optional DatadogAdapter
    supabase_store : optional SupabaseStore / supabase_mca_mirror
    dry_run : bool
    """

    def __init__(
        self,
        perplexity_client=None,
        oad_signal_router=None,
        datadog_adapter=None,
        supabase_store=None,
        dry_run: bool = True,
    ):
        self._pplx = perplexity_client
        self._signal_router = oad_signal_router
        self._datadog = datadog_adapter
        self._supabase = supabase_store
        self._dry_run = dry_run

    # ── Public entry point ────────────────────────────────────────────────────

    def run(
        self,
        order_id: str,
        targets: Optional[List[str]] = None,
        dry_run: Optional[bool] = None,
    ) -> DiagnosticsReport:
        """
        Execute the full READ→THINK→WRITE→ASSESS cycle.

        Parameters
        ----------
        order_id : str   — correlates report to an OrchestratorV3 order
        targets : list   — data sources to query (default: all)
        dry_run : bool   — override instance-level dry_run if provided

        Returns
        -------
        DiagnosticsReport
        """
        effective_dry_run = self._dry_run if dry_run is None else dry_run
        diag_id = f"DIAG-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

        logger.info("DiagnosticsLoop.run: order=%s diag=%s dry_run=%s",
                    order_id, diag_id, effective_dry_run)

        # ── READ ──────────────────────────────────────────────────────────────
        telemetry = self._read(order_id, targets, effective_dry_run)

        # ── THINK ─────────────────────────────────────────────────────────────
        snapshot = self._think(order_id, diag_id, telemetry)

        # ── Health gate: write NO-GO to Supabase if critical ─────────────────
        if snapshot.health_grade in _CRITICAL_GRADES and snapshot.health_score < 60:
            self._write_no_go(snapshot, effective_dry_run)

        # ── WRITE ─────────────────────────────────────────────────────────────
        self._write(snapshot, effective_dry_run)

        # ── ASSESS ────────────────────────────────────────────────────────────
        self._assess(snapshot, effective_dry_run)

        report = DiagnosticsReport(
            order_id=order_id,
            verdict=self._map_verdict(snapshot.health_grade),
            risk=100 - snapshot.health_score,
            blockers=snapshot.blockers,
            outputs={
                "diag_id": diag_id,
                "health_grade": snapshot.health_grade,
                "health_score": snapshot.health_score,
                "go_no_go": snapshot.go_no_go,
                "snapshot": snapshot.to_dict(),
            },
        )
        logger.info("DiagnosticsLoop.run: verdict=%s risk=%s", report.verdict, report.risk)
        return report

    # ── READ ──────────────────────────────────────────────────────────────────

    def _read(
        self,
        order_id: str,
        targets: Optional[List[str]],
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Gather telemetry from all configured sources."""
        data: Dict[str, Any] = {
            "order_id": order_id,
            "signals": [],
            "perplexity": None,
            "supabase": None,
        }

        # OAD signals (REFLEX OBSERVE)
        if self._signal_router:
            try:
                signals = self._signal_router.pull_latest_signals()
                data["signals"] = [s.to_dict() for s in signals]
                logger.debug("DiagnosticsLoop._read: %d signals", len(signals))
            except Exception as e:
                logger.warning("DiagnosticsLoop._read: signal_router error: %s", e)

        # Perplexity Control Loop diagnostics
        if self._pplx:
            try:
                request = DiagnosticsRequest(order_id=order_id,
                                             mode="dry_run" if dry_run else "live")
                pplx_report = self._pplx.run(request)
                data["perplexity"] = pplx_report.to_dict()
            except Exception as e:
                logger.warning("DiagnosticsLoop._read: perplexity error: %s", e)

        return data

    # ── THINK ─────────────────────────────────────────────────────────────────

    def _think(
        self,
        order_id: str,
        diag_id: str,
        telemetry: Dict[str, Any],
    ) -> CitadelHealthSnapshot:
        """Merge telemetry into a CitadelHealthSnapshot."""
        pplx = telemetry.get("perplexity") or {}
        signals: List[Dict[str, Any]] = telemetry.get("signals", [])

        # Derive health grade/score from Perplexity output (or defaults)
        health_grade = pplx.get("verdict", "UNKNOWN")
        # Map DiagnosticsReport verdict back to health_grade
        verdict_to_grade = {
            "OK": "HEALTHY", "DEGRADED": "DEGRADING",
            "RECOVERING": "RECOVERING", "CRITICAL": "CRITICAL", "UNKNOWN": "UNKNOWN",
        }
        health_grade = verdict_to_grade.get(health_grade, health_grade)
        health_score = max(0, min(100, 100 - pplx.get("risk", 0)))

        # Blockers from Perplexity + critical signals
        blockers = list(pplx.get("blockers", []))
        for sig in signals:
            if sig.get("priority") == "critical":
                blockers.append(f"{sig.get('source')}: {sig.get('event_type')}")

        # GO / NO-GO decision
        go_no_go = "GO"
        if health_grade in _CRITICAL_GRADES and health_score < 60:
            go_no_go = "NO-GO"
        elif blockers:
            go_no_go = "WARNING"

        snapshot = CitadelHealthSnapshot(
            snapshot_id=f"HEALTH-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="merged",
            overall_grade=health_grade,
            overall_score=health_score,
            code=HealthCodeMetrics(),
            infrastructure=HealthInfraMetrics(),
            revenue=HealthRevenueMetrics(),
            diag_id=diag_id,
            health_grade=health_grade,
            health_score=health_score,
            l3_verdict=pplx.get("outputs", {}).get("mode", ""),
            go_no_go=go_no_go,
            blockers=blockers,
            recommendations=list(pplx.get("actions", [])),
        )
        return snapshot

    # ── WRITE ─────────────────────────────────────────────────────────────────

    def _write(self, snapshot: CitadelHealthSnapshot, dry_run: bool) -> None:
        """Write diagnostics report to Notion / Linear / GitLab (stubs)."""
        if dry_run:
            logger.debug("DiagnosticsLoop._write: dry_run — skip writes")
            return
        logger.info("DiagnosticsLoop._write: writing report (MS-A3 stub)")

    def _write_no_go(self, snapshot: CitadelHealthSnapshot, dry_run: bool) -> None:
        """Write NO-GO state to Supabase vcc_loop_state."""
        if dry_run or self._supabase is None:
            logger.info(
                "DiagnosticsLoop: health gate triggered — NO-GO (grade=%s score=%s) [%s]",
                snapshot.health_grade, snapshot.health_score,
                "dry_run" if dry_run else "no supabase client",
            )
            return
        try:
            self._supabase.upsert("vcc_loop_state", {
                "loop_source": "orchestrator",
                "cycle_id": snapshot.crp_cycle_id or "",
                "go_no_go": "NO-GO",
                "blocking_reasons": snapshot.blockers,
                "health_grade": snapshot.health_grade,
                "health_score": snapshot.health_score,
            })
            logger.warning(
                "DiagnosticsLoop: NO-GO written to vcc_loop_state (grade=%s score=%s)",
                snapshot.health_grade, snapshot.health_score,
            )
        except Exception as e:
            logger.error("DiagnosticsLoop._write_no_go error: %s", e)

    # ── ASSESS ────────────────────────────────────────────────────────────────

    def _assess(self, snapshot: CitadelHealthSnapshot, dry_run: bool) -> None:
        """Emit observability metrics."""
        if self._datadog:
            try:
                self._datadog.emit_metric(
                    "citadel.diagnostics.health_score",
                    float(snapshot.health_score),
                    tags=[f"grade:{snapshot.health_grade}", f"go_no_go:{snapshot.go_no_go}"],
                )
                if snapshot.go_no_go == "NO-GO":
                    self._datadog.emit_event(
                        title="Citadel Health Gate: NO-GO",
                        text=f"health_grade={snapshot.health_grade} score={snapshot.health_score}",
                        tags=["alert:citadel_nogo"],
                        alert_type="error",
                    )
            except Exception as e:
                logger.warning("DiagnosticsLoop._assess: datadog error: %s", e)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _map_verdict(health_grade: str) -> str:
        """Map health_grade to DiagnosticsReport verdict."""
        mapping = {
            "HEALTHY": "OK",
            "DEGRADING": "DEGRADED",
            "RECOVERING": "RECOVERING",
            "CRITICAL": "CRITICAL",
        }
        return mapping.get(health_grade, "UNKNOWN")
