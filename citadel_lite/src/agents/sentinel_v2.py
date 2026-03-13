# src/agents/sentinel_v2.py
"""
Enhanced Sentinel agent with richer classification, severity mapping,
and signal extraction from log excerpts and event metadata.

Supports two modes:
- LLM mode: Uses Azure OpenAI / OpenAI for intelligent classification
- Rule mode: Falls back to pattern-based logic when no LLM is available

Coexists with Kousaki's sentinel.py (which remains untouched).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from src.types import HandoffPacket, CGRFMetadata

logger = logging.getLogger(__name__)


# Module metadata constants
_MODULE_NAME = "sentinel_v2"
_MODULE_VERSION = "2.1.0"
_CGRF_TIER = 1  # Development tier (50% test coverage target)


# Severity mapping by event type
_SEVERITY_MAP: Dict[str, str] = {
    "ci_failed": "medium",
    "deploy_failed": "high",
    "security_alert": "critical",
    "test_regression": "medium",
    "config_drift": "low",
    "performance_degradation": "medium",
}

# Signal extraction patterns from log text
_SIGNAL_PATTERNS: List[tuple] = [
    ("modulenotfounderror", "missing_dependency"),
    ("importerror", "missing_dependency"),
    ("permissionerror", "permission_denied"),
    ("permission denied", "permission_denied"),
    ("connectionrefused", "service_unavailable"),
    ("timeout", "timeout"),
    ("outofmemory", "resource_exhaustion"),
    ("cve-", "security_vulnerability"),
    ("cvss", "security_vulnerability"),
    ("prototype pollution", "security_vulnerability"),
    ("sql injection", "security_vulnerability"),
    ("keyerror", "missing_configuration"),
    ("env", "environment_issue"),
    ("segfault", "crash"),
    ("killed", "oom_killed"),
]


def _generate_cgrf_metadata(packet: HandoffPacket) -> CGRFMetadata:
    """Generate CGRF v3.0 metadata for Sentinel agent output."""
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    report_id = f"SRS-SENTINEL-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{packet.event.event_id[:8]}-V3.0"

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


def _run_sentinel_llm(packet: HandoffPacket) -> Dict[str, Any] | None:
    """Try LLM-based classification. Returns None if unavailable."""
    try:
        from src.llm.client import LLMClient
        from src.llm.prompts import SENTINEL_SYSTEM, build_sentinel_message

        client = LLMClient()
        if not client.is_available():
            return None

        event_data = {
            "event_type": packet.event.event_type,
            "source": packet.event.source,
            "summary": packet.event.summary,
            "log_excerpt": packet.event.artifacts.log_excerpt,
            "repo": packet.event.repo,
        }
        resp = client.complete(SENTINEL_SYSTEM, build_sentinel_message(event_data))
        if resp.success and resp.parsed:
            result = resp.parsed
            # Ensure required fields
            result.setdefault("classification", packet.event.event_type)
            result.setdefault("severity", "medium")
            result.setdefault("signals", [])
            result.setdefault("signal_count", len(result["signals"]))
            result["source"] = packet.event.source
            result["llm_powered"] = True
            result["llm_usage"] = {
                "backend": resp.usage.backend,
                "tokens": resp.usage.total_tokens,
                "latency_ms": resp.usage.latency_ms,
            }
            # Add CGRF metadata
            result["cgrf_metadata"] = _generate_cgrf_metadata(packet).to_dict()
            logger.info("Sentinel LLM classification: %s", result.get("classification"))
            return result
    except Exception as e:
        logger.warning("Sentinel LLM fallback: %s", e)
    return None


def _run_sentinel_rules(packet: HandoffPacket) -> Dict[str, Any]:
    """Rule-based classification (original v2 logic)."""
    et = packet.event.event_type
    log_text = (packet.event.artifacts.log_excerpt or "").lower()
    extra = packet.event.artifacts.extra or {}

    severity = extra.get("severity") or _SEVERITY_MAP.get(et, "medium")

    signals = []
    if et:
        signals.append(et)

    for pattern, signal in _SIGNAL_PATTERNS:
        if pattern in log_text and signal not in signals:
            signals.append(signal)

    if "security_vulnerability" in signals and severity not in ("critical", "high"):
        severity = "high"

    classification = et
    if "security_vulnerability" in signals:
        classification = "security_alert" if et != "security_alert" else et

    return {
        "classification": classification,
        "severity": severity,
        "signals": signals,
        "signal_count": len(signals),
        "source": packet.event.source,
        "llm_powered": False,
        "cgrf_metadata": _generate_cgrf_metadata(packet).to_dict(),
    }


def run_sentinel_v2(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Enhanced detection & classification.
    Tries LLM first, falls back to rule-based logic.
    """
    result = _run_sentinel_llm(packet)
    if result is not None:
        return result
    return _run_sentinel_rules(packet)
