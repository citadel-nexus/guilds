# src/agents/fixer_v3.py
"""
Enhanced Fixer agent with diagnosis-aware fix proposals, memory-informed
remediation, and variable risk estimation.

Supports two modes:
- LLM mode: Uses Azure OpenAI / OpenAI for intelligent fix generation
- Rule mode: Falls back to template-based logic when no LLM is available

Coexists with Kousaki's fixer.py (which remains untouched).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from src.types import HandoffPacket, CGRFMetadata

logger = logging.getLogger(__name__)


# Module metadata constants
_MODULE_NAME = "fixer_v3"
_MODULE_VERSION = "3.0.0"
_CGRF_TIER = 1  # Development tier (50% test coverage target)


# Fix templates keyed by diagnostic signal/hypothesis keywords
_FIX_TEMPLATES: List[Tuple[str, str, Optional[str], float]] = [
    ("missing dependency", "Add missing module to requirements.txt and re-run pip install", 'echo "{module}" >> requirements.txt', 0.15),
    ("missing python dependency", "Add missing module to requirements.txt and re-run pip install", 'echo "{module}" >> requirements.txt', 0.15),
    ("module not installed", "Add missing module to requirements.txt and re-run pip install", 'echo "{module}" >> requirements.txt', 0.15),
    ("not installed", "Add missing module to requirements.txt and re-run pip install", 'echo "{module}" >> requirements.txt', 0.15),
    ("import failure", "Verify package version compatibility and update requirements", None, 0.25),
    ("permission denied", "Set execute permission on the affected file with chmod +x", "chmod +x {file}", 0.10),
    ("file permission", "Set correct permissions on the affected file", "chmod +x {file}", 0.10),
    ("lacks execute permission", "Set execute permission on the affected file with chmod +x", "chmod +x {file}", 0.10),
    ("lacks permission", "Set correct permissions on the affected file", "chmod +x {file}", 0.10),
    ("missing configuration", "Add missing environment variable to CI secrets or .env file", None, 0.20),
    ("database connection", "Configure DATABASE_URL in environment variables", None, 0.25),
    ("security vulnerability", "Upgrade affected dependency to patched version", None, 0.35),
    ("known cve", "Upgrade affected dependency to patched version", None, 0.35),
    ("cve detected", "Upgrade affected dependency to patched version", None, 0.35),
    ("prototype pollution", "Upgrade affected package to latest secure version", None, 0.30),
    ("service unavailable", "Verify target service health and retry with exponential backoff", None, 0.40),
    ("memory exhaustion", "Increase memory limit or optimize resource usage in the failing step", None, 0.50),
    ("timeout", "Increase timeout threshold or optimize the slow operation", None, 0.35),
    ("syntax error", "Fix syntax error in recent commit — review diff for obvious typos", None, 0.20),
    ("assertion failure", "Review test expectations against actual behavior — possible regression", None, 0.30),
]

def _extract_module_name(log_excerpt: str) -> Optional[str]:
    """
    Extract python module name from common ModuleNotFoundError patterns.
    Example: "ModuleNotFoundError: No module named 'requests'"
    """
    s = (log_excerpt or "")
    m = re.search(r"No module named ['\"]([^'\"]+)['\"]", s, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None

def _extract_file_hint(text: str) -> Optional[str]:
    """
    Best-effort file hint extraction for permission denied.
    Example: "permission denied on deploy.sh" -> "deploy.sh"
    """
    s = (text or "")
    _EXT = r"\.(sh|py|rb|pl|exe|bat|cmd|ps1)"
    # "permission denied on deploy.sh"
    m = re.search(r"\bon\s+([A-Za-z0-9_./-]+" + _EXT + r")\b", s, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # "Error: setup.py not executable"
    m = re.search(r":\s*([A-Za-z0-9_./-]+" + _EXT + r")\b", s, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback: any path-like string ending with a known extension (e.g. /path/to/script.sh)
    m = re.search(r"(?:^|\s)(/[A-Za-z0-9_./-]+" + _EXT + r")\b", s, flags=re.IGNORECASE)
    if m:
        return Path(m.group(1).strip()).name
    return None

def _infer_label(packet: HandoffPacket, combined_hyp_lower: str) -> str:
    """
    Prefer Sherlock fixed label if present, else infer from hypotheses/log/event_type.
    Returns one of: deps_missing / permission_denied / security_alert / unknown
    """
    sherlock_out = packet.agent_outputs.get("sherlock")
    sh = sherlock_out.payload if sherlock_out else {}
    # Sherlockが固定ラベルをpayloadに載せている場合はそれを優先
    for k in ("label", "sherlock_label"):
        v = sh.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()

    # フォールバック推定
    log_excerpt = str(getattr(packet.event.artifacts, "log_excerpt", "") or "").lower()
    et = str(getattr(packet.event, "event_type", "") or "").lower()

    if ("no module named" in log_excerpt) or ("modulenotfounderror" in log_excerpt):
        return "deps_missing"
    if ("permission denied" in log_excerpt) or ("eacces" in log_excerpt) or ("eperm" in log_excerpt):
        return "permission_denied"
    if et == "security_alert":
        return "security_alert"
    if ("security vulnerability" in combined_hyp_lower) or ("prototype pollution" in combined_hyp_lower):
        return "security_alert"
    if ("missing dependency" in combined_hyp_lower) or ("missing python dependency" in combined_hyp_lower) or ("import failure" in combined_hyp_lower):
        return "deps_missing"
    if ("permission denied" in combined_hyp_lower) or ("file permission" in combined_hyp_lower):
        return "permission_denied"
    return "unknown"

def _infer_verification_steps(label: str, log_excerpt: str, summary: str) -> List[str]:
    """
    Deterministic verification steps templates (safe, local, reproducible).
    """
    lab = (label or "").lower()
    le = (log_excerpt or "")
    sm = (summary or "")

    if lab == "deps_missing":
        mod = _extract_module_name(le) or "{module}"
        return [
            "python -c \"import sys; print(sys.version)\"",
            "pip install -r requirements.txt",
            f"python -c \"import {mod}\"",
        ]

    if lab == "permission_denied":
        fh = _extract_file_hint(le) or _extract_file_hint(sm) or "{file}"
        return [
            f"ls -l {fh}",
            f"test -r {fh} && echo OK_READ || echo NG_READ",
            f"test -x {fh} && echo OK_EXEC || echo NG_EXEC",
        ]

    if lab == "security_alert":
        # best-effort package hint from summary like:
        # "Critical vulnerability detected in lodash < 4.17.21"
        # -> pkg="lodash"
        pkg = None
        m = re.search(r"\bin\s+([A-Za-z0-9_.@/-]+)\b", sm, flags=re.IGNORECASE)
        if m:
            pkg = m.group(1).strip()
        if not pkg:
            m = re.search(r"\b([A-Za-z0-9_.@/-]+)\s*<\s*\d", sm)
            if m:
                pkg = m.group(1).strip()
        pkg = pkg or "{package}"
        return [
            f"npm ls {pkg} || true",
            "npm audit || true",
            "npm audit fix || true",
            f"npm ls {pkg} || true",
        ]

    return []


def _generate_cgrf_metadata(packet: HandoffPacket) -> CGRFMetadata:
    """Generate CGRF v3.0 metadata for Fixer agent output."""
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    report_id = f"SRS-FIXER-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{packet.event.event_id[:8]}-V3.0"

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


def _run_fixer_llm(packet: HandoffPacket) -> Dict[str, Any] | None:
    """Try LLM-based fix generation. Returns None if unavailable."""
    try:
        from src.llm.client import LLMClient
        from src.llm.prompts import FIXER_SYSTEM, build_fixer_message

        client = LLMClient()
        if not client.is_available():
            return None

        sentinel_out = packet.agent_outputs.get("sentinel")
        sherlock_out = packet.agent_outputs.get("sherlock")
        sentinel_data = sentinel_out.payload if sentinel_out else {}
        sherlock_data = sherlock_out.payload if sherlock_out else {}
        memory_hits = packet.memory_hits or []

        event_data = {
            "summary": packet.event.summary,
            "log_excerpt": packet.event.artifacts.log_excerpt,
            "repo": packet.event.repo,
        }
        resp = client.complete(
            FIXER_SYSTEM,
            build_fixer_message(event_data, sherlock_data, sentinel_data, memory_hits),
        )
        if resp.success and resp.parsed:
            result = resp.parsed
            result.setdefault("fix_plan", "Manual investigation required")
            # Keep legacy field "patch" but also provide "patch_draft" for UI clarity.
            # Prefer patch_draft internally; mirror to patch for backward-compat.
            patch_draft = result.get("patch_draft", result.get("patch", None))
            result["patch_draft"] = patch_draft
            result["patch"] = patch_draft
            result.setdefault("risk_estimate", 0.5)
            result.setdefault("memory_informed", len(memory_hits) > 0)
            result.setdefault("based_on_memory", len(memory_hits) > 0)
            result.setdefault("revision", 1)
            # Test plan is required for hackathon “AI shows work”
            result.setdefault("test_plan", "Add/adjust minimal regression test covering the failure mode and rerun CI.")

            # VERIFY: if LLM returns nothing, still provide deterministic verify steps based on inferred label
            try:
                sherlock_out = packet.agent_outputs.get("sherlock")
                sh_payload = sherlock_out.payload if sherlock_out else {}
                # Sherlock v2 may return hypotheses as list[object]
                hyps = sh_payload.get("hypotheses", []) if isinstance(sh_payload, dict) else []
                hyp_texts: List[str] = []
                if isinstance(hyps, list) and hyps and isinstance(hyps[0], dict):
                    for h in hyps[:3]:
                        hyp_texts.append(str(h.get("explanation", h.get("title", ""))))
                elif isinstance(hyps, list):
                    hyp_texts = [str(x) for x in hyps[:3]]
                combined_hyp = " ".join(hyp_texts).lower()
                label = _infer_label(packet, combined_hyp)
                result.setdefault("sherlock_label", label)
                result.setdefault(
                    "verification_steps",
                    _infer_verification_steps(
                        label=label,
                        log_excerpt=str(getattr(packet.event.artifacts, "log_excerpt", "") or ""),
                        summary=str(getattr(packet.event, "summary", "") or ""),
                    ),
                )
            except Exception:
                result.setdefault("sherlock_label", "unknown")
                result.setdefault("verification_steps", [])
            result["llm_powered"] = True
            result["llm_usage"] = {
                "backend": resp.usage.backend,
                "tokens": resp.usage.total_tokens,
                "latency_ms": resp.usage.latency_ms,
            }
            # Add CGRF metadata
            result["cgrf_metadata"] = _generate_cgrf_metadata(packet).to_dict()
            logger.info("Fixer LLM proposal: risk=%.2f", result["risk_estimate"])
            return result
    except Exception as e:
        logger.warning("Fixer LLM fallback: %s", e)
    return None


def _run_fixer_rules(packet: HandoffPacket) -> Dict[str, Any]:
    """Rule-based fix proposal (original v2 logic)."""
    sherlock_out = packet.agent_outputs.get("sherlock")
    sh_payload = sherlock_out.payload if sherlock_out else {}
    hyps = sh_payload.get("hypotheses", []) if isinstance(sh_payload, dict) else []
    # Sherlock may return list[object] (preferred) or list[str] (legacy)
    hypotheses_text: List[str] = []
    if isinstance(hyps, list) and hyps and isinstance(hyps[0], dict):
        for h in hyps[:3]:
            hypotheses_text.append(str(h.get("explanation", h.get("title", ""))))
    elif isinstance(hyps, list):
        hypotheses_text = [str(x) for x in hyps[:3]]
    confidence = sh_payload.get("confidence", 0.5) if isinstance(sh_payload, dict) else 0.5


    sentinel_out = packet.agent_outputs.get("sentinel")
    severity = sentinel_out.payload.get("severity", "medium") if sentinel_out else "medium"

    memory_hits = packet.memory_hits or []

    fix_plan_parts: List[str] = []
    patches: List[str] = []
    risk_estimates: List[float] = []

    combined_hyp = " ".join(hypotheses_text).lower()

    for pattern, plan, patch_tpl, risk in _FIX_TEMPLATES:
        if pattern in combined_hyp:
            fix_plan_parts.append(plan)
            if patch_tpl:
                patches.append(patch_tpl)
            risk_estimates.append(risk)

    memory_fix = None
    for hit in memory_hits:
        snippet = getattr(hit, "snippet", "").lower()
        if "resolved" in snippet or "fixed" in snippet or "outcome: approve" in snippet:
            memory_fix = getattr(hit, "snippet", "")
            break

    if memory_fix:
        fix_plan_parts.append(f"Past resolution: {memory_fix}")

    if not fix_plan_parts:
        fix_plan_parts.append("Manual investigation required — no automated fix template matched")
        risk_estimates.append(0.5)

    base_risk = min(risk_estimates) if risk_estimates else 0.5
    severity_multiplier = {"low": 0.7, "medium": 1.0, "high": 1.3, "critical": 1.8}.get(severity, 1.0)
    confidence_discount = 1.0 - (confidence * 0.3)
    final_risk = round(min(base_risk * severity_multiplier * confidence_discount, 0.95), 3)

    patch_str = "\n".join(patches) if patches else None
    patch_draft = patch_str

    label = _infer_label(packet, combined_hyp)
    verification_steps = _infer_verification_steps(
        label=label,
        log_excerpt=str(getattr(packet.event.artifacts, "log_excerpt", "") or ""),
        summary=str(getattr(packet.event, "summary", "") or ""),
    )

    # Deterministic minimal test plan per label (hackathon-visible output)
    if label == "deps_missing":
        test_plan = "Add a smoke import test for the missing module (e.g., python -c \"import X\") and run CI."
    elif label == "permission_denied":
        test_plan = "Add a CI step to assert file permissions (ls -l + test -x) before deployment step."
    elif label == "security_alert":
        test_plan = "Add dependency audit step (npm audit) and lockfile update test; ensure vulnerable version is excluded."
    else:
        test_plan = "Add/adjust minimal regression test covering the failure mode and rerun CI."


    return {
        "fix_plan": "; ".join(fix_plan_parts),
        # Backward-compat
        "patch": patch_str,
        # Preferred field for UI clarity
        "patch_draft": patch_draft,
        "risk_estimate": final_risk,
        "memory_informed": memory_fix is not None,
        "based_on_memory": memory_fix is not None,
        "revision": 1,
        "templates_matched": len(risk_estimates),
        "severity_factor": severity,
        "sherlock_label": label,
        "verification_steps": verification_steps,
        "test_plan": test_plan,
        "llm_powered": False,
        "cgrf_metadata": _generate_cgrf_metadata(packet).to_dict(),
    }


def run_fixer_v3(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Enhanced fix proposal.
    Tries LLM first, falls back to template-based logic.
    """
    result = _run_fixer_llm(packet)
    if result is not None:
        return result
    return _run_fixer_rules(packet)
