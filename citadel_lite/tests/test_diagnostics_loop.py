# tests/test_diagnostics_loop.py
"""
Tests for DiagnosticsLoop.

CGRF v3.0: MS-A3 / Tier 1
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.contracts.diagnostics import DiagnosticsReport, Signal
from src.modules.diagnostics_loop import DiagnosticsLoop


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_loop(**kwargs) -> DiagnosticsLoop:
    return DiagnosticsLoop(dry_run=True, **kwargs)


def _pplx_stub(verdict="OK", risk=10, blockers=None):
    """Return a minimal Perplexity mock whose run() returns a DiagnosticsReport."""
    report = DiagnosticsReport(
        order_id="test-order",
        verdict=verdict,
        risk=risk,
        blockers=blockers or [],
        outputs={"mode": "dry_run"},
    )
    mock = MagicMock()
    mock.run.return_value = report
    return mock


# ── TestDiagnosticsLoopRun ─────────────────────────────────────────────────────

class TestDiagnosticsLoopRun:
    def test_run_returns_diagnostics_report(self):
        loop = _make_loop()
        report = loop.run(order_id="ord-001")
        assert isinstance(report, DiagnosticsReport)

    def test_run_returns_correct_order_id(self):
        loop = _make_loop()
        report = loop.run(order_id="ord-999")
        assert report.order_id == "ord-999"

    def test_run_with_healthy_perplexity(self):
        loop = _make_loop(perplexity_client=_pplx_stub(verdict="OK", risk=5))
        report = loop.run(order_id="ord-002")
        assert report.verdict == "OK"
        # health_score = 100 - 5 = 95; report.risk = 100 - health_score = 5
        assert report.risk == 5

    def test_run_with_critical_perplexity(self):
        loop = _make_loop(perplexity_client=_pplx_stub(verdict="CRITICAL", risk=80))
        report = loop.run(order_id="ord-003")
        assert report.verdict == "CRITICAL"

    def test_run_outputs_contains_health_grade(self):
        loop = _make_loop()
        report = loop.run(order_id="ord-004")
        assert "health_grade" in report.outputs
        assert "go_no_go" in report.outputs

    def test_run_outputs_contains_diag_id(self):
        loop = _make_loop()
        report = loop.run(order_id="ord-005")
        assert report.outputs.get("diag_id", "").startswith("DIAG-")


# ── TestDiagnosticsLoopHealthGate ─────────────────────────────────────────────

class TestDiagnosticsLoopHealthGate:
    def test_no_go_when_critical_and_score_lt_60(self):
        loop = _make_loop(perplexity_client=_pplx_stub(verdict="CRITICAL", risk=70))
        report = loop.run(order_id="gate-001")
        assert report.outputs["go_no_go"] == "NO-GO"

    def test_go_when_degrading_but_score_gte_60(self):
        loop = _make_loop(perplexity_client=_pplx_stub(verdict="DEGRADED", risk=35))
        report = loop.run(order_id="gate-002")
        # DEGRADED from perplexity maps to DEGRADING → health_score=65 → no NO-GO
        assert report.outputs["go_no_go"] != "NO-GO"

    def test_no_go_writes_to_supabase_when_provided(self):
        supabase_mock = MagicMock()
        loop = DiagnosticsLoop(
            perplexity_client=_pplx_stub(verdict="CRITICAL", risk=80),
            supabase_store=supabase_mock,
            dry_run=False,
        )
        loop.run(order_id="gate-003")
        supabase_mock.upsert.assert_called_once()
        call_args = supabase_mock.upsert.call_args
        assert call_args[0][0] == "vcc_loop_state"
        assert call_args[0][1]["go_no_go"] == "NO-GO"

    def test_no_go_dry_run_does_not_call_supabase(self):
        supabase_mock = MagicMock()
        loop = DiagnosticsLoop(
            perplexity_client=_pplx_stub(verdict="CRITICAL", risk=80),
            supabase_store=supabase_mock,
            dry_run=True,  # dry_run → no write
        )
        loop.run(order_id="gate-004")
        supabase_mock.upsert.assert_not_called()


# ── TestDiagnosticsLoopSignals ─────────────────────────────────────────────────

class TestDiagnosticsLoopSignals:
    def test_critical_signal_added_to_blockers(self):
        signal = Signal(
            signal_id="s1", source="gitlab", event_type="ci_fail",
            signal_class="CODE", priority="critical",
        )
        router_mock = MagicMock()
        router_mock.pull_latest_signals.return_value = [signal]
        loop = _make_loop(oad_signal_router=router_mock)
        report = loop.run(order_id="sig-001")
        # Blockers should contain the critical signal
        assert any("gitlab" in b for b in report.blockers)

    def test_non_critical_signal_not_in_blockers(self):
        signal = Signal(
            signal_id="s2", source="gitlab", event_type="lint_warn",
            signal_class="CODE", priority="low",
        )
        router_mock = MagicMock()
        router_mock.pull_latest_signals.return_value = [signal]
        loop = _make_loop(oad_signal_router=router_mock)
        report = loop.run(order_id="sig-002")
        assert not any("gitlab" in b for b in report.blockers)


# ── TestDiagnosticsLoopAssess ─────────────────────────────────────────────────

class TestDiagnosticsLoopAssess:
    def test_datadog_metric_emitted_when_provided(self):
        dd_mock = MagicMock()
        loop = DiagnosticsLoop(datadog_adapter=dd_mock, dry_run=True)
        loop.run(order_id="assess-001")
        dd_mock.emit_metric.assert_called_once()
        call_args = dd_mock.emit_metric.call_args
        assert call_args[0][0] == "citadel.diagnostics.health_score"

    def test_datadog_nogo_event_emitted_on_critical(self):
        dd_mock = MagicMock()
        loop = DiagnosticsLoop(
            perplexity_client=_pplx_stub(verdict="CRITICAL", risk=80),
            datadog_adapter=dd_mock,
            dry_run=True,
        )
        loop.run(order_id="assess-002")
        dd_mock.emit_event.assert_called_once()


# ── TestMapVerdict ─────────────────────────────────────────────────────────────

class TestMapVerdict:
    def test_healthy_maps_to_ok(self):
        assert DiagnosticsLoop._map_verdict("HEALTHY") == "OK"

    def test_degrading_maps_to_degraded(self):
        assert DiagnosticsLoop._map_verdict("DEGRADING") == "DEGRADED"

    def test_critical_maps_to_critical(self):
        assert DiagnosticsLoop._map_verdict("CRITICAL") == "CRITICAL"

    def test_unknown_maps_to_unknown(self):
        assert DiagnosticsLoop._map_verdict("UNKNOWN") == "UNKNOWN"

    def test_recovering_maps_to_recovering(self):
        assert DiagnosticsLoop._map_verdict("RECOVERING") == "RECOVERING"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
