"""
Prometheus metric definitions and recording functions.

All functions are safe to call even when ``prometheus_client`` is not
installed — they simply no-op.  A dedicated :class:`CollectorRegistry`
is used to avoid polluting the global default registry.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ---- optional import ----

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False

# ---- isolated registry ----

_REGISTRY: Optional["CollectorRegistry"] = None  # type: ignore[type-arg]

if _HAS_PROMETHEUS:
    _REGISTRY = CollectorRegistry()

    # ==== Counters ====

    PIPELINE_RUNS_TOTAL = Counter(
        "citadel_pipeline_runs_total",
        "Total pipeline executions",
        labelnames=["event_type", "outcome"],
        registry=_REGISTRY,
    )
    AGENT_RUNS_TOTAL = Counter(
        "citadel_agent_runs_total",
        "Total individual agent invocations",
        labelnames=["agent_id"],
        registry=_REGISTRY,
    )
    AGS_VERDICTS_TOTAL = Counter(
        "citadel_ags_verdicts_total",
        "AGS judiciary verdicts",
        labelnames=["verdict"],
        registry=_REGISTRY,
    )
    VERIFY_RETRIES_TOTAL = Counter(
        "citadel_verify_retries_total",
        "Number of verify-retry loops triggered",
        registry=_REGISTRY,
    )
    AUTO_MERGE_TOTAL = Counter(
        "citadel_auto_merge_total",
        "Auto-merge attempts",
        labelnames=["result"],
        registry=_REGISTRY,
    )

    # ==== Histograms ====

    PIPELINE_DURATION_MS = Histogram(
        "citadel_pipeline_duration_ms",
        "End-to-end pipeline duration in milliseconds",
        buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10000),
        registry=_REGISTRY,
    )
    RISK_SCORES = Histogram(
        "citadel_risk_scores",
        "Distribution of Guardian risk scores",
        buckets=(0.1, 0.25, 0.5, 0.65, 0.8, 1.0),
        registry=_REGISTRY,
    )

    # ==== Gauges ====

    AGENT_XP = Gauge(
        "citadel_agent_xp",
        "Current XP for each agent",
        labelnames=["agent_id"],
        registry=_REGISTRY,
    )
    AGENT_TP = Gauge(
        "citadel_agent_tp",
        "Current TP for each agent",
        labelnames=["agent_id"],
        registry=_REGISTRY,
    )
    AGENT_GRADE = Gauge(
        "citadel_agent_grade",
        "Current CAPS grade (0=D, 1=C, 2=B, 3=A, 4=S)",
        labelnames=["agent_id"],
        registry=_REGISTRY,
    )
    PIPELINES_IN_FLIGHT = Gauge(
        "citadel_pipelines_in_flight",
        "Number of currently executing pipelines",
        registry=_REGISTRY,
    )

    # ==== MCA (Market Coverage & Automation) metrics ====

    MCA_EVOLUTION_PROPOSALS_TOTAL = Counter(
        "citadel_mca_evolution_proposals_total",
        "Total MCA evolution proposals generated",
        labelnames=["domain", "ep_type"],
        registry=_REGISTRY,
    )
    MCA_EVOLUTION_PROPOSALS_APPROVED = Counter(
        "citadel_mca_evolution_proposals_approved",
        "MCA evolution proposals that were auto-approved",
        labelnames=["domain"],
        registry=_REGISTRY,
    )
    MCA_DOMAIN_HEALTH_SCORE = Gauge(
        "citadel_mca_domain_health_score",
        "Current MCA domain health score (0–100)",
        labelnames=["domain"],
        registry=_REGISTRY,
    )
    MCA_EVOLUTION_CYCLE_DURATION_SECONDS = Histogram(
        "citadel_mca_evolution_cycle_duration_seconds",
        "End-to-end MCA evolution cycle duration in seconds",
        buckets=(1, 5, 10, 30, 60, 120, 300, 600),
        registry=_REGISTRY,
    )

# ---- grade mapping ----

_GRADE_MAP = {"D": 0, "C": 1, "B": 2, "A": 3, "S": 4}


# ---- public API ----

def is_enabled() -> bool:
    """Return ``True`` when ``prometheus_client`` is available."""
    return _HAS_PROMETHEUS


# -- counters --

def record_pipeline_run(event_type: str, outcome: str) -> None:
    if _HAS_PROMETHEUS:
        PIPELINE_RUNS_TOTAL.labels(event_type=event_type, outcome=outcome).inc()


def record_agent_run(agent_id: str) -> None:
    if _HAS_PROMETHEUS:
        AGENT_RUNS_TOTAL.labels(agent_id=agent_id).inc()


def record_ags_verdict(verdict: str) -> None:
    """*verdict* is one of ``allow``, ``review``, ``deny``."""
    if _HAS_PROMETHEUS:
        AGS_VERDICTS_TOTAL.labels(verdict=verdict.lower()).inc()


def record_verify_retry() -> None:
    if _HAS_PROMETHEUS:
        VERIFY_RETRIES_TOTAL.inc()


def record_auto_merge(result: str) -> None:
    """*result* is one of ``success``, ``failure``, ``skipped``."""
    if _HAS_PROMETHEUS:
        AUTO_MERGE_TOTAL.labels(result=result).inc()


# -- histograms --

def record_pipeline_duration(duration_ms: float) -> None:
    if _HAS_PROMETHEUS:
        PIPELINE_DURATION_MS.observe(duration_ms)


def record_risk_score(score: float) -> None:
    if _HAS_PROMETHEUS:
        RISK_SCORES.observe(score)


# -- gauges --

def set_agent_xp(agent_id: str, xp: int) -> None:
    if _HAS_PROMETHEUS:
        AGENT_XP.labels(agent_id=agent_id).set(xp)


def set_agent_tp(agent_id: str, tp: int) -> None:
    if _HAS_PROMETHEUS:
        AGENT_TP.labels(agent_id=agent_id).set(tp)


def set_agent_grade(agent_id: str, grade_str: str) -> None:
    if _HAS_PROMETHEUS:
        AGENT_GRADE.labels(agent_id=agent_id).set(_GRADE_MAP.get(grade_str, 0))


def inc_pipelines_in_flight() -> None:
    if _HAS_PROMETHEUS:
        PIPELINES_IN_FLIGHT.inc()


def dec_pipelines_in_flight() -> None:
    if _HAS_PROMETHEUS:
        PIPELINES_IN_FLIGHT.dec()


# -- MCA metrics --

def record_mca_proposals(domain: str, ep_type: str, count: int = 1) -> None:
    """Increment the MCA proposals counter.

    *domain*  e.g. ``"sales"``, ``"marketing"``
    *ep_type* e.g. ``"new_feature"``, ``"market_expansion"``
    """
    if _HAS_PROMETHEUS:
        MCA_EVOLUTION_PROPOSALS_TOTAL.labels(domain=domain, ep_type=ep_type).inc(count)


def record_mca_proposals_approved(domain: str, count: int = 1) -> None:
    """Increment the approved proposals counter for a given domain."""
    if _HAS_PROMETHEUS:
        MCA_EVOLUTION_PROPOSALS_APPROVED.labels(domain=domain).inc(count)


def set_mca_domain_health(domain: str, score: float) -> None:
    """Set the MCA domain health score gauge (0–100)."""
    if _HAS_PROMETHEUS:
        MCA_DOMAIN_HEALTH_SCORE.labels(domain=domain).set(score)


def record_mca_cycle_duration(duration_seconds: float) -> None:
    """Observe an MCA evolution cycle duration in seconds."""
    if _HAS_PROMETHEUS:
        MCA_EVOLUTION_CYCLE_DURATION_SECONDS.observe(duration_seconds)


# -- exposition --

def get_metrics_response() -> Tuple[bytes, str]:
    """Return ``(body_bytes, content_type)`` for the ``/metrics`` endpoint."""
    if not _HAS_PROMETHEUS or _REGISTRY is None:
        return (b"# prometheus_client not installed\n", "text/plain; charset=utf-8")
    return (generate_latest(_REGISTRY), CONTENT_TYPE_LATEST)
