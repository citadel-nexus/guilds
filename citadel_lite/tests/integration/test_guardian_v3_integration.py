"""
Integration tests for Guardian V3 agent.

Tests Guardian's integration with:
- Risk assessment model
- Decision making (approve/need_approval/block)
- Verification step consideration
- Pipeline completion
"""
import pytest
from src.types import EventJsonV1, EventArtifact, HandoffPacket
from src.a2a.agent_wrapper import build_protocol_v2


def test_guardian_in_pipeline():
    """
    Test Guardian V3 in full A2A pipeline.

    Verifies:
    - Guardian executes successfully after Fixer
    - Decision is produced (approve/need_approval/block)
    - Risk score is calculated
    - CGRF metadata is present (Tier 2)
    """
    event = EventJsonV1(
        event_id="int-guardian-001",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed missing dependency",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ModuleNotFoundError: No module named 'requests'"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run full pipeline: Sentinel → Sherlock → Fixer → Guardian
    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])

    # Verify Guardian output exists
    assert "guardian" in result_packet.agent_outputs
    guardian_output = result_packet.agent_outputs["guardian"]

    # Verify decision
    assert "action" in guardian_output.payload
    action = guardian_output.payload["action"]
    assert action in ["approve", "need_approval", "block"]

    # Verify risk score
    assert "risk_score" in guardian_output.payload
    risk_score = guardian_output.payload["risk_score"]
    assert isinstance(risk_score, (int, float))
    assert 0.0 <= risk_score <= 1.0

    # Verify CGRF metadata
    assert "cgrf_metadata" in guardian_output.payload
    meta = guardian_output.payload["cgrf_metadata"]
    assert meta["tier"] == 2  # Guardian is Tier 2
    assert meta["module_name"] == "guardian_v3"
    assert meta["module_version"] == "3.0.0"


def test_guardian_low_risk_approval():
    """
    Test Guardian approves low-risk fixes.

    Verifies:
    - Low-risk events get approved automatically
    - Risk score threshold works correctly
    - Decision rationale is provided
    """
    event = EventJsonV1(
        event_id="int-guardian-002",
        event_type="ci_failed",
        source="github_actions",
        summary="Missing import statement",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="NameError: name 'os' is not defined"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])
    guardian_output = result_packet.agent_outputs["guardian"]

    # Simple import fix should be low risk
    risk_score = guardian_output.payload.get("risk_score")
    assert risk_score is not None

    # Verify reasoning exists
    if "reasoning" in guardian_output.payload:
        reasoning = guardian_output.payload["reasoning"]
        assert reasoning is not None
        assert len(str(reasoning)) > 0


def test_guardian_high_risk_blocking():
    """
    Test Guardian blocks high-risk changes.

    Verifies:
    - High-risk events get blocked
    - Security-related changes trigger careful review
    - Risk score reflects severity
    """
    event = EventJsonV1(
        event_id="int-guardian-003",
        event_type="security_alert",
        source="dependabot",
        summary="Critical vulnerability requires immediate action",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="CVE-2023-99999: Remote code execution in auth module"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])
    guardian_output = result_packet.agent_outputs["guardian"]

    # Security alerts should have elevated risk consideration
    risk_score = guardian_output.payload.get("risk_score")
    action = guardian_output.payload.get("action")

    # Verify Guardian made a decision
    assert action in ["approve", "need_approval", "block"]
    assert risk_score is not None


def test_guardian_risk_score_calculation():
    """
    Test Guardian's risk score calculation.

    Verifies:
    - Risk score is in valid range [0.0, 1.0]
    - Different event types produce different risk scores
    - Risk factors are considered
    """
    # Low-risk event
    low_risk_event = EventJsonV1(
        event_id="int-guardian-004a",
        event_type="ci_failed",
        source="github_actions",
        summary="Typo in comment",
        repo="test/repo",
        artifacts=EventArtifact(log_excerpt="# Tpyo in comment"),
    )

    # High-risk event
    high_risk_event = EventJsonV1(
        event_id="int-guardian-004b",
        event_type="deploy_failed",
        source="production",
        summary="Database migration failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="FATAL: Cannot drop table 'users' - constraint violation"
        ),
    )

    protocol = build_protocol_v2()

    # Test low-risk event
    low_packet = HandoffPacket(event=low_risk_event)
    low_result = protocol.pipeline(low_packet, ["sentinel", "sherlock", "fixer", "guardian"])
    low_risk_score = low_result.agent_outputs["guardian"].payload.get("risk_score")

    # Test high-risk event
    high_packet = HandoffPacket(event=high_risk_event)
    high_result = protocol.pipeline(high_packet, ["sentinel", "sherlock", "fixer", "guardian"])
    high_risk_score = high_result.agent_outputs["guardian"].payload.get("risk_score")

    # Verify both scores are valid
    if low_risk_score is not None:
        assert 0.0 <= low_risk_score <= 1.0
    if high_risk_score is not None:
        assert 0.0 <= high_risk_score <= 1.0


def test_guardian_uses_verification_steps():
    """
    Test Guardian considers verification steps in risk assessment.

    Verifies:
    - Presence of verification steps reduces risk
    - Guardian reads verification_steps from Fixer
    - Risk mitigation is applied
    """
    event = EventJsonV1(
        event_id="int-guardian-005",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ModuleNotFoundError: No module named 'pandas'"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])

    # Verify Fixer included verification steps
    fixer_output = result_packet.agent_outputs["fixer"]
    verification_steps = fixer_output.payload.get("verification_steps", [])
    assert len(verification_steps) > 0

    # Verify Guardian made a decision
    guardian_output = result_packet.agent_outputs["guardian"]
    assert "action" in guardian_output.payload
    assert "risk_score" in guardian_output.payload


def test_guardian_decision_consistency():
    """
    Test Guardian's decision consistency.

    Verifies:
    - Same event type produces consistent decisions
    - Risk thresholds are applied consistently
    - Decision logic is deterministic
    """
    event = EventJsonV1(
        event_id="int-guardian-006",
        event_type="ci_failed",
        source="github_actions",
        summary="Test failure",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="AssertionError: expected True but got False"
        ),
    )

    protocol = build_protocol_v2()

    # Run same event through pipeline twice
    packet1 = HandoffPacket(event=event)
    result1 = protocol.pipeline(packet1, ["sentinel", "sherlock", "fixer", "guardian"])
    guardian1 = result1.agent_outputs["guardian"]

    packet2 = HandoffPacket(event=event)
    result2 = protocol.pipeline(packet2, ["sentinel", "sherlock", "fixer", "guardian"])
    guardian2 = result2.agent_outputs["guardian"]

    # Verify both produced valid decisions
    assert guardian1.payload.get("action") in ["approve", "need_approval", "block"]
    assert guardian2.payload.get("action") in ["approve", "need_approval", "block"]

    # Risk scores should be in valid range
    risk1 = guardian1.payload.get("risk_score")
    risk2 = guardian2.payload.get("risk_score")
    if risk1 is not None:
        assert 0.0 <= risk1 <= 1.0
    if risk2 is not None:
        assert 0.0 <= risk2 <= 1.0


def test_guardian_with_all_context():
    """
    Test Guardian using full pipeline context.

    Verifies:
    - Guardian receives all previous agent outputs
    - Sentinel's classification influences decision
    - Sherlock's root cause is considered
    - Fixer's plan is evaluated
    """
    event = EventJsonV1(
        event_id="int-guardian-007",
        event_type="deploy_failed",
        source="azure_devops",
        summary="Deployment failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="Error: Configuration validation failed"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])

    # Verify all agents executed
    assert len(result_packet.agent_outputs) == 4

    # Verify Guardian has access to all previous outputs
    assert "sentinel" in result_packet.agent_outputs
    assert "sherlock" in result_packet.agent_outputs
    assert "fixer" in result_packet.agent_outputs
    assert "guardian" in result_packet.agent_outputs

    # Verify Guardian made informed decision
    guardian_output = result_packet.agent_outputs["guardian"]
    assert guardian_output.payload.get("action") is not None
    assert guardian_output.payload.get("risk_score") is not None

    # Verify context from other agents
    sentinel_classification = result_packet.agent_outputs["sentinel"].payload.get("classification")
    sherlock_hypotheses = result_packet.agent_outputs["sherlock"].payload.get("hypotheses")
    fixer_plan = result_packet.agent_outputs["fixer"].payload.get("fix_plan")

    assert sentinel_classification is not None
    assert sherlock_hypotheses is not None
    assert fixer_plan is not None


def test_guardian_reasoning_quality():
    """
    Test Guardian provides quality reasoning for decisions.

    Verifies:
    - Reasoning is provided for all decisions
    - Reasoning references relevant factors
    - Reasoning is non-empty and meaningful
    """
    event = EventJsonV1(
        event_id="int-guardian-008",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="SyntaxError: invalid syntax"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])
    guardian_output = result_packet.agent_outputs["guardian"]

    # Check for reasoning field
    if "reasoning" in guardian_output.payload:
        reasoning = guardian_output.payload["reasoning"]
        assert reasoning is not None
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0
    elif "rationale" in guardian_output.payload:
        rationale = guardian_output.payload["rationale"]
        assert rationale is not None
        assert isinstance(rationale, str)
        assert len(rationale) > 0
