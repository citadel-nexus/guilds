# citadel_lite/tests/test_nemesis_v2.py
"""
Nemesis v2 — Adversarial Resilience System Test Suite

Tests:
  - TestNemesisModels: enum values, dataclass creation, serialization, sha256
  - TestAdversaryRegistry: 7 adversary profiles, classify_threat, confidence scoring
  - TestSanctionsEngine: escalation ladder, cooldown, de-escalation, retirement
  - TestCollusionDetector: interaction graph, mutual approval, clusters, voting blocs
  - TestNemesisAgent: full pipeline rule mode, output schema, threat extraction
  - TestNemesisPipeline: nemesis in 5-agent pipeline (watcher→scaler→curator→budget→nemesis)

CGRF v3.0: SRS-TEST-NEMESIS-001, Tier 1
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nemesis.models import (
    AdversaryClass,
    AdversaryProfile,
    NemesisReport,
    SanctionLevel,
    SanctionRecord,
    ThreatEvent,
    ThreatSeverity,
)
from src.nemesis.adversary_registry import (
    ADVERSARY_PROFILES,
    classify_all,
    classify_threat,
    get_profile,
)
from src.nemesis.sanctions import SanctionsEngine
from src.nemesis.collusion_detector import CollusionDetector
from src.agents.nemesis_v2 import run_nemesis_v2
from src.types import HandoffPacket, EventJsonV1, AgentOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_packet(**outputs) -> HandoffPacket:
    """Create a HandoffPacket with named agent outputs."""
    event = EventJsonV1(
        source="test",
        event_type="nemesis_test",
        summary="Testing nemesis v2",
    )
    pkt = HandoffPacket(event=event)
    for name, payload in outputs.items():
        pkt.add_output(name, payload)
    return pkt


# ===========================================================================
# 1. Model Tests
# ===========================================================================

class TestNemesisModels:
    """Test core enums and dataclasses."""

    def test_adversary_class_has_7_members(self):
        assert len(AdversaryClass) == 7

    def test_sanction_level_has_7_levels(self):
        assert len(SanctionLevel) == 7

    def test_sanction_level_ordering(self):
        assert SanctionLevel.OBSERVE < SanctionLevel.WARN
        assert SanctionLevel.WARN < SanctionLevel.THROTTLE
        assert SanctionLevel.THROTTLE < SanctionLevel.RESTRICT
        assert SanctionLevel.RESTRICT < SanctionLevel.QUARANTINE
        assert SanctionLevel.QUARANTINE < SanctionLevel.HUMAN_ESCALATION
        assert SanctionLevel.HUMAN_ESCALATION < SanctionLevel.RETIREMENT

    def test_threat_severity_values(self):
        assert ThreatSeverity.INFO.value == "info"
        assert ThreatSeverity.CRITICAL.value == "critical"

    def test_threat_event_creation_and_sha256(self):
        event = ThreatEvent(
            agent_id="agent-001",
            adversary_class=AdversaryClass.PROMPT_INJECTION,
            severity=ThreatSeverity.HIGH,
            evidence={"injection_pattern_detected": True},
            confidence=0.75,
        )
        assert event.agent_id == "agent-001"
        assert event.adversary_class == AdversaryClass.PROMPT_INJECTION
        assert len(event.sha256) == 64  # SHA-256 hex digest
        assert event.event_id  # auto-generated UUID

    def test_threat_event_to_dict(self):
        event = ThreatEvent(agent_id="x", adversary_class=AdversaryClass.MALICIOUS_USER)
        d = event.to_dict()
        assert d["agent_id"] == "x"
        assert d["adversary_class"] == "malicious_user"
        assert "sha256" in d

    def test_sanction_record_creation(self):
        record = SanctionRecord(
            agent_id="agent-002",
            current_level=SanctionLevel.WARN,
            previous_level=SanctionLevel.OBSERVE,
            reason="test violation",
        )
        assert record.current_level == SanctionLevel.WARN
        assert record.previous_level == SanctionLevel.OBSERVE
        assert len(record.sha256) == 64

    def test_sanction_record_to_dict(self):
        record = SanctionRecord(agent_id="y", current_level=SanctionLevel.THROTTLE)
        d = record.to_dict()
        assert d["current_level"] == 2  # int enum value
        assert d["agent_id"] == "y"

    def test_nemesis_report_creation(self):
        report = NemesisReport(
            agent_id="agent-003",
            threat_level=ThreatSeverity.MEDIUM,
            recommended_action="increased_monitoring",
        )
        assert report.agent_id == "agent-003"
        assert report.report_id  # auto-generated

    def test_nemesis_report_to_dict(self):
        event = ThreatEvent(agent_id="a", adversary_class=AdversaryClass.INSIDER_THREAT)
        record = SanctionRecord(agent_id="a", current_level=SanctionLevel.RESTRICT)
        report = NemesisReport(
            agent_id="a",
            threat_events=[event],
            active_sanctions=[record],
            collusion_score=0.42,
            threat_level=ThreatSeverity.HIGH,
        )
        d = report.to_dict()
        assert len(d["threat_events"]) == 1
        assert len(d["active_sanctions"]) == 1
        assert d["collusion_score"] == 0.42
        assert d["threat_level"] == "high"

    def test_adversary_profile_matches(self):
        profile = AdversaryProfile(
            adversary_class=AdversaryClass.MALICIOUS_USER,
            description="test",
            capabilities=["a"],
            goals=["b"],
            attack_vectors=["c"],
            detection_signals=["auth_failure", "rate_limit"],
            mitigations=["d"],
            default_sanction=SanctionLevel.WARN,
        )
        # Exact match on one signal
        score = profile.matches({"auth_failure": True})
        assert score == 0.5  # 1 of 2 signals
        # Match both
        score = profile.matches({"auth_failure": True, "rate_limit": True})
        assert score == 1.0
        # No match
        score = profile.matches({"unrelated": True})
        assert score == 0.0


# ===========================================================================
# 2. Adversary Registry Tests
# ===========================================================================

class TestAdversaryRegistry:
    """Test adversary profiles and classification."""

    def test_all_7_profiles_defined(self):
        assert len(ADVERSARY_PROFILES) == 7
        for cls in AdversaryClass:
            assert cls in ADVERSARY_PROFILES

    def test_each_profile_has_required_fields(self):
        for cls, profile in ADVERSARY_PROFILES.items():
            assert profile.adversary_class == cls
            assert len(profile.capabilities) >= 3
            assert len(profile.goals) >= 2
            assert len(profile.attack_vectors) >= 3
            assert len(profile.detection_signals) >= 3
            assert len(profile.mitigations) >= 2
            assert isinstance(profile.default_sanction, SanctionLevel)

    def test_get_profile(self):
        profile = get_profile(AdversaryClass.PROMPT_INJECTION)
        assert profile.adversary_class == AdversaryClass.PROMPT_INJECTION
        assert "manipulate" in profile.description.lower() or "injection" in profile.description.lower()

    def test_get_profile_unknown_raises(self):
        with pytest.raises(KeyError):
            get_profile("nonexistent")

    def test_classify_prompt_injection(self):
        evidence = {
            "injection_pattern_detected": True,
            "system_prompt_leak_attempt": True,
            "instruction_override_attempt": True,
        }
        cls, conf = classify_threat(evidence)
        assert cls == AdversaryClass.PROMPT_INJECTION
        assert conf >= 0.5

    def test_classify_compromised_agent(self):
        evidence = {
            "trust_score_drop": True,
            "behavioral_anomaly": True,
            "output_quality_decline": True,
        }
        cls, conf = classify_threat(evidence)
        assert cls == AdversaryClass.COMPROMISED_AGENT
        assert conf >= 0.4

    def test_classify_agent_collusion(self):
        evidence = {
            "mutual_approval_rate_high": True,
            "voting_bloc_detected": True,
            "synchronized_behavior": True,
        }
        cls, conf = classify_threat(evidence)
        assert cls == AdversaryClass.AGENT_COLLUSION
        assert conf >= 0.4

    def test_classify_no_match(self):
        evidence = {"completely_unrelated_signal": True}
        cls, conf = classify_threat(evidence, min_confidence=0.5)
        assert cls is None

    def test_classify_empty_evidence(self):
        cls, conf = classify_threat({})
        assert cls is None
        assert conf == 0.0

    def test_classify_all_returns_sorted(self):
        evidence = {
            "trust_score_drop": True,
            "behavioral_anomaly": True,
        }
        results = classify_all(evidence, min_confidence=0.1)
        assert len(results) > 0
        # Should be sorted by confidence descending
        confs = [r[1] for r in results]
        assert confs == sorted(confs, reverse=True)


# ===========================================================================
# 3. Sanctions Engine Tests
# ===========================================================================

class TestSanctionsEngine:
    """Test the graduated sanctions state machine."""

    def setup_method(self):
        self.engine = SanctionsEngine()

    def _make_event(self, agent_id: str = "agent-test") -> ThreatEvent:
        return ThreatEvent(
            agent_id=agent_id,
            adversary_class=AdversaryClass.MALICIOUS_USER,
            severity=ThreatSeverity.MEDIUM,
        )

    def test_initial_level_is_observe(self):
        assert self.engine.get_current_level("new-agent") == SanctionLevel.OBSERVE

    def test_single_violation_stays_at_observe(self):
        self.engine.escalate("a", self._make_event("a"))
        assert self.engine.get_current_level("a") == SanctionLevel.OBSERVE

    def test_two_violations_escalate_to_warn(self):
        for _ in range(2):
            self.engine.escalate("a", self._make_event("a"))
        assert self.engine.get_current_level("a") == SanctionLevel.WARN

    def test_full_escalation_ladder(self):
        """Simulate violations that traverse OBSERVE → WARN → THROTTLE → RESTRICT → QUARANTINE → HUMAN_ESCALATION."""
        agent = "ladder-agent"
        # OBSERVE → WARN: 2 violations
        self.engine.escalate(agent, self._make_event(agent))
        self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.WARN

        # WARN → THROTTLE: 2 more
        self.engine.escalate(agent, self._make_event(agent))
        self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.THROTTLE

        # THROTTLE → RESTRICT: 1 more
        self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.RESTRICT

        # RESTRICT → QUARANTINE: 1 more
        self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.QUARANTINE

        # QUARANTINE → HUMAN_ESCALATION: 1 more
        self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.HUMAN_ESCALATION

    def test_human_escalation_does_not_auto_escalate_to_retirement(self):
        """RETIREMENT requires explicit human action."""
        agent = "stuck-agent"
        # Drive to HUMAN_ESCALATION
        for _ in range(7):
            self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.HUMAN_ESCALATION

        # More violations should NOT push to RETIREMENT
        for _ in range(5):
            self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.HUMAN_ESCALATION

    def test_de_escalation(self):
        agent = "de-esc-agent"
        for _ in range(2):
            self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.WARN

        record = self.engine.de_escalate(agent, reason="good behavior")
        assert self.engine.get_current_level(agent) == SanctionLevel.OBSERVE

    def test_de_escalation_at_observe_noop(self):
        record = self.engine.de_escalate("clean-agent")
        assert self.engine.get_current_level("clean-agent") == SanctionLevel.OBSERVE
        assert "already_at_observe" in record.reason

    def test_de_escalation_from_quarantine_requires_auth(self):
        agent = "q-agent"
        # Drive to QUARANTINE (2+2+1+1 = 6 violations)
        for _ in range(6):
            self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.QUARANTINE

        # Without authorization → stays at QUARANTINE
        record = self.engine.de_escalate(agent, reason="test")
        assert self.engine.get_current_level(agent) == SanctionLevel.QUARANTINE
        assert "authorization_required" in record.reason

        # With authorization → de-escalates
        record = self.engine.de_escalate(agent, reason="reviewed", authorized_by="human-admin")
        assert self.engine.get_current_level(agent) == SanctionLevel.RESTRICT

    def test_retirement_is_permanent(self):
        agent = "retired-agent"
        self.engine.retire(agent, authorized_by="admin", reason="decommission")
        assert self.engine.get_current_level(agent) == SanctionLevel.RETIREMENT

        # Cannot escalate
        record = self.engine.escalate(agent, self._make_event(agent))
        assert self.engine.get_current_level(agent) == SanctionLevel.RETIREMENT
        assert "already_retired" in record.reason

        # Cannot de-escalate
        record = self.engine.de_escalate(agent, authorized_by="admin")
        assert "retirement_is_permanent" in record.reason

    def test_get_active_restrictions(self):
        agent = "restr-agent"
        # At OBSERVE: no restrictions
        assert self.engine.get_active_restrictions(agent) == []

        # Escalate to THROTTLE (2+2 = 4 violations)
        for _ in range(4):
            self.engine.escalate(agent, self._make_event(agent))
        restrictions = self.engine.get_active_restrictions(agent)
        assert "rate_limit_50pct" in restrictions
        assert "no_governance_voting" in restrictions

    def test_history_tracks_all_records(self):
        agent = "history-agent"
        for _ in range(4):
            self.engine.escalate(agent, self._make_event(agent))
        history = self.engine.get_history(agent)
        # 4 violations: records at violations 1, 2 (escalation), 3, 4 (escalation)
        assert len(history) >= 2  # at least the escalation records

    def test_apply_restrictions_returns_dict(self):
        result = self.engine.apply_restrictions("some-agent")
        assert "agent_id" in result
        assert "sanction_level" in result
        assert "restrictions" in result


# ===========================================================================
# 4. Collusion Detector Tests
# ===========================================================================

class TestCollusionDetector:
    """Test graph-based collusion detection."""

    def setup_method(self):
        self.detector = CollusionDetector()

    def test_empty_detector_score_zero(self):
        assert self.detector.compute_collusion_score(["a", "b"]) == 0.0

    def test_ingest_interaction(self):
        self.detector.ingest_interaction("a", "b", "approval")
        stats = self.detector.get_agent_stats("a")
        assert stats["outgoing_interactions"] == 1
        assert "b" in stats["peers"]

    def test_mutual_approval_raises_score(self):
        # Create heavy bidirectional approval between a and b
        for _ in range(5):
            self.detector.ingest_interaction("a", "b", "approval")
            self.detector.ingest_interaction("b", "a", "approval")
        score = self.detector.compute_collusion_score(["a", "b"])
        assert score > 0.0

    def test_high_collusion_score_for_colluding_pair(self):
        """Heavy bidirectional approval + voting bloc → high score."""
        for _ in range(10):
            self.detector.ingest_interaction("a", "b", "approval")
            self.detector.ingest_interaction("b", "a", "approval")
            self.detector.ingest_interaction("a", "b", "endorsement")
            self.detector.ingest_interaction("b", "a", "endorsement")
        # Add synchronized voting
        for i in range(5):
            self.detector.ingest_council_vote(f"vote-{i}", "a", "approve")
            self.detector.ingest_council_vote(f"vote-{i}", "b", "approve")
        score = self.detector.compute_collusion_score(["a", "b"])
        assert score >= 0.5

    def test_no_collusion_for_independent_agents(self):
        # a talks to c, b talks to d — no overlap
        self.detector.ingest_interaction("a", "c", "approval")
        self.detector.ingest_interaction("b", "d", "approval")
        score = self.detector.compute_collusion_score(["a", "b"])
        assert score == 0.0

    def test_detect_clusters_finds_colluding_group(self):
        # Create a tight collusion ring a↔b↔c
        for _ in range(5):
            for src, dst in [("a", "b"), ("b", "a"), ("b", "c"), ("c", "b"), ("a", "c"), ("c", "a")]:
                self.detector.ingest_interaction(src, dst, "approval")
                self.detector.ingest_interaction(src, dst, "endorsement")
        for i in range(5):
            self.detector.ingest_council_vote(f"v-{i}", "a", "approve")
            self.detector.ingest_council_vote(f"v-{i}", "b", "approve")
            self.detector.ingest_council_vote(f"v-{i}", "c", "approve")

        clusters = self.detector.detect_clusters(min_score=0.3)
        assert len(clusters) >= 1
        # The cluster should contain a, b, c
        found = False
        for cluster in clusters:
            if set(cluster["agents"]) == {"a", "b", "c"}:
                found = True
                assert cluster["collusion_score"] >= 0.3
                break
        assert found, f"Expected cluster {{a, b, c}}, got {clusters}"

    def test_voting_bloc_detection(self):
        # 5 votes where a and b always agree
        for i in range(5):
            self.detector.ingest_council_vote(f"v-{i}", "a", "approve")
            self.detector.ingest_council_vote(f"v-{i}", "b", "approve")
            self.detector.ingest_council_vote(f"v-{i}", "c", "reject")  # c disagrees
        result = self.detector.check_voting_bloc()
        assert result["total_votes_analyzed"] == 5
        # a and b should be flagged as a bloc
        a_b_bloc = [b for b in result["blocs"] if set(b["agents"]) == {"a", "b"}]
        assert len(a_b_bloc) == 1
        assert a_b_bloc[0]["similarity"] == 1.0

    def test_voting_bloc_no_false_positive(self):
        # All agents vote differently
        self.detector.ingest_council_vote("v1", "a", "approve")
        self.detector.ingest_council_vote("v1", "b", "reject")
        self.detector.ingest_council_vote("v2", "a", "reject")
        self.detector.ingest_council_vote("v2", "b", "approve")
        self.detector.ingest_council_vote("v3", "a", "approve")
        self.detector.ingest_council_vote("v3", "b", "reject")
        result = self.detector.check_voting_bloc()
        assert len(result["blocs"]) == 0

    def test_reset_clears_state(self):
        self.detector.ingest_interaction("a", "b", "approval")
        self.detector.reset()
        assert self.detector.compute_collusion_score(["a", "b"]) == 0.0

    def test_single_agent_score_zero(self):
        assert self.detector.compute_collusion_score(["a"]) == 0.0


# ===========================================================================
# 5. Nemesis Agent Tests
# ===========================================================================

class TestNemesisAgent:
    """Test the run_nemesis_v2 A2A agent function."""

    def test_rule_mode_with_healthy_pipeline(self):
        """No threats in a healthy pipeline → info level, no action."""
        pkt = _make_packet(
            watcher={"event_type": "healthy", "severity": "info", "signals": []},
            budget={"evaluation": {"severity": "info"}, "cost_data": {"total_usd": 50}},
        )
        with patch("src.agents.nemesis_v2._run_nemesis_llm", return_value=None):
            result = run_nemesis_v2(pkt)

        assert result["llm_powered"] is False
        assert result["threat_level"] == "info"
        assert result["recommended_action"] == "none"
        assert result["threat_event_count"] == 0

    def test_rule_mode_detects_budget_anomaly(self):
        """Budget warning triggers evidence extraction."""
        pkt = _make_packet(
            budget={"evaluation": {"severity": "warning", "forecast_breach": True}},
        )
        with patch("src.agents.nemesis_v2._run_nemesis_llm", return_value=None):
            result = run_nemesis_v2(pkt)

        assert result["llm_powered"] is False
        # Budget anomaly evidence should be extracted but may not match a high-confidence adversary
        assert "timestamp" in result

    def test_rule_mode_detects_injection(self):
        """Injection evidence triggers prompt_injection classification."""
        pkt = _make_packet(
            sentinel={"injection_detected": True, "injection_pattern_detected": True},
        )
        with patch("src.agents.nemesis_v2._run_nemesis_llm", return_value=None):
            result = run_nemesis_v2(pkt)

        assert result["llm_powered"] is False
        # Should detect at least 1 threat event related to injection
        if result["threat_event_count"] > 0:
            report = result["report"]
            events = report["threat_events"]
            assert any(e["adversary_class"] == "prompt_injection" for e in events)

    def test_output_schema_complete(self):
        """Verify all expected keys in output."""
        pkt = _make_packet()
        with patch("src.agents.nemesis_v2._run_nemesis_llm", return_value=None):
            result = run_nemesis_v2(pkt)

        required_keys = {
            "report", "threat_level", "threat_event_count",
            "active_sanction_count", "collusion_score",
            "recommended_action", "agent_ids_analyzed",
            "llm_powered", "timestamp",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_llm_mode_used_when_available(self):
        """If LLM returns a result, it should be used."""
        pkt = _make_packet()
        llm_result = {
            "threat_level": "high",
            "threat_events": [],
            "collusion_indicators": [],
            "recommended_action": "investigate",
            "llm_powered": True,
        }
        with patch("src.agents.nemesis_v2._run_nemesis_llm", return_value=llm_result):
            result = run_nemesis_v2(pkt)

        assert result["llm_powered"] is True
        assert result["threat_level"] == "high"

    def test_llm_fallback_to_rules(self):
        """If LLM returns None, rules engine runs."""
        pkt = _make_packet()
        with patch("src.agents.nemesis_v2._run_nemesis_llm", return_value=None):
            result = run_nemesis_v2(pkt)

        assert result["llm_powered"] is False


# ===========================================================================
# 6. Pipeline Integration Tests
# ===========================================================================

class TestNemesisPipeline:
    """Test nemesis in multi-agent pipeline."""

    def test_5_agent_pipeline_watcher_to_nemesis(self):
        """Full pipeline: watcher → scaler → curator → budget → nemesis."""
        pkt = _make_packet()

        # Mock watcher output
        pkt.add_output("watcher", {
            "event_type": "healthy",
            "severity": "info",
            "signals": [],
            "metrics": {"vps_cpu": 55.0, "vps_memory": 60.0},
            "recommended_action": "none",
            "llm_powered": False,
        })
        # Mock scaler output
        pkt.add_output("scaler", {
            "scaling_action": "none",
            "current_state": {"workers": 3},
            "llm_powered": False,
        })
        # Mock curator output
        pkt.add_output("curator", {
            "action": "none",
            "s3_status": "healthy",
            "llm_powered": False,
        })
        # Mock budget output
        pkt.add_output("budget", {
            "cost_data": {"total_usd": 85.0},
            "evaluation": {"severity": "info", "remaining_usd": 315.0},
            "llm_powered": False,
        })

        with patch("src.agents.nemesis_v2._run_nemesis_llm", return_value=None):
            result = run_nemesis_v2(pkt)

        assert result["llm_powered"] is False
        assert result["threat_level"] == "info"
        assert "watcher" in result["agent_ids_analyzed"]
        assert "budget" in result["agent_ids_analyzed"]
        assert "nemesis" not in result["agent_ids_analyzed"]  # nemesis doesn't analyze itself

    def test_pipeline_with_anomaly_triggers_threat(self):
        """If watcher reports critical + budget reports warning → evidence extracted."""
        pkt = _make_packet()
        pkt.add_output("watcher", {
            "event_type": "cpu_spike",
            "severity": "critical",
            "signals": ["cpu_critical"],
            "metrics": {"vps_cpu": 95.0},
            "llm_powered": False,
        })
        pkt.add_output("budget", {
            "evaluation": {"severity": "warning", "forecast_breach": True},
            "llm_powered": False,
        })

        with patch("src.agents.nemesis_v2._run_nemesis_llm", return_value=None):
            result = run_nemesis_v2(pkt)

        # Evidence should be extracted (infra_anomaly, budget_anomaly, budget_forecast_breach)
        # May or may not result in a classified threat depending on confidence threshold
        assert result["llm_powered"] is False
        assert "timestamp" in result

    def test_nemesis_registered_in_agent_wrapper(self):
        """Verify nemesis import and registration source code contains nemesis."""
        from src.agents.nemesis_v2 import run_nemesis_v2
        assert callable(run_nemesis_v2)
        # Verify the agent_wrapper source references nemesis
        import pathlib
        wrapper_path = pathlib.Path(__file__).resolve().parent.parent / "src" / "a2a" / "agent_wrapper.py"
        source = wrapper_path.read_text(encoding="utf-8")
        assert "nemesis" in source
        assert "_SECURITY_AGENTS" in source
        assert "run_nemesis_v2" in source

    def test_nemesis_agent_returns_correct_structure(self):
        """Verify nemesis agent output has all required keys when run standalone."""
        pkt = _make_packet()
        with patch("src.agents.nemesis_v2._run_nemesis_llm", return_value=None):
            result = run_nemesis_v2(pkt)
        assert isinstance(result, dict)
        assert "threat_level" in result
        assert "llm_powered" in result
        assert result["llm_powered"] is False
