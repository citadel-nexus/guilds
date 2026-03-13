"""
Diagnostics contracts — RepairRequest/Result, DiagnosticsRequest/Report,
CitadelHealthSnapshot, Signal dataclasses.

These are the internal contracts passed between Citadel Lite adapters and
the Orchestrator V3.  All fields have safe defaults so that callers can
construct minimal instances without error.

Score / grade naming:
  health_grade / health_score  — from Perplexity Loop (DiagnosticCompletedPayload)
  overall_grade / overall_score — weighted merge (Pplx 40% + guardrail 20% + …)
  caps_grade                   — from VCCSakeReader (T1–T5, MS-C3)

CGRF compliance
---------------
_MODULE_NAME    = "diagnostics"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "CONTRACT"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "diagnostics"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "CONTRACT"
# ─────────────────────────────────────────────────────────────────────────────


# ── Signal ───────────────────────────────────────────────────────────────────

@dataclass
class Signal:
    """
    Normalised signal from OAD signal_router (REFLEX OBSERVE stage input).

    ``should_trigger_reflex=True`` tells OADClient to dispatch a mission.
    """
    signal_id: str = ""
    source: str = ""              # "gitlab" | "datadog" | "posthog" | …
    event_type: str = ""          # "pipeline_failed" | "error_spike" | …
    signal_class: str = "technical"   # "technical" | "business"
    priority: str = "medium"     # "low" | "medium" | "high" | "critical"
    should_trigger_reflex: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "source": self.source,
            "event_type": self.event_type,
            "signal_class": self.signal_class,
            "priority": self.priority,
            "should_trigger_reflex": self.should_trigger_reflex,
            "raw": self.raw,
        }


# ── Repair contracts ─────────────────────────────────────────────────────────

@dataclass
class RepairRequest:
    """Citadel Lite → OAD: request to repair a failed build/test."""
    schema: str = "oad.repair_request.v1"
    order_id: str = ""
    build_result: Dict[str, Any] = field(default_factory=dict)
    test_failures: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "order_id": self.order_id,
            "build_result": self.build_result,
            "test_failures": self.test_failures,
            "signals": self.signals,
        }


@dataclass
class RepairResult:
    """OAD → Citadel Lite: result of an OAD repair cycle."""
    schema: str = "oad.repair_result.v1"
    order_id: str = ""
    status: str = "ok"           # "ok" | "partial" | "failed" | "stub"
    patches_applied: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "order_id": self.order_id,
            "status": self.status,
            "patches_applied": self.patches_applied,
            "notes": self.notes,
        }


# ── Diagnostics contracts ─────────────────────────────────────────────────────

@dataclass
class DiagnosticsRequest:
    """Citadel Lite → Perplexity Loop: request a diagnostic run."""
    schema: str = "pplx.diagnostics_request.v1"
    order_id: str = ""
    windows: Dict[str, Any] = field(default_factory=lambda: {"dd_hours": 6, "ph_days": 14})
    targets: List[str] = field(default_factory=lambda: [
        "gitlab", "supabase", "notion", "datadog", "posthog", "stripe", "metabase"
    ])
    mode: str = "dry_run"        # "dry_run" | "live"
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "order_id": self.order_id,
            "windows": self.windows,
            "targets": self.targets,
            "mode": self.mode,
            "context": self.context,
        }


@dataclass
class DiagnosticsReport:
    """Perplexity Loop → Citadel Lite: result of a diagnostic run."""
    schema: str = "pplx.diagnostics_report.v1"
    order_id: str = ""
    verdict: str = "UNKNOWN"     # "OK" | "DEGRADED" | "RECOVERING" | "CRITICAL"
    risk: int = 0                # 0–100
    blockers: List[str] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "order_id": self.order_id,
            "verdict": self.verdict,
            "risk": self.risk,
            "blockers": self.blockers,
            "actions": self.actions,
            "outputs": self.outputs,
        }


# ── Health snapshot sub-dataclasses ──────────────────────────────────────────

@dataclass
class HealthServiceStatus:
    name: str = ""
    port: Optional[int] = None
    status: str = "unknown"      # "up" | "down" | "unknown"
    latency_p95_ms: Optional[float] = None


@dataclass
class HealthInfraMetrics:
    nats_connections: int = 0
    cpu_pct: float = 0.0
    memory_pct: float = 0.0


@dataclass
class HealthCodeMetrics:
    pipeline_pass_rate: float = 0.0
    vcc_test_passed: int = 0
    vcc_test_failed: int = 0
    coverage_pct: float = 0.0
    caps_grade: str = "UNKNOWN"   # T1–T5 via VCCSakeReader (MS-C3)


@dataclass
class HealthRevenueMetrics:
    mrr_cents: int = 0
    active_subscriptions: int = 0


# ── CitadelHealthSnapshot ─────────────────────────────────────────────────────

@dataclass
class CitadelHealthSnapshot:
    """
    Merged health view used by OrchestratorV3.decide() and loop_orchestrator.

    ``health_grade`` / ``health_score`` come from Perplexity Loop output.
    ``overall_grade`` / ``overall_score`` are the weighted merge result
    (computed by merge_health()).
    ``go_no_go`` is the final gate decision.
    """
    snapshot_id: str = ""
    timestamp: str = ""
    source: str = "merged"       # "merged" | "crp" | "perplexity" | "stub"

    # Weighted merge result
    overall_grade: str = "UNKNOWN"
    overall_score: int = 0

    # Per-source metrics
    services: List[HealthServiceStatus] = field(default_factory=list)
    infrastructure: HealthInfraMetrics = field(default_factory=HealthInfraMetrics)
    code: HealthCodeMetrics = field(default_factory=HealthCodeMetrics)
    revenue: HealthRevenueMetrics = field(default_factory=HealthRevenueMetrics)

    # CRP cycle info
    crp_cycle_id: str = ""
    guardrail_pass: bool = True
    drift_clean: bool = True
    sla_compliant: bool = True

    # Perplexity diagnostics
    diag_id: str = ""
    health_grade: str = "UNKNOWN"
    health_score: int = 0
    l3_verdict: str = ""

    # Decision gate
    go_no_go: str = "GO"         # "GO" | "NO-GO" | "WARNING"
    blockers: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "overall_grade": self.overall_grade,
            "overall_score": self.overall_score,
            "services": [
                {"name": s.name, "port": s.port, "status": s.status,
                 "latency_p95_ms": s.latency_p95_ms}
                for s in self.services
            ],
            "infrastructure": {
                "nats_connections": self.infrastructure.nats_connections,
                "cpu_pct": self.infrastructure.cpu_pct,
                "memory_pct": self.infrastructure.memory_pct,
            },
            "code": {
                "pipeline_pass_rate": self.code.pipeline_pass_rate,
                "vcc_test_passed": self.code.vcc_test_passed,
                "vcc_test_failed": self.code.vcc_test_failed,
                "coverage_pct": self.code.coverage_pct,
                "caps_grade": self.code.caps_grade,
            },
            "revenue": {
                "mrr_cents": self.revenue.mrr_cents,
                "active_subscriptions": self.revenue.active_subscriptions,
            },
            "crp_cycle_id": self.crp_cycle_id,
            "guardrail_pass": self.guardrail_pass,
            "drift_clean": self.drift_clean,
            "sla_compliant": self.sla_compliant,
            "diag_id": self.diag_id,
            "health_grade": self.health_grade,
            "health_score": self.health_score,
            "l3_verdict": self.l3_verdict,
            "go_no_go": self.go_no_go,
            "blockers": self.blockers,
            "recommendations": self.recommendations,
        }
