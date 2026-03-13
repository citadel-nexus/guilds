"""Unit tests for Monitoring & Observability — Phase 26."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ========== metrics module loads ==========

def test_metrics_module_loads():
    """Monitoring module imports without error."""
    from src.monitoring import metrics

    assert hasattr(metrics, "record_pipeline_run")
    assert hasattr(metrics, "get_metrics_response")
    assert hasattr(metrics, "is_enabled")


def test_is_enabled_reflects_prometheus():
    """is_enabled() returns True when prometheus_client is installed."""
    from src.monitoring.metrics import is_enabled

    assert isinstance(is_enabled(), bool)
    # prometheus_client is installed in test env
    assert is_enabled() is True


# ========== recording functions ==========

def test_record_functions_noop_without_crash():
    """All recording functions are callable without raising."""
    from src.monitoring import metrics

    metrics.record_pipeline_run("ci_failed", "approve")
    metrics.record_agent_run("sentinel")
    metrics.record_ags_verdict("allow")
    metrics.record_verify_retry()
    metrics.record_auto_merge("success")
    metrics.record_pipeline_duration(123.4)
    metrics.record_risk_score(0.15)
    metrics.set_agent_xp("sentinel", 1000)
    metrics.set_agent_tp("sentinel", 50)
    metrics.set_agent_grade("sentinel", "B")
    metrics.inc_pipelines_in_flight()
    metrics.dec_pipelines_in_flight()


# ========== exposition ==========

def test_get_metrics_response_returns_bytes():
    """get_metrics_response returns (bytes, str) tuple."""
    from src.monitoring.metrics import get_metrics_response

    body, content_type = get_metrics_response()
    assert isinstance(body, bytes)
    assert isinstance(content_type, str)
    assert b"citadel_" in body


# ========== counter increments ==========

def test_counter_increments():
    """Pipeline runs counter appears in exposition output."""
    from src.monitoring.metrics import record_pipeline_run, get_metrics_response

    record_pipeline_run("ci_failed", "approve")
    body, _ = get_metrics_response()
    assert b"citadel_pipeline_runs_total" in body
    assert b"ci_failed" in body
    assert b"approve" in body


def test_agent_runs_counter():
    """Agent runs counter tracks per-agent invocations."""
    from src.monitoring.metrics import record_agent_run, get_metrics_response

    record_agent_run("sherlock")
    body, _ = get_metrics_response()
    assert b"citadel_agent_runs_total" in body
    assert b"sherlock" in body


def test_ags_verdict_counter():
    """AGS verdict counter tracks allow/review/deny."""
    from src.monitoring.metrics import record_ags_verdict, get_metrics_response

    record_ags_verdict("DENY")
    body, _ = get_metrics_response()
    assert b"citadel_ags_verdicts_total" in body
    assert b"deny" in body  # lowercased


# ========== gauges ==========

def test_gauge_set_xp():
    """Agent XP gauge reflects set value."""
    from src.monitoring.metrics import set_agent_xp, AGENT_XP

    set_agent_xp("sentinel", 2500)
    val = AGENT_XP.labels(agent_id="sentinel")._value.get()
    assert val == 2500.0


def test_gauge_set_tp():
    """Agent TP gauge reflects set value."""
    from src.monitoring.metrics import set_agent_tp, AGENT_TP

    set_agent_tp("fixer", 75)
    val = AGENT_TP.labels(agent_id="fixer")._value.get()
    assert val == 75.0


def test_grade_numeric_mapping():
    """Grade gauge converts letter grades to numbers correctly."""
    from src.monitoring.metrics import set_agent_grade, AGENT_GRADE

    cases = {"D": 0, "C": 1, "B": 2, "A": 3, "S": 4}
    for letter, expected in cases.items():
        set_agent_grade("test_agent", letter)
        val = AGENT_GRADE.labels(agent_id="test_agent")._value.get()
        assert val == float(expected), f"Expected {letter}={expected}, got {val}"


# ========== histograms ==========

def test_histogram_pipeline_duration():
    """Pipeline duration histogram records observation."""
    from src.monitoring.metrics import record_pipeline_duration, get_metrics_response

    record_pipeline_duration(350.0)
    body, _ = get_metrics_response()
    assert b"citadel_pipeline_duration_ms" in body


def test_histogram_risk_score():
    """Risk score histogram records observation."""
    from src.monitoring.metrics import record_risk_score, get_metrics_response

    record_risk_score(0.42)
    body, _ = get_metrics_response()
    assert b"citadel_risk_scores" in body


# ========== fail-open ==========

def test_metrics_absent_gracefully():
    """When prometheus_client is missing, get_metrics_response returns fallback."""
    from src.monitoring import metrics

    original = metrics._HAS_PROMETHEUS
    try:
        metrics._HAS_PROMETHEUS = False
        body, ct = metrics.get_metrics_response()
        assert b"not installed" in body
        assert "text/plain" in ct
    finally:
        metrics._HAS_PROMETHEUS = original


# ========== in-flight gauge ==========

def test_pipelines_in_flight_gauge():
    """In-flight gauge increments and decrements."""
    from src.monitoring.metrics import (
        inc_pipelines_in_flight,
        dec_pipelines_in_flight,
        PIPELINES_IN_FLIGHT,
    )

    # Reset to known state
    PIPELINES_IN_FLIGHT._value.set(0)
    inc_pipelines_in_flight()
    assert PIPELINES_IN_FLIGHT._value.get() == 1.0
    inc_pipelines_in_flight()
    assert PIPELINES_IN_FLIGHT._value.get() == 2.0
    dec_pipelines_in_flight()
    assert PIPELINES_IN_FLIGHT._value.get() == 1.0
    dec_pipelines_in_flight()
    assert PIPELINES_IN_FLIGHT._value.get() == 0.0


# ========== middleware ==========

def test_middleware_importable():
    """Middleware module imports; MetricsMiddleware is available."""
    from src.monitoring.middleware import MetricsMiddleware

    # MetricsMiddleware is a class (or None if starlette missing)
    assert MetricsMiddleware is None or callable(MetricsMiddleware)
