"""Tests for MCA ProfCodeEthicist (MS-6).

Covers:
  - analyze() with mock Bedrock (JSON, markdown-wrapped JSON, None)
  - Empty/invalid input handling
  - Governance assessment defaults
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest

from src.mca.professors.prof_code_ethicist import ProfCodeEthicist

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_prof_code_ethicist"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_SAMPLE_CODE = """\
class UserScoring:
    def calculate_score(self, user):
        # Score based on location and purchase history
        base = user.purchases * 10
        if user.country in ["US", "UK", "JP"]:
            base *= 1.5  # Premium markets
        return base
"""

_LLM_JSON_RESPONSE = """{
  "ethical_concerns": [
    {
      "concern_id": "EC1",
      "category": "bias",
      "severity": "medium",
      "description": "Geographic bias in scoring favors specific countries",
      "location": "UserScoring.calculate_score",
      "recommendation": "Use market-tier configuration instead of hardcoded countries"
    }
  ],
  "governance_assessment": {
    "audit_trail": "missing",
    "decision_transparency": "partial",
    "override_safeguards": "missing",
    "overall_verdict": "conditional_pass"
  },
  "safeguard_recommendations": [
    "Add audit logging for score calculations",
    "Make country multipliers configurable via config file"
  ],
  "summary": "Geographic bias detected in user scoring with missing audit trail"
}"""

_LLM_MARKDOWN_RESPONSE = """Assessment:

```json
{
  "ethical_concerns": [
    {
      "concern_id": "EC2",
      "category": "fairness",
      "severity": "low",
      "description": "Minor fairness issue",
      "location": "module",
      "recommendation": "Review"
    }
  ],
  "governance_assessment": {
    "audit_trail": "compliant",
    "decision_transparency": "compliant",
    "override_safeguards": "compliant",
    "overall_verdict": "pass"
  },
  "safeguard_recommendations": [],
  "summary": "Minor issue only"
}
```
"""


class TestProfCodeEthicist:
    """Tests for ProfCodeEthicist."""

    def _make_prof(self, llm_return: Optional[str] = None) -> ProfCodeEthicist:
        """Create professor with mocked Bedrock."""
        mock_bedrock = MagicMock()
        mock_bedrock.is_available.return_value = llm_return is not None

        if llm_return is not None:
            resp = MagicMock()
            resp.success = True
            resp.content = llm_return
            resp.input_tokens = 100
            resp.output_tokens = 50
            resp.latency_ms = 200
            mock_bedrock.invoke.return_value = resp
        else:
            resp = MagicMock()
            resp.success = False
            resp.content = None
            resp.error = "unavailable"
            mock_bedrock.invoke.return_value = resp

        return ProfCodeEthicist(bedrock_client=mock_bedrock)

    def test_analyze_with_json_response(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(_SAMPLE_CODE)

        assert len(result["ethical_concerns"]) == 1
        assert result["ethical_concerns"][0]["category"] == "bias"
        assert result["ethical_concerns"][0]["severity"] == "medium"
        assert result["governance_assessment"]["overall_verdict"] == "conditional_pass"
        assert len(result["safeguard_recommendations"]) == 2
        assert "bias" in result["summary"].lower()

    def test_analyze_with_markdown_response(self) -> None:
        prof = self._make_prof(_LLM_MARKDOWN_RESPONSE)
        result = prof.analyze(_SAMPLE_CODE)

        assert len(result["ethical_concerns"]) == 1
        assert result["governance_assessment"]["overall_verdict"] == "pass"

    def test_analyze_llm_unavailable(self) -> None:
        prof = self._make_prof(None)
        result = prof.analyze(_SAMPLE_CODE)

        assert result["ethical_concerns"] == []
        assert result["governance_assessment"]["overall_verdict"] == "fail"
        assert result["safeguard_recommendations"] == []

    def test_analyze_empty_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze("")

        assert result == prof._empty_result()

    def test_analyze_invalid_input(self) -> None:
        prof = self._make_prof(_LLM_JSON_RESPONSE)
        result = prof.analyze(123)  # type: ignore[arg-type]

        assert result == prof._empty_result()

    def test_unparseable_llm_output(self) -> None:
        prof = self._make_prof("Not valid JSON output")
        result = prof.analyze(_SAMPLE_CODE)

        assert result["ethical_concerns"] == []
        assert result["governance_assessment"]["overall_verdict"] == "fail"
        assert "Not valid JSON" in result["summary"]

    def test_default_governance(self) -> None:
        defaults = ProfCodeEthicist._default_governance()
        assert defaults["audit_trail"] == "missing"
        assert defaults["overall_verdict"] == "fail"

    def test_cgrf_metadata(self) -> None:
        from src.mca.professors import prof_code_ethicist as mod

        assert mod._MODULE_NAME == "prof_code_ethicist"
        assert mod._CGRF_TIER == 1
