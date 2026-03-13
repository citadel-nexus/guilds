# tests/test_sentinel_v2.py
"""Unit tests for Sentinel V2 agent."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.sentinel_v2 import (
    _MODULE_NAME,
    _MODULE_VERSION,
    _CGRF_TIER,
    _generate_cgrf_metadata,
    _run_sentinel_rules,
    run_sentinel_v2,
)
from src.types import EventJsonV1, EventArtifact, HandoffPacket, CGRFMetadata


def test_module_metadata():
    """Test that module metadata constants are defined correctly."""
    assert _MODULE_NAME == "sentinel_v2"
    assert _MODULE_VERSION == "2.1.0"
    assert _CGRF_TIER == 1


def test_cgrf_metadata_generation():
    """Test CGRF metadata generation for Sentinel agent."""
    # Create test event
    event = EventJsonV1(
        event_id="test-001",
        event_type="ci_failed",
        source="github_actions",
        summary="CI pipeline failed",
        repo="test/repo",
        artifacts=EventArtifact(),
    )
    packet = HandoffPacket(event=event)

    # Generate metadata
    metadata = _generate_cgrf_metadata(packet)

    # Verify structure
    assert isinstance(metadata, CGRFMetadata)
    assert metadata.tier == 1
    assert metadata.module_version == "2.1.0"
    assert metadata.module_name == "sentinel_v2"
    assert metadata.execution_role == "BACKEND_SERVICE"
    assert metadata.author == "agent"
    assert "SRS-SENTINEL-" in metadata.report_id


def test_sentinel_classification_ci_failed():
    """Test Sentinel classification for CI failure event."""
    event = EventJsonV1(
        event_id="test-ci-001",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="ModuleNotFoundError: No module named 'requests'"),
    )
    packet = HandoffPacket(event=event)

    result = _run_sentinel_rules(packet)

    assert result["classification"] == "ci_failed"
    assert result["severity"] == "medium"
    assert "ci_failed" in result["signals"]
    assert "missing_dependency" in result["signals"]
    assert result["signal_count"] >= 2
    assert result["source"] == "github_actions"
    assert result["llm_powered"] is False
    assert "cgrf_metadata" in result


def test_sentinel_severity_mapping():
    """Test Sentinel severity assignment based on event type."""
    test_cases = [
        ("ci_failed", "medium"),
        ("deploy_failed", "high"),
        ("security_alert", "critical"),
        ("config_drift", "low"),
    ]

    for event_type, expected_severity in test_cases:
        event = EventJsonV1(
            event_id=f"test-{event_type}",
            event_type=event_type,
            source="test",
            summary="Test event",
            repo="test/repo",
            artifacts=EventArtifact(),
        )
        packet = HandoffPacket(event=event)
        result = _run_sentinel_rules(packet)

        assert result["severity"] == expected_severity, f"Failed for {event_type}"


def test_sentinel_signal_extraction():
    """Test signal extraction from log excerpts."""
    test_cases = [
        ("ModuleNotFoundError", ["missing_dependency"]),
        ("PermissionError", ["permission_denied"]),
        ("ConnectionRefused", ["service_unavailable"]),
        ("CVE-2024-1234", ["security_vulnerability"]),
    ]

    for log_pattern, expected_signals in test_cases:
        event = EventJsonV1(
            event_id="test-signal",
            event_type="ci_failed",
            source="test",
            summary="Test",
            repo="test/repo",
            artifacts=EventArtifact(log_excerpt=log_pattern),
        )
        packet = HandoffPacket(event=event)
        result = _run_sentinel_rules(packet)

        for signal in expected_signals:
            assert signal in result["signals"], f"Signal {signal} not found for {log_pattern}"


def test_sentinel_security_severity_escalation():
    """Test that security vulnerabilities escalate severity."""
    event = EventJsonV1(
        event_id="test-sec",
        event_type="ci_failed",  # Originally medium severity
        source="test",
        summary="Security issue",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="CVE-2024-1234 detected"),
    )
    packet = HandoffPacket(event=event)
    result = _run_sentinel_rules(packet)

    # Security signal should escalate severity to at least high
    assert result["severity"] in ("high", "critical")
    assert "security_vulnerability" in result["signals"]


def test_sentinel_v2_main_entry_point():
    """Test the main run_sentinel_v2 entry point."""
    event = EventJsonV1(
        event_id="test-main",
        event_type="ci_failed",
        source="github_actions",
        summary="Pipeline failure",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="ImportError: cannot import name 'foo'"),
    )
    packet = HandoffPacket(event=event)

    # Run sentinel (will try LLM then fall back to rules)
    result = run_sentinel_v2(packet)

    # Verify minimum contract
    assert "classification" in result
    assert "severity" in result
    assert "signals" in result
    assert "signal_count" in result
    assert "source" in result
    assert "llm_powered" in result
    assert "cgrf_metadata" in result

    # Verify CGRF metadata structure
    cgrf = result["cgrf_metadata"]
    assert cgrf["tier"] == 1
    assert cgrf["module_name"] == "sentinel_v2"
    assert cgrf["module_version"] == "2.1.0"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
