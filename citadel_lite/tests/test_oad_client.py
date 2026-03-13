# tests/test_oad_client.py
"""
Tests for OADClient and OADSignalRouter.

CGRF v3.0: MS-A2/A4 / Tier 1
"""
from __future__ import annotations

import pytest

from src.contracts.diagnostics import RepairRequest, RepairResult, Signal
from src.integrations.oad.client import OADClient
from src.integrations.oad.signal_router import OADSignalRouter


class TestOADClientStub:
    def test_stub_returns_stub_result(self):
        client = OADClient(nats_client=None, dry_run=False)
        req = RepairRequest(order_id="ORD-001")
        result = client.repair(req)
        assert result.status == "stub"

    def test_dry_run_returns_dry_run_result(self):
        class FakeNATS:
            pass
        client = OADClient(nats_client=FakeNATS(), dry_run=True)
        req = RepairRequest(order_id="ORD-002")
        result = client.repair(req)
        assert result.status == "dry_run"

    def test_dispatch_mission_stub(self):
        client = OADClient(nats_client=None, dry_run=False)
        result = client.dispatch_mission("ORD-003", mission_type="reflex")
        assert result.status == "stub"

    def test_pull_signals_returns_list(self):
        client = OADClient(nats_client=None, dry_run=True)
        signals = client.pull_latest_signals()
        assert isinstance(signals, list)


class TestOADSignalRouter:
    def test_stub_returns_empty_list(self):
        router = OADSignalRouter(dry_run=True)
        signals = router.pull_latest_signals()
        assert signals == []

    def test_make_signal_has_required_fields(self):
        sig = OADSignalRouter._make_signal(
            source="gitlab",
            event_type="pipeline_failed",
            priority="high",
            should_trigger_reflex=True,
        )
        assert sig.source == "gitlab"
        assert sig.should_trigger_reflex is True
        assert sig.signal_id.startswith("sig-")


class TestRepairContracts:
    def test_repair_request_to_dict(self):
        req = RepairRequest(order_id="O", test_failures=[{"name": "test_x"}])
        d = req.to_dict()
        assert d["schema"] == "oad.repair_request.v1"
        assert len(d["test_failures"]) == 1

    def test_repair_result_default_status(self):
        result = RepairResult()
        assert result.status == "ok"

    def test_signal_to_dict(self):
        sig = Signal(signal_id="s-001", source="datadog",
                     event_type="error_spike", priority="critical")
        d = sig.to_dict()
        assert d["priority"] == "critical"
        assert d["should_trigger_reflex"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
