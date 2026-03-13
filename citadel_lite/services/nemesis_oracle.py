"""
Nemesis L4 Oracle — ML-based threat classifier.

Classifies HTTP requests into threat categories and computes a composite
threat score.  In the current implementation the classifier is a rule-weight
ensemble (no external ML runtime required).  The interface is designed for
future replacement with a real scikit-learn or ONNX model.

Integrates with DatadogAdapter for metrics emission:
  - ``nemesis.l4.oracle.risk_score`` (Histogram)
  - ``nemesis.l4.oracle.latency_ms`` (Histogram)

CGRF compliance
---------------
_MODULE_NAME    = "nemesis_oracle"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "BACKEND_SERVICE"
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from middleware.nemesis_inspector import score_payload

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "nemesis_oracle"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "BACKEND_SERVICE"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


@dataclass
class OracleVerdict:
    """Classification result from NemesisOracle."""
    risk_score: float               # 0.0–1.0
    threat_categories: List[str]    # detected categories
    quarantine: bool                # True when risk_score >= quarantine_threshold
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "threat_categories": self.threat_categories,
            "quarantine": self.quarantine,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }


class NemesisOracle:
    """
    L4 threat classification oracle.

    Parameters
    ----------
    quarantine_threshold : float
        Score at or above which ``OracleVerdict.quarantine`` is set True.
        Default 0.8 (higher than L2 block threshold).
    datadog_adapter : optional DatadogAdapter
        If provided, emits Prometheus-style metrics via Datadog.
    dry_run : bool
        When True no Datadog API calls are made.
    """

    def __init__(
        self,
        quarantine_threshold: float = 0.8,
        datadog_adapter: Optional[Any] = None,
        dry_run: bool = True,
    ) -> None:
        self._threshold = quarantine_threshold
        self._dd = datadog_adapter
        self._dry_run = dry_run

    def classify(self, payload: str, context: Optional[Dict[str, Any]] = None) -> OracleVerdict:
        """
        Classify *payload* and return an OracleVerdict.

        Parameters
        ----------
        payload : str
            Raw request content (path + query string + body snippet).
        context : dict, optional
            Extra context: source_ip, method, country_code, etc.
        """
        t0 = time.perf_counter()

        assessment = score_payload(payload)
        risk_score = assessment["threat_score"]
        categories = assessment["threats_found"]

        # Boost score when IP context is supplied and IP is in known bad ranges
        if context:
            source_ip = context.get("source_ip", "")
            risk_score = min(1.0, risk_score + self._ip_reputation_boost(source_ip))

        quarantine = risk_score >= self._threshold

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        verdict = OracleVerdict(
            risk_score=round(risk_score, 4),
            threat_categories=categories,
            quarantine=quarantine,
            latency_ms=latency_ms,
            metadata=context or {},
        )

        self._emit_metrics(verdict)
        logger.debug(
            "NemesisOracle.classify: score=%.4f quarantine=%s categories=%s latency=%.1fms",
            verdict.risk_score, verdict.quarantine, verdict.threat_categories, verdict.latency_ms,
        )
        return verdict

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _ip_reputation_boost(ip: str) -> float:
        """
        Simple rule-based IP reputation boost.
        Returns 0.0–0.3 based on IP characteristics.
        Placeholder for real AbuseIPDB integration.
        """
        if not ip:
            return 0.0
        # Tor exit-node pattern (simplified heuristic)
        if ip.startswith("185.220."):
            return 0.3
        return 0.0

    def _emit_metrics(self, verdict: OracleVerdict) -> None:
        """Emit Datadog metrics if adapter is available."""
        if self._dd is None:
            return
        try:
            self._dd.emit_metric(
                "nemesis.l4.oracle.risk_score",
                verdict.risk_score,
                tags=[f"quarantine:{verdict.quarantine}"],
            )
            self._dd.emit_metric(
                "nemesis.l4.oracle.latency_ms",
                verdict.latency_ms,
            )
        except Exception as e:
            logger.debug("NemesisOracle: datadog emit failed: %s", e)
