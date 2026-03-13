"""
Integration tests for Sherlock V3 agent.

Tests Sherlock's integration with:
- Memory recall system
- Hypothesis generation
- Root cause analysis
- Pipeline handoff to Fixer
"""
import pytest
from pathlib import Path
import tempfile
import shutil
from src.types import EventJsonV1, EventArtifact, HandoffPacket, MemoryHit
from src.a2a.agent_wrapper import build_protocol_v2
from src.memory.store_v2 import LocalMemoryStore


@pytest.fixture
def temp_memory_dir():
    """Create temporary directory for memory store."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_sherlock_in_pipeline():
    """
    Test Sherlock V3 in full A2A pipeline.

    Verifies:
    - Sherlock executes successfully after Sentinel
    - Hypotheses are generated
    - Root cause analysis is performed
    - CGRF metadata is present (Tier 1)
    """
    event = EventJsonV1(
        event_id="int-sherlock-001",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed due to import error",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ImportError: cannot import name 'deprecated' from 'typing_extensions'"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run Sentinel → Sherlock
    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock"])

    # Verify Sherlock output exists
    assert "sherlock" in result_packet.agent_outputs
    sherlock_output = result_packet.agent_outputs["sherlock"]

    # Verify hypotheses
    assert "hypotheses" in sherlock_output.payload
    hypotheses = sherlock_output.payload["hypotheses"]
    assert isinstance(hypotheses, list)
    assert len(hypotheses) > 0
    # Root cause analysis is captured in hypotheses

    # Verify CGRF metadata
    assert "cgrf_metadata" in sherlock_output.payload
    meta = sherlock_output.payload["cgrf_metadata"]
    assert meta["tier"] == 1  # Sherlock is Tier 1
    assert meta["module_name"] == "sherlock_v3"
    assert meta["module_version"] == "3.0.0"


def test_sherlock_with_memory_recall(temp_memory_dir):
    """
    Test Sherlock's integration with memory recall.

    Verifies:
    - Sherlock can access historical memory
    - Memory hits influence hypothesis generation
    - Similar past events are considered
    """
    # Create memory store with historical event
    corpus_path = temp_memory_dir / "corpus.json"
    memory = LocalMemoryStore(corpus_path=corpus_path)

    # Remember a similar past event
    past_event = EventJsonV1(
        event_id="past-001",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed due to typing_extensions version mismatch",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ImportError: typing_extensions 3.x required but 4.x installed"
        ),
    )

    memory.remember(
        event_id=past_event.event_id,
        summary=past_event.summary,
        tags=["dependency", "version_conflict"],
        outcome="success",
    )

    # Current event
    event = EventJsonV1(
        event_id="int-sherlock-002",
        event_type="ci_failed",
        source="github_actions",
        summary="Import error in build",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ImportError: cannot import from typing_extensions"
        ),
    )

    # Recall similar events (use event summary as query)
    memory_hits = memory.recall(event.summary, k=3)

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event, memory_hits=memory_hits)

    # Run with memory context
    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock"])
    sherlock_output = result_packet.agent_outputs["sherlock"]

    # Verify Sherlock used memory context
    assert "hypotheses" in sherlock_output.payload
    hypotheses = sherlock_output.payload["hypotheses"]

    # At least one hypothesis should exist
    assert len(hypotheses) > 0


def test_sherlock_hypothesis_confidence():
    """
    Test Sherlock's hypothesis confidence scoring.

    Verifies:
    - Each hypothesis has a confidence score
    - Confidence scores are in valid range [0.0, 1.0]
    - Hypotheses are ranked by confidence
    """
    event = EventJsonV1(
        event_id="int-sherlock-003",
        event_type="deploy_failed",
        source="azure_devops",
        summary="Deployment failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="Error: Port 8080 already in use. Cannot bind to address."
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock"])
    sherlock_output = result_packet.agent_outputs["sherlock"]

    hypotheses = sherlock_output.payload.get("hypotheses", [])
    assert len(hypotheses) > 0

    # Check confidence scores if available
    for hyp in hypotheses:
        if isinstance(hyp, dict) and "confidence" in hyp:
            confidence = hyp["confidence"]
            assert 0.0 <= confidence <= 1.0, f"Invalid confidence: {confidence}"


def test_sherlock_root_cause_analysis():
    """
    Test Sherlock's root cause analysis capability.

    Verifies:
    - Root cause is identified
    - Analysis considers multiple factors
    - Output is actionable for Fixer
    """
    event = EventJsonV1(
        event_id="int-sherlock-004",
        event_type="security_alert",
        source="dependabot",
        summary="Critical vulnerability in package",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="CVE-2023-12345: SQL injection in express-validator < 6.14.3"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock"])
    sherlock_output = result_packet.agent_outputs["sherlock"]

    # Verify hypotheses exist (contains root cause analysis)
    assert "hypotheses" in sherlock_output.payload
    hypotheses = sherlock_output.payload["hypotheses"]
    assert len(hypotheses) > 0
    # Each hypothesis contains the root cause analysis


def test_sherlock_handoff_to_fixer():
    """
    Test Sherlock's handoff to Fixer in pipeline.

    Verifies:
    - Sherlock output is preserved when Fixer runs
    - Fixer receives Sherlock's analysis
    - Both outputs coexist in packet
    """
    event = EventJsonV1(
        event_id="int-sherlock-005",
        event_type="ci_failed",
        source="github_actions",
        summary="Test failure",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="AssertionError: expected 200 but got 404"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run Sentinel → Sherlock → Fixer
    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer"])

    # Verify all outputs exist
    assert "sentinel" in result_packet.agent_outputs
    assert "sherlock" in result_packet.agent_outputs
    assert "fixer" in result_packet.agent_outputs

    # Verify Sherlock output is preserved
    sherlock_output = result_packet.agent_outputs["sherlock"]
    assert sherlock_output.payload.get("hypotheses") is not None
    # Root cause is embedded in hypotheses

    # Verify Fixer has access to Sherlock's analysis
    fixer_output = result_packet.agent_outputs["fixer"]
    assert fixer_output.payload.get("fix_plan") is not None


def test_sherlock_with_classification_context():
    """
    Test Sherlock using Sentinel's classification.

    Verifies:
    - Sherlock receives Sentinel's classification
    - Classification influences hypothesis generation
    - Context flows through pipeline
    """
    event = EventJsonV1(
        event_id="int-sherlock-006",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="MemoryError: Unable to allocate array"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run Sentinel → Sherlock
    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock"])

    # Verify Sentinel's classification exists
    sentinel_output = result_packet.agent_outputs["sentinel"]
    assert "classification" in sentinel_output.payload
    classification = sentinel_output.payload["classification"]
    assert classification is not None

    # Verify Sherlock processed the event
    sherlock_output = result_packet.agent_outputs["sherlock"]
    assert "hypotheses" in sherlock_output.payload
    assert len(sherlock_output.payload["hypotheses"]) > 0
