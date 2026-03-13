# tests/test_nemesis_honeypots.py
"""
Tests for Nemesis L3 Honeypot routes (MS-B2).

CGRF v3.0: MS-B2 / Tier 1
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from routes.nemesis_honeypots import (
    _build_hit_record,
    _handle_honeypot_hit,
    _HONEYPOT_PATHS,
    _record_hit_supabase,
)


# ── TestHoneypotPaths ─────────────────────────────────────────────────────────

class TestHoneypotPaths:
    def test_at_least_five_honeypot_paths_defined(self):
        assert len(_HONEYPOT_PATHS) >= 5

    def test_admin_path_included(self):
        assert "/admin" in _HONEYPOT_PATHS

    def test_env_path_included(self):
        assert "/.env" in _HONEYPOT_PATHS

    def test_wp_login_included(self):
        assert "/wp-login.php" in _HONEYPOT_PATHS


# ── TestBuildHitRecord ────────────────────────────────────────────────────────

class TestBuildHitRecord:
    def test_record_has_required_fields(self):
        record = _build_hit_record("/admin", "1.2.3.4", "GET")
        assert record["path"] == "/admin"
        assert record["client_ip"] == "1.2.3.4"
        assert record["method"] == "GET"
        assert "hit_id" in record
        assert "timestamp" in record
        assert record["threat_label"] == "L3_HONEYPOT"

    def test_hit_id_is_unique(self):
        r1 = _build_hit_record("/.env", "1.1.1.1", "GET")
        r2 = _build_hit_record("/.env", "1.1.1.1", "GET")
        assert r1["hit_id"] != r2["hit_id"]


# ── TestHandleHoneypotHit ─────────────────────────────────────────────────────

class TestHandleHoneypotHit:
    def test_handle_hit_no_credentials_does_not_raise(self, monkeypatch):
        monkeypatch.setattr("routes.nemesis_honeypots._SUPABASE_URL", None)
        monkeypatch.setattr("routes.nemesis_honeypots._SUPABASE_KEY", None)
        # Should complete without exception even when no Supabase creds
        _handle_honeypot_hit("/.env", "5.5.5.5", "GET")

    def test_record_hit_supabase_no_creds_noop(self, monkeypatch):
        monkeypatch.setattr("routes.nemesis_honeypots._SUPABASE_URL", None)
        monkeypatch.setattr("routes.nemesis_honeypots._SUPABASE_KEY", None)
        record = _build_hit_record("/admin", "1.2.3.4", "GET")
        # Should not raise
        _record_hit_supabase(record)

    def test_handle_hit_nats_noop_when_not_available(self, monkeypatch):
        monkeypatch.setattr("routes.nemesis_honeypots._SUPABASE_URL", None)
        # NATSBridgeClient is lazily imported — in stub mode (NATS_URL unset) no-op
        _handle_honeypot_hit("/admin", "9.9.9.9", "POST")


# ── TestHoneypotRouterCreated ─────────────────────────────────────────────────

class TestHoneypotRouterCreated:
    def test_router_is_none_or_has_routes(self):
        from routes.nemesis_honeypots import honeypot_router
        # Either FastAPI not installed (None) or router has routes
        if honeypot_router is not None:
            assert hasattr(honeypot_router, "routes")
            assert len(honeypot_router.routes) > 0

    def test_router_covers_all_honeypot_paths(self):
        from routes.nemesis_honeypots import honeypot_router
        if honeypot_router is None:
            pytest.skip("FastAPI not installed")
        route_paths = {r.path for r in honeypot_router.routes}
        for hp in _HONEYPOT_PATHS:
            assert hp in route_paths, f"Missing honeypot path: {hp}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
