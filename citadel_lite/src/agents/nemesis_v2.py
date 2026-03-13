# src/agents/nemesis_v2.py
"""
Nemesis v2 Agent — Adversarial Resilience Assessment

A2A-compatible agent that wraps Nemesis v1 (NemesisAuditor) and adds:
  - Adversary classification (7 classes)
  - Graduated sanctions (7-level ladder)
  - Collusion detection (graph-based)

Dual mode: LLM-first with rule-based fallback.

Pipeline role: Security assessment — runs after infrastructure pipeline
or as standalone check.

CGRF v3.0 Compliance:
  SRS Code: SRS-NEMESIS-20260205-001-V3.0
  Tier: 1 (DEVELOPMENT)
  Execution Role: SECURITY

SRS: NEM-001 to NEM-099
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket
from src.nemesis.models import (
    AdversaryClass,
    NemesisReport,
    SanctionLevel,
    ThreatEvent,
    ThreatSeverity,
)
from src.nemesis.adversary_registry import classify_threat, get_profile
from src.nemesis.sanctions import SanctionsEngine
from src.nemesis.collusion_detector import CollusionDetector

logger = logging.getLogger(__name__)

# Module-level shared instances (single-process singletons)
_sanctions_engine = SanctionsEngine()
_collusion_detector = CollusionDetector()


# ---------------------------------------------------------------------------
# LLM mode (optional)
# ---------------------------------------------------------------------------

def _run_nemesis_llm(packet: HandoffPacket) -> Optional[Dict[str, Any]]:
    """Try LLM-based threat analysis. Returns None if unavailable."""
    try:
        from src.llm.client import LLMClient

        client = LLMClient()
        if not client.is_available():
            return None

        # Gather context from upstream agent outputs
        outputs = {}
        if hasattr(packet, "agent_outputs") and packet.agent_outputs:
            for name, output in packet.agent_outputs.items():
                if hasattr(output, "payload"):
                    outputs[name] = output.payload
                else:
                    outputs[name] = output

        system_prompt = (
            "You are a security assessment agent for the Citadel Nexus platform. "
            "Analyze the following agent outputs and pipeline data for adversarial "
            "behavior patterns. Respond with JSON containing: "
            "threat_level (info|low|medium|high|critical), "
            "threat_events (list of {adversary_class, severity, evidence, description}), "
            "collusion_indicators (list of strings), "
            "recommended_action (string)."
        )

        import json
        user_msg = (
            f"Pipeline outputs to analyze:\n"
            f"{json.dumps(outputs, indent=2, default=str)}\n\n"
            f"Check for: gaming patterns, trust manipulation, unauthorized access, "
            f"prompt injection, coordinated behavior, and policy violations."
        )

        resp = client.complete(system_prompt, user_msg)
        if resp.success and resp.parsed:
            result = resp.parsed
            result.setdefault("threat_level", "info")
            result.setdefault("threat_events", [])
            result.setdefault("collusion_indicators", [])
            result.setdefault("recommended_action", "none")
            result["llm_powered"] = True
            result["llm_usage"] = {
                "backend": resp.usage.backend,
                "tokens": resp.usage.total_tokens,
                "latency_ms": resp.usage.latency_ms,
            }
            logger.info("Nemesis LLM analysis: %s", result["threat_level"])
            return result

    except Exception as e:
        logger.warning("Nemesis LLM fallback: %s", e)
    return None


# ---------------------------------------------------------------------------
# Rules mode (deterministic)
# ---------------------------------------------------------------------------

def _run_nemesis_rules(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Deterministic threat assessment using adversary registry,
    sanctions engine, and collusion detector.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    threat_events: List[ThreatEvent] = []
    threat_level = ThreatSeverity.INFO

    # 1. Extract evidence from upstream agent outputs
    evidence = _extract_evidence(packet)

    # 2. Classify threats via adversary registry
    if evidence:
        adv_class, confidence = classify_threat(evidence)
        if adv_class is not None and confidence >= 0.2:
            severity = _confidence_to_severity(confidence)
            event = ThreatEvent(
                agent_id=evidence.get("target_agent_id", "unknown"),
                adversary_class=adv_class,
                severity=severity,
                evidence=evidence,
                confidence=confidence,
                description=f"Classified as {adv_class.value} with {confidence:.0%} confidence",
            )
            threat_events.append(event)

            # Update threat level
            if severity.value in ("high", "critical"):
                threat_level = severity

    # 3. Check sanctions for known agents
    agent_ids = _extract_agent_ids(packet)
    active_sanctions = []
    for agent_id in agent_ids:
        level = _sanctions_engine.get_current_level(agent_id)
        if level != SanctionLevel.OBSERVE:
            record = _sanctions_engine.get_record(agent_id)
            if record:
                active_sanctions.append(record)

        # Process new threat events through sanctions
        for event in threat_events:
            if event.agent_id == agent_id:
                _sanctions_engine.escalate(agent_id, event)

        # Check cooldown for auto-de-escalation
        _sanctions_engine.check_cooldown(agent_id)

    # 4. Run collusion detection
    collusion_score = 0.0
    if len(agent_ids) >= 2:
        collusion_score = _collusion_detector.compute_collusion_score(agent_ids)

    # 5. Determine recommended action
    recommended_action = _determine_action(threat_level, threat_events, active_sanctions, collusion_score)

    # 6. Build report
    report = NemesisReport(
        agent_id=agent_ids[0] if agent_ids else "pipeline",
        threat_events=threat_events,
        active_sanctions=active_sanctions,
        collusion_score=collusion_score,
        threat_level=threat_level,
        recommended_action=recommended_action,
    )

    return {
        "report": report.to_dict(),
        "threat_level": threat_level.value,
        "threat_event_count": len(threat_events),
        "active_sanction_count": len(active_sanctions),
        "collusion_score": collusion_score,
        "recommended_action": recommended_action,
        "agent_ids_analyzed": agent_ids,
        "llm_powered": False,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------

def _extract_evidence(packet: HandoffPacket) -> Dict[str, Any]:
    """Extract threat evidence signals from upstream agent outputs."""
    evidence: Dict[str, Any] = {}

    if not hasattr(packet, "agent_outputs") or not packet.agent_outputs:
        return evidence

    for name, output in packet.agent_outputs.items():
        payload = output.payload if hasattr(output, "payload") else output
        if not isinstance(payload, dict):
            continue

        # Watcher signals
        if name == "watcher":
            signals = payload.get("signals", [])
            if signals:
                evidence["watcher_signals"] = signals
            severity = payload.get("severity", "info")
            if severity in ("warning", "critical"):
                evidence["infra_anomaly"] = True

        # Budget signals
        if name == "budget":
            eval_data = payload.get("evaluation", {})
            if eval_data.get("severity") in ("warning", "critical"):
                evidence["budget_anomaly"] = True
            if eval_data.get("forecast_breach"):
                evidence["budget_forecast_breach"] = True

        # Curator signals
        if name == "curator":
            if payload.get("action") in ("emergency_cleanup", "alert"):
                evidence["storage_anomaly"] = True

        # Scaler signals
        if name == "scaler":
            if payload.get("scaling_action") in ("scale_up_immediately",):
                evidence["scaling_emergency"] = True

        # Any agent output with explicit threat markers
        if payload.get("trust_score_drop"):
            evidence["trust_score_drop"] = True
        if payload.get("behavioral_anomaly"):
            evidence["behavioral_anomaly"] = True
        if payload.get("policy_violation"):
            evidence["policy_violation"] = True
        if payload.get("injection_detected") or payload.get("injection_pattern_detected"):
            evidence["injection_pattern_detected"] = True

    return evidence


def _extract_agent_ids(packet: HandoffPacket) -> List[str]:
    """Extract relevant agent IDs from the packet for collusion analysis."""
    agent_ids = []

    if hasattr(packet, "agent_outputs") and packet.agent_outputs:
        for name in packet.agent_outputs:
            agent_ids.append(name)

    # Also check for explicit agent_id in packet
    if hasattr(packet, "agent_id") and packet.agent_id:
        if packet.agent_id not in agent_ids:
            agent_ids.append(packet.agent_id)

    return agent_ids


# ---------------------------------------------------------------------------
# Severity / action helpers
# ---------------------------------------------------------------------------

def _confidence_to_severity(confidence: float) -> ThreatSeverity:
    """Map classification confidence to threat severity."""
    if confidence >= 0.8:
        return ThreatSeverity.CRITICAL
    elif confidence >= 0.6:
        return ThreatSeverity.HIGH
    elif confidence >= 0.4:
        return ThreatSeverity.MEDIUM
    elif confidence >= 0.2:
        return ThreatSeverity.LOW
    return ThreatSeverity.INFO


def _determine_action(
    threat_level: ThreatSeverity,
    threat_events: List[ThreatEvent],
    active_sanctions: list,
    collusion_score: float,
) -> str:
    """Determine the recommended action based on all signals."""
    # Collusion takes precedence
    if collusion_score >= 0.8:
        return "investigate_collusion"

    # Active quarantine or higher
    for sanction in active_sanctions:
        if sanction.current_level.value >= SanctionLevel.QUARANTINE.value:
            return "maintain_quarantine"
        if sanction.current_level.value >= SanctionLevel.RESTRICT.value:
            return "enforce_restrictions"

    # Threat-based actions
    if threat_level == ThreatSeverity.CRITICAL:
        return "escalate_immediately"
    elif threat_level == ThreatSeverity.HIGH:
        return "escalate_and_monitor"
    elif threat_level == ThreatSeverity.MEDIUM:
        return "increased_monitoring"
    elif threat_level == ThreatSeverity.LOW:
        return "log_and_observe"

    return "none"


# ---------------------------------------------------------------------------
# Public entry point (A2A compatible)
# ---------------------------------------------------------------------------

def run_nemesis_v2(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Adversarial resilience assessment.
    Tries LLM first, falls back to rule-based logic.

    Compatible with A2A HandoffPacket pipeline.
    """
    result = _run_nemesis_llm(packet)
    if result is not None:
        return result
    return _run_nemesis_rules(packet)


# ---------------------------------------------------------------------------
# Accessors for engine state (for testing / external use)
# ---------------------------------------------------------------------------

def get_sanctions_engine() -> SanctionsEngine:
    """Get the module-level SanctionsEngine instance."""
    return _sanctions_engine


def get_collusion_detector() -> CollusionDetector:
    """Get the module-level CollusionDetector instance."""
    return _collusion_detector
