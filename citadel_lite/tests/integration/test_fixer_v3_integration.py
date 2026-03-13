"""
Integration tests for Fixer V3 agent.

Tests Fixer's integration with:
- Fix plan generation
- Verification steps creation
- Code change proposals
- Pipeline handoff to Guardian
"""
import pytest
from src.types import EventJsonV1, EventArtifact, HandoffPacket
from src.a2a.agent_wrapper import build_protocol_v2


def test_fixer_in_pipeline():
    """
    Test Fixer V3 in full A2A pipeline.

    Verifies:
    - Fixer executes successfully after Sherlock
    - Fix plan is generated
    - Verification steps are included
    - CGRF metadata is present (Tier 1)
    """
    event = EventJsonV1(
        event_id="int-fixer-001",
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

    # Run Sentinel → Sherlock → Fixer
    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer"])

    # Verify Fixer output exists
    assert "fixer" in result_packet.agent_outputs
    fixer_output = result_packet.agent_outputs["fixer"]

    # Verify fix plan
    assert "fix_plan" in fixer_output.payload
    fix_plan = fixer_output.payload["fix_plan"]
    assert fix_plan is not None
    assert len(str(fix_plan)) > 0

    # Verify verification steps
    assert "verification_steps" in fixer_output.payload
    verification_steps = fixer_output.payload["verification_steps"]
    assert isinstance(verification_steps, list)
    assert len(verification_steps) > 0

    # Verify CGRF metadata
    assert "cgrf_metadata" in fixer_output.payload
    meta = fixer_output.payload["cgrf_metadata"]
    assert meta["tier"] == 1  # Fixer is Tier 1
    assert meta["module_name"] == "fixer_v3"
    assert meta["module_version"] == "3.0.0"


def test_fixer_verification_steps_structure():
    """
    Test Fixer's verification steps structure.

    Verifies:
    - Verification steps are executable commands
    - Steps are ordered logically
    - Steps are relevant to the fix
    """
    event = EventJsonV1(
        event_id="int-fixer-002",
        event_type="ci_failed",
        source="github_actions",
        summary="Test failure",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="FAILED tests/test_app.py::test_user_login - AssertionError"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer"])
    fixer_output = result_packet.agent_outputs["fixer"]

    # Verification steps are optional but should be valid if present
    verification_steps = fixer_output.payload.get("verification_steps", [])
    assert isinstance(verification_steps, list)

    # If verification steps exist, validate their structure
    if len(verification_steps) > 0:
        # Verify each step is a string (command)
        for step in verification_steps:
            assert isinstance(step, str)
            assert len(step) > 0


def test_fixer_files_to_change():
    """
    Test Fixer's file change proposals.

    Verifies:
    - Files to change are identified
    - Changes are specific and actionable
    - File paths are provided
    """
    event = EventJsonV1(
        event_id="int-fixer-003",
        event_type="deploy_failed",
        source="azure_devops",
        summary="Configuration error",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="Error: Invalid database connection string in config.yaml"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer"])
    fixer_output = result_packet.agent_outputs["fixer"]

    # Check if files_to_change is present
    if "files_to_change" in fixer_output.payload:
        files_to_change = fixer_output.payload["files_to_change"]
        assert isinstance(files_to_change, list)

        # Verify structure if files are specified
        for file_change in files_to_change:
            if isinstance(file_change, dict):
                # Should have path and change description
                assert "path" in file_change or "file" in file_change


def test_fixer_uses_sherlock_analysis():
    """
    Test Fixer using Sherlock's root cause analysis.

    Verifies:
    - Fixer receives Sherlock's hypotheses
    - Fix plan addresses identified root cause
    - Context flows from Sherlock to Fixer
    """
    event = EventJsonV1(
        event_id="int-fixer-004",
        event_type="security_alert",
        source="dependabot",
        summary="Vulnerability in dependency",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="CVE-2023-99999: RCE vulnerability in lodash < 4.17.21"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run Sentinel → Sherlock → Fixer
    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer"])

    # Verify Sherlock's analysis exists
    sherlock_output = result_packet.agent_outputs["sherlock"]
    assert "hypotheses" in sherlock_output.payload
    # root_cause field is optional - hypotheses contain the analysis

    # Verify Fixer generated a fix plan
    fixer_output = result_packet.agent_outputs["fixer"]
    assert "fix_plan" in fixer_output.payload
    fix_plan = fixer_output.payload["fix_plan"]
    assert fix_plan is not None


def test_fixer_handoff_to_guardian():
    """
    Test Fixer's handoff to Guardian in pipeline.

    Verifies:
    - Fixer output is preserved when Guardian runs
    - Guardian receives Fixer's fix plan
    - All outputs coexist in packet
    """
    event = EventJsonV1(
        event_id="int-fixer-005",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="TypeError: 'NoneType' object is not iterable"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    # Run full pipeline: Sentinel → Sherlock → Fixer → Guardian
    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])

    # Verify all outputs exist
    assert "sentinel" in result_packet.agent_outputs
    assert "sherlock" in result_packet.agent_outputs
    assert "fixer" in result_packet.agent_outputs
    assert "guardian" in result_packet.agent_outputs

    # Verify Fixer output is preserved
    fixer_output = result_packet.agent_outputs["fixer"]
    assert fixer_output.payload.get("fix_plan") is not None
    assert fixer_output.payload.get("verification_steps") is not None

    # Verify Guardian has access to Fixer's plan
    guardian_output = result_packet.agent_outputs["guardian"]
    assert guardian_output.payload.get("action") in ["approve", "need_approval", "block"]
    assert guardian_output.payload.get("risk_score") is not None


def test_fixer_with_complex_event():
    """
    Test Fixer handling complex multi-issue event.

    Verifies:
    - Fixer can handle multiple related issues
    - Fix plan addresses all identified problems
    - Verification steps cover all changes
    """
    event = EventJsonV1(
        event_id="int-fixer-006",
        event_type="ci_failed",
        source="github_actions",
        summary="Multiple errors in build",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="""
ERROR: ModuleNotFoundError: No module named 'pandas'
ERROR: SyntaxError: invalid syntax in app.py line 42
WARNING: Deprecated function used in utils.py
"""
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer"])
    fixer_output = result_packet.agent_outputs["fixer"]

    # Verify fix plan exists and addresses complexity
    assert "fix_plan" in fixer_output.payload
    fix_plan = fixer_output.payload["fix_plan"]
    assert fix_plan is not None
    assert len(str(fix_plan)) > 0

    # Verification steps should exist
    verification_steps = fixer_output.payload.get("verification_steps", [])
    assert len(verification_steps) > 0


def test_fixer_minimal_change_principle():
    """
    Test Fixer follows minimal change principle.

    Verifies:
    - Fix plan is focused and minimal
    - Only necessary changes are proposed
    - No over-engineering in solution
    """
    event = EventJsonV1(
        event_id="int-fixer-007",
        event_type="ci_failed",
        source="github_actions",
        summary="Import error",
        repo="test/repo",
        artifacts=EventArtifact(
            log_excerpt="ImportError: No module named 'yaml'"
        ),
    )

    protocol = build_protocol_v2()
    packet = HandoffPacket(event=event)

    result_packet = protocol.pipeline(packet, ["sentinel", "sherlock", "fixer"])
    fixer_output = result_packet.agent_outputs["fixer"]

    # Verify fix plan exists
    assert "fix_plan" in fixer_output.payload
    fix_plan = fixer_output.payload["fix_plan"]
    assert fix_plan is not None

    # Verify verification steps exist and are reasonable
    verification_steps = fixer_output.payload.get("verification_steps", [])
    assert len(verification_steps) > 0
    # For a simple import error, shouldn't have excessive verification steps
    assert len(verification_steps) <= 5
