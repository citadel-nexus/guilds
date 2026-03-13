# src/types.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid


# ---------- Event JSON v1 ----------

@dataclass
class EventArtifact:
    log_excerpt: Optional[str] = None
    links: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventJsonV1:
    schema_version: str = "event_json_v1"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    source: str = ""
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))

    repo: Optional[str] = None
    ref: Optional[str] = None
    summary: Optional[str] = None
    artifacts: EventArtifact = field(default_factory=EventArtifact)


# ---------- A2A Handoff Packet ----------

@dataclass
class AgentOutput:
    name: str
    payload: Any


@dataclass
class HandoffPacket:
    event: EventJsonV1
    artifacts: Dict[str, Any] = field(default_factory=dict)

    memory_hits: List["MemoryHit"] = field(default_factory=list)
    agent_outputs: Dict[str, AgentOutput] = field(default_factory=dict)

    risk: Dict[str, Any] = field(default_factory=dict)
    audit_span_id: Optional[str] = None

    def add_output(self, name: str, payload: Dict[str, Any]) -> None:
        self.agent_outputs[name] = AgentOutput(name=name, payload=payload)


# ---------- Guardian Decision ----------

@dataclass
class Decision:
    action: str  # approve | need_approval | block
    risk_score: float
    rationale: str
    policy_refs: List[str] = field(default_factory=list)


# ---------- CGRF Metadata ----------

@dataclass
class CGRFMetadata:
    """
    CGRF v3.0 Module Metadata (MCHS-META standard)
    Represents governance tier, versioning, and execution context.

    Based on blueprints/CGRF.txt Section 10 "Module Metadata Standards (MCHS-META)"
    """
    report_id: str  # e.g., "SRS-SENTINEL-20260211-001-V3.0"
    tier: int  # 0 (experimental), 1 (dev), 2 (production), 3 (mission-critical)
    module_version: str  # e.g., "2.1.0"
    module_name: str  # e.g., "sentinel_v2"
    execution_role: str  # BACKEND_SERVICE | FRONTEND_SERVICE | DATA_PIPELINE | ...
    created: str  # ISO timestamp
    author: str  # "agent" or "human" or specific identifier
    last_updated: Optional[str] = None  # ISO timestamp

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryHit:
    """
    Minimal memory hit contract for MVP.
    Keep this stable; agents/audit depend on this shape.
    """
    memory_id: str
    title: str
    summary: str
    tags: List[str]
    confidence: float
    evidence: List[str]
    source: str = "mock_memory_v0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------- SapientPacket — Autonomous Decision Audit ----------

@dataclass
class SapientPacket:
    """
    Complete audit envelope for autonomous development decisions.

    Every autonomous action (code generation, merge, deploy, rollback)
    produces a SapientPacket for full traceability.

    Sections S00-S07 map to the pipeline stages.
    """
    # S00: Decision metadata
    packet_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
    action_type: str = ""  # code_generation | merge | deploy | rollback
    autonomy_budget_at_decision: float = 0.0

    # S01: Intent provenance
    intent_source: str = ""  # github_issue | watcher_finding | college_gap | rollback
    intent_id: str = ""
    intent_priority: float = 0.0

    # S02: Processing trace
    sake_envelope_hash: str = ""
    college_professors_consulted: List[str] = field(default_factory=list)
    college_aggregation_time_ms: int = 0

    # S03: Council deliberation
    council_votes: Dict[str, str] = field(default_factory=dict)
    council_confidence: float = 0.0
    dissent_reasons: List[str] = field(default_factory=list)

    # S04: Risk assessment
    guardian_risk_score: float = 0.0
    risk_factors: List[Dict[str, Any]] = field(default_factory=list)
    fate_recommendation: str = ""  # proceed | review | block

    # S05: Execution record
    code_diff_hash: str = ""
    test_results_hash: str = ""
    sandbox_exit_code: int = -1
    coverage_percentage: float = 0.0
    generation_mode: str = ""  # llm | template

    # S06: Outcome
    final_decision: str = ""  # AUTO_MERGE | HUMAN_REVIEW | BLOCKED | ROLLED_BACK
    merge_commit_hash: Optional[str] = None
    deployment_id: Optional[str] = None

    # S07: Post-deployment monitoring
    canary_health_score: Optional[float] = None
    regression_detected: bool = False
    rollback_triggered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)