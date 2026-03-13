"""
Nemesis GeoIP Aggregator — groups threat events by country/region.

Uses MaxMind GeoIP2 when ``GEOIP_ACCOUNT_ID`` / ``GEOIP_LICENSE_KEY`` are set.
Falls back to a no-op stub (returns ``UNKNOWN``) when credentials are absent or
the ``geoip2`` package is not installed.

CGRF compliance
---------------
_MODULE_NAME    = "nemesis_geo_aggregator"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "nemesis_geo_aggregator"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

_ACCOUNT_ID = os.getenv("GEOIP_ACCOUNT_ID")
_LICENSE_KEY = os.getenv("GEOIP_LICENSE_KEY")


class GeoAggregator:
    """
    Aggregates IP addresses into country-level threat counts.

    Usage
    -----
    agg = GeoAggregator()
    record = agg.lookup("203.0.113.5")
    # {"ip": "203.0.113.5", "country_code": "US", "country_name": "United States"}
    """

    def __init__(self) -> None:
        self._available = bool(_ACCOUNT_ID and _LICENSE_KEY)
        if not self._available:
            logger.debug("GeoAggregator: no credentials — using no-op stub")

    def lookup(self, ip: str) -> Dict[str, Any]:
        """
        Return GeoIP data for *ip*.

        Returns
        -------
        dict with keys: ip, country_code, country_name.
        Returns UNKNOWN when credentials are unset or lookup fails.
        """
        if not self._available:
            return {"ip": ip, "country_code": "UNKNOWN", "country_name": "UNKNOWN"}

        try:
            import geoip2.webservice  # type: ignore
            with geoip2.webservice.Client(
                int(_ACCOUNT_ID), _LICENSE_KEY, host="geolite.info"
            ) as client:
                record = client.country(ip)
                return {
                    "ip": ip,
                    "country_code": record.country.iso_code or "UNKNOWN",
                    "country_name": record.country.name or "UNKNOWN",
                }
        except Exception as e:
            logger.warning("GeoAggregator.lookup: failed for %s: %s", ip, e)
            return {"ip": ip, "country_code": "UNKNOWN", "country_name": "UNKNOWN"}

    def aggregate(self, ips: List[str]) -> Dict[str, int]:
        """
        Aggregate a list of IPs into country_code → hit_count mapping.

        Returns {} when all lookups return UNKNOWN.
        """
        result: Dict[str, int] = {}
        for ip in ips:
            record = self.lookup(ip)
            cc = record.get("country_code", "UNKNOWN")
            result[cc] = result.get(cc, 0) + 1
        return result
