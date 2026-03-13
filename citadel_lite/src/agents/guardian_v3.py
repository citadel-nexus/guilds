# src/agents/guardian_v3.py
"""
Enhanced Guardian agent with multi-factor risk scoring, policy engine,
and responsible AI checks.

Supports two modes:
- LLM mode: Uses Azure OpenAI / OpenAI for nuanced governance reasoning
- Rule mode: Falls back to multi-factor arithmetic when no LLM is available

Now loads and enforces policies from governance/policies.yaml via PolicyEngine.

Coexists with Kousaki's guardian.py (which remains untouched).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List
from src.types import HandoffPacket, Decision, CGRFMetadata

logger = logging.getLogger(__name__)


# Module metadata constants
_MODULE_NAME = "guardian_v3"
_MODULE_VERSION = "3.0.0"
_CGRF_TIER = 2  # Production tier (80% test coverage, policy enforcement)


# ---------- CGRF Metadata ----------

def _generate_cgrf_metadata(packet: HandoffPacket) -> CGRFMetadata:
    """Generate CGRF v3.0 metadata for Guardian agent output."""
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    report_id = f"SRS-GUARDIAN-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{packet.event.event_id[:8]}-V3.0"

    return CGRFMetadata(
        report_id=report_id,
        tier=_CGRF_TIER,
        module_version=_MODULE_VERSION,
        module_name=_MODULE_NAME,
        execution_role="BACKEND_SERVICE",
        created=timestamp,
        author="agent",
        last_updated=timestamp,
    )


# ---------- Policy Engine Integration ----------

def _get_policy_engine():
    """Lazy-load PolicyEngine to avoid hard dependency on pyyaml."""
    try:
        from src.governance.policy_engine import PolicyEngine
        return PolicyEngine()
    except Exception:
        return None


# ---------- LLM Path ----------

def _run_guardian_llm(packet: HandoffPacket) -> Decision | None:
    """Try LLM-based governance. Returns None if unavailable."""
    try:
        from src.llm.client import LLMClient
        from src.llm.prompts import GUARDIAN_SYSTEM, build_guardian_message

        client = LLMClient()
        if not client.is_available():
            return None

        sentinel_out = packet.agent_outputs.get("sentinel", SimpleNamespace(payload={}))
        sherlock_out = packet.agent_outputs.get("sherlock", SimpleNamespace(payload={}))
        fixer_out = packet.agent_outputs.get("fixer", SimpleNamespace(payload={}))

        # Load real policies for the prompt
        engine = _get_policy_engine()
        policies = []
        if engine:
            report = engine.generate_report()
            policies = report.get("governance_rules", []) + [
                {"id": p["id"], "name": p["name"]} for p in report.get("principles", [])
            ]

        resp = client.complete(
            GUARDIAN_SYSTEM,
            build_guardian_message(
                sentinel_out.payload, sherlock_out.payload,
                fixer_out.payload, policies,
            ),
        )
        if resp.success and resp.parsed:
            result = resp.parsed
            action = result.get("action", "need_approval")
            if action not in ("approve", "need_approval", "block"):
                action = "need_approval"

            decision = Decision(
                action=action,
                risk_score=float(result.get("risk_score", 0.5)),
                rationale=result.get("rationale", "LLM governance decision"),
                policy_refs=result.get("policy_refs", []),
            )
            # Record CGRF metadata in packet artifacts
            if getattr(packet, "artifacts", None) is None:
                packet.artifacts = {}
            packet.artifacts["guardian_cgrf_metadata"] = _generate_cgrf_metadata(packet).to_dict()
            logger.info("Guardian LLM decision: %s (risk=%.2f)", decision.action, decision.risk_score)
            return decision
    except Exception as e:
        logger.warning("Guardian LLM fallback: %s", e)
    return None


# ---------- Rule Path ----------

def _run_guardian_rules(packet: HandoffPacket) -> Decision:
    """Rule-based governance with real policy enforcement."""
    fixer_out = packet.agent_outputs.get("fixer", SimpleNamespace(payload={}))
    sentinel_out = packet.agent_outputs.get("sentinel", SimpleNamespace(payload={}))
    sherlock_out = packet.agent_outputs.get("sherlock", SimpleNamespace(payload={}))

    fixer_risk = fixer_out.payload.get("risk_estimate", 0.5)
    severity = sentinel_out.payload.get("severity", "medium")
    signals = sentinel_out.payload.get("signals", [])
    confidence = sherlock_out.payload.get("confidence", 0.5)
    hypotheses = sherlock_out.payload.get("hypotheses", [])

    # VERIFY: explicit verification steps provided by Fixer (deterministic)
    verification_steps = fixer_out.payload.get("verification_steps") or []
    has_verification_steps = isinstance(verification_steps, list) and len(verification_steps) > 0

    # Optional: verification results recorded by Executor (prefer packet.artifacts, fallback to event.artifacts/meta)
    # We support both:
    # - packet.artifacts["verification_results"]  (orchestrator/executor attaches)
    # - packet.event.artifacts.* (if modeled there)
    pkt_artifacts = getattr(packet, "artifacts", None) or {}
    ev_artifacts = getattr(getattr(packet, "event", None), "artifacts", None)
    ev_meta = {}
    try:
        # Some implementations store extra blobs under event.artifacts.meta or similar
        ev_meta = getattr(ev_artifacts, "meta", None) or {}
    except Exception:
        ev_meta = {}

    verification_results = (
        pkt_artifacts.get("verification_results")
        or ev_meta.get("verification_results")
        or []
    )
    has_verification_results = isinstance(verification_results, list) and len(verification_results) > 0
    verification_all_success = False
    if has_verification_results:
        try:
            verification_all_success = all(
                bool(r.get("success")) for r in verification_results if isinstance(r, dict)
            )
        except Exception:
            verification_all_success = False

    # Multi-factor risk aggregation
    severity_weight = {"low": 0.1, "medium": 0.3, "high": 0.6, "critical": 0.9}.get(severity, 0.3)
    confidence_penalty = (1.0 - confidence) * 0.2
    security_bump = 0.2 if "security_vulnerability" in signals else 0.0

    base_risk = round(min(
        fixer_risk * 0.4 + severity_weight * 0.3 + confidence_penalty + security_bump,
        0.99,
    ), 3)

    # Mitigations: verify steps reduce uncertainty; passed verification reduces further
    mit_steps = 0.04 if has_verification_steps else 0.0
    mit_passed = 0.08 if verification_all_success else 0.0

    aggregate_risk = round(base_risk - mit_steps - mit_passed, 3)
    if aggregate_risk < 0.0:
        aggregate_risk = 0.0
    if aggregate_risk > 1.0:
        aggregate_risk = 1.0

    triggered_policies: List[str] = []
    rationale_parts: List[str] = []

    # Security override
    if "security_vulnerability" in signals and severity == "critical":
        triggered_policies.append("GOV-SEC-001")
        if aggregate_risk < 0.25:
            aggregate_risk = 0.35
            rationale_parts.append("Security escalation: critical vulnerability overrides auto-approve")

    # Risk band decision
    if aggregate_risk < 0.25:
        action = "approve"
        triggered_policies.append("GOV-RISK-BAND-001")
        rationale_parts.append(f"Low aggregated risk ({aggregate_risk}): auto-approved")
    elif aggregate_risk < 0.65:
        action = "need_approval"
        triggered_policies.append("GOV-RISK-BAND-002")
        rationale_parts.append(f"Medium aggregated risk ({aggregate_risk}): human review required")
    else:
        action = "block"
        triggered_policies.append("GOV-RISK-BAND-003")
        rationale_parts.append(f"High aggregated risk ({aggregate_risk}): blocked by policy")

    # RAI policies
    triggered_policies.extend(["RAI-001", "RAI-002", "RAI-003"])

    # Evidence chain
    rationale_parts.append(f"Severity: {severity}, Diagnosis confidence: {confidence}")
    # Sherlock hypotheses may be list[object] (preferred) or list[str] (legacy)
    if isinstance(hypotheses, list) and hypotheses:
        if isinstance(hypotheses[0], dict):
            rationale_parts.append(f"Top hypothesis: {str(hypotheses[0].get('title',''))[:80]}")
        else:
            rationale_parts.append(f"Top hypothesis: {str(hypotheses[0])[:80]}")

    rationale_parts.append(f"Fixer risk: {fixer_risk}, Security signals: {len([s for s in signals if 'security' in s])}")
    if has_verification_steps:
        rationale_parts.append("Mitigation: verification_steps provided (-0.04)")
    if verification_all_success:
        rationale_parts.append("Mitigation: verification passed (-0.08)")

    decision = Decision(
        action=action,
        risk_score=aggregate_risk,
        rationale=" | ".join(rationale_parts),
        policy_refs=triggered_policies,
    )

    # Expose guardian risk model for audit/report (deterministic)
    if getattr(packet, "artifacts", None) is None:
        packet.artifacts = {}
    packet.artifacts["guardian_risk_model"] = {
        "base_risk": float(base_risk),
        "mitigations": [
            {"id": "M_VERIFICATION_STEPS_PROVIDED", "delta": -0.04, "active": bool(has_verification_steps)},
            {"id": "M_VERIFICATION_PASSED", "delta": -0.08, "active": bool(verification_all_success)},
        ],
        "final_risk": float(aggregate_risk),
        "verify": {
            "has_steps": bool(has_verification_steps),
            "has_results": bool(has_verification_results),
            "all_success": bool(verification_all_success),
        },
        "inputs": {
            "verification_results_source": (
                "packet.artifacts" if pkt_artifacts.get("verification_results") else
                ("event.artifacts.meta" if ev_meta.get("verification_results") else "none")
            )
        },
    }
    # Record CGRF metadata
    packet.artifacts["guardian_cgrf_metadata"] = _generate_cgrf_metadata(packet).to_dict()

    # Real policy compliance check
    engine = _get_policy_engine()
    if engine:
        compliance = engine.check_compliance({
            "risk_score": aggregate_risk,
            "action": action,
            "policy_refs": triggered_policies,
        })
        if not compliance.get("compliant", True):
            violations = compliance.get("violations", [])
            logger.warning("Policy violations detected: %s", violations)
            # If we're not blocking and there are violations, escalate
            if action == "approve" and violations:
                decision = Decision(
                    action="need_approval",
                    risk_score=aggregate_risk,
                    rationale=f"Policy violation override: {'; '.join(violations)} | {decision.rationale}",
                    policy_refs=triggered_policies,
                )

    return decision


def run_guardian_v3(packet: HandoffPacket) -> Decision:
    """
    Enhanced governance gate.
    Tries LLM first, falls back to rule-based logic with real policy enforcement.
    """
    result = _run_guardian_llm(packet)
    if result is not None:
        return result
    return _run_guardian_rules(packet)
