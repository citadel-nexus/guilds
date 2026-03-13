"""MCA Code Ethicist Professor — governance verification and bias detection.

Rewritten from bookmaker-era code for MCA use.  Evaluates code and proposals
for ethical concerns (bias, fairness, surveillance), governance pattern
compliance, and safeguard gaps.  Functions as the SANCTUM governance
verification layer alongside Government professor's CAPS checks.
Uses AWS Bedrock via ``BedrockProfessorBase``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.mca.professors.bedrock_adapter import BedrockProfessorBase

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "prof_code_ethicist"
_MODULE_VERSION = "2.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# -- System prompt ----------------------------------------------------------
_MCA_ETHICIST_SYSTEM_PROMPT = """\
You are **Code Ethicist**, an MCA (Meta Cognitive Architecture) professor
specializing in **computational ethics**, **bias detection**, and
**algorithmic governance**.

Your mission:
1. Evaluate code and proposals for ethical concerns:
   - Bias in data handling, scoring, or ranking logic
   - Fairness issues in user-facing features
   - Privacy and surveillance risks
   - Potential for misuse or abuse
2. Assess governance pattern compliance:
   - Audit trail completeness
   - Decision transparency
   - Override safeguards
   - Data retention policies
3. Recommend specific governance safeguards.
4. Provide a governance verdict for SANCTUM recording.

You MUST return your analysis as a JSON object with these keys:
{
  "ethical_concerns": [
    {
      "concern_id": "<short unique id>",
      "category": "bias | fairness | privacy | misuse | governance",
      "severity": "critical | high | medium | low",
      "description": "<what the concern is>",
      "location": "<file, module, or proposal affected>",
      "recommendation": "<specific remediation>"
    }
  ],
  "governance_assessment": {
    "audit_trail": "compliant | partial | missing",
    "decision_transparency": "compliant | partial | missing",
    "override_safeguards": "compliant | partial | missing",
    "overall_verdict": "pass | conditional_pass | fail"
  },
  "safeguard_recommendations": ["<specific safeguard>"],
  "summary": "<1-2 sentence overview>"
}

Be precise and factual. Base analysis only on the provided data.
"""


class ProfCodeEthicist(BedrockProfessorBase):
    """MCA Code Ethicist -- governance verification and bias detection.

    Evaluates code and proposals for ethical concerns and governance
    compliance.  Provides a governance verdict that is recorded in
    SANCTUM alongside Government CAPS decisions.
    """

    DOSSIER_CONFIG: Dict[str, Any] = {
        "meta": [
            "ethical_concern_count",
            "governance_verdict",
            "safeguard_count",
        ],
        "professor_tags": [
            "ethics",
            "bias_detection",
            "governance",
            "sanctum",
            "compliance",
        ],
        "version_code": "prof_code_ethicist_mca_v2.0",
        "full_text_key": "full_llm_output_ethicist",
        "display_title_template": "MCA Code Ethicist Assessment",
        "inject_emotion_profile": False,
    }

    def __init__(
        self,
        bedrock_client=None,
        session_id: Optional[str] = None,
    ) -> None:
        BedrockProfessorBase.__init__(self, bedrock_client=bedrock_client)
        self.name = "code_ethicist_mca"
        self.system_prompt = _MCA_ETHICIST_SYSTEM_PROMPT
        self.logger = logging.getLogger(f"Professor.{self.name}")
        self.session_id = session_id or "ethicist_mca_default"

    # -- Public API ---------------------------------------------------------
    def analyze(
        self,
        input_data: str,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate code or proposals for ethical concerns and governance.

        Parameters
        ----------
        input_data:
            Source code, proposal JSON, or policy description to evaluate.
        session_id:
            Optional session identifier for tracing.

        Returns
        -------
        Dict with keys: ``ethical_concerns``, ``governance_assessment``,
        ``safeguard_recommendations``, ``summary``.
        """
        if not isinstance(input_data, str) or not input_data.strip():
            return self._empty_result()

        sid = session_id or self.session_id
        return self._analyze_with_llm(input_data, sid)

    # -- Internal -----------------------------------------------------------
    def _analyze_with_llm(
        self, input_data: str, session_id: str
    ) -> Dict[str, Any]:
        """Call Bedrock for ethical analysis."""
        raw_output = self.refine_text_with_llm(
            text_to_refine=input_data,
            llm_system_prompt=self.system_prompt,
            current_session_id=session_id,
        )

        if raw_output is None:
            self.logger.warning("Ethicist LLM returned None -- using empty result")
            return self._empty_result()

        return self._parse_output(raw_output)

    def _parse_output(self, raw_output: str) -> Dict[str, Any]:
        """Parse LLM JSON output into structured dict."""
        # Try direct JSON parse
        try:
            data = json.loads(raw_output)
            if isinstance(data, dict):
                return self._normalize_result(data)
        except json.JSONDecodeError:
            pass

        # Fallback: extract JSON block from markdown
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_output)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict):
                    return self._normalize_result(data)
            except json.JSONDecodeError:
                pass

        # Last resort: return raw as summary
        self.logger.warning("Could not parse Ethicist JSON -- using raw output")
        return {
            "ethical_concerns": [],
            "governance_assessment": self._default_governance(),
            "safeguard_recommendations": [],
            "summary": raw_output[:500],
        }

    @staticmethod
    def _normalize_result(data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure result has the expected keys."""
        concerns = data.get("ethical_concerns", [])
        if not isinstance(concerns, list):
            concerns = []
        governance = data.get("governance_assessment", {})
        if not isinstance(governance, dict):
            governance = ProfCodeEthicist._default_governance()
        safeguards = data.get("safeguard_recommendations", [])
        if not isinstance(safeguards, list):
            safeguards = []
        return {
            "ethical_concerns": [c for c in concerns if isinstance(c, dict)],
            "governance_assessment": governance,
            "safeguard_recommendations": [str(s) for s in safeguards],
            "summary": data.get("summary", ""),
        }

    @staticmethod
    def _default_governance() -> Dict[str, str]:
        return {
            "audit_trail": "missing",
            "decision_transparency": "missing",
            "override_safeguards": "missing",
            "overall_verdict": "fail",
        }

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "ethical_concerns": [],
            "governance_assessment": ProfCodeEthicist._default_governance(),
            "safeguard_recommendations": [],
            "summary": "",
        }
