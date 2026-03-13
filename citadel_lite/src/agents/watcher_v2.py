# src/agents/watcher_v2.py
"""
Watcher Agent — Infrastructure Sentinel

Monitors VPS/ECS/S3 metrics and classifies infrastructure events.
Acts as the "eyes" of the infrastructure agent ecosystem.

Pipeline role: First in Watcher → Scaler → Curator chain.
Analogous to Sentinel in the incident pipeline.

Supports two modes:
- LLM mode: Uses Bedrock/OpenAI for anomaly analysis and diagnosis
- Rule mode: Threshold-based detection when no LLM is available

CGRF v3.0 Compliance:
- SRS Code: SRS-WATCHER-20260204-001-V3.0
- Tier: 1 (DEVELOPMENT)
- Execution Role: INFRASTRUCTURE

@module citadel_lite.src.agents.watcher_v2
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket

logger = logging.getLogger(__name__)

# Thresholds for rule-based detection
_THRESHOLDS = {
    "cpu_critical": 90.0,
    "cpu_warning": 80.0,
    "cpu_low": 40.0,
    "memory_critical": 90.0,
    "memory_warning": 80.0,
    "s3_warning_gb": 900.0,
    "s3_critical_gb": 1000.0,
    "s3_growth_warning_gb_day": 10.0,
}


def _run_watcher_llm(packet: HandoffPacket) -> Optional[Dict[str, Any]]:
    """Try LLM-based infrastructure analysis. Returns None if unavailable."""
    try:
        from src.llm.client import LLMClient

        client = LLMClient()
        if not client.is_available():
            return None

        # Collect current metrics for LLM analysis
        metrics = _collect_raw_metrics()

        system_prompt = (
            "You are an infrastructure monitoring agent for the Citadel Nexus platform. "
            "Analyze the following infrastructure metrics and classify any issues. "
            "Respond with JSON containing: event_type (cpu_spike|s3_growth|service_unhealthy|"
            "scaling_needed|healthy), severity (critical|warning|info), signals (list of "
            "detected anomalies), and recommended_action (string)."
        )

        user_msg = (
            f"Current infrastructure state:\n"
            f"- VPS CPU: {metrics.get('vps_cpu', 'unknown')}%\n"
            f"- VPS Memory: {metrics.get('vps_memory', 'unknown')}%\n"
            f"- ECS Services: {metrics.get('ecs_services', [])}\n"
            f"- S3 Size: {metrics.get('s3_size_gb', 'unknown')} GB\n"
            f"- S3 Growth Rate: {metrics.get('s3_growth_rate_gb_day', 'unknown')} GB/day\n"
            f"- Alarms: {metrics.get('alarms', [])}\n"
        )

        resp = client.complete(system_prompt, user_msg)
        if resp.success and resp.parsed:
            result = resp.parsed
            result.setdefault("event_type", "healthy")
            result.setdefault("severity", "info")
            result.setdefault("signals", [])
            result.setdefault("recommended_action", "none")
            result["metrics"] = metrics
            result["llm_powered"] = True
            result["llm_usage"] = {
                "backend": resp.usage.backend,
                "tokens": resp.usage.total_tokens,
                "latency_ms": resp.usage.latency_ms,
            }
            logger.info("Watcher LLM analysis: %s (%s)", result["event_type"], result["severity"])
            return result

    except Exception as e:
        logger.warning("Watcher LLM fallback: %s", e)
    return None


def _collect_raw_metrics() -> Dict[str, Any]:
    """Collect raw infrastructure metrics from AWS APIs."""
    metrics: Dict[str, Any] = {
        "vps_cpu": None,
        "vps_memory": None,
        "ecs_services": [],
        "s3_size_gb": None,
        "s3_growth_rate_gb_day": None,
        "alarms": [],
        "collected_at": time.time(),
    }

    try:
        from src.agents.aws_agent import (
            cloudwatch_get_vps_metrics,
            ecs_status,
            cloudwatch_get_alarms,
            s3_bucket_stats,
        )

        # VPS metrics
        try:
            vps = cloudwatch_get_vps_metrics(5)
            cpu_data = vps.get("cpu_usage_user", {})
            mem_data = vps.get("mem_used_percent", {})
            metrics["vps_cpu"] = cpu_data.get("average")
            metrics["vps_memory"] = mem_data.get("average")
        except Exception as exc:
            logger.debug("VPS metrics collection failed: %s", exc)

        # Per-container metrics (SRS-MIGRATE-MONITOR-001)
        try:
            from src.agents.aws_agent import cloudwatch_get_container_metrics
            container_data = cloudwatch_get_container_metrics(5)
            metrics["container_stats"] = container_data
        except Exception as exc:
            logger.debug("Container metrics collection failed: %s", exc)

        # ECS status
        try:
            ecs = ecs_status()
            metrics["ecs_services"] = ecs.get("services", [])
        except Exception as exc:
            logger.debug("ECS status collection failed: %s", exc)

        # CloudWatch alarms
        try:
            alarms = cloudwatch_get_alarms()
            metrics["alarms"] = alarms.get("alarms", [])
        except Exception as exc:
            logger.debug("Alarms collection failed: %s", exc)

        # S3 bucket stats
        try:
            s3 = s3_bucket_stats()
            metrics["s3_size_gb"] = s3.get("total_size_gb")
        except Exception as exc:
            logger.debug("S3 stats collection failed: %s", exc)

    except ImportError:
        logger.warning("aws_agent not available for metrics collection")

    return metrics


def _run_watcher_rules(packet: HandoffPacket) -> Dict[str, Any]:
    """Rule-based infrastructure monitoring (deterministic fallback)."""
    metrics = _collect_raw_metrics()
    signals: List[str] = []
    event_type = "healthy"
    severity = "info"
    action = "none"

    cpu = metrics.get("vps_cpu")
    mem = metrics.get("vps_memory")
    s3_gb = metrics.get("s3_size_gb")
    services = metrics.get("ecs_services", [])
    alarms = metrics.get("alarms", [])

    # CPU checks
    if cpu is not None:
        if cpu >= _THRESHOLDS["cpu_critical"]:
            signals.append("cpu_critical")
            event_type = "cpu_spike"
            severity = "critical"
            action = "scale_up_immediately"
        elif cpu >= _THRESHOLDS["cpu_warning"]:
            signals.append("cpu_high")
            event_type = "scaling_needed"
            severity = "warning"
            action = "scale_up"
        elif cpu <= _THRESHOLDS["cpu_low"]:
            signals.append("cpu_low")
            # Only suggest scale-down if services are scaled up
            action = "consider_scale_down"

    # Memory checks
    if mem is not None:
        if mem >= _THRESHOLDS["memory_critical"]:
            signals.append("memory_critical")
            if severity != "critical":
                severity = "critical"
                event_type = "scaling_needed"
                action = "scale_up_immediately"
        elif mem >= _THRESHOLDS["memory_warning"]:
            signals.append("memory_high")
            if severity == "info":
                severity = "warning"

    # ECS service health
    for svc in services:
        desired = svc.get("desired", 0)
        running = svc.get("running", 0)
        if desired > 0 and running < desired:
            signals.append(f"service_unhealthy:{svc.get('name', 'unknown')}")
            if event_type == "healthy":
                event_type = "service_unhealthy"
            if severity == "info":
                severity = "warning"
            action = "investigate_service"

    # S3 checks
    if s3_gb is not None:
        if s3_gb >= _THRESHOLDS["s3_critical_gb"]:
            signals.append("s3_critical_size")
            if severity == "info":
                severity = "warning"
                event_type = "s3_growth"
                action = "apply_lifecycle_rules"
        elif s3_gb >= _THRESHOLDS["s3_warning_gb"]:
            signals.append("s3_warning_size")

    # Per-container checks (SRS-MIGRATE-MONITOR-001)
    container_stats = metrics.get("container_stats", {})
    containers = container_stats.get("containers", {}) if isinstance(container_stats, dict) else {}
    for cname, cstats in containers.items():
        c_cpu = cstats.get("cpu_percent", {})
        c_mem = cstats.get("mem_percent", {})
        c_cpu_avg = c_cpu.get("average") if isinstance(c_cpu, dict) else c_cpu
        c_mem_avg = c_mem.get("average") if isinstance(c_mem, dict) else c_mem

        if c_cpu_avg is not None and c_cpu_avg >= 15.0:
            signals.append(f"container_cpu_high:{cname}")
        if c_mem_avg is not None and c_mem_avg >= 70.0:
            signals.append(f"container_mem_high:{cname}")

    # If any container is high CPU and overall VPS CPU is high, recommend migration
    has_container_cpu_high = any(s.startswith("container_cpu_high:") for s in signals)
    if has_container_cpu_high and cpu is not None and cpu >= _THRESHOLDS["cpu_warning"]:
        if action in ("scale_up", "scale_up_immediately"):
            action = "consider_migration"

    # Active alarms
    for alarm in alarms:
        if alarm.get("state") == "ALARM":
            signals.append(f"alarm_active:{alarm.get('name', 'unknown')}")
            if severity == "info":
                severity = "warning"

    return {
        "event_type": event_type,
        "severity": severity,
        "signals": signals,
        "signal_count": len(signals),
        "metrics": metrics,
        "recommended_action": action,
        "llm_powered": False,
    }


def run_watcher_v2(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Infrastructure monitoring and event classification.
    Tries LLM first, falls back to rule-based logic.
    """
    result = _run_watcher_llm(packet)
    if result is not None:
        return result
    return _run_watcher_rules(packet)
