# src/agents/curator_v2.py
"""
Curator Agent — Data Lifecycle Guardian

Manages S3 data lifecycle for 1TB+ storage, classifies objects by
access pattern, recommends tiering transitions, and optimizes costs.

Pipeline role: Third in Watcher → Scaler → Curator chain.
Analogous to Guardian in the incident pipeline.

Supports two modes:
- LLM mode: Intelligent data classification and cost optimization
- Rule mode: Prefix-based lifecycle rules when no LLM is available

CGRF v3.0 Compliance:
- SRS Code: SRS-CURATOR-20260204-001-V3.0
- Tier: 1 (DEVELOPMENT)
- Execution Role: INFRASTRUCTURE

@module citadel_lite.src.agents.curator_v2
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket

logger = logging.getLogger(__name__)

# S3 storage cost per GB/month (us-east-1)
_STORAGE_COSTS = {
    "STANDARD": 0.023,
    "STANDARD_IA": 0.0125,
    "INTELLIGENT_TIERING": 0.023,  # Same as Standard for frequent access
    "GLACIER_IR": 0.004,
    "GLACIER": 0.004,
    "DEEP_ARCHIVE": 0.00099,
}

# Lifecycle rules by prefix
_LIFECYCLE_RULES = {
    "builds/": {
        "hot_days": 7,
        "warm_days": 30,
        "cold_days": 90,
        "delete_days": 180,
        "description": "Build artifacts",
    },
    "logs/": {
        "hot_days": 7,
        "warm_days": 30,
        "cold_days": 365,
        "archive_days": 2555,  # 7 years
        "description": "Logs and audit trails",
    },
    "tmp/": {
        "delete_days": 7,
        "description": "Temporary/cache files",
    },
    "assets/": {
        "hot_days": 30,
        "warm_days": 90,
        "cold_days": 365,
        "description": "Generated images and media",
    },
    "embeddings/": {
        "hot_days": 30,
        "warm_days": 90,
        "delete_days": 365,
        "description": "Vector embeddings",
    },
    "uploads/": {
        "hot_days": 30,
        "warm_days": 90,
        "cold_days": 365,
        "description": "User uploads",
    },
}


def _run_curator_llm(packet: HandoffPacket) -> Optional[Dict[str, Any]]:
    """Try LLM-based data lifecycle analysis. Returns None if unavailable."""
    try:
        from src.llm.client import LLMClient

        client = LLMClient()
        if not client.is_available():
            return None

        # Get upstream context
        watcher_out = packet.agent_outputs.get("watcher")
        watcher_data = {}
        if watcher_out:
            watcher_data = watcher_out.payload if hasattr(watcher_out, "payload") else watcher_out

        bucket_stats = _get_bucket_stats()

        system_prompt = (
            "You are a data lifecycle management agent for the Citadel Nexus platform. "
            "Analyze the S3 bucket usage and recommend lifecycle transitions to optimize "
            "storage costs. The budget target is ~$15/mo for 1TB storage. "
            "Respond with JSON containing: action (apply_lifecycle|archive|delete|alert|no_action), "
            "bucket_stats (dict with total_size_gb, object_count, monthly_cost, "
            "projected_cost_next_month), transitions_proposed (list of prefix/tier transitions), "
            "deletions_proposed (list), risk_score (0.0-1.0), rationale (string)."
        )

        user_msg = (
            f"S3 Bucket Stats:\n{bucket_stats}\n\n"
            f"Watcher Context:\n"
            f"- S3 size: {watcher_data.get('metrics', {}).get('s3_size_gb', 'unknown')} GB\n"
            f"- S3 growth: {watcher_data.get('metrics', {}).get('s3_growth_rate_gb_day', 'unknown')} GB/day\n"
            f"- S3 signals: {[s for s in watcher_data.get('signals', []) if 's3' in s]}\n\n"
            f"Lifecycle rules:\n{_LIFECYCLE_RULES}\n"
        )

        resp = client.complete(system_prompt, user_msg)
        if resp.success and resp.parsed:
            result = resp.parsed
            result.setdefault("action", "no_action")
            result.setdefault("bucket_stats", bucket_stats)
            result.setdefault("transitions_proposed", [])
            result.setdefault("deletions_proposed", [])
            result.setdefault("risk_score", 0.1)
            result.setdefault("rationale", "LLM-generated lifecycle recommendation")
            result["llm_powered"] = True
            result["llm_usage"] = {
                "backend": resp.usage.backend,
                "tokens": resp.usage.total_tokens,
                "latency_ms": resp.usage.latency_ms,
            }
            logger.info("Curator LLM decision: %s", result["action"])
            return result

    except Exception as e:
        logger.warning("Curator LLM fallback: %s", e)
    return None


def _get_bucket_stats() -> Dict[str, Any]:
    """Get S3 bucket statistics."""
    try:
        from src.agents.aws_agent import s3_bucket_stats
        return s3_bucket_stats()
    except Exception as exc:
        return {"error": str(exc), "total_size_gb": 0, "object_count": 0}


def _estimate_savings(prefix: str, size_gb: float, from_tier: str, to_tier: str) -> float:
    """Estimate monthly savings from a storage tier transition."""
    from_cost = _STORAGE_COSTS.get(from_tier, 0.023)
    to_cost = _STORAGE_COSTS.get(to_tier, 0.023)
    return round((from_cost - to_cost) * size_gb, 2)


def _run_curator_rules(packet: HandoffPacket) -> Dict[str, Any]:
    """Rule-based data lifecycle management (deterministic fallback)."""
    # Get upstream context
    watcher_out = packet.agent_outputs.get("watcher")
    watcher_data = {}
    if watcher_out:
        watcher_data = watcher_out.payload if hasattr(watcher_out, "payload") else watcher_out

    bucket_stats = _get_bucket_stats()
    total_gb = bucket_stats.get("total_size_gb", 0)
    monthly_cost = bucket_stats.get("monthly_cost_estimate", total_gb * 0.023)

    transitions: List[Dict[str, Any]] = []
    deletions: List[Dict[str, Any]] = []
    action = "no_action"
    risk = 0.05
    rationale = "Storage is within normal parameters"

    # Check S3-related signals from Watcher
    s3_signals = [s for s in watcher_data.get("signals", []) if "s3" in s]

    # Analyze by prefix
    try:
        from src.agents.aws_agent import s3_list

        for prefix, rules in _LIFECYCLE_RULES.items():
            try:
                objects = s3_list(prefix)
                prefix_count = len(objects)
                prefix_size = sum(o.get("size", 0) for o in objects) / (1024 ** 3)

                if prefix_size > 0:
                    # Recommend tiering based on prefix rules
                    if "delete_days" in rules and prefix == "tmp/":
                        deletions.append({
                            "prefix": prefix,
                            "count": prefix_count,
                            "size_gb": round(prefix_size, 2),
                            "reason": f"Temp files older than {rules['delete_days']} days",
                        })
                        action = "delete"

                    if "warm_days" in rules and prefix_size > 1.0:
                        savings = _estimate_savings(prefix, prefix_size, "STANDARD", "STANDARD_IA")
                        if savings > 0.5:  # Only recommend if savings > $0.50/mo
                            transitions.append({
                                "prefix": prefix,
                                "from_tier": "STANDARD",
                                "to_tier": "STANDARD_IA",
                                "size_gb": round(prefix_size, 2),
                                "savings_monthly": savings,
                                "description": rules.get("description", prefix),
                            })
                            action = "apply_lifecycle"

                    if "cold_days" in rules and prefix_size > 5.0:
                        savings = _estimate_savings(prefix, prefix_size, "STANDARD", "GLACIER_IR")
                        if savings > 1.0:
                            transitions.append({
                                "prefix": prefix,
                                "from_tier": "STANDARD",
                                "to_tier": "GLACIER_IR",
                                "size_gb": round(prefix_size, 2),
                                "savings_monthly": savings,
                                "description": rules.get("description", prefix),
                            })

            except Exception as exc:
                logger.debug("Curator prefix analysis failed for %s: %s", prefix, exc)

    except ImportError:
        logger.warning("aws_agent not available for S3 analysis")

    # Alert if S3 is growing too fast
    if "s3_critical_size" in s3_signals:
        action = "alert"
        risk = 0.4
        rationale = f"S3 bucket at {total_gb} GB — approaching 1TB limit, lifecycle rules needed"
    elif "s3_warning_size" in s3_signals:
        action = "apply_lifecycle" if transitions else "alert"
        risk = 0.2
        rationale = f"S3 bucket at {total_gb} GB — consider aggressive tiering"
    elif transitions or deletions:
        rationale = f"Found {len(transitions)} tiering opportunities and {len(deletions)} cleanup targets"
    else:
        rationale = f"S3 bucket at {total_gb} GB — no immediate action needed"

    # Calculate projected savings
    total_savings = sum(t.get("savings_monthly", 0) for t in transitions)

    return {
        "action": action,
        "bucket_stats": {
            "total_size_gb": total_gb,
            "object_count": bucket_stats.get("object_count", 0),
            "monthly_cost": round(monthly_cost, 2),
            "projected_cost_next_month": round(monthly_cost - total_savings, 2),
        },
        "transitions_proposed": transitions,
        "deletions_proposed": deletions,
        "risk_score": risk,
        "rationale": rationale,
        "llm_powered": False,
    }


def run_curator_v2(packet: HandoffPacket) -> Dict[str, Any]:
    """
    S3 data lifecycle management and cost optimization.
    Tries LLM first, falls back to rule-based logic.
    """
    result = _run_curator_llm(packet)
    if result is not None:
        return result
    return _run_curator_rules(packet)
