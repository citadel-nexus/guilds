"""
DatadogAdapter — emit events and metrics to Datadog.

All methods return False / empty list gracefully when DD_API_KEY is unset.
Use ``dry_run=True`` (default) during testing to prevent live Datadog calls.

Prometheus (src/monitoring/metrics.py) handles internal metrics.
Datadog handles external observability: loop execution results, blocker alerts.

CGRF compliance
---------------
_MODULE_NAME    = "datadog_adapter"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "datadog_adapter"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

_DD_EVENTS_URL = "https://api.{site}/api/v1/events"
_DD_METRICS_URL = "https://api.{site}/api/v1/series"
_DD_MONITORS_URL = "https://api.{site}/api/v1/monitor"


class DatadogAdapter:
    """
    Thin adapter for Datadog Events API and Metrics API.

    Parameters
    ----------
    dry_run : bool
        When True no HTTP calls are made (returns False/empty on all calls).
    """

    def __init__(self, dry_run: bool = True):
        self._dry_run = dry_run
        self._api_key: Optional[str] = os.getenv("DD_API_KEY")
        self._app_key: Optional[str] = os.getenv("DD_APP_KEY")
        self._site: str = os.getenv("DD_SITE", "datadoghq.com")
        self._env: str = os.getenv("DD_ENV", "")

    # ── Public API ───────────────────────────────────────────────────────────

    def emit_event(
        self,
        title: str,
        text: str,
        tags: Optional[List[str]] = None,
        alert_type: str = "info",
    ) -> bool:
        """
        Post an event to Datadog Events API.

        Parameters
        ----------
        title : str
        text : str
        tags : list of str, optional
        alert_type : "info" | "warning" | "error" | "success"

        Returns True on success, False otherwise.
        """
        if self._dry_run or not self._api_key:
            logger.debug(
                "DatadogAdapter.emit_event (%s): title=%s",
                "dry_run" if self._dry_run else "no DD_API_KEY",
                title,
            )
            return False

        payload = {
            "title": title,
            "text": text,
            "tags": self._enrich_tags(tags),
            "alert_type": alert_type,
        }
        url = _DD_EVENTS_URL.format(site=self._site)
        try:
            resp = _requests.post(
                url,
                headers={"DD-API-KEY": self._api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=5,
            )
            resp.raise_for_status()
            logger.info("DatadogAdapter: event posted — %s", title)
            return True
        except Exception as exc:
            logger.warning("DatadogAdapter.emit_event failed: %s", exc)
            return False

    def emit_metric(
        self,
        metric: str,
        value: float,
        tags: Optional[List[str]] = None,
        metric_type: str = "gauge",
    ) -> bool:
        """
        Post a single-point metric to Datadog Metrics API.

        Parameters
        ----------
        metric : str  — metric name (e.g. "citadel.loop.risk")
        value : float
        tags : list of str, optional
        metric_type : "gauge" | "count" | "rate"
        """
        if self._dry_run or not self._api_key:
            logger.debug("DatadogAdapter.emit_metric (%s): %s = %s",
                         "dry_run" if self._dry_run else "no DD_API_KEY",
                         metric, value)
            return False

        import time
        payload = {
            "series": [{
                "metric": metric,
                "points": [[int(time.time()), value]],
                "type": metric_type,
                "tags": self._enrich_tags(tags),
            }]
        }
        url = _DD_METRICS_URL.format(site=self._site)
        try:
            resp = _requests.post(
                url,
                headers={"DD-API-KEY": self._api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=5,
            )
            resp.raise_for_status()
            logger.debug("DatadogAdapter: metric posted — %s = %s", metric, value)
            return True
        except Exception as exc:
            logger.warning("DatadogAdapter.emit_metric failed: %s", exc)
            return False

    def read_monitors(self, tag: str = "citadel") -> List[Dict[str, Any]]:
        """
        Query Datadog monitors filtered by *tag*.

        Returns an empty list when DD_API_KEY or DD_APP_KEY are unset.
        """
        if self._dry_run or not self._api_key or not self._app_key:
            logger.debug("DatadogAdapter.read_monitors: stub — no DD_API_KEY/APP_KEY")
            return []

        url = _DD_MONITORS_URL.format(site=self._site)
        try:
            resp = _requests.get(
                url,
                headers={
                    "DD-API-KEY": self._api_key,
                    "DD-APPLICATION-KEY": self._app_key,
                },
                params={"tags": tag},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json() if isinstance(resp.json(), list) else []
        except Exception as exc:
            logger.warning("DatadogAdapter.read_monitors failed: %s", exc)
            return []

    # ── Private helpers ───────────────────────────────────────────────────────

    def _enrich_tags(self, tags: Optional[List[str]]) -> List[str]:
        base = list(tags or [])
        base.append("source:citadel_lite")
        if self._env:
            base.append(f"env:{self._env}")
        return base
