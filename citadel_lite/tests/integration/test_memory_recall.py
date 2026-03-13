"""
Integration tests for Memory Store integration with pipeline.

Tests memory recall and persistence:
- Memory integration with Sherlock
- Recall during pipeline execution
- Remember after completion

Verifies:
- Memory is recalled before Sherlock runs
- Memory hits are injected into HandoffPacket
- Similar incidents are found and used
- New incidents are stored after completion
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from src.types import EventJsonV1, EventArtifact, HandoffPacket
from src.memory.store_v2 import LocalMemoryStore
from src.a2a.agent_wrapper import build_protocol_v2


@pytest.fixture
def temp_memory_dir():
    """Create temporary directory for memory store."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_memory_integration_with_sherlock(temp_memory_dir):
    """
    Test that memory is correctly integrated with Sherlock agent.

    Verifies:
    - Memory store can recall past incidents
    - Memory hits are injected into HandoffPacket
    - Sherlock can access memory_hits
    """
    # Create memory store with temporary directory
    memory = LocalMemoryStore(corpus_path=temp_memory_dir / "corpus.json")

    # Store a past incident
    memory.remember(
        event_id="past-001",
        summary="CI failed due to missing requests library",
        tags=["ci_failed", "deps_missing", "requests"],
        outcome="success",
    )

    # Create similar event
    event = EventJsonV1(
        event_id="integration-mem-001",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed - requests module not found",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ModuleNotFoundError: No module named 'requests'"
        ),
    )

    # Recall memory (simulating Orchestrator behavior)
    memory_hits = memory.recall("CI failed requests module", k=3)

    # Verify memory recall works
    assert len(memory_hits) > 0
    # Check if "requests" is in title or snippet
    assert any(
        "requests" in getattr(hit, "title", "").lower() or
        "requests" in getattr(hit, "snippet", "").lower()
        for hit in memory_hits
    )

    # Create packet and inject memory hits
    packet = HandoffPacket(event=event, memory_hits=memory_hits)

    # Verify memory_hits are in packet
    assert packet.memory_hits is not None
    assert len(packet.memory_hits) > 0

    # Run Sherlock with memory context
    protocol = build_protocol_v2()
    result_packet = protocol.pipeline(packet, ["sherlock"])

    # Verify Sherlock completed successfully with memory context
    assert result_packet is not None
    assert "sherlock" in result_packet.agent_outputs
    sherlock_output = result_packet.agent_outputs["sherlock"]
    assert sherlock_output.payload.get("hypotheses") is not None


def test_memory_recall_in_pipeline(temp_memory_dir):
    """
    Test memory recall during full pipeline execution.

    Verifies:
    - Memory is recalled before pipeline starts
    - Memory hits persist through all agents
    - All agents can access memory_hits
    """
    memory = LocalMemoryStore(corpus_path=temp_memory_dir / "corpus.json")

    # Store multiple past incidents
    past_incidents = [
        {
            "event_id": "past-ci-001",
            "summary": "CI failed missing dependency numpy",
            "tags": ["ci_failed", "deps_missing"],
            "outcome": "success",
        },
        {
            "event_id": "past-ci-002",
            "summary": "CI failed permission denied on /tmp",
            "tags": ["ci_failed", "permission_denied"],
            "outcome": "success",
        },
    ]

    for incident in past_incidents:
        memory.remember(
            event_id=incident["event_id"],
            summary=incident["summary"],
            tags=incident["tags"],
            outcome=incident["outcome"],
        )

    # Create new event similar to past incident
    event = EventJsonV1(
        event_id="integration-mem-002",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed - numpy not installed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ImportError: No module named 'numpy'"
        ),
    )

    # Recall memory
    memory_hits = memory.recall("CI failed missing numpy", k=3)
    assert len(memory_hits) > 0

    # Create packet with memory
    packet = HandoffPacket(event=event, memory_hits=memory_hits)

    # Run through all agents
    protocol = build_protocol_v2()
    final_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])

    # Verify memory_hits are still in final packet
    assert final_packet.memory_hits is not None
    assert len(final_packet.memory_hits) > 0

    # Verify at least one memory hit is relevant (check title or snippet)
    assert any(
        "numpy" in getattr(hit, "title", "").lower() or
        "numpy" in getattr(hit, "snippet", "").lower()
        for hit in final_packet.memory_hits
    )


def test_memory_remember_after_completion(temp_memory_dir):
    """
    Test storing new incidents in memory after pipeline completion.

    Verifies:
    - New incidents can be stored
    - Stored incidents can be recalled later
    - Tags are correctly indexed
    """
    memory = LocalMemoryStore(corpus_path=temp_memory_dir / "corpus.json")

    # Simulate pipeline completion and memory storage
    event = EventJsonV1(
        event_id="integration-mem-003",
        event_type="deploy_failed",
        source="azure_devops",
        summary="Deployment failed due to port conflict",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="Error: Port 8080 already in use"
        ),
    )

    # Store the incident
    memory.remember(
        event_id=event.event_id,
        summary=event.summary,
        tags=["deploy_failed", "port_conflict", "8080"],
        outcome="success",
    )

    # Verify it can be recalled
    hits = memory.recall("deployment port 8080", k=3)
    assert len(hits) > 0

    # Verify the stored incident is found (check title contains keywords)
    found = any("port" in getattr(hit, "title", "").lower() for hit in hits)
    assert found, "Stored incident with 'port' keyword not found in recall"

    # Verify tags are searchable
    port_hits = memory.recall("port conflict", k=3)
    assert len(port_hits) > 0
    # Check if "port" is in title or snippet or tags
    assert any(
        "port" in getattr(hit, "title", "").lower() or
        "port" in getattr(hit, "snippet", "").lower() or
        any("port" in str(tag).lower() for tag in getattr(hit, "tags", []))
        for hit in port_hits
    )


def test_memory_similarity_ranking(temp_memory_dir):
    """
    Test that memory recall ranks by similarity.

    Verifies:
    - More similar incidents rank higher
    - Recall returns top-k results
    - Similarity scoring works correctly
    """
    memory = LocalMemoryStore(corpus_path=temp_memory_dir / "corpus.json")

    # Store incidents with varying similarity
    incidents = [
        {
            "event_id": "mem-sim-001",
            "summary": "CI failed due to missing pandas library",
            "tags": ["ci_failed", "deps_missing", "pandas"],
            "outcome": "success",
        },
        {
            "event_id": "mem-sim-002",
            "summary": "CI failed permission denied",
            "tags": ["ci_failed", "permission_denied"],
            "outcome": "success",
        },
        {
            "event_id": "mem-sim-003",
            "summary": "Deployment failed timeout",
            "tags": ["deploy_failed", "timeout"],
            "outcome": "failure",
        },
    ]

    for incident in incidents:
        memory.remember(
            event_id=incident["event_id"],
            summary=incident["summary"],
            tags=incident["tags"],
            outcome=incident["outcome"],
        )

    # Query for pandas-related incident
    hits = memory.recall("CI failed pandas missing", k=3)
    assert len(hits) > 0

    # Most similar should contain "pandas" in title
    top_hit = hits[0]
    top_title = getattr(top_hit, "title", "").lower()
    assert "pandas" in top_title, f"Most similar incident should be about pandas, got: {top_title}"

    # Query for permission issue
    perm_hits = memory.recall("CI failed permission", k=3)
    assert len(perm_hits) > 0
    top_perm = perm_hits[0]
    top_perm_title = getattr(top_perm, "title", "").lower()
    assert "permission" in top_perm_title, f"Most similar incident should be about permission, got: {top_perm_title}"


def test_memory_empty_recall(temp_memory_dir):
    """
    Test memory recall when no past incidents exist.

    Verifies:
    - Empty memory returns empty list
    - Pipeline handles no memory hits gracefully
    """
    memory = LocalMemoryStore(corpus_path=temp_memory_dir / "corpus.json")

    # Recall from empty memory
    hits = memory.recall("some query", k=3)
    assert hits == []

    # Create event and packet with no memory
    event = EventJsonV1(
        event_id="integration-mem-004",
        event_type="ci_failed",
        source="github_actions",
        summary="New incident with no history",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="Error: Something new"),
    )

    packet = HandoffPacket(event=event, memory_hits=[])

    # Verify pipeline handles empty memory
    protocol = build_protocol_v2()
    result_packet = protocol.pipeline(packet, ["sentinel"])

    assert result_packet is not None
    assert "sentinel" in result_packet.agent_outputs
