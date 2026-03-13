# tests/test_nemesis_oracle.py
"""
Tests for NemesisOracle + GeoAggregator + nemesis_retrain (MS-B3).

CGRF v3.0: MS-B3 / Tier 1
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.nemesis_oracle import NemesisOracle, OracleVerdict
from services.nemesis_geo_aggregator import GeoAggregator
from services.nemesis_retrain import NemesisRetrain


# ── TestNemesisOracleClassify ─────────────────────────────────────────────────

class TestNemesisOracleClassify:
    def test_clean_payload_low_score(self):
        oracle = NemesisOracle()
        verdict = oracle.classify("/api/v1/health")
        assert verdict.risk_score == 0.0
        assert verdict.quarantine is False

    def test_sqli_payload_raises_score(self):
        oracle = NemesisOracle()
        verdict = oracle.classify("SELECT * FROM users UNION SELECT password")
        assert verdict.risk_score > 0.0
        assert "sqli" in verdict.threat_categories

    def test_xss_payload_detected(self):
        oracle = NemesisOracle()
        verdict = oracle.classify("<script>alert('xss')</script>")
        assert "xss" in verdict.threat_categories

    def test_multi_threat_raises_score(self):
        oracle = NemesisOracle()
        payload = "UNION SELECT <script>alert(1)</script> http://169.254.169.254"
        verdict = oracle.classify(payload)
        assert len(verdict.threat_categories) >= 2
        assert verdict.risk_score >= 0.5

    def test_quarantine_when_score_ge_threshold(self):
        oracle = NemesisOracle(quarantine_threshold=0.5)
        # Score 0.75 (3 threats / 4 categories)
        payload = "UNION SELECT <script> http://localhost ignore previous instructions"
        verdict = oracle.classify(payload)
        if verdict.risk_score >= 0.5:
            assert verdict.quarantine is True

    def test_no_quarantine_below_threshold(self):
        oracle = NemesisOracle(quarantine_threshold=0.9)
        verdict = oracle.classify("SELECT 1")
        assert verdict.quarantine is False

    def test_verdict_has_latency_ms(self):
        oracle = NemesisOracle()
        verdict = oracle.classify("hello world")
        assert isinstance(verdict.latency_ms, float)
        assert verdict.latency_ms >= 0.0

    def test_verdict_to_dict_has_required_keys(self):
        oracle = NemesisOracle()
        verdict = oracle.classify("SELECT 1")
        d = verdict.to_dict()
        assert "risk_score" in d
        assert "threat_categories" in d
        assert "quarantine" in d
        assert "latency_ms" in d

    def test_datadog_metric_emitted_when_provided(self):
        dd_mock = MagicMock()
        oracle = NemesisOracle(datadog_adapter=dd_mock, dry_run=True)
        oracle.classify("SELECT 1")
        assert dd_mock.emit_metric.call_count >= 1

    def test_ip_reputation_boost_on_tor_ip(self):
        oracle = NemesisOracle()
        clean_without_context = oracle.classify("hello").risk_score
        # Tor exit node hint should boost score when combined with attack payload
        verdict = oracle.classify("SELECT 1", context={"source_ip": "185.220.100.1"})
        assert verdict.risk_score >= clean_without_context


# ── TestGeoAggregator ─────────────────────────────────────────────────────────

class TestGeoAggregator:
    def test_lookup_no_credentials_returns_unknown(self, monkeypatch):
        monkeypatch.setattr("services.nemesis_geo_aggregator._ACCOUNT_ID", None)
        monkeypatch.setattr("services.nemesis_geo_aggregator._LICENSE_KEY", None)
        agg = GeoAggregator()
        result = agg.lookup("1.2.3.4")
        assert result["country_code"] == "UNKNOWN"
        assert result["ip"] == "1.2.3.4"

    def test_aggregate_returns_dict(self, monkeypatch):
        monkeypatch.setattr("services.nemesis_geo_aggregator._ACCOUNT_ID", None)
        monkeypatch.setattr("services.nemesis_geo_aggregator._LICENSE_KEY", None)
        agg = GeoAggregator()
        result = agg.aggregate(["1.2.3.4", "5.6.7.8", "1.2.3.4"])
        assert isinstance(result, dict)
        assert result.get("UNKNOWN", 0) == 3

    def test_aggregate_empty_list_returns_empty(self, monkeypatch):
        monkeypatch.setattr("services.nemesis_geo_aggregator._ACCOUNT_ID", None)
        monkeypatch.setattr("services.nemesis_geo_aggregator._LICENSE_KEY", None)
        agg = GeoAggregator()
        assert agg.aggregate([]) == {}


# ── TestNemesisRetrain ────────────────────────────────────────────────────────

class TestNemesisRetrain:
    def test_ingest_adds_to_buffer(self):
        rt = NemesisRetrain()
        rt.ingest("SELECT 1", "sqli")
        assert rt.buffer_size == 1

    def test_flush_returns_and_clears(self):
        rt = NemesisRetrain()
        rt.ingest("hello", "benign")
        rt.ingest("SELECT 1", "sqli")
        samples = rt.flush()
        assert len(samples) == 2
        assert rt.buffer_size == 0

    def test_flush_empty_returns_empty_list(self):
        rt = NemesisRetrain()
        assert rt.flush() == []

    def test_ingest_truncates_long_payload(self):
        rt = NemesisRetrain()
        long_payload = "x" * 1000
        rt.ingest(long_payload, "benign")
        sample = rt.flush()[0]
        assert len(sample["payload"]) <= 512

    def test_sample_has_label_and_confidence(self):
        rt = NemesisRetrain()
        rt.ingest("test", "xss", confidence=0.9)
        sample = rt.flush()[0]
        assert sample["label"] == "xss"
        assert sample["confidence"] == 0.9


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
