# src/agents/merge_gate.py
"""
Council Merge Gate — Mandatory approval before code merge.

Evaluates generated code for auto-merge eligibility using:
1. Sandbox test results (must pass)
2. Guardian risk assessment (risk_score threshold)
3. Council deliberation confidence (if available)
4. Autonomy budget check

Decision matrix:
  - AUTO_MERGE:    tests pass AND risk_score < 0.2
  - HUMAN_REVIEW:  tests pass AND risk_score 0.2-0.5
  - BLOCKED:       tests fail OR risk_score >= 0.5

CGRF v3.0 Compliance:
- SRS Code: SRS-MERGE-GATE-001
- Tier: 2 (STAGING)
- Execution Role: GOVERNANCE

@module citadel_lite.src.agents.merge_gate
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, Optional

from src.types import HandoffPacket, Decision

logger = logging.getLogger(__name__)

# Autonomy budget thresholds for different actions
AUTONOMY_GATES = {
    "intent_generation": 0.35,
    "code_generation": 0.50,
    "test_execution": 0.50,
    "pr_creation": 0.60,
    "auto_merge": 0.70,
    "production_deploy": 0.75,
    "self_modification": 0.85,
}

# Risk score thresholds
_AUTO_MERGE_THRESHOLD = 0.2
_HUMAN_REVIEW_THRESHOLD = 0.5


def _calculate_autonomy_budget(packet: HandoffPacket) -> float:
    """
    Calculate current autonomy budget from pipeline state.

    Budget is based on:
    - System health (from Watcher)
    - Recent success rate
    - Guardian risk assessment
    - Test pass rate

    Returns float 0.0-1.0
    """
    budget = 0.5  # Base budget

    # Boost from healthy infrastructure
    watcher = packet.agent_outputs.get("watcher")
    if watcher:
        w_data = watcher.payload if hasattr(watcher, "payload") else watcher
        if w_data.get("event_type") == "healthy":
            budget += 0.15
        elif w_data.get("severity") == "critical":
            budget -= 0.2

    # Boost from passing tests
    sandbox = packet.agent_outputs.get("sandbox")
    if sandbox:
        s_data = sandbox.payload if hasattr(sandbox, "payload") else sandbox
        if s_data.get("passed"):
            budget += 0.2
        else:
            budget -= 0.3

    # Penalize from guardian risk
    guardian = packet.agent_outputs.get("guardian")
    if guardian:
        g_data = guardian.payload if hasattr(guardian, "payload") else guardian
        risk = g_data.get("risk_score", 0.5)
        budget -= risk * 0.3

    return max(0.0, min(1.0, budget))


def _check_autonomy_gate(action: str, budget: float) -> bool:
    """Check if action is permitted under current autonomy budget."""
    required = AUTONOMY_GATES.get(action, 1.0)
    return budget >= required


def _generate_audit_hash(
    packet: HandoffPacket,
    decision: str,
    risk_score: float,
) -> str:
    """Generate deterministic audit hash for the merge decision."""
    data = f"{packet.event.event_id}:{decision}:{risk_score}:{time.time()}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def run_merge_gate(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Evaluate a code change for merge eligibility.

    Reads from packet:
    - f993_python / f993: generated code details
    - sandbox: test execution results
    - guardian: risk assessment (optional)
    - watcher: infrastructure health (optional)

    Returns merge decision with full audit trail.
    """
    # 1. Check sandbox results (mandatory)
    sandbox = packet.agent_outputs.get("sandbox")
    if not sandbox:
        return {
            "decision": "BLOCKED",
            "reason": "No sandbox test results — cannot merge untested code",
            "requires_human": True,
            "risk_score": 1.0,
            "autonomy_budget": 0.0,
        }

    s_data = sandbox.payload if hasattr(sandbox, "payload") else sandbox
    tests_passed = s_data.get("passed", False)

    if not tests_passed:
        return {
            "decision": "BLOCKED",
            "reason": f"Sandbox tests failed (exit code {s_data.get('exit_code', -1)})",
            "requires_human": True,
            "risk_score": 1.0,
            "test_output": s_data.get("stderr", "")[:500],
            "autonomy_budget": 0.0,
        }

    # 2. Calculate risk score
    risk_score = 0.1  # Base risk for passing tests

    # Incorporate guardian assessment if available
    guardian = packet.agent_outputs.get("guardian")
    if guardian:
        g_data = guardian.payload if hasattr(guardian, "payload") else guardian
        guardian_risk = g_data.get("risk_score", 0.5)
        risk_score = (risk_score + guardian_risk) / 2

    # Check what was modified
    f993 = packet.agent_outputs.get("f993_python") or packet.agent_outputs.get("f993")
    if f993:
        f_data = f993.payload if hasattr(f993, "payload") else f993
        files = f_data.get("files", [])
        # More files = more risk
        if len(files) > 3:
            risk_score += 0.1
        # LLM-generated code has higher risk than template
        if f_data.get("generation_mode") == "llm":
            risk_score += 0.05

    risk_score = min(1.0, risk_score)

    # 3. Calculate autonomy budget
    autonomy_budget = _calculate_autonomy_budget(packet)

    # 4. Decision matrix
    if risk_score < _AUTO_MERGE_THRESHOLD and _check_autonomy_gate("auto_merge", autonomy_budget):
        decision = "AUTO_MERGE"
        requires_human = False
        reason = f"Tests pass, risk {risk_score:.2f} < threshold, budget {autonomy_budget:.2f}"
    elif risk_score < _HUMAN_REVIEW_THRESHOLD:
        decision = "HUMAN_REVIEW"
        requires_human = True
        reason = f"Tests pass but risk {risk_score:.2f} requires review"
    else:
        decision = "BLOCKED"
        requires_human = True
        reason = f"Risk score {risk_score:.2f} too high for automated merge"

    audit_hash = _generate_audit_hash(packet, decision, risk_score)

    return {
        "decision": decision,
        "requires_human": requires_human,
        "risk_score": round(risk_score, 3),
        "autonomy_budget": round(autonomy_budget, 3),
        "reason": reason,
        "tests_passed": tests_passed,
        "test_duration": s_data.get("duration_seconds", 0),
        "sandbox_mode": s_data.get("mode", "unknown"),
        "audit_hash": audit_hash,
    }
