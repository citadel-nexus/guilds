# tests/test_execution.py
"""Tests for the execution layer."""
import json
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.types import EventJsonV1, Decision
from src.execution.runner_V2 import ExecutionRunner, ExecutionOutcome
from src.execution.outcome_store import OutcomeStore


def _make_test_event() -> EventJsonV1:
    return EventJsonV1(
        event_id="test-exec-001",
        event_type="ci_failed",
        source="github_actions",
        repo="test/repo",
        ref="main",
        summary="CI failed",
    )


def _make_test_decision() -> Decision:
    return Decision(
        action="approve",
        risk_score=0.2,
        rationale="Low risk",
        policy_refs=["POLICY_DEMO_01"],
    )


def test_local_backend():
    """Test local execution backend writes action JSON."""
    event = _make_test_event()
    decision = _make_test_decision()
    fix_plan = {"fix_plan": "Add requests to requirements.txt", "patch": None, "risk_estimate": 0.2}

    runner = ExecutionRunner(mode="local")
    outcome = runner.execute(decision, fix_plan, event)

    assert outcome.success is True
    assert outcome.action_taken == "write_action_json"

    # Check file was written
    action_path = Path("out") / event.event_id / "execution_action.json"
    assert action_path.exists()

    data = json.loads(action_path.read_text(encoding="utf-8"))
    assert data["backend"] == "local"

    # Cleanup
    shutil.rmtree(Path("out") / event.event_id, ignore_errors=True)
    print("  Local backend test passed")


def test_dry_run_backend():
    """Test dry run backend returns success without side effects."""
    event = _make_test_event()
    decision = _make_test_decision()
    fix_plan = {"fix_plan": "Add requests to requirements.txt"}

    runner = ExecutionRunner(mode="dry_run")
    outcome = runner.execute(decision, fix_plan, event)

    assert outcome.success is True
    assert outcome.action_taken == "dry_run"
    assert "DRY RUN" in outcome.details

    print("  Dry run backend test passed")


def test_outcome_store():
    """Test outcome store records and retrieves outcomes."""
    store_path = Path("out/.test_outcomes.jsonl")
    store_path.unlink(missing_ok=True)

    store = OutcomeStore(path=store_path)

    outcome = ExecutionOutcome(
        event_id="test-001",
        action_taken="test",
        success=True,
        details="test outcome",
    )
    store.record(outcome)

    results = store.get_outcomes("test-001")
    assert len(results) == 1
    assert results[0]["event_id"] == "test-001"
    assert results[0]["success"] is True

    # Test filtering
    results_all = store.get_outcomes()
    assert len(results_all) >= 1

    results_none = store.get_outcomes("nonexistent")
    assert len(results_none) == 0

    # Cleanup
    store_path.unlink(missing_ok=True)
    print("  Outcome store test passed")


if __name__ == "__main__":
    test_local_backend()
    test_dry_run_backend()
    test_outcome_store()
    print("\nAll execution tests passed.")
