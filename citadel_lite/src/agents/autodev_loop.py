# src/agents/autodev_loop.py
"""
Autonomous Development Loop — Closed-loop self-development orchestrator.

Wires together all pipeline stages into a single autonomous cycle:

  Intent Generator → F993 Code Gen → College Analysis → Council Deliberation →
  Sandbox Executor → Merge Gate → Deploy → Watcher → Rollback (if needed)

Each cycle:
1. Intent Generator identifies what to build (issues, findings, gaps)
2. F993 Backend generates code from selected intent's SAKE spec
3. College Bridge analyzes generated code (professor review)
4. Council Bridge deliberates via 4-seat SAKE framework
5. Sandbox Executor runs tests in isolation
6. Merge Gate evaluates for auto-merge vs. human review
7. If approved, creates deployment plan
8. Watcher monitors for regressions post-deploy
9. Rollback Agent reverts if regression detected (closes loop)

Safety constraints:
- Autonomy budget gates every action
- Guardian risk scoring at merge gate
- Sandbox isolation (Docker/subprocess)
- SapientPacket audit trail for every decision

CGRF v3.0 Compliance:
- SRS Code: SRS-AUTODEV-LOOP-001
- Tier: 2 (STAGING)
- Execution Role: ORCHESTRATION

@module citadel_lite.src.agents.autodev_loop
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket, EventJsonV1, SapientPacket

logger = logging.getLogger(__name__)


def _extract_college_summary(packet: HandoffPacket) -> Dict[str, Any]:
    """Extract College analysis summary from packet."""
    college = packet.agent_outputs.get("college")
    if not college:
        return {"analyzed": False}
    c_data = college.payload if hasattr(college, "payload") else college
    return {
        "analyzed": c_data.get("analyzed", False),
        "quality_score": c_data.get("quality_score", 0.0),
        "professors": c_data.get("professors_consulted", []),
    }


def _extract_council_summary(packet: HandoffPacket) -> Dict[str, Any]:
    """Extract Council deliberation summary from packet."""
    council = packet.agent_outputs.get("council")
    if not council:
        return {"deliberated": False}
    co_data = council.payload if hasattr(council, "payload") else council
    return {
        "deliberated": co_data.get("deliberated", False),
        "decision": co_data.get("decision"),
        "confidence": co_data.get("confidence"),
    }


def _build_sapient_packet(
    packet: HandoffPacket,
    action_type: str,
) -> SapientPacket:
    """
    Build a SapientPacket from the current pipeline state for audit.
    """
    sp = SapientPacket(action_type=action_type)

    # S01: Intent
    intent = packet.agent_outputs.get("intent_generator")
    if intent:
        i_data = intent.payload if hasattr(intent, "payload") else intent
        selected = i_data.get("selected_intent", {})
        if selected:
            sp.intent_source = selected.get("source", "")
            sp.intent_id = str(selected.get("id", ""))
            sp.intent_priority = selected.get("priority", 0.0)

    # S02: College processing
    college = packet.agent_outputs.get("college")
    if college:
        c_data = college.payload if hasattr(college, "payload") else college
        sp.college_professors_consulted = c_data.get("professors_consulted", [])
        sp.college_aggregation_time_ms = c_data.get("duration_ms", 0)

    # S03: Council deliberation
    council = packet.agent_outputs.get("council")
    if council:
        co_data = council.payload if hasattr(council, "payload") else council
        seat_votes = co_data.get("seat_votes", {})
        sp.council_votes = {k: v.get("vote", "") if isinstance(v, dict) else v for k, v in seat_votes.items()}
        sp.council_confidence = co_data.get("confidence", 0.0)
        sp.dissent_reasons = co_data.get("dissent", [])

    # S05: Execution
    f993 = packet.agent_outputs.get("f993_python") or packet.agent_outputs.get("f993_typescript")
    if f993:
        f_data = f993.payload if hasattr(f993, "payload") else f993
        files = f_data.get("files", [])
        if files:
            sp.code_diff_hash = files[0].get("content_hash", "")
        sp.generation_mode = f_data.get("generation_mode", "")

    # S05: Sandbox
    sandbox = packet.agent_outputs.get("sandbox")
    if sandbox:
        s_data = sandbox.payload if hasattr(sandbox, "payload") else sandbox
        sp.sandbox_exit_code = s_data.get("exit_code", -1)
        sp.test_results_hash = hashlib.sha256(
            str(s_data).encode()
        ).hexdigest()[:16]

    # S04: Risk
    merge = packet.agent_outputs.get("merge_gate")
    if merge:
        m_data = merge.payload if hasattr(merge, "payload") else merge
        sp.guardian_risk_score = m_data.get("risk_score", 0.0)
        sp.autonomy_budget_at_decision = m_data.get("autonomy_budget", 0.0)
        sp.final_decision = m_data.get("decision", "")
        sp.fate_recommendation = (
            "proceed" if m_data.get("decision") == "AUTO_MERGE"
            else "review" if m_data.get("decision") == "HUMAN_REVIEW"
            else "block"
        )

    # S07: Rollback
    rollback = packet.agent_outputs.get("rollback")
    if rollback:
        r_data = rollback.payload if hasattr(rollback, "payload") else rollback
        sp.regression_detected = r_data.get("rollback_needed", False)
        sp.rollback_triggered = r_data.get("rollback_needed", False)

    return sp


def run_autodev_cycle(
    packet: Optional[HandoffPacket] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Execute one autonomous development cycle.

    This is the main entry point for the closed loop. Each call:
    1. Runs the intent generator to pick a task
    2. Generates code via F993
    3. Tests in sandbox
    4. Evaluates via merge gate
    5. Returns the full result + SapientPacket audit

    Args:
        packet: Optional pre-built packet. If None, creates a fresh one.
        dry_run: If True, don't actually write files or create PRs.

    Returns:
        Dict with cycle results and audit trail.
    """
    from src.agents.intent_generator import run_intent_generator
    from src.agents.college_bridge import run_college_bridge
    from src.agents.council_bridge import run_council_bridge
    from src.agents.merge_gate import run_merge_gate
    from src.agents.rollback_agent import run_rollback_agent

    if packet is None:
        packet = HandoffPacket(
            event=EventJsonV1(
                event_type="autodev_cycle",
                source="autodev_loop",
                summary="Autonomous development cycle",
            ),
        )

    cycle_start = time.time()
    stages_completed: List[str] = []
    cycle_result: Dict[str, Any] = {
        "cycle_id": packet.event.event_id,
        "dry_run": dry_run,
        "stages": [],
    }

    # ── Stage 1: Intent Generation ──────────────────────────────────────
    try:
        intent_result = run_intent_generator(packet)
        packet.add_output("intent_generator", intent_result)
        stages_completed.append("intent_generator")

        if not intent_result.get("selected_intent"):
            cycle_result["outcome"] = "no_intent"
            cycle_result["reason"] = "No actionable intents found"
            cycle_result["stages"] = stages_completed
            return cycle_result
    except Exception as e:
        logger.error("Intent generator failed: %s", e)
        cycle_result["outcome"] = "error"
        cycle_result["error"] = f"intent_generator: {e}"
        return cycle_result

    selected = intent_result["selected_intent"]
    sake_spec = selected.get("sake_spec", {})

    # ── Stage 2: F993 Python Code Generation ────────────────────────────
    try:
        # Determine target path
        task_name = sake_spec.get("taskir_blocks", {}).get("task_name", "generated")
        target_path = f"generated/{task_name.lower()}.py"

        if not dry_run:
            from F993_python_backend import run_f993_python
            f993_result = run_f993_python(sake_spec, target_path)
        else:
            # Dry run: just validate the spec can be parsed
            from F993_python_backend import PythonBackendTranslator
            translator = PythonBackendTranslator(sake_spec, target_path)
            f993_result = translator.translate()

        packet.add_output("f993_python", f993_result)
        stages_completed.append("f993_python")

        if not f993_result.get("valid"):
            cycle_result["outcome"] = "generation_failed"
            cycle_result["error"] = f993_result.get("validation_error")
            cycle_result["stages"] = stages_completed
            return cycle_result

    except Exception as e:
        logger.error("F993 Python generation failed: %s", e)
        cycle_result["outcome"] = "error"
        cycle_result["error"] = f"f993_python: {e}"
        cycle_result["stages"] = stages_completed
        return cycle_result

    # ── Stage 3: College Code Analysis ────────────────────────────────────
    try:
        college_result = run_college_bridge(packet)
        packet.add_output("college", college_result)
        stages_completed.append("college")
    except Exception as e:
        logger.error("College analysis failed: %s", e)
        packet.add_output("college", {
            "analyzed": False,
            "quality_score": 0.0,
            "error": str(e),
        })
        stages_completed.append("college")

    # ── Stage 4: Council Deliberation ──────────────────────────────────
    try:
        council_result = run_council_bridge(packet)
        packet.add_output("council", council_result)
        stages_completed.append("council")

        # If Council DENY, short-circuit
        if council_result.get("decision") == "DENY":
            cycle_result.update({
                "outcome": "council_denied",
                "stages": stages_completed,
                "council": {
                    "decision": "DENY",
                    "confidence": council_result.get("confidence"),
                    "dissent": council_result.get("dissent", []),
                },
                "sapient_packet": _build_sapient_packet(packet, "autodev_cycle").to_dict(),
                "duration_seconds": round(time.time() - cycle_start, 2),
            })
            return cycle_result
    except Exception as e:
        logger.error("Council deliberation failed: %s", e)
        packet.add_output("council", {
            "deliberated": False,
            "decision": "DEFER",
            "error": str(e),
        })
        stages_completed.append("council")

    # ── Stage 5: Sandbox Execution ──────────────────────────────────────
    try:
        from src.agents.sandbox_executor import run_sandbox_executor
        sandbox_result = run_sandbox_executor(packet)
        packet.add_output("sandbox", sandbox_result)
        stages_completed.append("sandbox")
    except Exception as e:
        logger.error("Sandbox execution failed: %s", e)
        packet.add_output("sandbox", {
            "passed": False,
            "exit_code": -1,
            "error": str(e),
        })
        stages_completed.append("sandbox")

    # ── Stage 6: Merge Gate ─────────────────────────────────────────────
    try:
        merge_result = run_merge_gate(packet)
        packet.add_output("merge_gate", merge_result)
        stages_completed.append("merge_gate")
    except Exception as e:
        logger.error("Merge gate failed: %s", e)
        merge_result = {"decision": "BLOCKED", "reason": str(e)}
        packet.add_output("merge_gate", merge_result)
        stages_completed.append("merge_gate")

    # ── Stage 7: Rollback Check ─────────────────────────────────────────
    sandbox_data = packet.agent_outputs.get("sandbox")
    s_payload = sandbox_data.payload if hasattr(sandbox_data, "payload") else sandbox_data
    if s_payload and not s_payload.get("passed", True):
        try:
            rollback_result = run_rollback_agent(packet)
            packet.add_output("rollback", rollback_result)
            stages_completed.append("rollback")
        except Exception as e:
            logger.error("Rollback agent failed: %s", e)

    # ── Build Audit Trail ───────────────────────────────────────────────
    sapient = _build_sapient_packet(packet, "autodev_cycle")

    cycle_result.update({
        "outcome": merge_result.get("decision", "BLOCKED"),
        "stages": stages_completed,
        "intent": {
            "source": selected.get("source"),
            "id": selected.get("id"),
            "title": selected.get("title"),
            "priority": selected.get("priority"),
        },
        "generation": {
            "mode": f993_result.get("generation_mode"),
            "valid": f993_result.get("valid"),
            "files": len(f993_result.get("files", [])),
        },
        "college": _extract_college_summary(packet),
        "council": _extract_council_summary(packet),
        "sandbox": {
            "passed": s_payload.get("passed", False) if s_payload else False,
            "mode": s_payload.get("mode", "unknown") if s_payload else "none",
        },
        "merge": {
            "decision": merge_result.get("decision"),
            "risk_score": merge_result.get("risk_score"),
            "autonomy_budget": merge_result.get("autonomy_budget"),
        },
        "sapient_packet": sapient.to_dict(),
        "duration_seconds": round(time.time() - cycle_start, 2),
    })

    logger.info(
        "AutoDev cycle %s: outcome=%s, stages=%s, duration=%.1fs",
        cycle_result["cycle_id"],
        cycle_result["outcome"],
        stages_completed,
        cycle_result["duration_seconds"],
    )

    return cycle_result
