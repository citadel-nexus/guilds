# tests/test_sherlock_v3.py
"""Unit tests for Sherlock V3 agent."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.sherlock_v3 import (
    _MODULE_NAME,
    _MODULE_VERSION,
    _CGRF_TIER,
    _generate_cgrf_metadata,
    _run_sherlock_rules,
    _infer_sherlock_label,
    _mk_hypothesis,
    run_sherlock_v3,
)
from src.types import (
    EventJsonV1,
    EventArtifact,
    HandoffPacket,
    AgentOutput,
    CGRFMetadata,
)


def test_module_metadata():
    """Test that module metadata constants are defined correctly."""
    assert _MODULE_NAME == "sherlock_v3"
    assert _MODULE_VERSION == "3.0.0"
    assert _CGRF_TIER == 1


def test_cgrf_metadata_generation():
    """Test CGRF metadata generation for Sherlock agent."""
    event = EventJsonV1(
        event_id="test-001",
        event_type="ci_failed",
        source="github_actions",
        summary="CI pipeline failed",
        repo="test/repo",
        artifacts=EventArtifact(),
    )
    packet = HandoffPacket(event=event)

    metadata = _generate_cgrf_metadata(packet)

    assert isinstance(metadata, CGRFMetadata)
    assert metadata.tier == 1
    assert metadata.module_version == "3.0.0"
    assert metadata.module_name == "sherlock_v3"
    assert metadata.execution_role == "BACKEND_SERVICE"
    assert metadata.author == "agent"
    assert "SRS-SHERLOCK-" in metadata.report_id


def test_hypothesis_builder():
    """Test hypothesis object builder (_mk_hypothesis)."""
    hyp = _mk_hypothesis(
        title="Missing dependency",
        explanation="Module 'requests' not found in environment",
        evidence=[{"type": "log_pattern", "value": "ModuleNotFoundError"}],
        confidence=0.85,
    )

    assert hyp["title"] == "Missing dependency"
    assert hyp["explanation"] == "Module 'requests' not found in environment"
    assert len(hyp["evidence"]) == 1
    assert hyp["confidence"] == 0.85


def test_hypothesis_confidence_normalization():
    """Test that confidence scores are normalized to [0, 1]."""
    # Test confidence > 1.0
    hyp1 = _mk_hypothesis("Test", "Test", [], 1.5)
    assert hyp1["confidence"] == 1.0

    # Test confidence < 0.0
    hyp2 = _mk_hypothesis("Test", "Test", [], -0.5)
    assert hyp2["confidence"] == 0.0

    # Test valid range
    hyp3 = _mk_hypothesis("Test", "Test", [], 0.75)
    assert hyp3["confidence"] == 0.75


def test_label_inference_deps_missing():
    """Test label inference for missing dependency scenarios."""
    test_cases = [
        ("ModuleNotFoundError: No module named 'requests'", "ci_failed", "deps_missing"),
        ("ImportError: cannot import foo", "ci_failed", "deps_missing"),
        ("no module named numpy", "test_failed", "deps_missing"),
    ]

    for combined_text, event_type, expected_label in test_cases:
        label = _infer_sherlock_label(combined_text, event_type)
        assert label == expected_label, f"Failed for: {combined_text}"


def test_label_inference_permission_denied():
    """Test label inference for permission denied scenarios."""
    test_cases = [
        ("PermissionError: [Errno 13] Permission denied", "ci_failed", "permission_denied"),
        ("permission denied on deploy.sh", "deploy_failed", "permission_denied"),
        ("EACCES: permission denied", "ci_failed", "permission_denied"),
    ]

    for combined_text, event_type, expected_label in test_cases:
        label = _infer_sherlock_label(combined_text, event_type)
        assert label == expected_label, f"Failed for: {combined_text}"


def test_label_inference_security_alert():
    """Test label inference for security alert scenarios."""
    test_cases = [
        ("CVE-2024-1234 detected", "security_alert", "security_alert"),
        ("CVSS score: 9.8", "security_alert", "security_alert"),
        ("prototype pollution vulnerability", "ci_failed", "security_alert"),
    ]

    for combined_text, event_type, expected_label in test_cases:
        label = _infer_sherlock_label(combined_text, event_type)
        assert label == expected_label, f"Failed for: {combined_text}"


def test_sherlock_rules_missing_dependency():
    """Test Sherlock rule-based diagnosis for missing dependency."""
    event = EventJsonV1(
        event_id="test-deps",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ModuleNotFoundError: No module named 'requests'"
        ),
    )

    # Add sentinel output to packet
    packet = HandoffPacket(event=event)
    sentinel_payload = {
        "classification": "ci_failed",
        "severity": "medium",
        "signals": ["ci_failed", "missing_dependency"],
    }
    packet.add_output("sentinel", sentinel_payload)

    result = _run_sherlock_rules(packet)

    assert result["label"] == "deps_missing"
    assert isinstance(result["hypotheses"], list)
    assert len(result["hypotheses"]) > 0
    assert result["confidence"] >= 0.8  # High confidence for clear pattern
    assert result["llm_powered"] is False
    assert "cgrf_metadata" in result


def test_sherlock_rules_permission_denied():
    """Test Sherlock rule-based diagnosis for permission denied."""
    event = EventJsonV1(
        event_id="test-perm",
        event_type="deploy_failed",
        source="github_actions",
        summary="Deploy script failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="PermissionError: [Errno 13] Permission denied: 'deploy.sh'"
        ),
    )

    packet = HandoffPacket(event=event)
    sentinel_payload = {
        "classification": "deploy_failed",
        "severity": "high",
        "signals": ["deploy_failed", "permission_denied"],
    }
    packet.add_output("sentinel", sentinel_payload)

    result = _run_sherlock_rules(packet)

    assert result["label"] == "permission_denied"
    assert len(result["hypotheses"]) > 0
    assert result["confidence"] >= 0.75


def test_sherlock_rules_security_vulnerability():
    """Test Sherlock rule-based diagnosis for security vulnerability."""
    event = EventJsonV1(
        event_id="test-sec",
        event_type="security_alert",
        source="dependabot",
        summary="Critical vulnerability in lodash",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="CVE-2024-1234: Prototype pollution in lodash < 4.17.21"
        ),
    )

    packet = HandoffPacket(event=event)
    sentinel_payload = {
        "classification": "security_alert",
        "severity": "critical",
        "signals": ["security_alert", "security_vulnerability"],
    }
    packet.add_output("sentinel", sentinel_payload)

    result = _run_sherlock_rules(packet)

    assert result["label"] == "security_alert"
    assert len(result["hypotheses"]) > 0
    assert result["confidence"] >= 0.85  # High confidence for CVE pattern


def test_sherlock_memory_integration():
    """Test that Sherlock incorporates memory hits into diagnosis."""
    event = EventJsonV1(
        event_id="test-memory",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="ModuleNotFoundError"),
    )

    packet = HandoffPacket(event=event)

    # Add sentinel output
    packet.add_output("sentinel", {"classification": "ci_failed", "severity": "medium", "signals": []})

    # Add memory hits
    packet.memory_hits = [
        {
            "event_id": "prev-001",
            "title": "Similar dependency issue",
            "outcome": "resolved by adding to requirements.txt",
            "distance": 0.15,
        }
    ]

    result = run_sherlock_v3(packet)

    # Memory hits should influence diagnosis
    assert "hypotheses" in result
    assert "confidence" in result
    # Result should acknowledge memory context
    assert result.get("memory_hits_count", 0) >= 0


def test_sherlock_v3_main_entry_point():
    """Test the main run_sherlock_v3 entry point."""
    event = EventJsonV1(
        event_id="test-main",
        event_type="ci_failed",
        source="github_actions",
        summary="Pipeline failure",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="ImportError: No module named 'flask'"),
    )

    packet = HandoffPacket(event=event)
    packet.add_output("sentinel", {
        "classification": "ci_failed",
        "severity": "medium",
        "signals": ["ci_failed", "missing_dependency"],
    })

    result = run_sherlock_v3(packet)

    # Verify minimum contract
    assert "hypotheses" in result
    assert "confidence" in result
    assert "label" in result
    assert "llm_powered" in result
    assert "cgrf_metadata" in result

    # Verify CGRF metadata structure
    cgrf = result["cgrf_metadata"]
    assert cgrf["tier"] == 1
    assert cgrf["module_name"] == "sherlock_v3"
    assert cgrf["module_version"] == "3.0.0"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
