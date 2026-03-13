"""Unit tests for AGS (Agent Governance System) pipeline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.types import (
    EventJsonV1, EventArtifact, HandoffPacket, Decision,
)
from src.audit.logger import AuditLogger
from src.ags.pipeline import AGSPipeline, AGSVerdict
from src.ags.caps_stub import CAPSGrade, CAPSProfile, resolve_caps_grade, get_default_profile
from src.ags.s00_generator import S00Generator
from src.ags.s01_definer import S01Definer
from src.ags.s02_fate import S02Fate, AGSVerdictEnum
from src.ags.s03_archivist import S03Archivist


# ========== Helpers ==========

def _make_packet(risk_estimate=0.15, severity="medium", confidence=0.85):
    """Create a HandoffPacket with agent outputs for testing."""
    event = EventJsonV1(
        event_id="ags-test-001",
        event_type="ci_failed",
        source="github_actions",
        summary="Build failed: missing dependency",
        artifacts=EventArtifact(),
    )
    packet = HandoffPacket(event=event)
    packet.add_output("sentinel", {
        "classification": "ci_failed",
        "severity": severity,
        "signals": [],
    })
    packet.add_output("sherlock", {
        "hypotheses": [{"title": "Missing dep"}],
        "confidence": confidence,
    })
    packet.add_output("fixer", {
        "fix_plan": "Add dependency to requirements.txt",
        "risk_estimate": risk_estimate,
        "verification_steps": ["echo test"],
    })
    return packet


# ========== CAPS Stub Tests ==========

def test_caps_grade_resolution():
    """Test XP -> CAPS grade mapping."""
    assert resolve_caps_grade(0) == CAPSGrade.D
    assert resolve_caps_grade(100) == CAPSGrade.D
    assert resolve_caps_grade(101) == CAPSGrade.C
    assert resolve_caps_grade(500) == CAPSGrade.C
    assert resolve_caps_grade(501) == CAPSGrade.B
    assert resolve_caps_grade(2000) == CAPSGrade.B
    assert resolve_caps_grade(2001) == CAPSGrade.A
    assert resolve_caps_grade(10001) == CAPSGrade.S


def test_caps_profile_meets_tier():
    """Test CAPS grade vs CGRF tier requirements."""
    profile_b = CAPSProfile(agent_id="test", grade=CAPSGrade.B)
    assert profile_b.meets_tier(0)   # D+ required
    assert profile_b.meets_tier(1)   # C+ required
    assert profile_b.meets_tier(2)   # B+ required
    assert not profile_b.meets_tier(3)  # A+ required

    profile_d = CAPSProfile(agent_id="test", grade=CAPSGrade.D)
    assert profile_d.meets_tier(0)
    assert not profile_d.meets_tier(1)


def test_default_profile():
    """Test default CAPS profile (Phase 25 stub)."""
    p = get_default_profile("agent-1")
    assert p.agent_id == "agent-1"
    assert p.xp == 1000
    assert p.tp == 50
    assert p.grade == CAPSGrade.B


# ========== S00 Generator Tests ==========

def test_s00_generator_produces_sapient_packet():
    """Test S00 generates a valid SapientPacket from pipeline context."""
    packet = _make_packet()
    decision = Decision(
        action="approve", risk_score=0.15,
        rationale="low risk", policy_refs=["GOV-RISK-BAND-001"],
    )
    sapient = S00Generator().run(packet, decision)

    assert sapient.packet_id  # non-empty UUID
    assert sapient.action_type == "code_generation"
    assert sapient.intent_source == "github_actions"
    assert sapient.intent_id == "ags-test-001"
    assert sapient.guardian_risk_score == 0.15
    assert sapient.fate_recommendation == "proceed"
    assert sapient.final_decision == "AUTO_MERGE"
    assert sapient.council_votes == {"guardian": "approve"}


def test_s00_generator_block_scenario():
    """Test S00 handles block decision correctly."""
    packet = _make_packet(risk_estimate=0.8, severity="critical")
    decision = Decision(
        action="block", risk_score=0.8,
        rationale="high risk", policy_refs=[],
    )
    sapient = S00Generator().run(packet, decision)

    assert sapient.final_decision == "BLOCKED"
    assert sapient.fate_recommendation == "block"
    assert sapient.guardian_risk_score == 0.8
    assert "high risk" in sapient.dissent_reasons[0]


# ========== S01 Definer Tests ==========

def test_s01_definer_valid_packet():
    """Test S01 validates a well-formed packet."""
    packet = _make_packet()
    decision = Decision(action="approve", risk_score=0.15, rationale="ok", policy_refs=[])
    sapient = S00Generator().run(packet, decision)

    result = S01Definer().run(sapient, cgrf_tier=2)
    assert result.valid
    assert result.caps_meets_tier  # default B meets tier 2
    assert result.caps_grade == "B"
    assert len(result.violations) == 0


def test_s01_definer_caps_tier_violation():
    """Test S01 detects CAPS grade below tier requirement."""
    packet = _make_packet()
    decision = Decision(action="approve", risk_score=0.15, rationale="ok", policy_refs=[])
    sapient = S00Generator().run(packet, decision)

    low_caps = CAPSProfile(agent_id="weak", grade=CAPSGrade.D, xp=50)
    result = S01Definer().run(sapient, cgrf_tier=2, caps_profile=low_caps)
    assert not result.valid
    assert not result.caps_meets_tier
    assert any("CAPS grade" in v for v in result.violations)


# ========== S02 Fate Tests ==========

def test_s02_fate_allow_low_risk():
    """Test FATE allows low-risk events."""
    packet = _make_packet()
    decision = Decision(action="approve", risk_score=0.10, rationale="ok", policy_refs=[])
    sapient = S00Generator().run(packet, decision)
    definer_result = S01Definer().run(sapient, cgrf_tier=1)

    fate_result = S02Fate().run(sapient, definer_result, "approve")
    assert fate_result.verdict == AGSVerdictEnum.ALLOW
    assert not fate_result.escalated
    assert fate_result.risk_score == 0.10


def test_s02_fate_review_medium_risk():
    """Test FATE produces REVIEW for medium-risk events."""
    packet = _make_packet(risk_estimate=0.4, confidence=0.6)
    decision = Decision(action="need_approval", risk_score=0.35, rationale="medium", policy_refs=[])
    sapient = S00Generator().run(packet, decision)
    definer_result = S01Definer().run(sapient, cgrf_tier=1)

    fate_result = S02Fate().run(sapient, definer_result, "need_approval")
    assert fate_result.verdict == AGSVerdictEnum.REVIEW
    assert not fate_result.escalated  # Guardian already said need_approval


def test_s02_fate_escalation():
    """Test FATE escalates approve -> REVIEW/DENY when CAPS violated."""
    packet = _make_packet()
    decision = Decision(action="approve", risk_score=0.10, rationale="ok", policy_refs=[])
    sapient = S00Generator().run(packet, decision)

    # Force CAPS tier violation: D-grade for tier 2 (requires B+)
    low_caps = CAPSProfile(agent_id="weak", grade=CAPSGrade.D, xp=50)
    definer_result = S01Definer().run(sapient, cgrf_tier=2, caps_profile=low_caps)

    fate_result = S02Fate().run(sapient, definer_result, "approve")
    assert fate_result.escalated  # Was "approve", now escalated
    assert fate_result.verdict in (AGSVerdictEnum.REVIEW, AGSVerdictEnum.DENY)
    assert fate_result.original_guardian_action == "approve"


def test_s02_fate_deny_high_risk():
    """Test FATE denies high-risk events."""
    packet = _make_packet(risk_estimate=0.8, severity="critical")
    decision = Decision(action="block", risk_score=0.85, rationale="high", policy_refs=[])
    sapient = S00Generator().run(packet, decision)
    definer_result = S01Definer().run(sapient, cgrf_tier=2)

    fate_result = S02Fate().run(sapient, definer_result, "block")
    assert fate_result.verdict == AGSVerdictEnum.DENY
    assert not fate_result.escalated  # Guardian already blocked


# ========== S03 Archivist Tests ==========

def test_s03_archivist_records_verdict():
    """Test S03 records verdict in audit trail with hash chain."""
    audit = AuditLogger()
    audit.start("ags-test-event")

    packet = _make_packet()
    decision = Decision(action="approve", risk_score=0.10, rationale="ok", policy_refs=[])
    sapient = S00Generator().run(packet, decision)
    definer_result = S01Definer().run(sapient)
    fate_result = S02Fate().run(sapient, definer_result, "approve")

    record = S03Archivist().run(sapient, fate_result, audit=audit)

    assert record["verdict"] == "ALLOW"
    assert record["packet_id"] == sapient.packet_id
    assert record["intent_id"] == "ags-test-001"

    # Verify it was logged in the audit chain
    trail = audit.get_trail()
    ags_entries = [e for e in trail if e.stage == "ags.verdict"]
    assert len(ags_entries) == 1
    assert audit.verify_chain()


# ========== Full Pipeline Tests ==========

def test_ags_pipeline_low_risk():
    """Test full AGS pipeline with low-risk approve scenario."""
    audit = AuditLogger()
    audit.start("ags-pipeline-low")

    pipeline = AGSPipeline(audit=audit)
    packet = _make_packet()
    decision = Decision(action="approve", risk_score=0.10, rationale="ok", policy_refs=[])

    verdict = pipeline.run(packet, decision, cgrf_tier=1)

    assert isinstance(verdict, AGSVerdict)
    assert verdict.action == "approve"
    assert verdict.verdict == "ALLOW"
    assert not verdict.escalated
    assert verdict.sapient_packet_id  # non-empty
    assert "ags_verdict" in packet.artifacts


def test_ags_pipeline_escalation_override():
    """Test AGS pipeline escalates Guardian approve to block for tier violation."""
    audit = AuditLogger()
    audit.start("ags-pipeline-escalation")

    low_caps = CAPSProfile(agent_id="weak", grade=CAPSGrade.D, xp=50)
    pipeline = AGSPipeline(audit=audit, caps_profile=low_caps)

    packet = _make_packet()
    decision = Decision(action="approve", risk_score=0.10, rationale="ok", policy_refs=[])

    verdict = pipeline.run(packet, decision, cgrf_tier=3)  # Tier 3 requires A+

    assert verdict.escalated
    assert verdict.action in ("need_approval", "block")
    assert verdict.original_guardian_action == "approve"


def test_ags_pipeline_audit_chain_integrity():
    """Test AGS pipeline maintains audit hash chain integrity."""
    audit = AuditLogger()
    audit.start("ags-chain-test")

    pipeline = AGSPipeline(audit=audit)
    packet = _make_packet()
    decision = Decision(action="approve", risk_score=0.10, rationale="ok", policy_refs=[])

    pipeline.run(packet, decision)

    assert audit.verify_chain()
    chain = audit.get_chain_summary()
    assert chain["chain_length"] >= 2  # start + ags.verdict


def test_ags_pipeline_high_risk_deny():
    """Test AGS pipeline denies high-risk blocked events."""
    audit = AuditLogger()
    audit.start("ags-high-risk")

    pipeline = AGSPipeline(audit=audit)
    packet = _make_packet(risk_estimate=0.8, severity="critical")
    decision = Decision(action="block", risk_score=0.85, rationale="blocked", policy_refs=[])

    verdict = pipeline.run(packet, decision, cgrf_tier=2)

    assert verdict.verdict == "DENY"
    assert verdict.action == "block"
    assert not verdict.escalated  # Already blocked by Guardian


# ========== AIS Integration Test ==========

def test_ags_pipeline_with_ais_profile():
    """AGS pipeline uses AIS-backed profiles when available."""
    import tempfile
    import shutil
    from src.ais.engine import AISEngine
    from src.ais.storage import ProfileStore

    tmp = Path(tempfile.mkdtemp())
    try:
        storage = ProfileStore(base_path=tmp / "profiles")
        engine = AISEngine(storage=storage)

        # Create an A-grade profile (1000 + 4000 = 5000 XP)
        profile = engine.get_profile("pipeline_agent")
        profile.add_xp(4000, "promote_to_A")
        storage.save_profile(profile)

        caps = engine.get_caps_profile("pipeline_agent")
        assert caps.grade == CAPSGrade.A

        # Run AGS with the real CAPSProfile
        audit = AuditLogger()
        audit.start("ags-ais-test")
        pipeline = AGSPipeline(audit=audit, caps_profile=caps)

        packet = _make_packet()
        decision = Decision(action="approve", risk_score=0.10, rationale="ok", policy_refs=[])
        verdict = pipeline.run(packet, decision, cgrf_tier=3)

        # A-grade meets tier 3, so GATE-CAPS-TIER should pass
        assert verdict.action == "approve"
        assert not verdict.escalated
    finally:
        shutil.rmtree(tmp)
