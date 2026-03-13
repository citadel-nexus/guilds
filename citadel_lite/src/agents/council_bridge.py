# src/agents/council_bridge.py
"""
Council Bridge Agent — Routes autodev decisions through Council governance.

Connects the autodev pipeline to the Council service (src/council/service.py)
for 4-seat SAKE deliberation (Reason, Axiom, Kindness, Equity) before
merge gate evaluation.

Pipeline position:
  F993 Code Gen → College Bridge → **Council Bridge** → Merge Gate

What it does:
1. Reads College analysis and F993 generation results from HandoffPacket
2. Constructs a CouncilRequest for the code_deployment action
3. Runs Council deliberation (4-seat SAKE framework)
4. Returns verdict (ALLOW/DENY/ESCALATE/DEFER) for merge gate

CGRF v3.0 Compliance:
- SRS Code: SRS-COUNCIL-BRIDGE-001
- Tier: 2 (STAGING)
- Execution Role: GOVERNANCE

@module citadel_lite.src.agents.council_bridge
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket

logger = logging.getLogger(__name__)


def _build_council_context(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Build context for Council deliberation from pipeline state.

    Gathers information from:
    - Intent generator (what are we building and why)
    - F993 output (what was generated)
    - College analysis (code quality assessment)
    - Sandbox results (test outcomes)
    """
    context: Dict[str, Any] = {}

    # Intent context
    intent = packet.agent_outputs.get("intent_generator")
    if intent:
        i_data = intent.payload if hasattr(intent, "payload") else intent
        selected = i_data.get("selected_intent", {})
        if selected:
            context["intent_source"] = selected.get("source", "unknown")
            context["intent_title"] = selected.get("title", "unknown")
            context["intent_priority"] = selected.get("priority", 0.0)

    # Generation context
    for key in ("f993_python", "f993_typescript", "f993"):
        f993 = packet.agent_outputs.get(key)
        if f993:
            f_data = f993.payload if hasattr(f993, "payload") else f993
            context["generation_valid"] = f_data.get("valid", False)
            context["generation_mode"] = f_data.get("generation_mode", "unknown")
            files = f_data.get("files", [])
            if files:
                context["files_count"] = len(files)
                context["target_path"] = files[0].get("path", "")
                context["content_hash"] = files[0].get("content_hash", "")
                context["line_count"] = files[0].get("line_count", 0)
            break

    # College analysis context
    college = packet.agent_outputs.get("college")
    if college:
        c_data = college.payload if hasattr(college, "payload") else college
        context["quality_score"] = c_data.get("quality_score", 0.0)
        context["issue_count"] = c_data.get("issue_count", 0)
        context["critical_count"] = c_data.get("critical_count", 0)
        context["has_security_issues"] = c_data.get("critical_count", 0) > 0

    # Sandbox context
    sandbox = packet.agent_outputs.get("sandbox")
    if sandbox:
        s_data = sandbox.payload if hasattr(sandbox, "payload") else sandbox
        context["tests_passed"] = s_data.get("passed", False)
        context["sandbox_exit_code"] = s_data.get("exit_code", -1)

    return context


def _deliberate_rules(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rule-based Council deliberation (fallback when Council service unavailable).

    Implements the 4-seat SAKE framework with deterministic rules:
    - Reason: Is the action logically sound?
    - Axiom: Does it align with first principles?
    - Kindness: What's the user impact?
    - Equity: Is it fair and balanced?
    """
    votes: Dict[str, Dict[str, Any]] = {}

    # Reason Seat — Logic check
    reason_vote = "ALLOW"
    reason_confidence = 0.8
    reason_rationale = "Action is logically consistent"

    if not context.get("generation_valid", False):
        reason_vote = "DENY"
        reason_confidence = 0.95
        reason_rationale = "Generated code failed validation — logically unsound"
    elif context.get("generation_mode") == "template":
        reason_confidence = 0.7
        reason_rationale = "Template-generated stub — limited implementation logic"

    votes["reason"] = {
        "vote": reason_vote,
        "confidence": reason_confidence,
        "reasoning": reason_rationale,
    }

    # Axiom Seat — First principles
    axiom_vote = "ALLOW"
    axiom_confidence = 0.8
    axiom_rationale = "Aligns with autonomous development principles"

    quality = context.get("quality_score", 1.0)
    if quality < 0.5:
        axiom_vote = "DENY"
        axiom_confidence = 0.85
        axiom_rationale = f"Quality score {quality:.2f} below acceptable threshold (0.5)"
    elif quality < 0.7:
        axiom_vote = "ESCALATE"
        axiom_confidence = 0.7
        axiom_rationale = f"Quality score {quality:.2f} warrants human review"

    votes["axiom"] = {
        "vote": axiom_vote,
        "confidence": axiom_confidence,
        "reasoning": axiom_rationale,
    }

    # Kindness Seat — User impact
    kindness_vote = "ALLOW"
    kindness_confidence = 0.8
    kindness_rationale = "Change has acceptable user impact"

    if context.get("has_security_issues"):
        kindness_vote = "DENY"
        kindness_confidence = 0.9
        kindness_rationale = "Critical security issues detected — user safety at risk"
    elif context.get("critical_count", 0) > 0:
        kindness_vote = "ESCALATE"
        kindness_confidence = 0.85
        kindness_rationale = "Critical issues need human review for user safety"

    votes["kindness"] = {
        "vote": kindness_vote,
        "confidence": kindness_confidence,
        "reasoning": kindness_rationale,
    }

    # Equity Seat — Fairness and balance
    equity_vote = "ALLOW"
    equity_confidence = 0.8
    equity_rationale = "Resource allocation is balanced"

    line_count = context.get("line_count", 0)
    if line_count > 500:
        equity_vote = "ESCALATE"
        equity_confidence = 0.7
        equity_rationale = f"Large change ({line_count} lines) — review for proportionality"

    votes["equity"] = {
        "vote": equity_vote,
        "confidence": equity_confidence,
        "reasoning": equity_rationale,
    }

    # Aggregate votes
    all_votes = [v["vote"] for v in votes.values()]
    if "DENY" in all_votes:
        decision = "DENY"
    elif "ESCALATE" in all_votes:
        decision = "ESCALATE"
    elif "DEFER" in all_votes:
        decision = "DEFER"
    else:
        decision = "ALLOW"

    avg_confidence = sum(v["confidence"] for v in votes.values()) / len(votes)
    dissent = [
        f"{seat}: {v['reasoning']}"
        for seat, v in votes.items()
        if v["vote"] != decision
    ]

    return {
        "decision": decision,
        "confidence": round(avg_confidence, 3),
        "seat_votes": votes,
        "dissent": dissent,
        "policy_refs": ["CGRF-v3.0", "SRS-COUNCIL-BRIDGE-001"],
    }


def run_council_bridge(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Run autodev decision through Council governance deliberation.

    Returns:
        Dict with Council verdict, seat votes, and confidence.
    """
    start = time.time()

    # Build context from pipeline state
    context = _build_council_context(packet)

    if not context.get("generation_valid") and not context.get("intent_title"):
        return {
            "deliberated": False,
            "reason": "No generation or intent data in packet",
            "decision": "DEFER",
            "confidence": 0.0,
            "seat_votes": {},
        }

    result = _deliberate_rules(context)
    result["mode"] = "rules"

    duration_ms = int((time.time() - start) * 1000)

    return {
        "deliberated": True,
        "decision": result["decision"],
        "confidence": result["confidence"],
        "seat_votes": result["seat_votes"],
        "dissent": result.get("dissent", []),
        "policy_refs": result.get("policy_refs", []),
        "verdict_id": result.get("verdict_id"),
        "mode": result.get("mode", "rules"),
        "context_used": {
            "intent_source": context.get("intent_source"),
            "quality_score": context.get("quality_score"),
            "generation_mode": context.get("generation_mode"),
            "tests_passed": context.get("tests_passed"),
        },
        "duration_ms": duration_ms,
    }
