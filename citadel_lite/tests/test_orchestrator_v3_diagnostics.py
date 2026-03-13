# tests/test_orchestrator_v3_diagnostics.py
"""
Tests for OrchestratorV3 DiagnosticsLoop wire-in (MS-A6).

CGRF v3.0: MS-A6 / Tier 1
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from src.modules.diagnostics_loop import DiagnosticsLoop
from src.contracts.diagnostics import DiagnosticsReport


# ── Bootstrap: patch missing transitive deps before importing orchestrator ────

@pytest.fixture(autouse=True, scope="module")
def _stub_missing_deps():
    """Inject stubs for packages genuinely absent from the test environment.

    Why only ``langdetect``:
      - ``langdetect`` is not in requirements.txt.  ``runner_recursive_soul``
        imports it at module level; the stub prevents ImportError on collection.
        (runner_recursive_soul now has a try/except fallback, so this stub is
        purely defensive insurance.)
      - ``yaml`` is intentionally NOT stubbed.  PyYAML is in requirements.txt
        and ``orchestrator_v3`` already handles ``ImportError`` gracefully
        (``yaml = None`` → ``_load_settings`` returns ``{}``).  Stubbing yaml
        would cause ``orchestrator_v3`` to cache a ``MagicMock`` yaml for the
        rest of the process, contaminating ``test_pipeline_e2e.py`` (TypeError
        at orchestrator_v3.py line 735 when comparing risk_score >= MagicMock).

    Cleanup:
      After all tests in this module finish, any ``src.*`` modules that were
      freshly imported *during this session* (while stubs were active) are
      evicted from ``sys.modules``.  This guarantees subsequent test files
      (e.g. ``test_pipeline_e2e.py``) perform a clean, stub-free import.
    """
    stubs = {k: MagicMock() for k in ("langdetect",) if k not in sys.modules}
    _pre_cached_src = frozenset(k for k in sys.modules if k.startswith("src."))

    with patch.dict(sys.modules, stubs):
        yield

    # Evict freshly-imported src modules that may have captured the langdetect
    # stub, so subsequent test files always start from a clean state.
    for key in list(sys.modules):
        if key.startswith("src.") and key not in _pre_cached_src:
            sys.modules.pop(key, None)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_diag_loop_mock(verdict="OK", risk=10):
    report = DiagnosticsReport(
        order_id="test-event",
        verdict=verdict,
        risk=risk,
        blockers=[],
        outputs={"health_grade": "HEALTHY", "go_no_go": "GO"},
    )
    mock = MagicMock(spec=DiagnosticsLoop)
    mock.run.return_value = report
    return mock


def _make_orchestrator(diagnostics_loop=None, settings=None):
    with patch("src.orchestrator_v3.build_protocol_v2", return_value=MagicMock()), \
         patch("src.orchestrator_v3.LocalMemoryStore", return_value=MagicMock()), \
         patch("src.orchestrator_v3.AuditLogger", return_value=MagicMock()), \
         patch("src.orchestrator_v3.ExecutionRunner", return_value=MagicMock()), \
         patch("src.orchestrator_v3.OutcomeStore", return_value=MagicMock()), \
         patch("src.orchestrator_v3.ReflexDispatcher", return_value=MagicMock()), \
         patch("src.orchestrator_v3.GitHubClient", return_value=MagicMock()), \
         patch("src.orchestrator_v3._load_settings", return_value=settings or {}):
        from src.orchestrator_v3 import OrchestratorV3
        return OrchestratorV3(diagnostics_loop=diagnostics_loop)


# ── TestDiagnosticsLoopInjection ──────────────────────────────────────────────

class TestDiagnosticsLoopInjection:
    def test_diagnostics_loop_injected_directly(self):
        mock_loop = _make_diag_loop_mock()
        orch = _make_orchestrator(diagnostics_loop=mock_loop)
        assert orch.diagnostics_loop is mock_loop

    def test_diagnostics_loop_none_when_disabled(self):
        settings = {"diagnostics_loop": {"enabled": False}}
        orch = _make_orchestrator(settings=settings)
        assert orch.diagnostics_loop is None

    def test_diagnostics_loop_none_when_no_settings(self):
        orch = _make_orchestrator()
        assert orch.diagnostics_loop is None


# ── TestRunDiagnosticsLoop ────────────────────────────────────────────────────

class TestRunDiagnosticsLoop:
    def test_run_diagnostics_loop_calls_loop_run(self):
        mock_loop = _make_diag_loop_mock()
        orch = _make_orchestrator(diagnostics_loop=mock_loop)

        mock_event = MagicMock()
        mock_event.event_id = "evt-001"

        orch._run_diagnostics_loop(mock_event, MagicMock())
        mock_loop.run.assert_called_once_with(order_id="evt-001", dry_run=True)

    def test_run_diagnostics_loop_noop_when_none(self):
        orch = _make_orchestrator()
        mock_event = MagicMock()
        mock_event.event_id = "evt-002"
        # Should not raise
        orch._run_diagnostics_loop(mock_event, MagicMock())

    def test_run_diagnostics_loop_respects_dry_run_false(self):
        mock_loop = _make_diag_loop_mock()
        settings = {"diagnostics_loop": {"enabled": False, "dry_run": False}}
        orch = _make_orchestrator(diagnostics_loop=mock_loop, settings=settings)

        mock_event = MagicMock()
        mock_event.event_id = "evt-003"
        orch._run_diagnostics_loop(mock_event, MagicMock())

        mock_loop.run.assert_called_once_with(order_id="evt-003", dry_run=False)

    def test_run_diagnostics_loop_logs_verdict(self):
        mock_loop = _make_diag_loop_mock(verdict="DEGRADED", risk=40)
        orch = _make_orchestrator(diagnostics_loop=mock_loop)

        mock_event = MagicMock()
        mock_event.event_id = "evt-004"
        orch._run_diagnostics_loop(mock_event, MagicMock())

        orch.audit.log.assert_called_with("diagnostics_loop", {
            "verdict": "DEGRADED",
            "risk": 40,
            "blockers": [],
        })

    def test_run_diagnostics_loop_exception_non_fatal(self):
        mock_loop = MagicMock(spec=DiagnosticsLoop)
        mock_loop.run.side_effect = RuntimeError("network error")
        orch = _make_orchestrator(diagnostics_loop=mock_loop)

        mock_event = MagicMock()
        mock_event.event_id = "evt-005"
        # Should NOT raise — DiagnosticsLoop errors are non-fatal
        orch._run_diagnostics_loop(mock_event, MagicMock())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
