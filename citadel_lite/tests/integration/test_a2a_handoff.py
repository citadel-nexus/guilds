"""
Integration tests for A2A Protocol handoff flow.

Tests the complete A2A pipeline with all 4 agents:
- Sentinel V2 → Sherlock V3 → Fixer V3 → Guardian V3

Verifies:
- HandoffPacket propagation
- Agent output accumulation
- CGRF metadata preservation
- Decision flow
"""
import pytest
from src.types import EventJsonV1, EventArtifact, HandoffPacket
from src.a2a.agent_wrapper import build_protocol_v2


def test_full_a2a_pipeline():
    """
    Test complete A2A handoff: Sentinel → Sherlock → Fixer → Guardian.

    Verifies:
    - All 4 agents execute successfully
    - HandoffPacket contains outputs from all agents
    - CGRF metadata is present in all outputs
    - Guardian produces a valid decision
    """
    # Create test event
    event = EventJsonV1(
        event_id="integration-a2a-001",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed due to missing dependency",
        repo="test/repo",
        ref="main",
        artifacts=EventArtifact(
            log_excerpt="ERROR: ModuleNotFoundError: No module named 'requests'"
        ),
    )

    # Build protocol with all 4 agents
    protocol = build_protocol_v2()

    # Create initial packet
    packet = HandoffPacket(event=event)

    # Run through all agents using pipeline
    final_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])

    # Verify all outputs are present
    assert len(final_packet.agent_outputs) == 4
    assert "sentinel" in final_packet.agent_outputs
    assert "sherlock" in final_packet.agent_outputs
    assert "fixer" in final_packet.agent_outputs
    assert "guardian" in final_packet.agent_outputs

    # Verify each agent's output structure
    sentinel_output = final_packet.agent_outputs["sentinel"]
    assert sentinel_output.payload.get("classification") is not None
    assert "cgrf_metadata" in sentinel_output.payload
    assert sentinel_output.payload["cgrf_metadata"]["tier"] == 1

    sherlock_output = final_packet.agent_outputs["sherlock"]
    assert sherlock_output.payload.get("hypotheses") is not None
    assert "cgrf_metadata" in sherlock_output.payload
    assert sherlock_output.payload["cgrf_metadata"]["tier"] == 1

    fixer_output = final_packet.agent_outputs["fixer"]
    assert fixer_output.payload.get("fix_plan") is not None
    assert "cgrf_metadata" in fixer_output.payload
    assert fixer_output.payload["cgrf_metadata"]["tier"] == 1

    guardian_output = final_packet.agent_outputs["guardian"]
    assert guardian_output.payload.get("action") in ["approve", "need_approval", "block"]
    assert guardian_output.payload.get("risk_score") is not None
    assert "cgrf_metadata" in guardian_output.payload
    assert guardian_output.payload["cgrf_metadata"]["tier"] == 2  # Guardian is Tier 2


def test_handoff_packet_propagation():
    """
    Test that HandoffPacket is correctly propagated through the pipeline.

    Verifies:
    - Original event is preserved
    - Agent outputs accumulate
    - Metadata is maintained
    """
    event = EventJsonV1(
        event_id="integration-a2a-002",
        event_type="deploy_failed",
        source="azure_devops",
        summary="Deployment failed on production",
        repo="test/repo",
        ref="release/v1.0",
        artifacts=EventArtifact(
            log_excerpt="ERROR: Permission denied: /var/www/app"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run partial pipeline: Sentinel → Sherlock only
    partial_packet = protocol.pipeline(packet, ["sentinel", "sherlock"])

    # Verify original event is preserved
    assert partial_packet.event.event_id == "integration-a2a-002"
    assert partial_packet.event.event_type == "deploy_failed"
    assert partial_packet.event.summary == "Deployment failed on production"

    # Verify outputs are accumulated (not replaced)
    assert len(partial_packet.agent_outputs) == 2
    assert "sentinel" in partial_packet.agent_outputs
    assert "sherlock" in partial_packet.agent_outputs

    # Verify Sentinel's output is still present
    sentinel_output = partial_packet.agent_outputs["sentinel"]
    assert sentinel_output.payload.get("classification") is not None


def test_agent_output_accumulation():
    """
    Test that agent outputs accumulate correctly without overwriting.

    Verifies:
    - Each agent adds its output to the packet
    - Previous outputs are not overwritten
    - Output order is preserved
    """
    event = EventJsonV1(
        event_id="integration-a2a-003",
        event_type="security_alert",
        source="dependabot",
        summary="Critical vulnerability in lodash",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="CVE-2021-12345: Prototype pollution in lodash"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Initial packet should have no outputs
    assert len(packet.agent_outputs) == 0

    # Run agents one by one
    packet_after_sentinel = protocol.pipeline(packet, ["sentinel"])
    assert len(packet_after_sentinel.agent_outputs) == 1
    assert "sentinel" in packet_after_sentinel.agent_outputs

    packet_after_sherlock = protocol.pipeline(packet_after_sentinel, ["sherlock"])
    assert len(packet_after_sherlock.agent_outputs) == 2
    assert "sentinel" in packet_after_sherlock.agent_outputs
    assert "sherlock" in packet_after_sherlock.agent_outputs

    packet_after_fixer = protocol.pipeline(packet_after_sherlock, ["fixer"])
    assert len(packet_after_fixer.agent_outputs) == 3
    assert "sentinel" in packet_after_fixer.agent_outputs
    assert "sherlock" in packet_after_fixer.agent_outputs
    assert "fixer" in packet_after_fixer.agent_outputs

    packet_after_guardian = protocol.pipeline(packet_after_fixer, ["guardian"])
    assert len(packet_after_guardian.agent_outputs) == 4

    # Verify each output is unique and not overwritten
    outputs = packet_after_guardian.agent_outputs
    assert outputs["sentinel"].payload.get("classification") is not None
    assert outputs["sherlock"].payload.get("hypotheses") is not None
    assert outputs["fixer"].payload.get("fix_plan") is not None
    assert outputs["guardian"].payload.get("action") is not None


def test_cgrf_metadata_preservation():
    """
    Test that CGRF metadata is preserved throughout the pipeline.

    Verifies:
    - All agents produce CGRF metadata
    - Metadata contains correct tier information
    - Metadata is not lost during handoff
    """
    event = EventJsonV1(
        event_id="integration-a2a-004",
        event_type="ci_failed",
        source="github_actions",
        summary="Test failure",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="FAILED tests/test_app.py"),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run full pipeline
    final_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])

    # Verify all outputs have CGRF metadata
    for agent_name, output in final_packet.agent_outputs.items():
        assert "cgrf_metadata" in output.payload, f"{agent_name} missing CGRF metadata"
        meta = output.payload["cgrf_metadata"]
        assert meta["tier"] in [0, 1, 2, 3], f"{agent_name} has invalid tier"
        assert meta["module_name"] is not None
        assert meta["module_version"] is not None

    # Verify tier assignments
    assert final_packet.agent_outputs["sentinel"].payload["cgrf_metadata"]["tier"] == 1
    assert final_packet.agent_outputs["sherlock"].payload["cgrf_metadata"]["tier"] == 1
    assert final_packet.agent_outputs["fixer"].payload["cgrf_metadata"]["tier"] == 1
    assert final_packet.agent_outputs["guardian"].payload["cgrf_metadata"]["tier"] == 2
