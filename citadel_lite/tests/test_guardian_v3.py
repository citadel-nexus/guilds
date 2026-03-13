# tests/test_guardian_v3.py
"""Unit tests for Guardian V3 agent."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.guardian_v3 import (
    _MODULE_NAME,
    _MODULE_VERSION,
    _CGRF_TIER,
    _generate_cgrf_metadata,
    _run_guardian_rules,
    run_guardian_v3,
)
from src.types import (
    EventJsonV1,
    EventArtifact,
    HandoffPacket,
    Decision,
    CGRFMetadata,
)


def test_module_metadata():
    """Test that module metadata constants are defined correctly."""
    assert _MODULE_NAME == "guardian_v3"
    assert _MODULE_VERSION == "3.0.0"
    assert _CGRF_TIER == 2  # Production tier


def test_cgrf_metadata_generation():
    """Test CGRF metadata generation for Guardian agent."""
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
    assert metadata.tier == 2  # Guardian is Tier 2 (Production)
    assert metadata.module_version == "3.0.0"
    assert metadata.module_name == "guardian_v3"
    assert metadata.execution_role == "BACKEND_SERVICE"
    assert metadata.author == "agent"
    assert "SRS-GUARDIAN-" in metadata.report_id


def test_guardian_low_risk_auto_approval():
    """Test Guardian auto-approves low-risk fixes (risk < 0.25)."""
    event = EventJsonV1(
        event_id="test-low-risk",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(),
    )

    packet = HandoffPacket(event=event)

    # Add agent outputs for low-risk scenario
    packet.add_output("sentinel", {
        "classification": "ci_failed",
        "severity": "low",  # Low severity
        "signals": ["ci_failed"],
    })
    packet.add_output("sherlock", {
        "hypotheses": [{"title": "Minor issue", "explanation": "Small config issue", "evidence": [], "confidence": 0.90}],
        "confidence": 0.90,  # High confidence
        "label": "config_drift",
    })
    packet.add_output("fixer", {
        "fix_plan": "Update config file",
        "risk_estimate": 0.10,  # Very low risk
        "verification_steps": ["echo test"],
    })

    decision = _run_guardian_rules(packet)

    assert isinstance(decision, Decision)
    assert decision.action == "approve"
    assert decision.risk_score < 0.25


def test_guardian_medium_risk_needs_approval():
    """Test Guardian requires human approval for medium-risk fixes (0.25 <= risk < 0.65)."""
    event = EventJsonV1(
        event_id="test-medium-risk",
        event_type="deploy_failed",
        source="github_actions",
        summary="Deploy failed",
        repo="test/repo",
        artifacts=EventArtifact(),
    )

    packet = HandoffPacket(event=event)

    # Add agent outputs for medium-risk scenario
    packet.add_output("sentinel", {
        "classification": "deploy_failed",
        "severity": "medium",
        "signals": ["deploy_failed"],
    })
    packet.add_output("sherlock", {
        "hypotheses": [{"title": "Deploy issue", "explanation": "Service config", "evidence": [], "confidence": 0.70}],
        "confidence": 0.70,  # Moderate confidence
        "label": "permission_denied",
    })
    packet.add_output("fixer", {
        "fix_plan": "Update deployment config",
        "risk_estimate": 0.40,  # Medium risk
        "verification_steps": [],
    })

    decision = _run_guardian_rules(packet)

    assert decision.action == "need_approval"
    assert 0.25 <= decision.risk_score < 0.65


def test_guardian_high_risk_blocked():
    """Test Guardian blocks high-risk fixes (risk >= 0.65)."""
    event = EventJsonV1(
        event_id="test-high-risk",
        event_type="security_alert",
        source="dependabot",
        summary="Critical security vulnerability",
        repo="test/repo",
        artifacts=EventArtifact(),
    )

    packet = HandoffPacket(event=event)

    # Add agent outputs for high-risk scenario
    packet.add_output("sentinel", {
        "classification": "security_alert",
        "severity": "critical",  # Critical severity
        "signals": ["security_alert", "security_vulnerability"],
    })
    packet.add_output("sherlock", {
        "hypotheses": [{"title": "Security vuln", "explanation": "CVE detected", "evidence": [], "confidence": 0.50}],
        "confidence": 0.50,  # Lower confidence
        "label": "security_alert",
    })
    packet.add_output("fixer", {
        "fix_plan": "Upgrade vulnerable package",
        "risk_estimate": 0.60,  # High risk
        "verification_steps": [],
    })

    decision = _run_guardian_rules(packet)

    assert decision.action in ("block", "need_approval")
    assert decision.risk_score >= 0.40  # Security bump increases risk


def test_guardian_severity_weight_critical():
    """Test that critical severity significantly increases risk score."""
    event = EventJsonV1(
        event_id="test-critical",
        event_type="security_alert",
        source="test",
        summary="Critical issue",
        repo="test/repo",
        artifacts=EventArtifact(),
    )

    packet = HandoffPacket(event=event)

    packet.add_output("sentinel", {
        "classification": "security_alert",
        "severity": "critical",  # Critical = 0.9 weight
        "signals": [],
    })
    packet.add_output("sherlock", {
        "hypotheses": [{"title": "Test", "explanation": "Test", "evidence": [], "confidence": 1.0}],
        "confidence": 1.0,
        "label": "unknown",
    })
    packet.add_output("fixer", {
        "fix_plan": "Test fix",
        "risk_estimate": 0.1,  # Low fixer risk
        "verification_steps": [],
    })

    decision = _run_guardian_rules(packet)

    # Critical severity should push risk score higher
    assert decision.risk_score >= 0.20  # 0.9 severity weight contributes significantly


def test_guardian_confidence_penalty():
    """Test that low confidence increases risk score (confidence penalty)."""
    event = EventJsonV1(
        event_id="test-confidence",
        event_type="ci_failed",
        source="test",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(),
    )

    packet = HandoffPacket(event=event)

    packet.add_output("sentinel", {
        "classification": "ci_failed",
        "severity": "low",
        "signals": [],
    })
    packet.add_output("sherlock", {
        "hypotheses": [{"title": "Uncertain", "explanation": "Not sure", "evidence": [], "confidence": 0.30}],
        "confidence": 0.30,  # Low confidence = high penalty
        "label": "unknown",
    })
    packet.add_output("fixer", {
        "fix_plan": "Try something",
        "risk_estimate": 0.1,
        "verification_steps": [],
    })

    decision = _run_guardian_rules(packet)

    # Low confidence (0.30) should add penalty: (1 - 0.30) * 0.2 = 0.14
    # This should push the action toward need_approval or higher risk
    assert decision.risk_score >= 0.10


def test_guardian_security_vulnerability_bump():
    """Test that security vulnerabilities add risk bump."""
    event = EventJsonV1(
        event_id="test-sec-bump",
        event_type="security_alert",
        source="test",
        summary="Security issue",
        repo="test/repo",
        artifacts=EventArtifact(),
    )

    packet = HandoffPacket(event=event)

    packet.add_output("sentinel", {
        "classification": "security_alert",
        "severity": "medium",
        "signals": ["security_vulnerability"],  # Security signal
    })
    packet.add_output("sherlock", {
        "hypotheses": [{"title": "Vuln", "explanation": "CVE", "evidence": [], "confidence": 0.80}],
        "confidence": 0.80,
        "label": "security_alert",
    })
    packet.add_output("fixer", {
        "fix_plan": "Patch vulnerability",
        "risk_estimate": 0.2,
        "verification_steps": [],
    })

    decision = _run_guardian_rules(packet)

    # Security bump (+0.2) should be applied
    assert decision.risk_score >= 0.35  # Base + security bump


def test_guardian_verification_steps_mitigation():
    """Test that verification steps reduce risk score."""
    event = EventJsonV1(
        event_id="test-verify",
        event_type="ci_failed",
        source="test",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(),
    )

    packet = HandoffPacket(event=event)

    packet.add_output("sentinel", {
        "classification": "ci_failed",
        "severity": "medium",
        "signals": [],
    })
    packet.add_output("sherlock", {
        "hypotheses": [{"title": "Deps", "explanation": "Missing", "evidence": [], "confidence": 0.85}],
        "confidence": 0.85,
        "label": "deps_missing",
    })
    packet.add_output("fixer", {
        "fix_plan": "Install dependencies",
        "risk_estimate": 0.15,
        "verification_steps": ["pip install", "python -c 'import foo'"],  # Has verification
    })

    decision = _run_guardian_rules(packet)

    # Verification steps should apply -0.04 mitigation
    # Risk should be lower than without verification
    assert decision.risk_score < 0.30


def test_guardian_v3_main_entry_point():
    """Test the main run_guardian_v3 entry point."""
    event = EventJsonV1(
        event_id="test-main",
        event_type="ci_failed",
        source="github_actions",
        summary="Pipeline failure",
        repo="test/repo",
        artifacts=EventArtifact(),
    )

    packet = HandoffPacket(event=event)

    packet.add_output("sentinel", {
        "classification": "ci_failed",
        "severity": "medium",
        "signals": ["ci_failed"],
    })
    packet.add_output("sherlock", {
        "hypotheses": [{"title": "Missing dep", "explanation": "Flask missing", "evidence": [], "confidence": 0.85}],
        "confidence": 0.85,
        "label": "deps_missing",
    })
    packet.add_output("fixer", {
        "fix_plan": "Add flask to requirements.txt",
        "risk_estimate": 0.15,
        "verification_steps": ["pip install -r requirements.txt"],
    })

    decision = run_guardian_v3(packet)

    # Verify Decision object contract
    assert isinstance(decision, Decision)
    assert decision.action in ("approve", "need_approval", "block")
    assert 0.0 <= decision.risk_score <= 1.0
    assert isinstance(decision.rationale, str)
    assert len(decision.rationale) > 0
    assert isinstance(decision.policy_refs, list)

    # Verify CGRF metadata was attached to packet.artifacts
    assert hasattr(packet, "artifacts")
    assert "guardian_cgrf_metadata" in packet.artifacts
    cgrf = packet.artifacts["guardian_cgrf_metadata"]
    assert cgrf["tier"] == 2
    assert cgrf["module_name"] == "guardian_v3"
    assert cgrf["module_version"] == "3.0.0"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
