# src/nemesis/models.py
"""
Nemesis v2 — Core data models.

All enums, dataclasses, and type definitions used across the Nemesis
adversarial resilience subsystems.

SRS: NEM-ADV-001 (Adversary Class Definition), NEM-SAN-001 (Sanctions Ladder)
CGRF v3.0, Tier 1
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AdversaryClass(str, Enum):
    """Seven adversary classes per NEM-ADV-001."""
    MALICIOUS_USER = "malicious_user"
    COMPROMISED_AGENT = "compromised_agent"
    PROMPT_INJECTION = "prompt_injection"
    SUPPLY_CHAIN = "supply_chain"
    INSIDER_THREAT = "insider_threat"
    MODEL_PROVIDER = "model_provider"
    AGENT_COLLUSION = "agent_collusion"


class SanctionLevel(int, Enum):
    """Seven-level graduated sanctions ladder per NEM-SAN-001."""
    OBSERVE = 0            # Level 0: monitoring only
    WARN = 1               # Level 1: formal warning
    THROTTLE = 2           # Level 2: capability reduction
    RESTRICT = 3           # Level 3: major suspension
    QUARANTINE = 4         # Level 4: full isolation
    HUMAN_ESCALATION = 5   # Level 5: requires human review
    RETIREMENT = 6         # Level 6: permanent decommission


class ThreatSeverity(str, Enum):
    """Threat event severity classification."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AdversaryProfile:
    """
    Defines an adversary class with detection signals and default response.
    Per NEM-ADV-001: must include capabilities, goals, attack vectors,
    detection signals, and mitigations.
    """
    adversary_class: AdversaryClass
    description: str
    capabilities: List[str]
    goals: List[str]
    attack_vectors: List[str]
    detection_signals: List[str]
    mitigations: List[str]
    default_sanction: SanctionLevel
    ttl_hours: float = 168.0  # how long to track this threat type (default 1 week)

    def matches(self, evidence: Dict[str, Any]) -> float:
        """
        Score how well evidence matches this profile's detection signals.
        Returns confidence 0.0-1.0.
        """
        if not evidence:
            return 0.0

        evidence_signals = set()
        # Collect all signal-like keys from evidence
        for key, val in evidence.items():
            if isinstance(val, bool) and val:
                evidence_signals.add(key)
            elif isinstance(val, str):
                evidence_signals.add(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        evidence_signals.add(item)

        if not self.detection_signals:
            return 0.0

        matched = 0
        for signal in self.detection_signals:
            # Check if any evidence signal contains or matches this detection signal
            for ev in evidence_signals:
                if signal.lower() in ev.lower() or ev.lower() in signal.lower():
                    matched += 1
                    break

        return min(matched / len(self.detection_signals), 1.0)


@dataclass
class ThreatEvent:
    """
    A single detected threat event with evidence and cryptographic signature.
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    adversary_class: AdversaryClass = AdversaryClass.MALICIOUS_USER
    severity: ThreatSeverity = ThreatSeverity.INFO
    evidence: Dict[str, Any] = field(default_factory=dict)
    source: str = "nemesis_v2"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    confidence: float = 0.0
    description: str = ""

    @property
    def sha256(self) -> str:
        """Cryptographic signature for immutable audit trail."""
        content = f"{self.event_id}:{self.agent_id}:{self.adversary_class.value}:{self.timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "agent_id": self.agent_id,
            "adversary_class": self.adversary_class.value,
            "severity": self.severity.value,
            "evidence": self.evidence,
            "source": self.source,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "description": self.description,
            "sha256": self.sha256,
        }


@dataclass
class SanctionRecord:
    """
    Tracks an agent's sanction state with full history.
    Per NEM-SAN-002: must include current level, entry timestamp,
    escalation count, violation history, and hash chain integrity.
    """
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    current_level: SanctionLevel = SanctionLevel.OBSERVE
    previous_level: SanctionLevel = SanctionLevel.OBSERVE
    reason: str = ""
    threat_events: List[str] = field(default_factory=list)  # event_id references
    escalation_count: int = 0
    imposed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    expires_at: Optional[str] = None
    authorized_by: Optional[str] = None

    @property
    def sha256(self) -> str:
        content = f"{self.record_id}:{self.agent_id}:{self.current_level.value}:{self.imposed_at}"
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "agent_id": self.agent_id,
            "current_level": self.current_level.value,
            "previous_level": self.previous_level.value,
            "reason": self.reason,
            "threat_events": self.threat_events,
            "escalation_count": self.escalation_count,
            "imposed_at": self.imposed_at,
            "expires_at": self.expires_at,
            "authorized_by": self.authorized_by,
            "sha256": self.sha256,
        }


@dataclass
class NemesisReport:
    """
    Complete Nemesis v2 assessment report for an agent.
    Combines v1 audit data, threat classification, sanctions, and collusion analysis.
    """
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    v1_audit: Optional[Dict[str, Any]] = None
    threat_events: List[ThreatEvent] = field(default_factory=list)
    active_sanctions: List[SanctionRecord] = field(default_factory=list)
    collusion_score: float = 0.0
    threat_level: ThreatSeverity = ThreatSeverity.INFO
    recommended_action: str = "none"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "agent_id": self.agent_id,
            "v1_audit": self.v1_audit,
            "threat_events": [e.to_dict() for e in self.threat_events],
            "active_sanctions": [s.to_dict() for s in self.active_sanctions],
            "collusion_score": self.collusion_score,
            "threat_level": self.threat_level.value,
            "recommended_action": self.recommended_action,
            "timestamp": self.timestamp,
        }
