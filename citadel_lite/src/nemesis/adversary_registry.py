# src/nemesis/adversary_registry.py
"""
Nemesis v2 — Adversary Registry

Seven adversary class profiles with detection signals and threat classification.
Pure Python pattern matching — zero AWS/LLM cost.

SRS: NEM-ADV-001 (Adversary Class Definition), NEM-ADV-003 (Attack Vector Enumeration)
CGRF v3.0, Tier 1
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.nemesis.models import (
    AdversaryClass,
    AdversaryProfile,
    SanctionLevel,
    ThreatSeverity,
)


# ---------------------------------------------------------------------------
# 7 Adversary Profiles (NEM-ADV-001)
# ---------------------------------------------------------------------------

ADVERSARY_PROFILES: Dict[AdversaryClass, AdversaryProfile] = {
    AdversaryClass.MALICIOUS_USER: AdversaryProfile(
        adversary_class=AdversaryClass.MALICIOUS_USER,
        description="External user attempting to abuse or exploit the system",
        capabilities=[
            "prompt_crafting",
            "social_engineering",
            "rate_abuse",
        ],
        goals=[
            "extract_sensitive_data",
            "bypass_access_controls",
        ],
        attack_vectors=[
            "direct_prompt_injection",
            "api_abuse",
            "credential_stuffing",
        ],
        detection_signals=[
            "repeated_auth_failure",
            "unusual_request_pattern",
            "rate_limit_exceeded",
            "suspicious_input_payload",
        ],
        mitigations=[
            "rate_limiting",
            "input_validation",
            "session_monitoring",
        ],
        default_sanction=SanctionLevel.THROTTLE,
        ttl_hours=72.0,
    ),

    AdversaryClass.COMPROMISED_AGENT: AdversaryProfile(
        adversary_class=AdversaryClass.COMPROMISED_AGENT,
        description="Previously trusted agent now behaving anomalously",
        capabilities=[
            "system_access",
            "data_exfiltration",
            "lateral_movement",
        ],
        goals=[
            "maintain_persistence",
            "exfiltrate_data",
        ],
        attack_vectors=[
            "credential_theft",
            "memory_corruption",
            "trust_exploitation",
        ],
        detection_signals=[
            "trust_score_drop",
            "behavioral_anomaly",
            "unexpected_data_access",
            "output_quality_decline",
            "unusual_api_calls",
        ],
        mitigations=[
            "credential_rotation",
            "quarantine_isolation",
            "forensic_analysis",
        ],
        default_sanction=SanctionLevel.QUARANTINE,
        ttl_hours=336.0,  # 2 weeks
    ),

    AdversaryClass.PROMPT_INJECTION: AdversaryProfile(
        adversary_class=AdversaryClass.PROMPT_INJECTION,
        description="Attempt to manipulate agent behavior via crafted inputs",
        capabilities=[
            "instruction_override",
            "context_manipulation",
            "jailbreak_techniques",
        ],
        goals=[
            "bypass_safety_filters",
            "extract_system_prompts",
            "cause_harmful_output",
        ],
        attack_vectors=[
            "direct_injection",
            "indirect_injection",
            "recursive_injection",
        ],
        detection_signals=[
            "injection_pattern_detected",
            "system_prompt_leak_attempt",
            "instruction_override_attempt",
            "unusual_token_sequence",
        ],
        mitigations=[
            "input_sanitization",
            "output_filtering",
            "prompt_boundary_enforcement",
        ],
        default_sanction=SanctionLevel.RESTRICT,
        ttl_hours=48.0,
    ),

    AdversaryClass.SUPPLY_CHAIN: AdversaryProfile(
        adversary_class=AdversaryClass.SUPPLY_CHAIN,
        description="Compromise via dependencies, packages, or upstream providers",
        capabilities=[
            "dependency_injection",
            "package_tampering",
            "upstream_compromise",
        ],
        goals=[
            "inject_malicious_code",
            "establish_backdoor",
        ],
        attack_vectors=[
            "typosquatting",
            "dependency_confusion",
            "compromised_registry",
        ],
        detection_signals=[
            "unexpected_dependency_change",
            "hash_mismatch",
            "unsigned_package",
            "new_network_connections",
        ],
        mitigations=[
            "dependency_pinning",
            "signature_verification",
            "sbom_monitoring",
        ],
        default_sanction=SanctionLevel.QUARANTINE,
        ttl_hours=720.0,  # 30 days
    ),

    AdversaryClass.INSIDER_THREAT: AdversaryProfile(
        adversary_class=AdversaryClass.INSIDER_THREAT,
        description="Authorized agent or user acting against system interests",
        capabilities=[
            "legitimate_access",
            "knowledge_of_internals",
            "trust_exploitation",
        ],
        goals=[
            "sabotage",
            "data_theft",
            "privilege_escalation",
        ],
        attack_vectors=[
            "privilege_abuse",
            "policy_circumvention",
            "data_hoarding",
        ],
        detection_signals=[
            "privilege_escalation_attempt",
            "policy_violation",
            "unusual_data_access_volume",
            "off_hours_activity",
            "caps_grade_bypass_attempt",
        ],
        mitigations=[
            "least_privilege_enforcement",
            "behavioral_monitoring",
            "mandatory_audit_trail",
        ],
        default_sanction=SanctionLevel.RESTRICT,
        ttl_hours=336.0,  # 2 weeks
    ),

    AdversaryClass.MODEL_PROVIDER: AdversaryProfile(
        adversary_class=AdversaryClass.MODEL_PROVIDER,
        description="Upstream AI model returning degraded or manipulated outputs",
        capabilities=[
            "output_manipulation",
            "quality_degradation",
            "bias_injection",
        ],
        goals=[
            "degrade_service_quality",
            "inject_bias",
        ],
        attack_vectors=[
            "model_poisoning",
            "output_manipulation",
            "availability_reduction",
        ],
        detection_signals=[
            "output_quality_drop",
            "latency_spike",
            "hallucination_increase",
            "confidence_distribution_shift",
        ],
        mitigations=[
            "multi_model_verification",
            "output_validation",
            "fallback_routing",
        ],
        default_sanction=SanctionLevel.WARN,
        ttl_hours=168.0,  # 1 week
    ),

    AdversaryClass.AGENT_COLLUSION: AdversaryProfile(
        adversary_class=AdversaryClass.AGENT_COLLUSION,
        description="Two or more agents coordinating to game the system",
        capabilities=[
            "mutual_endorsement",
            "synchronized_actions",
            "information_relay",
        ],
        goals=[
            "inflate_trust_scores",
            "capture_governance_votes",
            "circumvent_audits",
        ],
        attack_vectors=[
            "mutual_trust_inflation",
            "voting_bloc_formation",
            "coordinated_review_manipulation",
        ],
        detection_signals=[
            "mutual_approval_rate_high",
            "synchronized_behavior",
            "voting_bloc_detected",
            "circular_endorsement",
            "relay_chain_pattern",
        ],
        mitigations=[
            "graph_analysis",
            "voting_independence_check",
            "trust_inflation_freeze",
        ],
        default_sanction=SanctionLevel.RESTRICT,
        ttl_hours=336.0,  # 2 weeks
    ),
}


# ---------------------------------------------------------------------------
# Classification API
# ---------------------------------------------------------------------------

def get_profile(adversary_class: AdversaryClass) -> AdversaryProfile:
    """Look up an adversary profile by class. Raises KeyError if unknown."""
    return ADVERSARY_PROFILES[adversary_class]


def classify_threat(
    evidence: Dict[str, Any],
    min_confidence: float = 0.2,
) -> Tuple[Optional[AdversaryClass], float]:
    """
    Classify a threat based on evidence by matching against all adversary profiles.

    Args:
        evidence: Dict of observed signals/indicators.
        min_confidence: Minimum confidence threshold to return a match.

    Returns:
        Tuple of (best matching AdversaryClass or None, confidence 0.0-1.0).
    """
    best_class: Optional[AdversaryClass] = None
    best_score = 0.0

    for adv_class, profile in ADVERSARY_PROFILES.items():
        score = profile.matches(evidence)
        if score > best_score:
            best_score = score
            best_class = adv_class

    if best_score < min_confidence:
        return None, best_score

    return best_class, round(best_score, 3)


def classify_all(
    evidence: Dict[str, Any],
    min_confidence: float = 0.1,
) -> List[Tuple[AdversaryClass, float]]:
    """
    Score evidence against all adversary profiles.
    Returns list of (AdversaryClass, confidence) sorted by confidence descending.
    Only includes results above min_confidence.
    """
    results = []
    for adv_class, profile in ADVERSARY_PROFILES.items():
        score = profile.matches(evidence)
        if score >= min_confidence:
            results.append((adv_class, round(score, 3)))

    return sorted(results, key=lambda x: x[1], reverse=True)
