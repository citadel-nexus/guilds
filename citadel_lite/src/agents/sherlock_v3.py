# src/agents/sherlock_v3.py
"""
Enhanced Sherlock agent with broader pattern matching, memory-aware diagnosis,
and confidence scoring based on evidence strength.

Supports two modes:
- LLM mode: Uses Azure OpenAI / OpenAI for intelligent root cause analysis
- Rule mode: Falls back to pattern-based logic when no LLM is available

Coexists with Kousaki's sherlock.py (which remains untouched).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from src.types import HandoffPacket, CGRFMetadata

logger = logging.getLogger(__name__)


# Module metadata constants
_MODULE_NAME = "sherlock_v3"
_MODULE_VERSION = "3.0.0"
_CGRF_TIER = 1  # Development tier (50% test coverage target)


# Diagnostic patterns: (log_pattern, hypothesis, base_confidence)
_DIAGNOSTIC_PATTERNS: List[Tuple[str, str, float]] = [
    ("modulenotfounderror", "Missing Python dependency — module not installed in environment", 0.85),
    ("importerror", "Import failure — package may be missing or have version conflict", 0.80),
    ("no module named", "Missing dependency — not declared in requirements", 0.85),
    ("permissionerror", "Permission denied — file or resource lacks execute/read permission", 0.80),
    ("permission denied", "Permission denied on file or directory access", 0.80),
    ("chmod", "File permission issue — needs chmod to set correct permissions", 0.75),
    ("connectionrefused", "Service unavailable — target service not running or unreachable", 0.70),
    ("timeout", "Operation timed out — possible network or resource bottleneck", 0.60),
    ("outofmemory", "Memory exhaustion — process exceeded available RAM", 0.75),
    ("killed", "Process killed — likely OOM killer or resource limit hit", 0.70),
    ("keyerror", "Missing configuration key — environment variable or config not set", 0.75),
    ("filenotfounderror", "Missing file — expected file does not exist at path", 0.80),
    ("cve-", "Known security vulnerability (CVE) detected in dependency", 0.90),
    ("cvss", "Security vulnerability with CVSS scoring — dependency update needed", 0.90),
    ("prototype pollution", "Prototype pollution vulnerability — upgrade affected package", 0.88),
    ("segfault", "Segmentation fault — possible memory corruption or native code bug", 0.65),
    ("syntax error", "Syntax error in source code — likely recent commit introduced bad syntax", 0.85),
    ("assertion", "Assertion failure — test expectation not met", 0.70),
    ("database_url", "Database connection not configured — missing DATABASE_URL", 0.80),
    ("secret", "Possible secrets/credentials issue in configuration", 0.60),
]

def _mk_hypothesis(title: str, explanation: str, evidence: List[Dict[str, Any]], confidence: float) -> Dict[str, Any]:
    # Deterministic normalized hypothesis object (UI-friendly, audit-friendly)
    c = float(confidence)
    if c < 0.0:
        c = 0.0
    if c > 1.0:
        c = 1.0
    return {
        "title": title.strip() or "Unknown",
        "explanation": explanation.strip() or "",
        "evidence": evidence or [],
        "confidence": round(c, 3),
    }

def _infer_sherlock_label(combined_text: str, event_type: str) -> str:
    t = (combined_text or "").lower()
    et = (event_type or "").lower()
    if ("no module named" in t) or ("modulenotfounderror" in t) or ("importerror" in t):
        return "deps_missing"
    if ("permission denied" in t) or ("permissionerror" in t) or ("eacces" in t) or ("eperm" in t):
        return "permission_denied"
    if (et == "security_alert") or ("cve-" in t) or ("cvss" in t) or ("prototype pollution" in t):
        return "security_alert"
    return "unknown"


def _generate_cgrf_metadata(packet: HandoffPacket) -> CGRFMetadata:
    """Generate CGRF v3.0 metadata for Sherlock agent output."""
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    report_id = f"SRS-SHERLOCK-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{packet.event.event_id[:8]}-V3.0"

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


def _run_sherlock_llm(packet: HandoffPacket) -> Dict[str, Any] | None:
    """Try LLM-based diagnosis. Returns None if unavailable."""
    try:
        from src.llm.client import LLMClient
        from src.llm.prompts import SHERLOCK_SYSTEM, build_sherlock_message

        client = LLMClient()
        if not client.is_available():
            return None

        sentinel_out = packet.agent_outputs.get("sentinel")
        sentinel_data = sentinel_out.payload if sentinel_out else {}
        memory_hits = packet.memory_hits or []

        event_data = {
            "summary": packet.event.summary,
            "log_excerpt": packet.event.artifacts.log_excerpt,
        }
        resp = client.complete(
            SHERLOCK_SYSTEM,
            build_sherlock_message(event_data, sentinel_data, memory_hits),
        )
        if resp.success and resp.parsed:
            result = resp.parsed
            # Normalize into structured hypotheses (preferred contract)
            # Backward-compat: if LLM returns old schema, convert.
            raw_hyps = result.get("hypotheses")
            if isinstance(raw_hyps, list) and raw_hyps and isinstance(raw_hyps[0], str):
                # Convert list[str] -> list[object]
                result["hypotheses"] = [
                    _mk_hypothesis(
                        title=h[:80],
                        explanation=h,
                        evidence=[{"type": "llm_reason", "value": "generated"}],
                        confidence=float(result.get("confidence", 0.5)),
                    )
                    for h in raw_hyps[:3]
                ]
            elif isinstance(raw_hyps, list) and raw_hyps and isinstance(raw_hyps[0], dict):
                # Ensure required fields exist
                norm = []
                for h in raw_hyps[:3]:
                    norm.append(_mk_hypothesis(
                        title=str(h.get("title", ""))[:120],
                        explanation=str(h.get("explanation", ""))[:2000],
                        evidence=h.get("evidence") if isinstance(h.get("evidence"), list) else [],
                        confidence=float(h.get("confidence", result.get("confidence", 0.5))),
                    ))
                result["hypotheses"] = norm
            else:
                result["hypotheses"] = [
                    _mk_hypothesis(
                        title="Unable to determine",
                        explanation="LLM could not determine a clear root cause",
                        evidence=[],
                        confidence=float(result.get("confidence", 0.5)),
                    )
                ]

            # Keep aggregate confidence for quick display
            result["confidence"] = float(result.get("confidence", 0.5))
            # Provide a fixed label for downstream agents (Fixer/Guardian)
            combined_text = f"{event_data.get('log_excerpt','')} {event_data.get('summary','')}"
            result.setdefault("label", _infer_sherlock_label(combined_text, getattr(packet.event, "event_type", "")))
            # Evidence list kept for backward-compat, and for quick filtering
            result.setdefault("evidence", [])
            result.setdefault("memory_informed", len(memory_hits) > 0)
            result["llm_powered"] = True
            result["llm_usage"] = {
                "backend": resp.usage.backend,
                "tokens": resp.usage.total_tokens,
                "latency_ms": resp.usage.latency_ms,
            }
            # Add CGRF metadata
            result["cgrf_metadata"] = _generate_cgrf_metadata(packet).to_dict()
            logger.info("Sherlock LLM diagnosis: confidence=%.2f", result["confidence"])
            return result
    except Exception as e:
        logger.warning("Sherlock LLM fallback: %s", e)
    return None


def _run_sherlock_rules(packet: HandoffPacket) -> Dict[str, Any]:
    """Rule-based diagnosis (original v2 logic)."""
    log_text = (packet.event.artifacts.log_excerpt or "").lower()
    summary_text = (packet.event.summary or "").lower()
    combined_text = f"{log_text} {summary_text}"

    sentinel_out = packet.agent_outputs.get("sentinel")
    signals = sentinel_out.payload.get("signals", []) if sentinel_out else []

    hypotheses_text: List[str] = []
    hypotheses_obj: List[Dict[str, Any]] = []
    confidence_scores: List[float] = []
    evidence_flat: List[str] = []

    for pattern, hypothesis, base_conf in _DIAGNOSTIC_PATTERNS:
        if pattern in combined_text:
            hypotheses_text.append(hypothesis)
            confidence_scores.append(base_conf)
            evidence_flat.append(f"pattern_match:{pattern}")

    memory_hits = packet.memory_hits or []
    memory_boost = 0.0
    memory_evidence = []

    for hit in memory_hits:
        hit_title = getattr(hit, 'title', '')
        hit_snippet = getattr(hit, 'snippet', '')
        hit_text = f"{hit_title} {hit_snippet}".lower()
        for hyp in hypotheses_text:
            hyp_keywords = set(hyp.lower().split()[:3])
            hit_keywords = set(hit_text.split())
            overlap = hyp_keywords & hit_keywords
            if len(overlap) >= 2:
                memory_boost = max(memory_boost, 0.1)
                hit_id = getattr(hit, 'id', 'unknown')
                memory_evidence.append(f"memory_recall:{hit_id}")

    if memory_evidence:
        evidence_flat.extend(memory_evidence)

    if not hypotheses_text:
        for signal in signals:
            if signal == "ci_failed":
                hypotheses_text.append("CI pipeline failure — check recent commits and test output")
                confidence_scores.append(0.4)
            elif signal == "permission_denied":
                hypotheses_text.append("Permission issue on resource access")
                confidence_scores.append(0.5)
            elif signal == "security_vulnerability":
                hypotheses_text.append("Security vulnerability detected — dependency update required")
                confidence_scores.append(0.7)
            evidence_flat.append(f"signal:{signal}")

    if not hypotheses_text:
        hypotheses_text.append("Unable to determine root cause — manual investigation recommended")
        confidence_scores.append(0.2)
        evidence_flat.append("no_pattern_match")

    aggregate_confidence = min(
        max(confidence_scores) + memory_boost if confidence_scores else 0.2,
        0.95,
    )

    # Build top 2-3 structured hypotheses
    # Evidence is attached per hypothesis as pattern list + memory refs
    # (UI can show per-hypothesis confidence and evidence)
    for i, hyp in enumerate(hypotheses_text[:3]):
        base_conf = confidence_scores[i] if i < len(confidence_scores) else float(aggregate_confidence)
        ev: List[Dict[str, Any]] = []
        # Attach the first matched pattern as a hint (best effort)
        # If none, attach signals/memory as evidence.
        for e in evidence_flat[:6]:
            if e.startswith("pattern_match:"):
                ev.append({"type": "pattern", "value": e.split(":", 1)[1]})
            elif e.startswith("signal:"):
                ev.append({"type": "signal", "value": e.split(":", 1)[1]})
            elif e.startswith("memory_recall:"):
                ev.append({"type": "memory", "value": e.split(":", 1)[1]})
        hypotheses_obj.append(_mk_hypothesis(
            title=hyp[:80],
            explanation=hyp,
            evidence=ev,
            confidence=float(base_conf),
        ))

    label = _infer_sherlock_label(combined_text, getattr(packet.event, "event_type", ""))


    return {
        # Preferred contract: list[object]
        "hypotheses": hypotheses_obj if hypotheses_obj else [
            _mk_hypothesis("Unable to determine", "Manual investigation recommended", [], float(aggregate_confidence))
        ],
        "confidence": round(aggregate_confidence, 3),
        # Backward-compat flat evidence list
        "evidence": evidence_flat,
        "label": label,
        "memory_informed": len(memory_evidence) > 0,
        "patterns_matched": len([s for s in confidence_scores if s > 0]),
        "llm_powered": False,
        "cgrf_metadata": _generate_cgrf_metadata(packet).to_dict(),
    }


def run_sherlock_v3(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Enhanced diagnosis.
    Tries LLM first, falls back to rule-based logic.
    """
    result = _run_sherlock_llm(packet)
    if result is not None:
        return result
    return _run_sherlock_rules(packet)
