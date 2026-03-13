"""
Pydantic schemas for Citadel Lite NATS JetStream event payloads.

Each class mirrors a NATS subject payload.  The ``CitadelNATSEnvelope``
wraps incoming messages for internal audit/tracing — upstream payloads
are never mutated.

Subjects covered:
  citadel.vcc.cycle.completed     → CycleCompletedPayload
  citadel.diagnostic.completed    → DiagnosticCompletedPayload
  citadel.test.completed          → TestCompletedPayload
  citadel.vcc.build.pause/resume  → BuildControlPayload
  citadel.oad.reflex.applied      → ReflexAppliedPayload
  citadel.oad.mission.dispatched  → MissionDispatchPayload
  citadel.oad.mission.completed   → MissionCompletedPayload
  (internal wrapper)              → CitadelNATSEnvelope

CGRF compliance
---------------
_MODULE_NAME    = "schemas"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "CONTRACT"
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, Field
    _HAS_PYDANTIC = True
except ImportError:  # pragma: no cover
    _HAS_PYDANTIC = False
    # Provide a minimal fallback so the module can be imported without pydantic
    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **data: Any):
            for k, v in data.items():
                setattr(self, k, v)
    def Field(default=None, **_kw):  # type: ignore[misc]
        return default

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "schemas"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "CONTRACT"
# ─────────────────────────────────────────────────────────────────────────────


class CycleCompletedPayload(BaseModel):
    """citadel.vcc.cycle.completed — emitted by vcc_cycle_reporter."""
    cycle_id: str = ""
    guild: str = ""
    phase: str = ""
    crp_version: str = "2.1"
    guardrail_pass: bool = True
    drift_clean: bool = True
    # NOTE: vcc_test_* = Finance Guild unit tests run by CRP (NOT Citadel Lite tests)
    vcc_test_passed: int = 0
    vcc_test_failed: int = 0
    srs_codes_touched: Dict[str, str] = Field(default_factory=dict)
    health_status: str = "healthy"
    sla_compliant: bool = True
    notion_page_id: str = ""
    timestamp: str = ""


class DiagnosticCompletedPayload(BaseModel):
    """citadel.diagnostic.completed — emitted by perplexity_control_loop_v2."""
    diag_id: str = ""
    health_grade: str = "UNKNOWN"   # "HEALTHY" | "DEGRADED" | "RECOVERING" | "CRITICAL"
    health_score: int = 0           # 0–100
    blockers: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    sources_read: List[str] = Field(default_factory=list)
    l3_verdict: str = ""
    pipeline_pass_rate: float = 0.0
    nats_connections: int = 0
    mrr_cents: int = 0
    triggered_by: str = ""
    crp_cycle_id: str = ""
    timestamp: str = ""


class TestCompletedPayload(BaseModel):
    """citadel.test.completed — emitted by OrchestratorV3 / ExecutionRunner."""
    order_id: str = ""
    crp_cycle_id: str = ""
    all_success: bool = False
    steps_total: int = 0
    steps_passed: int = 0
    steps_failed: int = 0
    simulated: bool = False
    timestamp: str = ""


class BuildControlPayload(BaseModel):
    """
    citadel.vcc.build.pause / citadel.vcc.build.resume

    IMPORTANT: Only loop_orchestrator.py should publish these subjects.
    OrchestratorV3 must NOT publish pause/resume directly.
    """
    action: str = ""             # "pause" | "resume"
    cycle_id: str = ""
    reason: str = ""
    issued_by: str = "loop_orchestrator"
    timestamp: str = ""


class ReflexAppliedPayload(BaseModel):
    """citadel.oad.reflex.applied — emitted by OAD Reflex Engine."""
    reflex_id: str = ""
    rig: str = ""
    pattern_code: str = ""       # "F924" | "F950" | "F960"
    file_path: str = ""
    fix_description: str = ""
    before_hash: str = ""
    after_hash: str = ""
    timestamp: str = ""


class MissionDispatchPayload(BaseModel):
    """citadel.oad.mission.dispatched — emitted by OrchestratorV3."""
    mission_id: str = ""
    rig_target: str = ""
    mission_type: str = ""       # "cognition" | "reflex"
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: str = "high"
    timestamp: str = ""


class MissionCompletedPayload(BaseModel):
    """citadel.oad.mission.completed — emitted by OAD."""
    mission_id: str = ""
    rig: str = ""
    status: str = "ok"
    result: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class CitadelNATSEnvelope(BaseModel):
    """
    Internal wrapper applied by NATSBridgeClient on message receipt.

    The upstream payload is stored verbatim in ``payload`` — never mutated.
    Used only for internal audit logs and Datadog traces.

    correlation_id priority: order_id → cycle_id → diag_id → None
    """
    schema: str = "citadel.event.v1"
    event_id: str = ""           # uuid4 assigned by NATSBridgeClient
    event_type: str = ""         # NATS subject (e.g. "citadel.vcc.cycle.completed")
    correlation_id: Optional[str] = None
    received_at: str = ""        # ISO 8601 timestamp
    nats_seq: int = 0            # upstream NATS sequence number
    payload: Dict[str, Any] = Field(default_factory=dict)
