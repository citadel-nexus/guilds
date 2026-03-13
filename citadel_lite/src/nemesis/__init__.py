# src/nemesis/__init__.py
"""
Nemesis v2 — Adversarial Resilience System

Phase 1: Adversary Registry, Sanctions Engine, Collusion Detector.
Wraps existing Nemesis v1 (NemesisAuditor) and adds adversary classification,
graduated sanctions, and collusion detection.

SRS: NEM-001 to NEM-099 (NEMESIS domain)
CGRF v3.0, Tier 1 (Core Trade Secret — Perpetual Protection)
"""

from src.nemesis.models import (
    AdversaryClass,
    SanctionLevel,
    ThreatSeverity,
    AdversaryProfile,
    ThreatEvent,
    SanctionRecord,
    NemesisReport,
)
from src.nemesis.adversary_registry import classify_threat, get_profile, ADVERSARY_PROFILES
from src.nemesis.sanctions import SanctionsEngine
from src.nemesis.collusion_detector import CollusionDetector

__all__ = [
    # Models
    "AdversaryClass",
    "SanctionLevel",
    "ThreatSeverity",
    "AdversaryProfile",
    "ThreatEvent",
    "SanctionRecord",
    "NemesisReport",
    # Registry
    "classify_threat",
    "get_profile",
    "ADVERSARY_PROFILES",
    # Engines
    "SanctionsEngine",
    "CollusionDetector",
]
