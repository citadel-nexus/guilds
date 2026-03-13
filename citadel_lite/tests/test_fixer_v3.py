# tests/test_fixer_v3.py
"""Unit tests for Fixer V3 agent."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.fixer_v3 import (
    _MODULE_NAME,
    _MODULE_VERSION,
    _CGRF_TIER,
    _generate_cgrf_metadata,
    _run_fixer_rules,
    _extract_module_name,
    _extract_file_hint,
    _infer_label,
    _infer_verification_steps,
    run_fixer_v3,
)
from src.types import EventJsonV1, EventArtifact, HandoffPacket, CGRFMetadata


def test_module_metadata():
    """Test that module metadata constants are defined correctly."""
    assert _MODULE_NAME == "fixer_v3"
    assert _MODULE_VERSION == "3.0.0"
    assert _CGRF_TIER == 1


def test_cgrf_metadata_generation():
    """Test CGRF metadata generation for Fixer agent."""
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
    assert metadata.module_name == "fixer_v3"
    assert metadata.execution_role == "BACKEND_SERVICE"
    assert metadata.author == "agent"
    assert "SRS-FIXER-" in metadata.report_id


def test_extract_module_name():
    """Test module name extraction from error messages."""
    test_cases = [
        ("ModuleNotFoundError: No module named 'requests'", "requests"),
        ('ImportError: No module named "flask"', "flask"),
        ("No module named 'numpy.core'", "numpy.core"),
        ("Random error message", None),
    ]

    for log_excerpt, expected_module in test_cases:
        result = _extract_module_name(log_excerpt)
        assert result == expected_module, f"Failed for: {log_excerpt}"


def test_extract_file_hint():
    """Test file name extraction from error messages."""
    test_cases = [
        ("permission denied on deploy.sh", "deploy.sh"),
        ("Error: setup.py not executable", "setup.py"),
        ("Failed to run /path/to/script.sh", "script.sh"),
        ("Random error", None),
    ]

    for text, expected_file in test_cases:
        result = _extract_file_hint(text)
        if expected_file:
            assert result == expected_file, f"Failed for: {text}"


def test_infer_label_deps_missing():
    """Test label inference for missing dependency scenarios."""
    event = EventJsonV1(
        event_id="test-deps",
        event_type="ci_failed",
        source="test",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ModuleNotFoundError: No module named 'requests'"
        ),
    )
    packet = HandoffPacket(event=event)

    # Add Sherlock output with label
    packet.add_output("sherlock", {"label": "deps_missing", "confidence": 0.85})

    label = _infer_label(packet, "")
    assert label == "deps_missing"


def test_infer_label_permission_denied():
    """Test label inference for permission denied scenarios."""
    event = EventJsonV1(
        event_id="test-perm",
        event_type="deploy_failed",
        source="test",
        summary="Deploy failed",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="permission denied on deploy.sh"),
    )
    packet = HandoffPacket(event=event)

    label = _infer_label(packet, "")
    assert label == "permission_denied"


def test_infer_label_security_alert():
    """Test label inference for security alert scenarios."""
    event = EventJsonV1(
        event_id="test-sec",
        event_type="security_alert",
        source="test",
        summary="Security vulnerability",
        repo="test/repo",
        artifacts=EventArtifact(),
    )
    packet = HandoffPacket(event=event)

    label = _infer_label(packet, "")
    assert label == "security_alert"


def test_verification_steps_deps_missing():
    """Test verification steps generation for missing dependency."""
    steps = _infer_verification_steps(
        label="deps_missing",
        log_excerpt="ModuleNotFoundError: No module named 'requests'",
        summary="Build failed",
    )

    assert len(steps) == 3
    assert "python -c" in steps[0]  # Version check
    assert "pip install" in steps[1]  # Install dependencies
    assert "import requests" in steps[2]  # Import check


def test_verification_steps_permission_denied():
    """Test verification steps generation for permission denied."""
    steps = _infer_verification_steps(
        label="permission_denied",
        log_excerpt="permission denied on deploy.sh",
        summary="Deploy failed",
    )

    assert len(steps) == 3
    assert "ls -l" in steps[0]  # List permissions
    assert "test -r" in steps[1]  # Read permission check
    assert "test -x" in steps[2]  # Execute permission check


def test_verification_steps_security_alert():
    """Test verification steps generation for security alert."""
    steps = _infer_verification_steps(
        label="security_alert",
        log_excerpt="CVE-2024-1234",
        summary="Critical vulnerability in lodash < 4.17.21",
    )

    assert len(steps) == 4
    assert "npm ls" in steps[0]  # List package
    assert "npm audit" in steps[1]  # Audit
    assert "npm audit fix" in steps[2]  # Fix
    assert "npm ls" in steps[3]  # Verify


def test_fixer_rules_missing_dependency():
    """Test Fixer rule-based fix generation for missing dependency."""
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

    packet = HandoffPacket(event=event)
    packet.add_output("sentinel", {
        "classification": "ci_failed",
        "severity": "medium",
        "signals": ["missing_dependency"],
    })
    packet.add_output("sherlock", {
        "label": "deps_missing",
        "hypotheses": [
            {
                "title": "Missing Python dependency",
                "explanation": "Module not installed",
                "evidence": [],
                "confidence": 0.85,
            }
        ],
        "confidence": 0.85,
    })

    result = _run_fixer_rules(packet)

    assert "fix_plan" in result
    assert "requirements.txt" in result["fix_plan"]
    assert result["risk_estimate"] <= 0.2  # Low risk for dependency fix
    assert len(result["verification_steps"]) > 0
    assert "cgrf_metadata" in result


def test_fixer_rules_permission_denied():
    """Test Fixer rule-based fix generation for permission denied."""
    event = EventJsonV1(
        event_id="test-perm",
        event_type="deploy_failed",
        source="github_actions",
        summary="Deploy script failed",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="permission denied on deploy.sh"),
    )

    packet = HandoffPacket(event=event)
    packet.add_output("sentinel", {
        "classification": "deploy_failed",
        "severity": "high",
        "signals": ["permission_denied"],
    })
    packet.add_output("sherlock", {
        "label": "permission_denied",
        "hypotheses": [
            {
                "title": "Permission denied",
                "explanation": "File lacks execute permission",
                "evidence": [],
                "confidence": 0.80,
            }
        ],
        "confidence": 0.80,
    })

    result = _run_fixer_rules(packet)

    assert "fix_plan" in result
    assert "chmod" in result["fix_plan"]
    assert result["risk_estimate"] <= 0.15  # Very low risk for chmod


def test_fixer_rules_security_vulnerability():
    """Test Fixer rule-based fix generation for security vulnerability."""
    event = EventJsonV1(
        event_id="test-sec",
        event_type="security_alert",
        source="dependabot",
        summary="Critical vulnerability in lodash",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="CVE-2024-1234: Prototype pollution"
        ),
    )

    packet = HandoffPacket(event=event)
    packet.add_output("sentinel", {
        "classification": "security_alert",
        "severity": "critical",
        "signals": ["security_vulnerability"],
    })
    packet.add_output("sherlock", {
        "label": "security_alert",
        "hypotheses": [
            {
                "title": "Security vulnerability",
                "explanation": "Known CVE detected",
                "evidence": [],
                "confidence": 0.90,
            }
        ],
        "confidence": 0.90,
    })

    result = _run_fixer_rules(packet)

    assert "fix_plan" in result
    assert "upgrade" in result["fix_plan"].lower() or "update" in result["fix_plan"].lower()
    assert result["risk_estimate"] >= 0.30  # Higher risk for security fixes


def test_fixer_v3_main_entry_point():
    """Test the main run_fixer_v3 entry point."""
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
        "signals": ["missing_dependency"],
    })
    packet.add_output("sherlock", {
        "label": "deps_missing",
        "hypotheses": [{"title": "Missing dependency", "explanation": "Flask not installed", "evidence": [], "confidence": 0.85}],
        "confidence": 0.85,
    })

    result = run_fixer_v3(packet)

    # Verify minimum contract
    assert "fix_plan" in result
    assert "risk_estimate" in result
    assert "verification_steps" in result
    assert "llm_powered" in result
    assert "cgrf_metadata" in result

    # Verify CGRF metadata structure
    cgrf = result["cgrf_metadata"]
    assert cgrf["tier"] == 1
    assert cgrf["module_name"] == "fixer_v3"
    assert cgrf["module_version"] == "3.0.0"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
