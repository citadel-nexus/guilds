# src/agents/scaler_v2.py
"""
Scaler Agent — Infrastructure Fixer

Decides and executes scaling actions based on Watcher output.
Manages ECS service scaling and task routing to NATS/Ray.

Pipeline role: Second in Watcher → Scaler → Curator chain.
Analogous to Fixer in the incident pipeline.

Supports two modes:
- LLM mode: Analyzes signals + history for optimal scaling decisions
- Rule mode: Direct threshold-based scaling when no LLM is available

CGRF v3.0 Compliance:
- SRS Code: SRS-SCALER-20260204-001-V3.0
- Tier: 1 (DEVELOPMENT)
- Execution Role: INFRASTRUCTURE

@module citadel_lite.src.agents.scaler_v2
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket

logger = logging.getLogger(__name__)

# Scaling limits
_MAX_TASKS = 3
_MIN_TASKS_WORKSHOP = 1
_MIN_TASKS_WORKER = 0

# Action mapping from Watcher signals to scaling decisions
_SIGNAL_ACTIONS = {
    "cpu_critical": {"action": "scale_up", "target": "worker", "delta": 2},
    "cpu_high": {"action": "scale_up", "target": "worker", "delta": 1},
    "cpu_low": {"action": "scale_down", "target": "worker", "delta": -1},
    "memory_critical": {"action": "scale_up", "target": "worker", "delta": 1},
    "memory_high": {"action": "scale_up", "target": "worker", "delta": 1},
    "container_cpu_high": {"action": "defer_to_migrator", "target": "migrate", "delta": 0},
    "container_mem_high": {"action": "defer_to_migrator", "target": "migrate", "delta": 0},
}


def _run_scaler_llm(packet: HandoffPacket) -> Optional[Dict[str, Any]]:
    """Try LLM-based scaling decision. Returns None if unavailable."""
    try:
        from src.llm.client import LLMClient

        client = LLMClient()
        if not client.is_available():
            return None

        # Get Watcher output
        watcher_out = packet.agent_outputs.get("watcher")
        if not watcher_out:
            return None

        watcher_data = watcher_out.payload if hasattr(watcher_out, "payload") else watcher_out

        system_prompt = (
            "You are an auto-scaling decision agent for the Citadel Nexus platform. "
            "Based on the Watcher's infrastructure analysis, decide what scaling actions "
            "to take. Consider cost optimization (budget ~$300/mo) and service stability. "
            "Respond with JSON containing: action (scale_up|scale_down|dispatch_task|no_action), "
            "target (workshop|worker|ray|nats), current_count (int), proposed_count (int), "
            "risk_estimate (0.0-1.0), rationale (string), execution_plan (list of steps), "
            "verification_steps (list of checks)."
        )

        user_msg = (
            f"Watcher analysis:\n"
            f"- Event type: {watcher_data.get('event_type', 'unknown')}\n"
            f"- Severity: {watcher_data.get('severity', 'unknown')}\n"
            f"- Signals: {watcher_data.get('signals', [])}\n"
            f"- Recommended action: {watcher_data.get('recommended_action', 'none')}\n"
            f"- Metrics: {watcher_data.get('metrics', {})}\n"
        )

        resp = client.complete(system_prompt, user_msg)
        if resp.success and resp.parsed:
            result = resp.parsed
            result.setdefault("action", "no_action")
            result.setdefault("target", "worker")
            result.setdefault("risk_estimate", 0.5)
            result.setdefault("rationale", "LLM-generated scaling decision")
            result.setdefault("execution_plan", [])
            result.setdefault("verification_steps", [])
            result["llm_powered"] = True
            result["llm_usage"] = {
                "backend": resp.usage.backend,
                "tokens": resp.usage.total_tokens,
                "latency_ms": resp.usage.latency_ms,
            }
            logger.info("Scaler LLM decision: %s %s", result["action"], result["target"])
            return result

    except Exception as e:
        logger.warning("Scaler LLM fallback: %s", e)
    return None


def _get_current_service_count(service_key: str) -> int:
    """Get current running count for a service."""
    try:
        from src.agents.aws_agent import ecs_status
        ecs = ecs_status()
        for svc in ecs.get("services", []):
            if service_key in svc.get("name", ""):
                return svc.get("running", 0)
    except Exception:
        pass
    return 0


def _run_scaler_rules(packet: HandoffPacket) -> Dict[str, Any]:
    """Rule-based scaling decision (deterministic fallback)."""
    # Get Watcher output
    watcher_out = packet.agent_outputs.get("watcher")
    watcher_data = {}
    if watcher_out:
        watcher_data = watcher_out.payload if hasattr(watcher_out, "payload") else watcher_out

    event_type = watcher_data.get("event_type", "healthy")
    severity = watcher_data.get("severity", "info")
    signals = watcher_data.get("signals", [])
    recommended = watcher_data.get("recommended_action", "none")

    action = "no_action"
    target = "worker"
    delta = 0
    risk = 0.1
    rationale = "No scaling needed"
    plan: List[str] = []
    verification: List[str] = []

    # Process signals to determine scaling
    for signal in signals:
        # Strip any suffix (e.g., "service_unhealthy:nats-service" → "service_unhealthy")
        base_signal = signal.split(":")[0]
        if base_signal in _SIGNAL_ACTIONS:
            sa = _SIGNAL_ACTIONS[base_signal]
            if abs(sa["delta"]) > abs(delta):
                action = sa["action"]
                target = sa["target"]
                delta = sa["delta"]

    # Override from recommended action
    if recommended == "scale_up_immediately":
        action = "scale_up"
        delta = max(delta, 2)
        risk = 0.3
    elif recommended == "scale_up":
        action = "scale_up"
        delta = max(delta, 1)
        risk = 0.2
    elif recommended == "consider_scale_down" and event_type == "healthy":
        action = "scale_down"
        delta = -1
        risk = 0.1
    elif recommended == "consider_migration":
        # Defer to MigrateOrchestrator — container-level migration needed
        action = "defer_to_migrator"
        target = "migrate"
        rationale = "Container-level CPU high with VPS overloaded — deferring to MigrateOrchestrator"
        risk = 0.2
    elif recommended == "apply_lifecycle_rules":
        # Pass through to Curator
        action = "no_action"
        rationale = "S3 lifecycle management deferred to Curator agent"

    # Calculate proposed count
    current = _get_current_service_count(target)
    min_count = _MIN_TASKS_WORKSHOP if target == "workshop" else _MIN_TASKS_WORKER
    proposed = max(min_count, min(_MAX_TASKS, current + delta))

    if action == "scale_up" and proposed > current:
        rationale = f"Scaling {target} from {current} to {proposed} due to {', '.join(signals[:3])}"
        plan = [
            f"aws ecs update-service --cluster citadel-cluster --service {target}-service --desired-count {proposed}",
            "Wait 60s for tasks to stabilize",
            "Verify new tasks are running",
        ]
        verification = [
            f"Confirm {target}-service has {proposed} running tasks",
            "Check CloudWatch CPU alarm returns to OK state",
            "Monitor for 5 minutes for task stability",
        ]
    elif action == "scale_down" and proposed < current:
        rationale = f"Scaling {target} from {current} to {proposed} — CPU load is low"
        risk = 0.15
        plan = [
            f"aws ecs update-service --cluster citadel-cluster --service {target}-service --desired-count {proposed}",
            "Wait for graceful task drain",
        ]
        verification = [
            f"Confirm {target}-service has {proposed} running tasks",
            "Verify no tasks were interrupted mid-work",
        ]
    else:
        action = "no_action"
        rationale = f"Current state is acceptable (event: {event_type}, severity: {severity})"
        proposed = current

    return {
        "action": action,
        "target": target,
        "current_count": current,
        "proposed_count": proposed,
        "risk_estimate": risk,
        "rationale": rationale,
        "execution_plan": plan,
        "verification_steps": verification,
        "llm_powered": False,
    }


def run_scaler_v2(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Auto-scaling decision and execution planning.
    Tries LLM first, falls back to rule-based logic.
    """
    result = _run_scaler_llm(packet)
    if result is not None:
        return result
    return _run_scaler_rules(packet)
