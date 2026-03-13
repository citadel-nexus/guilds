# tests/test_vcc_client.py
"""
Tests for VCCClient adapter.

CGRF v3.0: MS-A2 / Tier 1
"""
from __future__ import annotations

import pytest

from src.contracts.orders import BuildRequest, BuildResult
from src.integrations.vcc.client import VCCClient


class TestVCCClientStub:
    def test_stub_mode_returns_stub_result(self):
        client = VCCClient(nats_client=None, dry_run=False)
        req = BuildRequest(order_id="ORD-001", repo="citadel_lite")
        result = client.build(req)
        assert result.status == "stub"
        assert result.order_id == "ORD-001"

    def test_dry_run_returns_dry_run_result(self):
        class FakeNATS:
            pass
        client = VCCClient(nats_client=FakeNATS(), dry_run=True)
        req = BuildRequest(order_id="ORD-002")
        result = client.build(req)
        assert result.status == "dry_run"

    def test_get_latest_crp_stub_returns_none(self):
        client = VCCClient(nats_client=None, dry_run=False)
        assert client.get_latest_crp() is None

    def test_get_latest_crp_dry_run_returns_none(self):
        class FakeNATS:
            pass
        client = VCCClient(nats_client=FakeNATS(), dry_run=True)
        assert client.get_latest_crp() is None


class TestBuildRequest:
    def test_to_dict_roundtrip(self):
        req = BuildRequest(order_id="ORD-X", repo="repo_a",
                           target={"branch": "main"},
                           constraints={"timebox_minutes": 30})
        d = req.to_dict()
        restored = BuildRequest.from_dict(d)
        assert restored.order_id == "ORD-X"
        assert restored.target["branch"] == "main"

    def test_default_schema(self):
        req = BuildRequest()
        assert req.schema == "vcc.build_request.v1"


class TestBuildResult:
    def test_default_build_checks_passed(self):
        result = BuildResult()
        assert result.build_checks_passed is True

    def test_to_dict_includes_all_fields(self):
        result = BuildResult(order_id="ORD-1", status="ok",
                             crp_cycle_id="VCC-FIN-20260305-1200")
        d = result.to_dict()
        assert d["crp_cycle_id"] == "VCC-FIN-20260305-1200"
        assert "build_checks_passed" in d

    def test_from_dict_roundtrip(self):
        original = BuildResult(order_id="O", status="partial", notes="note")
        restored = BuildResult.from_dict(original.to_dict())
        assert restored.status == "partial"
        assert restored.notes == "note"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
