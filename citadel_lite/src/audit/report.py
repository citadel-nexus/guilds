# src/audit/report.py
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.types import HandoffPacket, Decision
from src.types import MemoryHit


def _safe_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    try:
        return d.get(key, default)
    except Exception:
        return default


def _pick_summary(packet: HandoffPacket) -> str:
    ev = packet.event
    base = ev.summary or f"Event: {ev.event_type}"

    s = packet.agent_outputs.get("sentinel")
    sh = packet.agent_outputs.get("sherlock")
    fx = packet.agent_outputs.get("fixer")

    classification = _safe_get(getattr(s, "payload", {}), "classification")
    hypotheses = _safe_get(getattr(sh, "payload", {}), "hypotheses", [])
    fix_plan = _safe_get(getattr(fx, "payload", {}), "fix_plan")

    parts = [base]
    if classification:
        parts.append(f"classification={classification}")
    if hypotheses:
        # Sherlock hypotheses may be list[dict] (preferred) or list[str] (legacy)
        try:
            h0 = hypotheses[0]
            if isinstance(h0, dict):
                parts.append(f"hypothesis={_safe_get(h0, 'title', '') or _safe_get(h0, 'explanation', '')}")
            else:
                parts.append(f"hypothesis={str(h0)}")
        except Exception:
            pass
    if fix_plan:
        parts.append(f"fix_plan={fix_plan}")
    return " | ".join(parts)

def _pick_memory_hits(packet: HandoffPacket, k: int = 3) -> list[dict[str, Any]]:
    """
    Pick top-k memory hits for audit report.
    - Dedup by (memory_id, evidence[0]) to avoid noisy repeats across agents
    - Sort by confidence desc, then memory_id for stability
    """
    hits = list(getattr(packet, "memory_hits", []) or [])



    # Normalize to dicts
    norm: list[dict[str, Any]] = []
    for h in hits:
        if isinstance(h, MemoryHit):
            norm.append(h.to_dict())
        elif isinstance(h, dict):
            norm.append(h)
        else:
            # unknown type -> skip
            continue

    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for d in norm:
        mid = str(d.get("memory_id", ""))
        ev0 = ""
        ev = d.get("evidence")
        if isinstance(ev, list) and ev:
            ev0 = str(ev[0])
        key = (mid, ev0)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)

    deduped.sort(
        key=lambda x: (
            -float(x.get("confidence", 0.0) or 0.0),
            # tie-break: prefer richer evidence (more items) for "more convincing" ordering
            -len(x.get("evidence") or []),
            str(x.get("memory_id", "")),
            str((x.get("evidence") or [""])[0]),
        )
    )
    return deduped[: max(0, int(k))]

def build_audit_report(packet: HandoffPacket, decision: Decision) -> Dict[str, Any]:
    """
    Minimal audit report for MVP:
      - stable fields
      - short summary
      - decision + rationale
      - agent outputs snapshot
      - evidence pointers
    """
    ev = packet.event

    sentinel_payload = packet.agent_outputs.get("sentinel").payload if "sentinel" in packet.agent_outputs else {}
    sherlock_payload = packet.agent_outputs.get("sherlock").payload if "sherlock" in packet.agent_outputs else {}
    fixer_payload = packet.agent_outputs.get("fixer").payload if "fixer" in packet.agent_outputs else {}

    # --- CGRF metadata extraction ---
    cgrf_metadata: Dict[str, Any] = {}
    if _safe_get(sentinel_payload, "cgrf_metadata"):
        cgrf_metadata["sentinel"] = _safe_get(sentinel_payload, "cgrf_metadata")
    if _safe_get(sherlock_payload, "cgrf_metadata"):
        cgrf_metadata["sherlock"] = _safe_get(sherlock_payload, "cgrf_metadata")
    if _safe_get(fixer_payload, "cgrf_metadata"):
        cgrf_metadata["fixer"] = _safe_get(fixer_payload, "cgrf_metadata")
    # Guardian stores metadata in packet.artifacts instead of payload
    guardian_cgrf = (getattr(packet, "artifacts", None) or {}).get("guardian_cgrf_metadata")
    if guardian_cgrf:
        cgrf_metadata["guardian"] = guardian_cgrf

    # --- artifacts: build outside dict literal (statements are not allowed inside {}) ---
    artifacts: Dict[str, Any] = {
        "log_excerpt_present": bool(getattr(ev.artifacts, "log_excerpt", None)),
        "links": getattr(ev.artifacts, "links", []) or [],
    }
    grm = (getattr(packet, "artifacts", None) or {}).get("guardian_risk_model")
    if grm is not None:
        artifacts["guardian_risk_model"] = grm

    # expose fixer intent (explainability) if present
    fixer_intent = (getattr(packet, "artifacts", None) or {}).get("fixer_intent")
    if fixer_intent is not None:
        artifacts["fixer_intent"] = fixer_intent

    # VERIFY: surface verification results if attached by orchestrator/execution
    verify_results = (getattr(packet, "artifacts", None) or {}).get("verification_results")
    if verify_results is not None:
        artifacts["verification_results"] = verify_results

    # Loop attempts (if orchestrator stores them)
    attempts = (getattr(packet, "artifacts", None) or {}).get("attempts")
    if attempts is not None:
        artifacts["attempts"] = attempts

    report: Dict[str, Any] = {
        "schema_version": "audit_report_v0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),

        "event": {
            "schema_version": ev.schema_version,
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "source": ev.source,
            "occurred_at": ev.occurred_at,
            "repo": ev.repo,
            "ref": ev.ref,
            "summary": ev.summary,
        },

        "audit": {
            "audit_span_id": packet.audit_span_id,
        },

        "decision": asdict(decision),

        "summary": _pick_summary(packet),

        "signals": {
            "severity": _safe_get(sentinel_payload, "severity"),
            "signals": _safe_get(sentinel_payload, "signals", []),
        },

        "diagnosis": {
            "hypotheses": _safe_get(sherlock_payload, "hypotheses", []),
            "confidence": _safe_get(sherlock_payload, "confidence"),
            "evidence": _safe_get(sherlock_payload, "evidence", []),
            "label": _safe_get(sherlock_payload, "label"),
        },

        "proposed_fix": {
            "fix_plan": _safe_get(fixer_payload, "fix_plan"),
            "risk_estimate": _safe_get(fixer_payload, "risk_estimate"),
            # Backward-compat + preferred field
            "patch": _safe_get(fixer_payload, "patch"),
            "patch_draft": _safe_get(fixer_payload, "patch_draft"),
            # VERIFY: surfaced for readability (agent_outputs also includes it)
            "verification_steps": _safe_get(fixer_payload, "verification_steps", []),
            # helpful for integrated explainability
            "sherlock_label": _safe_get(fixer_payload, "sherlock_label"),
            # Hackathon-visible
            "test_plan": _safe_get(fixer_payload, "test_plan"),
            "revision": _safe_get(fixer_payload, "revision"),
            "based_on_memory": _safe_get(fixer_payload, "based_on_memory"),
        },

        # keep the full snapshot for traceability (still small in MVP)
        "agent_outputs": {k: v.payload for k, v in packet.agent_outputs.items()},

        # memory recall (top-k)
        "memory_hits": _pick_memory_hits(packet, k=3),

        # CGRF v3.0 metadata per agent (governance, versioning, execution role)
        "cgrf_metadata": cgrf_metadata if cgrf_metadata else None,

        # minimal pointers (files are created by orchestrator)
        "artifacts": artifacts,
    }

    return report