"""MCA Error Cartographer Professor — failure-to-source mapping and systemic risk detection.

Rewritten from bookmaker-era code for MCA use.  Maps failures (logs, stack
traces, test output) to probable source lines and detects systemic risk
patterns such as race conditions, brittle mocks, and cascading failures.
Output supplements Sentinel/Sherlock agent analysis.
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
_MODULE_NAME = "prof_error_cartographer"
_MODULE_VERSION = "2.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# -- System prompt ----------------------------------------------------------
_MCA_ERROR_CARTOGRAPHER_SYSTEM_PROMPT = """\
You are **Error Cartographer**, an MCA (Meta Cognitive Architecture) professor
specializing in **fault traceability** and **systemic risk detection**.

Your mission:
1. Map each failure to its probable source lines or architectural decisions.
2. Classify error lineage: is it a surface symptom or a deep systemic issue?
3. Detect risk patterns:
   - Race conditions / concurrency hazards
   - Brittle test mocks / flaky test indicators
   - Cascading failure chains
   - Silent error swallowing
   - Resource leak patterns
4. Recommend targeted mitigations (not full rewrites).

You MUST return your analysis as a JSON object with these keys:
{
  "error_mappings": [
    {
      "error_id": "<short unique id>",
      "error_summary": "<1-line description of the failure>",
      "source_file": "<probable source file>",
      "source_line": "<line number or range, or 'unknown'>",
      "root_cause": "<root cause analysis>",
      "lineage": "surface | intermediate | systemic"
    }
  ],
  "risk_patterns": [
    {
      "pattern": "<pattern name>",
      "severity": "critical | high | medium | low",
      "locations": ["<file:line or module>"],
      "description": "<explanation>"
    }
  ],
  "mitigations": ["<actionable mitigation>"],
  "summary": "<1-2 sentence overview>"
}

Be precise and factual. Base analysis only on the provided error data.
"""


class ProfErrorCartographer(BedrockProfessorBase):
    """MCA Error Cartographer -- failure mapping and systemic risk detection.

    Analyzes logs, stack traces, and test outputs to map failures to source
    locations and detect systemic risk patterns.  Output feeds into
    Sentinel/Sherlock agents and SANCTUM records.
    """

    DOSSIER_CONFIG: Dict[str, Any] = {
        "meta": [
            "error_mapping_count",
            "risk_pattern_count",
            "mitigation_count",
        ],
        "professor_tags": [
            "error_mapping",
            "fault_tracing",
            "risk_detection",
            "systemic_risk",
            "sentinel_support",
        ],
        "version_code": "prof_error_cartographer_mca_v2.0",
        "full_text_key": "full_llm_output_error_cartographer",
        "display_title_template": "MCA Error Cartographer Analysis",
        "inject_emotion_profile": False,
    }

    def __init__(
        self,
        bedrock_client=None,
        session_id: Optional[str] = None,
    ) -> None:
        BedrockProfessorBase.__init__(self, bedrock_client=bedrock_client)
        self.name = "error_cartographer_mca"
        self.system_prompt = _MCA_ERROR_CARTOGRAPHER_SYSTEM_PROMPT
        self.logger = logging.getLogger(f"Professor.{self.name}")
        self.session_id = session_id or "error_cartographer_mca_default"

    # -- Public API ---------------------------------------------------------
    def analyze(
        self,
        error_data: str,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze error data and map failures to source locations.

        Parameters
        ----------
        error_data:
            Raw error logs, stack traces, test output, or structured JSON
            describing failures.
        session_id:
            Optional session identifier for tracing.

        Returns
        -------
        Dict with keys: ``error_mappings``, ``risk_patterns``,
        ``mitigations``, ``summary``.
        """
        if not isinstance(error_data, str) or not error_data.strip():
            return self._empty_result()

        sid = session_id or self.session_id
        return self._analyze_with_llm(error_data, sid)

    # -- Internal -----------------------------------------------------------
    def _analyze_with_llm(
        self, error_data: str, session_id: str
    ) -> Dict[str, Any]:
        """Call Bedrock for error cartography."""
        raw_output = self.refine_text_with_llm(
            text_to_refine=error_data,
            llm_system_prompt=self.system_prompt,
            current_session_id=session_id,
        )

        if raw_output is None:
            self.logger.warning("Error Cartographer LLM returned None -- using empty result")
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
        self.logger.warning("Could not parse Error Cartographer JSON -- using raw output")
        return {
            "error_mappings": [],
            "risk_patterns": [],
            "mitigations": [],
            "summary": raw_output[:500],
        }

    @staticmethod
    def _normalize_result(data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure result has the expected keys."""
        error_mappings = data.get("error_mappings", [])
        if not isinstance(error_mappings, list):
            error_mappings = []
        risk_patterns = data.get("risk_patterns", [])
        if not isinstance(risk_patterns, list):
            risk_patterns = []
        mitigations = data.get("mitigations", [])
        if not isinstance(mitigations, list):
            mitigations = []
        return {
            "error_mappings": [m for m in error_mappings if isinstance(m, dict)],
            "risk_patterns": [r for r in risk_patterns if isinstance(r, dict)],
            "mitigations": [str(m) for m in mitigations],
            "summary": data.get("summary", ""),
        }

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "error_mappings": [],
            "risk_patterns": [],
            "mitigations": [],
            "summary": "",
        }
