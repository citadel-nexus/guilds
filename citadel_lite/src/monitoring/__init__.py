"""
Monitoring & Observability (Phase 26) — Prometheus metrics for Citadel Lite.

Exports recording functions that are safe to call even when
``prometheus_client`` is not installed (fail-open design).
"""
from src.monitoring.metrics import (
    record_pipeline_run,
    record_agent_run,
    record_ags_verdict,
    record_verify_retry,
    record_auto_merge,
    record_pipeline_duration,
    record_risk_score,
    set_agent_xp,
    set_agent_tp,
    set_agent_grade,
    inc_pipelines_in_flight,
    dec_pipelines_in_flight,
    get_metrics_response,
    is_enabled,
)

__all__ = [
    "record_pipeline_run",
    "record_agent_run",
    "record_ags_verdict",
    "record_verify_retry",
    "record_auto_merge",
    "record_pipeline_duration",
    "record_risk_score",
    "set_agent_xp",
    "set_agent_tp",
    "set_agent_grade",
    "inc_pipelines_in_flight",
    "dec_pipelines_in_flight",
    "get_metrics_response",
    "is_enabled",
]
