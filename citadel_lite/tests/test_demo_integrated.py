# tests/test_demo_integrated.py
"""
Integrated demo test for MS-A7.

Simulates the Blueprint demo flow:
  OrchestratorV3 → DiagnosticsLoop → VCCClient → OADClient → DatadogAdapter

All adapters run in dry_run=True mode — no external API calls required.
Writes output artifacts to out/demo-a7-001/ and asserts on their shape.

CGRF v3.0: MS-A7 / Tier 1
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.integrations.vcc.client import VCCClient
from src.integrations.oad.client import OADClient
from src.integrations.perplexity.control_loop_client import PerplexityControlLoopClient
from src.monitoring.datadog_adapter import DatadogAdapter
from src.modules.diagnostics_loop import DiagnosticsLoop
from src.contracts.orders import BuildRequest
from src.contracts.diagnostics import DiagnosticsRequest, RepairRequest


# ── Shared event fixture ───────────────────────────────────────────────────────

ORDER_ID = "demo-a7-001"
REPO = "guilds/citadel_lite_repo"
OUT_DIR = Path("out") / ORDER_ID


# ── TestVCCAdapterDryRun ───────────────────────────────────────────────────────

class TestVCCAdapterDryRun:
    """VCCAdapter.build() — no NATS client → stub mode (no external calls)."""

    def test_build_no_nats_returns_stub(self):
        # Without nats_client, VCCClient returns "stub" regardless of dry_run
        client = VCCClient(dry_run=True)
        req = BuildRequest(order_id=ORDER_ID, repo=REPO, target={"service": "smp-fin-api"})
        result = client.build(req)
        assert result.status in ("stub", "dry_run")
        assert result.order_id == ORDER_ID

    def test_build_dry_run_build_checks_passed(self):
        client = VCCClient(dry_run=True)
        req = BuildRequest(order_id=ORDER_ID, repo=REPO)
        result = client.build(req)
        assert result.build_checks_passed is True

    def test_get_latest_crp_dry_run_returns_none(self):
        client = VCCClient(dry_run=True)
        assert client.get_latest_crp() is None


# ── TestOADAdapterDryRun ───────────────────────────────────────────────────────

class TestOADAdapterDryRun:
    """OADAdapter.repair() dry_run — no external GitLab calls."""

    def test_repair_dry_run_returns_stub_or_dry_run(self):
        client = OADClient(dry_run=True)
        req = RepairRequest(order_id=ORDER_ID, build_result={"reflex_code": "F924"})
        result = client.repair(req)
        assert result.status in ("stub", "dry_run")

    def test_dispatch_mission_dry_run(self):
        client = OADClient(dry_run=True)
        result = client.dispatch_mission(
            order_id=ORDER_ID,
            mission_type="diagnose",
            payload={"event_type": "ci_failed"},
        )
        assert result.status in ("dry_run", "stub")

    def test_pull_latest_signals_dry_run_returns_list(self):
        client = OADClient(dry_run=True)
        signals = client.pull_latest_signals()
        assert isinstance(signals, list)


# ── TestDatadogAdapterNoOp ────────────────────────────────────────────────────

class TestDatadogAdapterNoOp:
    """DatadogAdapter no-op when DD_API_KEY unset."""

    def test_emit_event_no_key_returns_false(self, monkeypatch):
        monkeypatch.delenv("DD_API_KEY", raising=False)
        dd = DatadogAdapter(dry_run=False)
        result = dd.emit_event("Demo: CI Failed", "ci_failed on demo-a7-001")
        assert result is False

    def test_emit_metric_no_key_returns_false(self, monkeypatch):
        monkeypatch.delenv("DD_API_KEY", raising=False)
        dd = DatadogAdapter(dry_run=False)
        result = dd.emit_metric("citadel.demo.health_score", 85.0)
        assert result is False

    def test_dry_run_emit_event_no_api_call(self):
        dd = DatadogAdapter(dry_run=True)
        # dry_run=True never calls external API
        result = dd.emit_event("Test", "body")
        assert result is False  # dry_run returns False (no-op)


# ── TestDiagnosticsLoopDemoRun ────────────────────────────────────────────────

class TestDiagnosticsLoopDemoRun:
    """DiagnosticsLoop full dry_run cycle — Blueprint demo assertions."""

    def test_run_returns_diagnostics_report(self):
        loop = DiagnosticsLoop(dry_run=True)
        report = loop.run(order_id=ORDER_ID)
        assert report.order_id == ORDER_ID

    def test_verdict_is_valid_string(self):
        loop = DiagnosticsLoop(dry_run=True)
        report = loop.run(order_id=ORDER_ID)
        valid_verdicts = {"OK", "DEGRADED", "RECOVERING", "CRITICAL", "UNKNOWN"}
        assert report.verdict in valid_verdicts

    def test_blockers_is_list(self):
        loop = DiagnosticsLoop(dry_run=True)
        report = loop.run(order_id=ORDER_ID)
        assert isinstance(report.blockers, list)

    def test_outputs_contains_required_keys(self):
        loop = DiagnosticsLoop(dry_run=True)
        report = loop.run(order_id=ORDER_ID)
        assert "health_grade" in report.outputs
        assert "go_no_go" in report.outputs
        assert "diag_id" in report.outputs

    def test_go_no_go_is_valid(self):
        loop = DiagnosticsLoop(dry_run=True)
        report = loop.run(order_id=ORDER_ID)
        assert report.outputs["go_no_go"] in ("GO", "WARNING", "NO-GO")

    def test_dry_run_does_not_call_supabase(self):
        from unittest.mock import MagicMock
        supabase_mock = MagicMock()
        loop = DiagnosticsLoop(supabase_store=supabase_mock, dry_run=True)
        loop.run(order_id=ORDER_ID)
        supabase_mock.upsert.assert_not_called()


# ── TestDemoArtifactsWritten ──────────────────────────────────────────────────

class TestDemoArtifactsWritten:
    """Write diagnostics report to out/demo-a7-001/ and assert shape."""

    def test_write_diagnostics_report_artifact(self, tmp_path):
        loop = DiagnosticsLoop(dry_run=True)
        report = loop.run(order_id=ORDER_ID)

        # Write artifact
        out = tmp_path / ORDER_ID
        out.mkdir(parents=True, exist_ok=True)
        report_path = out / "diagnostics_report.json"
        report_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Assert file exists and has correct shape
        assert report_path.exists()
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert data["order_id"] == ORDER_ID
        assert "verdict" in data
        assert "blockers" in data
        assert isinstance(data["blockers"], list)

    def test_write_build_result_artifact(self, tmp_path):
        client = VCCClient(dry_run=True)
        req = BuildRequest(order_id=ORDER_ID, repo=REPO)
        result = client.build(req)

        out = tmp_path / ORDER_ID
        out.mkdir(parents=True, exist_ok=True)
        path = out / "build_result.json"
        path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["order_id"] == ORDER_ID
        assert data["status"] in ("stub", "dry_run")

    def test_write_repair_result_artifact(self, tmp_path):
        client = OADClient(dry_run=True)
        req = RepairRequest(order_id=ORDER_ID, build_result={"reflex_code": "F924"})
        result = client.repair(req)

        out = tmp_path / ORDER_ID
        out.mkdir(parents=True, exist_ok=True)
        path = out / "repair_result.json"
        path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["order_id"] == ORDER_ID


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
