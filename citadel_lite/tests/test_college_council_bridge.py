# citadel_lite/tests/test_college_council_bridge.py
"""
Tests for College Bridge and Council Bridge agents.

Verifies:
- College code analysis catches security issues
- College quality scoring is reasonable
- Council 4-seat SAKE deliberation produces correct verdicts
- Council blocks code with critical issues
- Both agents handle missing data gracefully

CGRF v3.0: SRS-TEST-BRIDGE-001, Tier 1
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

CNWB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CNWB_ROOT))

from src.agents.college_bridge import run_college_bridge, _analyze_code_rules
from src.agents.council_bridge import run_council_bridge, _deliberate_rules


class TestCollegeCodeAnalysis:
    """Tests for rule-based code analysis."""

    def test_clean_code_high_quality(self):
        code = '"""\nModule docstring.\n"""\nimport logging\nlogger = logging.getLogger(__name__)\n\ndef hello() -> str:\n    return "world"\n'
        result = _analyze_code_rules(code)
        assert result["quality_score"] >= 0.8
        assert result["critical_count"] == 0

    def test_eval_detected(self):
        code = 'result = eval(user_input)\n'
        result = _analyze_code_rules(code)
        assert result["high_count"] >= 1
        assert any(i["type"] == "security" for i in result["issues"])

    def test_exec_detected(self):
        code = 'exec(code_string)\n'
        result = _analyze_code_rules(code)
        assert any("exec" in i["message"] for i in result["issues"])

    def test_hardcoded_password_detected(self):
        code = 'password = "hunter2"\nprint(password)\n'
        result = _analyze_code_rules(code)
        assert result["critical_count"] >= 1

    def test_shell_injection_detected(self):
        code = 'subprocess.call("rm -rf /", shell=True)\n'
        result = _analyze_code_rules(code)
        assert result["critical_count"] >= 1

    def test_missing_docstring_flagged(self):
        code = 'import os\ndef foo():\n    pass\n'
        result = _analyze_code_rules(code)
        assert not result["has_docstring"]
        assert any(i["type"] == "architecture" for i in result["issues"])

    def test_quality_score_degrades_with_issues(self):
        clean = '"""\nDoc.\n"""\ndef foo() -> int:\n    return 1\n'
        dirty = 'password = "x"\neval(y)\nexec(z)\n'
        clean_result = _analyze_code_rules(clean)
        dirty_result = _analyze_code_rules(dirty)
        assert clean_result["quality_score"] > dirty_result["quality_score"]


class TestCollegeBridgeAgent:
    """Tests for the College bridge A2A agent."""

    def test_analyzes_generated_code(self, packet_with_f993_output):
        result = run_college_bridge(packet_with_f993_output)
        assert result["analyzed"] is True
        assert result["language"] == "python"
        assert result["quality_score"] > 0
        assert "systems" in result["professors_consulted"] or len(result["professors_consulted"]) > 0

    def test_detects_security_issues(self, packet_with_security_issues):
        result = run_college_bridge(packet_with_security_issues)
        assert result["analyzed"] is True
        assert result["critical_count"] > 0
        assert result["quality_score"] < 0.5

    def test_handles_no_code(self):
        from src.types import EventJsonV1, HandoffPacket
        packet = HandoffPacket(event=EventJsonV1(event_type="test"))
        result = run_college_bridge(packet)
        assert result["analyzed"] is False

    def test_returns_duration(self, packet_with_f993_output):
        result = run_college_bridge(packet_with_f993_output)
        assert "duration_ms" in result
        assert result["duration_ms"] >= 0


class TestCouncilDeliberation:
    """Tests for rule-based Council deliberation."""

    def test_clean_context_allows(self):
        context = {
            "generation_valid": True,
            "generation_mode": "template",
            "quality_score": 0.9,
            "issue_count": 0,
            "critical_count": 0,
            "has_security_issues": False,
            "line_count": 50,
        }
        result = _deliberate_rules(context)
        assert result["decision"] == "ALLOW"
        assert result["confidence"] > 0.7

    def test_invalid_generation_denied(self):
        context = {"generation_valid": False}
        result = _deliberate_rules(context)
        assert result["decision"] == "DENY"

    def test_low_quality_escalated(self):
        context = {
            "generation_valid": True,
            "quality_score": 0.55,
            "critical_count": 0,
            "has_security_issues": False,
            "line_count": 20,
        }
        result = _deliberate_rules(context)
        assert result["decision"] == "ESCALATE"

    def test_security_issues_denied(self):
        context = {
            "generation_valid": True,
            "quality_score": 0.3,
            "critical_count": 2,
            "has_security_issues": True,
            "line_count": 10,
        }
        result = _deliberate_rules(context)
        assert result["decision"] == "DENY"

    def test_large_change_escalated(self):
        context = {
            "generation_valid": True,
            "quality_score": 0.9,
            "critical_count": 0,
            "has_security_issues": False,
            "line_count": 600,
        }
        result = _deliberate_rules(context)
        assert result["decision"] == "ESCALATE"

    def test_all_four_seats_vote(self):
        context = {"generation_valid": True, "quality_score": 0.9}
        result = _deliberate_rules(context)
        assert "reason" in result["seat_votes"]
        assert "axiom" in result["seat_votes"]
        assert "kindness" in result["seat_votes"]
        assert "equity" in result["seat_votes"]

    def test_dissent_recorded(self):
        context = {
            "generation_valid": True,
            "quality_score": 0.55,
            "critical_count": 0,
            "has_security_issues": False,
            "line_count": 20,
        }
        result = _deliberate_rules(context)
        # Axiom escalates but decision is ESCALATE, so seats that voted ALLOW are dissent
        assert isinstance(result["dissent"], list)


class TestCouncilBridgeAgent:
    """Tests for the Council bridge A2A agent."""

    def test_deliberates_on_valid_packet(self, packet_with_f993_output):
        result = run_council_bridge(packet_with_f993_output)
        assert result["deliberated"] is True
        assert result["decision"] in ("ALLOW", "ESCALATE", "DENY", "DEFER")
        assert "seat_votes" in result

    def test_handles_no_data(self):
        from src.types import EventJsonV1, HandoffPacket
        packet = HandoffPacket(event=EventJsonV1(event_type="test"))
        result = run_council_bridge(packet)
        assert result["deliberated"] is False
        assert result["decision"] == "DEFER"

    def test_blocks_security_issues(self, packet_with_security_issues):
        # First run college to populate quality data
        college_result = run_college_bridge(packet_with_security_issues)
        packet_with_security_issues.add_output("college", college_result)

        result = run_council_bridge(packet_with_security_issues)
        assert result["deliberated"] is True
        assert result["decision"] in ("DENY", "ESCALATE")

    def test_returns_context_used(self, packet_with_f993_output):
        result = run_council_bridge(packet_with_f993_output)
        assert "context_used" in result
        assert result["context_used"]["intent_source"] == "github_issue"

    def test_returns_duration(self, packet_with_f993_output):
        result = run_council_bridge(packet_with_f993_output)
        assert "duration_ms" in result


class TestAutodevPipelineIntegration:
    """Integration tests for College→Council in the autodev pipeline."""

    def test_college_then_council_flow(self, packet_with_f993_output):
        """College analysis feeds into Council deliberation."""
        # Step 1: College analyzes
        college_result = run_college_bridge(packet_with_f993_output)
        packet_with_f993_output.add_output("college", college_result)

        # Step 2: Council deliberates with College context
        council_result = run_council_bridge(packet_with_f993_output)

        assert college_result["analyzed"] is True
        assert council_result["deliberated"] is True
        # Clean code should be allowed
        assert council_result["decision"] == "ALLOW"

    def test_dirty_code_blocked_in_pipeline(self, packet_with_security_issues):
        """Security issues detected by College should cause Council to block."""
        college_result = run_college_bridge(packet_with_security_issues)
        packet_with_security_issues.add_output("college", college_result)

        council_result = run_council_bridge(packet_with_security_issues)

        assert college_result["critical_count"] > 0
        assert council_result["decision"] in ("DENY", "ESCALATE")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
