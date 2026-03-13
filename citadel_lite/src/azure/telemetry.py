# src/azure/telemetry.py
"""
Application Insights telemetry integration for Citadel Lite.

Tracks:
- Pipeline events (start, agent completions, decisions)
- Metrics (latency, risk scores, memory hit counts)
- Dependencies (agent calls as dependency tracking)
- Traces (audit trail entries)

Requires: pip install opencensus-ext-azure
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from src.azure.config import AzureConfig

try:
    from opencensus.ext.azure import metrics_exporter
    from opencensus.ext.azure.log_exporter import AzureLogHandler
    from opencensus.ext.azure.trace_exporter import AzureExporter
    from opencensus.trace import tracer as tracer_module
    from opencensus.trace.samplers import AlwaysOnSampler
    import logging
    _HAS_APPINSIGHTS = True
except ImportError:
    _HAS_APPINSIGHTS = False


class TelemetryClient:
    """
    Application Insights telemetry wrapper.
    No-ops gracefully if SDK is not installed or not configured.
    """

    def __init__(self, config: AzureConfig) -> None:
        self._enabled = False
        self._connection = config.app_insights_connection

        if _HAS_APPINSIGHTS and self._connection:
            self._setup(self._connection)
            self._enabled = True

    def _setup(self, connection_string: str) -> None:
        """Initialize Application Insights exporters."""
        self._logger = logging.getLogger("citadel-lite")
        self._logger.setLevel(logging.INFO)

        handler = AzureLogHandler(connection_string=connection_string)
        self._logger.addHandler(handler)

        self._exporter = AzureExporter(connection_string=connection_string)
        self._tracer = tracer_module.Tracer(
            exporter=self._exporter,
            sampler=AlwaysOnSampler(),
        )

    def track_event(self, name: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """Track a custom event."""
        if not self._enabled:
            return
        props = {k: str(v) for k, v in (properties or {}).items()}
        self._logger.info(name, extra={"custom_dimensions": props})

    def track_metric(self, name: str, value: float, properties: Optional[Dict[str, Any]] = None) -> None:
        """Track a numeric metric."""
        if not self._enabled:
            return
        props = {k: str(v) for k, v in (properties or {}).items()}
        props["metric_value"] = str(value)
        self._logger.info(f"metric:{name}", extra={"custom_dimensions": props})

    def track_dependency(
        self,
        name: str,
        target: str,
        duration_ms: float,
        success: bool,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Track an external dependency call (agent invocation, API call)."""
        if not self._enabled:
            return
        props = {k: str(v) for k, v in (properties or {}).items()}
        props.update({
            "dependency_name": name,
            "target": target,
            "duration_ms": str(round(duration_ms, 2)),
            "success": str(success),
        })
        self._logger.info(f"dependency:{name}", extra={"custom_dimensions": props})

    def track_trace(self, message: str, severity: str = "info") -> None:
        """Track a trace message."""
        if not self._enabled:
            return
        log_fn = getattr(self._logger, severity, self._logger.info)
        log_fn(message)

    def flush(self) -> None:
        """Flush pending telemetry."""
        if self._enabled and hasattr(self, "_logger"):
            for handler in self._logger.handlers:
                if hasattr(handler, "flush"):
                    handler.flush()


class DependencyTimer:
    """Context manager for timing dependency calls."""

    def __init__(self, telemetry: TelemetryClient, name: str, target: str) -> None:
        self.telemetry = telemetry
        self.name = name
        self.target = target
        self._start = 0.0

    def __enter__(self) -> "DependencyTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration = (time.perf_counter() - self._start) * 1000
        self.telemetry.track_dependency(
            name=self.name,
            target=self.target,
            duration_ms=duration,
            success=exc_type is None,
        )
