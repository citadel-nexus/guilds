# tests/test_datadog_adapter.py
"""
Tests for DatadogAdapter.

CGRF v3.0: MS-A5 / Tier 1
"""
from __future__ import annotations

import pytest

from src.monitoring.datadog_adapter import DatadogAdapter


class TestDatadogAdapterDryRun:
    def test_emit_event_dry_run_returns_false(self):
        adapter = DatadogAdapter(dry_run=True)
        result = adapter.emit_event("Test", "body")
        assert result is False

    def test_emit_metric_dry_run_returns_false(self):
        adapter = DatadogAdapter(dry_run=True)
        result = adapter.emit_metric("citadel.test.metric", 42.0)
        assert result is False

    def test_read_monitors_dry_run_returns_empty(self):
        adapter = DatadogAdapter(dry_run=True)
        result = adapter.read_monitors()
        assert result == []


class TestDatadogAdapterNoKey:
    def test_emit_event_no_key_returns_false(self, monkeypatch):
        monkeypatch.delenv("DD_API_KEY", raising=False)
        adapter = DatadogAdapter(dry_run=False)
        assert adapter.emit_event("T", "b") is False

    def test_emit_metric_no_key_returns_false(self, monkeypatch):
        monkeypatch.delenv("DD_API_KEY", raising=False)
        adapter = DatadogAdapter(dry_run=False)
        assert adapter.emit_metric("m", 1.0) is False

    def test_read_monitors_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("DD_API_KEY", raising=False)
        monkeypatch.delenv("DD_APP_KEY", raising=False)
        adapter = DatadogAdapter(dry_run=False)
        assert adapter.read_monitors() == []


class TestDatadogTagEnrichment:
    def test_enrich_tags_adds_source(self):
        adapter = DatadogAdapter(dry_run=True)
        tags = adapter._enrich_tags(["custom:tag"])
        assert "source:citadel_lite" in tags
        assert "custom:tag" in tags

    def test_enrich_tags_adds_env(self, monkeypatch):
        monkeypatch.setenv("DD_ENV", "production")
        adapter = DatadogAdapter(dry_run=True)
        tags = adapter._enrich_tags([])
        assert "env:production" in tags

    def test_enrich_tags_none_input(self):
        adapter = DatadogAdapter(dry_run=True)
        tags = adapter._enrich_tags(None)
        assert "source:citadel_lite" in tags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
