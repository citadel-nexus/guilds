# src/agents/migrate_orchestrator.py
"""
Migrate Orchestrator Agent — VPS ↔ ECS Workload Migration

Decides which Docker runtime services to migrate between VPS and ECS
based on per-container CPU/memory, overall VPS load, and AWS budget.

Pipeline role: Third in Watcher → Scaler → Migrator → Curator → Budget chain.

State machine per service:
    VPS_RUNNING → MIGRATING_TO_ECS → ECS_RUNNING → MIGRATING_TO_VPS → VPS_RUNNING

Supports two modes:
- LLM mode: Uses Bedrock/OpenAI for nuanced migration decisions
- Rule mode: Threshold-based migration when no LLM is available

CGRF v3.0 Compliance:
- SRS Code: SRS-MIGRATE-ORCH-20260205-001-V3.0
- Tier: 1 (DEVELOPMENT)
- Execution Role: INFRASTRUCTURE

@module citadel_lite.src.agents.migrate_orchestrator
"""
from __future__ import annotations

import json
import logging
import os
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Migration State Machine
# ---------------------------------------------------------------------------

MIGRATION_STATE_FILE = os.environ.get(
    "MIGRATION_STATE_FILE", "/tmp/citadel-migration-state.json"
)


class ServiceState(str, Enum):
    VPS_RUNNING = "VPS_RUNNING"
    MIGRATING_TO_ECS = "MIGRATING_TO_ECS"
    ECS_RUNNING = "ECS_RUNNING"
    MIGRATING_TO_VPS = "MIGRATING_TO_VPS"
    FAILED = "FAILED"


# Valid state transitions
_TRANSITIONS = {
    ServiceState.VPS_RUNNING: {ServiceState.MIGRATING_TO_ECS},
    ServiceState.MIGRATING_TO_ECS: {ServiceState.ECS_RUNNING, ServiceState.FAILED, ServiceState.VPS_RUNNING},
    ServiceState.ECS_RUNNING: {ServiceState.MIGRATING_TO_VPS},
    ServiceState.MIGRATING_TO_VPS: {ServiceState.VPS_RUNNING, ServiceState.FAILED, ServiceState.ECS_RUNNING},
    ServiceState.FAILED: {ServiceState.VPS_RUNNING, ServiceState.MIGRATING_TO_ECS, ServiceState.MIGRATING_TO_VPS},
}


# ---------------------------------------------------------------------------
# Service Registry
# ---------------------------------------------------------------------------

RUNTIME_SERVICES: Dict[str, Dict[str, Any]] = {
    "event-listener": {
        "port": 8100,
        "tier": 1,
        "redis_dependent": True,
        "stateful": False,
        "ecs_service": "event-listener-service",
        "compose_name": "event-listener",
    },
    "sake-builder": {
        "port": 8150,
        "tier": 1,
        "redis_dependent": True,
        "stateful": False,
        "ecs_service": "sake-builder-service",
        "compose_name": "sake-builder",
    },
    "governance-gateway": {
        "port": 8787,
        "tier": 1,
        "redis_dependent": True,
        "stateful": False,
        "ecs_service": "governance-gateway-service",
        "compose_name": "governance-gateway",
    },
    "smartbank": {
        "port": 8400,
        "tier": 2,
        "redis_dependent": False,
        "stateful": False,
        "ecs_service": "smartbank-service",
        "compose_name": "smartbank",
    },
    "guardian": {
        "port": 8500,
        "tier": 2,
        "redis_dependent": False,
        "stateful": False,
        "ecs_service": "guardian-runtime-service",
        "compose_name": "guardian",
    },
    "council": {
        "port": 8200,
        "tier": 2,
        "redis_dependent": False,
        "stateful": False,
        "ecs_service": "council-service",
        "compose_name": "council",
    },
    "reflex-runtime": {
        "port": 8170,
        "tier": 3,
        "redis_dependent": True,
        "stateful": False,
        "ecs_service": "reflex-runtime-service",
        "compose_name": "reflex-runtime",
    },
}

# Thresholds
_MIGRATE_CPU_THRESHOLD = 80.0      # VPS total CPU to trigger migration
_CONTAINER_CPU_THRESHOLD = 15.0    # Per-container CPU to be a migration candidate
_REVERSE_CPU_THRESHOLD = 40.0      # VPS CPU below which to consider reverse migration
_BUDGET_WARNING_PCT = 80.0         # Budget % to start reverse migration
_BUDGET_CRITICAL_PCT = 90.0        # Budget % to force all back to VPS
_MAX_CONCURRENT_MIGRATIONS = 1     # Only migrate one service at a time


# ---------------------------------------------------------------------------
# State Persistence
# ---------------------------------------------------------------------------

def load_migration_state() -> Dict[str, str]:
    """Load current migration state from file."""
    try:
        with open(MIGRATION_STATE_FILE, "r") as f:
            data = json.load(f)
            return data.get("services", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_migration_state(services: Dict[str, str]) -> None:
    """Save migration state to file."""
    state = {
        "timestamp": time.time(),
        "services": services,
    }
    try:
        with open(MIGRATION_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error("Failed to save migration state: %s", e)


def get_service_state(name: str) -> ServiceState:
    """Get current state of a service."""
    states = load_migration_state()
    raw = states.get(name, ServiceState.VPS_RUNNING.value)
    try:
        return ServiceState(raw)
    except ValueError:
        return ServiceState.VPS_RUNNING


def transition_service(name: str, new_state: ServiceState) -> bool:
    """Transition a service to a new state if valid."""
    current = get_service_state(name)
    if new_state not in _TRANSITIONS.get(current, set()):
        logger.warning(
            "Invalid transition for %s: %s → %s",
            name, current.value, new_state.value,
        )
        return False

    states = load_migration_state()
    states[name] = new_state.value
    save_migration_state(states)
    logger.info("Service %s: %s → %s", name, current.value, new_state.value)
    return True


# ---------------------------------------------------------------------------
# Decision Logic
# ---------------------------------------------------------------------------

def _get_container_stats(packet: HandoffPacket) -> Dict[str, Dict[str, float]]:
    """Extract per-container stats from Watcher output."""
    watcher_out = packet.agent_outputs.get("watcher")
    if not watcher_out:
        return {}

    watcher_data = watcher_out.payload if hasattr(watcher_out, "payload") else watcher_out
    metrics = watcher_data.get("metrics", {})
    container_stats = metrics.get("container_stats", {})

    # container_stats format from CloudWatch:
    # {"name": {"cpu_percent": {"average": X}, "mem_percent": {"average": Y}}}
    result = {}
    if isinstance(container_stats, dict):
        containers = container_stats.get("containers", container_stats)
        for name, stats in containers.items():
            cpu_data = stats.get("cpu_percent", {})
            mem_data = stats.get("mem_percent", {})
            cpu = cpu_data.get("average") if isinstance(cpu_data, dict) else cpu_data
            mem = mem_data.get("average") if isinstance(mem_data, dict) else mem_data
            if cpu is not None or mem is not None:
                result[name] = {
                    "cpu_percent": float(cpu) if cpu is not None else 0.0,
                    "mem_percent": float(mem) if mem is not None else 0.0,
                }
    elif isinstance(container_stats, list):
        for c in container_stats:
            result[c["name"]] = {
                "cpu_percent": c.get("cpu_percent", 0.0),
                "mem_percent": c.get("mem_percent", 0.0),
            }

    return result


def _get_vps_metrics(packet: HandoffPacket) -> Dict[str, Optional[float]]:
    """Extract VPS-level metrics from Watcher output."""
    watcher_out = packet.agent_outputs.get("watcher")
    if not watcher_out:
        return {"cpu": None, "memory": None}

    watcher_data = watcher_out.payload if hasattr(watcher_out, "payload") else watcher_out
    metrics = watcher_data.get("metrics", {})

    return {
        "cpu": metrics.get("vps_cpu"),
        "memory": metrics.get("vps_memory"),
    }


def _get_budget_utilization(packet: HandoffPacket) -> float:
    """Get budget utilization percentage from Budget agent output."""
    budget_out = packet.agent_outputs.get("budget")
    if not budget_out:
        return 0.0

    budget_data = budget_out.payload if hasattr(budget_out, "payload") else budget_out
    evaluation = budget_data.get("evaluation", budget_data)
    return float(evaluation.get("utilization_pct", 0.0))


def _select_migration_candidates(
    container_stats: Dict[str, Dict[str, float]],
) -> List[Dict[str, Any]]:
    """Select services to migrate, sorted by tier then CPU descending."""
    candidates = []
    for svc_name, svc_info in RUNTIME_SERVICES.items():
        state = get_service_state(svc_name)
        if state != ServiceState.VPS_RUNNING:
            continue

        # Match container name to service (Docker Compose prefixes vary)
        cpu = 0.0
        for container_name, stats in container_stats.items():
            # Match by compose service name substring
            if svc_info["compose_name"] in container_name:
                cpu = stats.get("cpu_percent", 0.0)
                break

        if cpu >= _CONTAINER_CPU_THRESHOLD:
            candidates.append({
                "name": svc_name,
                "tier": svc_info["tier"],
                "cpu_percent": cpu,
                "ecs_service": svc_info["ecs_service"],
            })

    # Sort: tier ascending (1 first), then CPU descending
    candidates.sort(key=lambda c: (c["tier"], -c["cpu_percent"]))
    return candidates


def _select_reverse_candidates(budget_pct: float) -> List[Dict[str, Any]]:
    """Select services to migrate back to VPS."""
    candidates = []
    for svc_name, svc_info in RUNTIME_SERVICES.items():
        state = get_service_state(svc_name)
        if state != ServiceState.ECS_RUNNING:
            continue
        candidates.append({
            "name": svc_name,
            "tier": svc_info["tier"],
            "ecs_service": svc_info["ecs_service"],
        })

    # Reverse: tier descending (highest tier = lowest priority, migrate back first)
    candidates.sort(key=lambda c: -c["tier"])
    return candidates


# ---------------------------------------------------------------------------
# LLM Mode
# ---------------------------------------------------------------------------

def _run_migrate_llm(packet: HandoffPacket) -> Optional[Dict[str, Any]]:
    """Try LLM-based migration decision. Returns None if unavailable."""
    try:
        from src.llm.client import LLMClient

        client = LLMClient()
        if not client.is_available():
            return None

        vps = _get_vps_metrics(packet)
        container_stats = _get_container_stats(packet)
        budget_pct = _get_budget_utilization(packet)
        current_states = load_migration_state()

        system_prompt = (
            "You are a workload migration agent for the Citadel Nexus platform. "
            "You manage migration of Docker runtime services between a VPS and AWS ECS Fargate. "
            "Services are tiered: Tier 1 (event-listener, sake-builder, governance-gateway) are "
            "easiest to migrate, Tier 2 (smartbank, guardian, council), Tier 3 (reflex-runtime). "
            "Redis NEVER migrates. Budget cap is $400/mo. "
            "Respond with JSON containing: action (migrate_to_ecs|migrate_to_vps|force_reverse_all|no_action), "
            "services (list of {name, from, to, reason}), risk_estimate (0.0-1.0), rationale (string)."
        )

        user_msg = (
            f"Current state:\n"
            f"- VPS CPU: {vps.get('cpu', 'unknown')}%\n"
            f"- VPS Memory: {vps.get('memory', 'unknown')}%\n"
            f"- Container stats: {json.dumps(container_stats)}\n"
            f"- Budget utilization: {budget_pct:.1f}%\n"
            f"- Current migration state: {json.dumps(current_states)}\n"
            f"- Migration thresholds: CPU>{_MIGRATE_CPU_THRESHOLD}% to migrate, "
            f"<{_REVERSE_CPU_THRESHOLD}% to reverse, budget>{_BUDGET_WARNING_PCT}% to reverse\n"
        )

        resp = client.complete(system_prompt, user_msg)
        if resp.success and resp.parsed:
            result = resp.parsed
            result.setdefault("action", "no_action")
            result.setdefault("services", [])
            result.setdefault("risk_estimate", 0.5)
            result.setdefault("rationale", "LLM-generated migration decision")
            result["current_state"] = {
                name: get_service_state(name).value
                for name in RUNTIME_SERVICES
            }
            result["budget_check"] = {
                "utilization_pct": budget_pct,
                "safe_to_migrate": budget_pct < _BUDGET_WARNING_PCT,
            }
            result["llm_powered"] = True
            result["llm_usage"] = {
                "backend": resp.usage.backend,
                "tokens": resp.usage.total_tokens,
                "latency_ms": resp.usage.latency_ms,
            }
            logger.info("Migrator LLM decision: %s", result["action"])
            return result

    except Exception as e:
        logger.warning("Migrator LLM fallback: %s", e)
    return None


# ---------------------------------------------------------------------------
# Rule Mode
# ---------------------------------------------------------------------------

def _run_migrate_rules(packet: HandoffPacket) -> Dict[str, Any]:
    """Rule-based migration decision (deterministic fallback)."""
    vps = _get_vps_metrics(packet)
    container_stats = _get_container_stats(packet)
    budget_pct = _get_budget_utilization(packet)

    vps_cpu = vps.get("cpu")
    vps_mem = vps.get("memory")

    action = "no_action"
    services: List[Dict[str, Any]] = []
    risk = 0.1
    rationale = "No migration needed"
    execution_plan: List[str] = []
    verification_steps: List[str] = []

    # Check for any services currently migrating (don't start new migrations)
    any_migrating = any(
        get_service_state(name) in (ServiceState.MIGRATING_TO_ECS, ServiceState.MIGRATING_TO_VPS)
        for name in RUNTIME_SERVICES
    )

    ecs_running_count = sum(
        1 for name in RUNTIME_SERVICES
        if get_service_state(name) == ServiceState.ECS_RUNNING
    )

    # Priority 1: Budget critical → force all back to VPS
    if budget_pct >= _BUDGET_CRITICAL_PCT and ecs_running_count > 0:
        action = "force_reverse_all"
        risk = 0.4
        rationale = f"Budget critical ({budget_pct:.1f}%) — forcing all services back to VPS"
        for candidate in _select_reverse_candidates(budget_pct):
            services.append({
                "name": candidate["name"],
                "from": "ecs",
                "to": "vps",
                "reason": f"Budget critical: {budget_pct:.1f}%",
            })
        execution_plan = [
            "Start VPS containers for each service",
            "Wait for health checks",
            "Switch nginx upstreams to VPS",
            "Scale down ECS services to 0",
        ]

    # Priority 2: Budget warning → reverse low-priority services
    elif budget_pct >= _BUDGET_WARNING_PCT and ecs_running_count > 0:
        reverse_candidates = _select_reverse_candidates(budget_pct)
        if reverse_candidates and not any_migrating:
            # Reverse one at a time
            candidate = reverse_candidates[0]
            action = "migrate_to_vps"
            risk = 0.2
            rationale = f"Budget warning ({budget_pct:.1f}%) — reversing {candidate['name']}"
            services.append({
                "name": candidate["name"],
                "from": "ecs",
                "to": "vps",
                "reason": f"Budget warning: {budget_pct:.1f}%",
            })

    # Priority 3: VPS CPU low → reverse migrate (cost savings)
    elif vps_cpu is not None and vps_cpu < _REVERSE_CPU_THRESHOLD and ecs_running_count > 0:
        if not any_migrating:
            reverse_candidates = _select_reverse_candidates(budget_pct)
            if reverse_candidates:
                candidate = reverse_candidates[0]
                action = "migrate_to_vps"
                risk = 0.15
                rationale = (
                    f"VPS CPU low ({vps_cpu:.1f}%) — "
                    f"reversing {candidate['name']} to save ECS costs"
                )
                services.append({
                    "name": candidate["name"],
                    "from": "ecs",
                    "to": "vps",
                    "reason": f"CPU low: {vps_cpu:.1f}%",
                })

    # Priority 4: VPS CPU high → migrate to ECS
    elif vps_cpu is not None and vps_cpu >= _MIGRATE_CPU_THRESHOLD:
        if not any_migrating and budget_pct < _BUDGET_WARNING_PCT:
            candidates = _select_migration_candidates(container_stats)
            if candidates:
                # Migrate one at a time
                candidate = candidates[0]
                action = "migrate_to_ecs"
                risk = 0.25
                rationale = (
                    f"VPS CPU high ({vps_cpu:.1f}%) — "
                    f"migrating {candidate['name']} (CPU: {candidate['cpu_percent']:.1f}%)"
                )
                services.append({
                    "name": candidate["name"],
                    "from": "vps",
                    "to": "ecs",
                    "reason": f"Container CPU: {candidate['cpu_percent']:.1f}%, VPS total: {vps_cpu:.1f}%",
                })
                execution_plan = [
                    f"Scale ECS service {candidate['ecs_service']} to 1",
                    "Wait for ECS task health check (60s)",
                    f"Switch nginx upstream for {candidate['name']} to ECS ALB",
                    f"Stop VPS Docker container {candidate['name']}",
                    "Verify traffic flows through ECS",
                ]
                verification_steps = [
                    f"ECS task for {candidate['ecs_service']} is RUNNING",
                    f"Health check at ALB returns 200 for {candidate['name']}",
                    f"VPS container {candidate['name']} is stopped",
                    "No error rate increase in logs",
                ]
    else:
        rationale = (
            f"System stable — VPS CPU: {vps_cpu}%, "
            f"Budget: {budget_pct:.1f}%, "
            f"ECS services: {ecs_running_count}"
        )

    current_state = {
        name: get_service_state(name).value
        for name in RUNTIME_SERVICES
    }

    return {
        "action": action,
        "services": services,
        "current_state": current_state,
        "budget_check": {
            "utilization_pct": budget_pct,
            "safe_to_migrate": budget_pct < _BUDGET_WARNING_PCT,
        },
        "risk_estimate": risk,
        "rationale": rationale,
        "execution_plan": execution_plan,
        "verification_steps": verification_steps,
        "llm_powered": False,
        "vps_cpu": vps_cpu,
        "vps_memory": vps_mem,
        "ecs_running_count": ecs_running_count,
        "container_stats_available": len(container_stats) > 0,
    }


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def run_migrate_v2(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Workload migration decision and planning.
    Tries LLM first, falls back to rule-based logic.
    """
    result = _run_migrate_llm(packet)
    if result is not None:
        return result
    return _run_migrate_rules(packet)
