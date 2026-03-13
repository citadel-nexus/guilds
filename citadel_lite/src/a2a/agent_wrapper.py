# src/a2a/agent_wrapper.py
"""
Wraps agent functions as A2A-protocol-compatible handlers.

- build_protocol_v2() → Enhanced agents with memory awareness, richer diagnosis,
                          variable risk scoring, and responsible AI policies
- build_protocol()    → Alias for build_protocol_v2() (backward compatibility)
"""
from __future__ import annotations

from typing import Callable, Dict, Any, List

from src.types import HandoffPacket, Decision
from src.a2a.protocol import A2AMessage, AgentCard, AgentHandler, A2AProtocol

# Enhanced agents
from src.agents.sentinel_v2 import run_sentinel_v2
from src.agents.sherlock_v3 import run_sherlock_v3
from src.agents.fixer_v3 import run_fixer_v3
from src.agents.guardian_v3 import run_guardian_v3

# AWS agent (infrastructure control)
from src.agents.aws_agent import register_aws_agent

# Infrastructure agents (Watcher → Scaler → Curator ecosystem)
from src.agents.watcher_v2 import run_watcher_v2
from src.agents.scaler_v2 import run_scaler_v2
from src.agents.curator_v2 import run_curator_v2

# Budget agent (cost tracking, alerts, Datadog + PostHog integration)
from src.agents.budget_v2 import run_budget_v2

# Migration orchestrator (VPS ↔ ECS workload migration)
from src.agents.migrate_orchestrator import run_migrate_v2

# Autonomous development agents (Intent → Sandbox → Merge Gate → Rollback)
from src.agents.intent_generator import run_intent_generator
from src.agents.sandbox_executor import run_sandbox_executor
from src.agents.merge_gate import run_merge_gate
from src.agents.rollback_agent import run_rollback_agent

# College/Council bridge agents (code analysis + governance deliberation)
from src.agents.college_bridge import run_college_bridge
from src.agents.council_bridge import run_council_bridge

# Security agents (adversarial resilience)
from src.agents.nemesis_v2 import run_nemesis_v2


def _wrap_dict_agent(name: str, fn: Callable[[HandoffPacket], Dict[str, Any]]) -> AgentHandler:
    """Wrap an agent function that returns a plain dict."""
    def handler(msg: A2AMessage) -> A2AMessage:
        result = fn(msg.packet)
        msg.packet.add_output(name, result)
        return msg
    return handler


def _wrap_guardian(fn: Callable[[HandoffPacket], Decision]) -> AgentHandler:
    """Wrap Guardian, which returns a Decision dataclass instead of dict."""
    def handler(msg: A2AMessage) -> A2AMessage:
        decision = fn(msg.packet)
        payload = {
            "action": decision.action,
            "risk_score": decision.risk_score,
            "rationale": decision.rationale,
            "policy_refs": decision.policy_refs,
        }
        # Include CGRF metadata if available (Guardian stores it in artifacts)
        if hasattr(msg.packet, "artifacts") and isinstance(msg.packet.artifacts, dict):
            cgrf_meta = msg.packet.artifacts.get("guardian_cgrf_metadata")
            if cgrf_meta:
                payload["cgrf_metadata"] = cgrf_meta
        msg.packet.add_output("guardian", payload)
        # Stash the Decision object on the message for the orchestrator to read
        msg.packet.risk = {
            "decision": decision,
            "risk_score": decision.risk_score,
        }
        return msg
    return handler


# ---------- Public API ----------

# Enhanced agents
_AGENTS_V2 = [
    ("sentinel", run_sentinel_v2, ["detect", "classify", "signal_extraction"]),
    ("sherlock", run_sherlock_v3, ["diagnose", "root_cause", "memory_aware"]),
    ("fixer",   run_fixer_v3,    ["propose_fix", "patch", "memory_informed", "variable_risk"]),
]

# Infrastructure agents (Watcher → Scaler → Curator → Budget pipeline)
_INFRA_AGENTS = [
    ("watcher", run_watcher_v2, ["monitor", "detect", "health_check", "metric_analysis"]),
    ("scaler",  run_scaler_v2,  ["auto_scale", "task_dispatch", "resource_allocate", "compute_route"]),
    ("migrator", run_migrate_v2, ["migrate", "offload", "rebalance", "route_switch", "vps_to_ecs"]),
    ("curator", run_curator_v2, ["s3_lifecycle", "data_tiering", "cost_optimize", "retention_policy"]),
    ("budget",  run_budget_v2,  ["cost_track", "budget_enforce", "spend_alert", "datadog_push", "posthog_push"]),
]

# Autonomous development agents (closed-loop self-development)
_AUTODEV_AGENTS = [
    ("intent_generator", run_intent_generator, ["intent_create", "issue_scan", "gap_detect"]),
    ("college",          run_college_bridge,    ["code_analysis", "quality_check", "professor_review"]),
    ("council",          run_council_bridge,    ["governance", "sake_deliberation", "4_seat_voting"]),
    ("sandbox",          run_sandbox_executor,  ["test_isolate", "code_verify", "sandbox_run"]),
    ("merge_gate",       run_merge_gate,        ["merge_evaluate", "risk_gate", "autonomy_check"]),
    ("rollback",         run_rollback_agent,     ["rollback_plan", "regression_detect", "remediation"]),
]


# Security agents (Nemesis adversarial resilience system)
_SECURITY_AGENTS = [
    ("nemesis", run_nemesis_v2, ["adversary_detect", "sanctions", "collusion_detect", "audit"]),
]


def build_protocol() -> A2AProtocol:
    """Alias for build_protocol_v2() — kept for backward compatibility."""
    return build_protocol_v2()


def build_protocol_v2() -> A2AProtocol:
    """
    Create an A2AProtocol with enhanced agents:
    - Richer classification and signal extraction
    - Memory-aware diagnosis with confidence scoring
    - Diagnosis-driven fix proposals with variable risk
    - Multi-factor governance with policy engine and responsible AI
    """
    proto = A2AProtocol()

    for name, fn, caps in _AGENTS_V2:
        card = AgentCard(name=name, capabilities=caps, version="2.0.0")
        proto.register(card, _wrap_dict_agent(name, fn))

    guardian_card = AgentCard(
        name="guardian",
        capabilities=["governance", "risk_gate", "policy_engine", "responsible_ai"],
        version="2.0.0",
    )
    proto.register(guardian_card, _wrap_guardian(run_guardian_v3))

    # Register infrastructure agents (Watcher → Scaler → Curator)
    for name, fn, caps in _INFRA_AGENTS:
        card = AgentCard(name=name, capabilities=caps, version="2.0.0")
        proto.register(card, _wrap_dict_agent(name, fn))

    # Register autonomous development agents
    for name, fn, caps in _AUTODEV_AGENTS:
        card = AgentCard(name=name, capabilities=caps, version="2.0.0")
        proto.register(card, _wrap_dict_agent(name, fn))

    # Register security agents (Nemesis adversarial resilience)
    for name, fn, caps in _SECURITY_AGENTS:
        card = AgentCard(name=name, capabilities=caps, version="2.0.0")
        proto.register(card, _wrap_dict_agent(name, fn))

    # Register AWS infrastructure agent (ECS, Bedrock, S3, CloudWatch)
    try:
        register_aws_agent(proto)
    except Exception:
        pass  # AWS agent is optional — skip if boto3 or AWS credentials unavailable

    return proto


def get_decision_from_packet(packet: HandoffPacket) -> Decision:
    """Extract the Decision object stashed by the Guardian wrapper."""
    risk = packet.risk or {}
    decision = risk.get("decision")
    if isinstance(decision, Decision):
        return decision
    # Fallback: reconstruct from guardian output
    g_out = packet.agent_outputs.get("guardian")
    if g_out:
        return Decision(
            action=g_out.payload.get("action", "block"),
            risk_score=g_out.payload.get("risk_score", 1.0),
            rationale=g_out.payload.get("rationale", ""),
            policy_refs=g_out.payload.get("policy_refs", []),
        )
    return Decision(action="block", risk_score=1.0, rationale="no guardian output")
