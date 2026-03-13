"""
Integration tests for Sentinel V2 agent.

Tests Sentinel's integration with:
- Event processing pipeline
- A2A Protocol handoff
- CGRF metadata generation
- Classification logic
"""
import pytest
from src.types import EventJsonV1, EventArtifact, HandoffPacket
from src.a2a.agent_wrapper import build_protocol_v2


def test_sentinel_in_pipeline():
    """
    Test Sentinel V2 in full A2A pipeline.

    Verifies:
    - Sentinel executes successfully in pipeline
    - Classification is produced
    - Severity is assigned
    - CGRF metadata is present (Tier 1)
    """
    event = EventJsonV1(
        event_id="int-sentinel-001",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed due to missing dependency",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ERROR: ModuleNotFoundError: No module named 'requests'"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run Sentinel only
    result_packet = protocol.pipeline(packet, ["sentinel"])

    # Verify Sentinel output exists
    assert "sentinel" in result_packet.agent_outputs
    sentinel_output = result_packet.agent_outputs["sentinel"]

    # Verify classification
    assert "classification" in sentinel_output.payload
    assert sentinel_output.payload["classification"] is not None

    # Verify severity
    assert "severity" in sentinel_output.payload
    assert sentinel_output.payload["severity"] in ["low", "medium", "high", "critical"]

    # Verify CGRF metadata
    assert "cgrf_metadata" in sentinel_output.payload
    meta = sentinel_output.payload["cgrf_metadata"]
    assert meta["tier"] == 1  # Sentinel is Tier 1
    assert meta["module_name"] == "sentinel_v2"
    assert meta["module_version"] == "2.1.0"


def test_sentinel_signal_extraction():
    """
    Test Sentinel's signal extraction from logs.

    Verifies:
    - Signals are extracted from log text
    - Common error patterns are detected
    """
    event = EventJsonV1(
        event_id="int-sentinel-002",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ERROR: Permission denied: /var/www/app\nFailed to write file"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel"])
    sentinel_output = result_packet.agent_outputs["sentinel"]

    # Verify signals exist
    assert "signals" in sentinel_output.payload
    signals = sentinel_output.payload["signals"]
    assert isinstance(signals, list)

    # Permission denied should be detected
    assert any("permission" in str(sig).lower() for sig in signals)


def test_sentinel_severity_escalation():
    """
    Test Sentinel's severity escalation for critical events.

    Verifies:
    - Security events are escalated to high/critical severity
    - Classification is appropriate for event type
    """
    event = EventJsonV1(
        event_id="int-sentinel-003",
        event_type="security_alert",
        source="dependabot",
        summary="Critical vulnerability in lodash",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="CVE-2021-12345: Prototype pollution vulnerability"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel"])
    sentinel_output = result_packet.agent_outputs["sentinel"]

    # Security alerts should have high or critical severity
    severity = sentinel_output.payload["severity"]
    assert severity in ["high", "critical"]

    # Classification should be security-related
    classification = sentinel_output.payload["classification"]
    assert classification in ["security_alert", "incident"]


def test_sentinel_handoff_to_sherlock():
    """
    Test Sentinel's handoff to Sherlock in pipeline.

    Verifies:
    - Sentinel output is preserved when Sherlock runs
    - HandoffPacket propagates correctly
    - Both outputs coexist
    """
    event = EventJsonV1(
        event_id="int-sentinel-004",
        event_type="deploy_failed",
        source="azure_devops",
        summary="Deployment failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="Error: Port 8080 already in use"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run Sentinel → Sherlock
    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock"])

    # Verify both outputs exist
    assert "sentinel" in result_packet.agent_outputs
    assert "sherlock" in result_packet.agent_outputs

    # Verify Sentinel output is preserved
    sentinel_output = result_packet.agent_outputs["sentinel"]
    assert sentinel_output.payload.get("classification") is not None

    # Verify Sherlock has access to Sentinel's classification
    sherlock_output = result_packet.agent_outputs["sherlock"]
    assert sherlock_output.payload.get("hypotheses") is not None
