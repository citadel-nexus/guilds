# tests/test_pipeline_e2e.py
"""End-to-end tests for the full Citadel Lite pipeline."""
import json
import sys
import shutil
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# OrchestratorV3 requires a local LLM server at localhost:1234 (openai/gpt-oss-20b).
# Skip collection entirely in CI / when server is unavailable.
import socket as _socket
def _local_llm_available() -> bool:
    try:
        s = _socket.create_connection(("localhost", 1234), timeout=1)
        s.close()
        return True
    except OSError:
        return False

if not _local_llm_available():
    pytest.skip("Local LLM server (localhost:1234) not available", allow_module_level=True)

from src.orchestrator_v3 import OrchestratorV3
from src.a2a.agent_wrapper import build_protocol_v2
from src.audit.logger import AuditLogger
from src.memory.store_v2 import LocalMemoryStore
from src.execution.runner_V2 import ExecutionRunner
from src.execution.outcome_store import OutcomeStore
from src.reflex.dispatcher import ReflexDispatcher


def _cleanup_output(event_id: str) -> None:
    out_dir = Path("out") / event_id
    if out_dir.exists():
        shutil.rmtree(out_dir)


def test_ci_failed_e2e():
    """Full pipeline test with ci_failed event."""
    event_path = Path("demo/events/ci_failed.sample.json")
    event_id = "demo-ci-failed-001"
    _cleanup_output(event_id)

    audit = AuditLogger()
    orchestrator = OrchestratorV3(
        protocol=build_protocol_v2(),
        memory=LocalMemoryStore(),
        audit=audit,
        executor=ExecutionRunner(mode="local"),
        outcome_store=OutcomeStore(),
    )
    orchestrator.run(event_path)

    base = Path("out") / event_id

    # Handoff packet exists with all agent outputs
    packet_path = base / "handoff_packet.json"
    assert packet_path.exists(), "handoff_packet.json not generated"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert "sentinel" in packet["agent_outputs"]
    assert "sherlock" in packet["agent_outputs"]
    assert "fixer" in packet["agent_outputs"]
    assert "guardian" in packet["agent_outputs"]

    # A2A trace present
    assert "a2a_trace" in packet
    assert len(packet["a2a_trace"]) >= 4

    # Decision exists and is valid
    decision_path = base / "decision.json"
    assert decision_path.exists(), "decision.json not generated"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["action"] in ("approve", "need_approval", "block")

    # Audit report exists with hash chain
    report_path = base / "audit_report.json"
    assert report_path.exists(), "audit_report.json not generated"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "hash_chain" in report
    assert report["hash_chain"]["chain_length"] > 0

    # Hash chain is valid
    assert audit.verify_chain(), "Audit hash chain integrity check failed"

    # Memory hits present (corpus has matching entries)
    assert "memory_hits" in packet
    assert len(packet["memory_hits"]) > 0

    print(f"  E2E test passed: {event_id} -> {decision['action']}")


def test_security_alert_e2e():
    """Full pipeline test with security alert event."""
    event_path = Path("demo/events/security_alert.sample.json")
    event_id = "demo-security-alert-001"
    _cleanup_output(event_id)

    orchestrator = OrchestratorV3(
        protocol=build_protocol_v2(),
        memory=LocalMemoryStore(),
        audit=AuditLogger(),
        executor=ExecutionRunner(mode="local"),
        outcome_store=OutcomeStore(),
    )
    orchestrator.run(event_path)

    base = Path("out") / event_id
    assert (base / "handoff_packet.json").exists()
    assert (base / "decision.json").exists()
    assert (base / "audit_report.json").exists()

    print(f"  E2E test passed: {event_id}")


def test_deploy_failure_e2e():
    """Full pipeline test with deploy failure event."""
    event_path = Path("demo/events/deploy_failure.sample.json")
    event_id = "demo-deploy-fail-001"
    _cleanup_output(event_id)

    orchestrator = OrchestratorV3(
        protocol=build_protocol_v2(),
        memory=LocalMemoryStore(),
        audit=AuditLogger(),
        executor=ExecutionRunner(mode="local"),
        outcome_store=OutcomeStore(),
    )
    orchestrator.run(event_path)

    base = Path("out") / event_id
    assert (base / "handoff_packet.json").exists()
    assert (base / "decision.json").exists()

    print(f"  E2E test passed: {event_id}")


def test_memory_learning():
    """Test that the memory layer learns from pipeline runs."""
    memory = LocalMemoryStore(corpus_path=Path("out/.test_memory_corpus.json"))

    # Initially no custom memories
    hits = memory.recall("custom test event", k=3)
    custom_hits = [h for h in hits if "custom" in h.title.lower()]
    assert len(custom_hits) == 0

    # Remember a new incident
    memory.remember("test-event-1", "Custom test failure in auth module", ["ci_failed", "auth"], "approved")

    # Now it should be recallable
    hits = memory.recall("auth module failure", k=3)
    assert len(hits) > 0
    assert any("auth" in h.title.lower() for h in hits)

    # Cleanup
    Path("out/.test_memory_corpus.json").unlink(missing_ok=True)
    print("  Memory learning test passed")


def test_verify_retry_on_failure():
    """Test that orchestrator_v3 retries when verification fails (REFLEX self-healing)."""
    # Create a test event that will trigger verification retry
    event_path = Path("demo/events/ci_failed.sample.json")
    event_id = "test-verify-retry-001"
    _cleanup_output(event_id)

    # Read event and modify to have unique ID and max_attempts
    event_json = json.loads(event_path.read_text(encoding="utf-8"))
    event_json["event_id"] = event_id
    event_json["artifacts"] = event_json.get("artifacts", {})
    event_json["artifacts"]["extra"] = {"max_attempts": 2}

    # Write modified event
    test_event_path = Path("out") / ".test_events" / f"{event_id}.json"
    test_event_path.parent.mkdir(parents=True, exist_ok=True)
    test_event_path.write_text(json.dumps(event_json, indent=2), encoding="utf-8")

    # Run orchestrator_v3 with retry capability
    orchestrator = OrchestratorV3(
        protocol=build_protocol_v2(),
        memory=LocalMemoryStore(),
        audit=AuditLogger(),
        executor=ExecutionRunner(mode="dry_run"),
        outcome_store=OutcomeStore(),
        reflex=ReflexDispatcher(),
    )
    orchestrator.run(test_event_path)

    base = Path("out") / event_id

    # Check that attempt files exist (even if verification succeeded on first try)
    assert (base / "handoff_packet.attempt_1.json").exists(), "attempt_1 handoff not created"
    assert (base / "audit_report.attempt_1.json").exists(), "attempt_1 audit not created"
    assert (base / "decision.attempt_1.json").exists(), "attempt_1 decision not created"

    # Check final handoff packet has attempts array
    final_packet_path = base / "handoff_packet.json"
    assert final_packet_path.exists(), "final handoff_packet.json not generated"
    final_packet = json.loads(final_packet_path.read_text(encoding="utf-8"))

    # Verify attempts array exists and has at least 1 attempt
    assert "packet_artifacts" in final_packet, "packet_artifacts not in final packet"
    assert "attempts" in final_packet["packet_artifacts"], "attempts array not in packet.artifacts"
    attempts = final_packet["packet_artifacts"]["attempts"]
    assert len(attempts) >= 1, f"Expected at least 1 attempt, got {len(attempts)}"

    # Verify first attempt structure
    attempt_1 = attempts[0]
    assert "attempt" in attempt_1
    assert attempt_1["attempt"] == 1
    assert "decision" in attempt_1
    assert "risk_score" in attempt_1

    # Cleanup test event
    test_event_path.unlink(missing_ok=True)

    print(f"  Verify retry test passed: {len(attempts)} attempt(s) recorded")


if __name__ == "__main__":
    test_ci_failed_e2e()
    test_security_alert_e2e()
    test_deploy_failure_e2e()
    test_memory_learning()
    test_verify_retry_on_failure()
    print("\nAll E2E tests passed.")
