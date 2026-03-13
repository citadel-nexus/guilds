"""MCA Code Fixer Professor — synthesizes fixes from multiple analysis results.

Rewritten from bookmaker-era code for MCA use.  Receives analysis outputs
from Archeologist, Compiler, Error Cartographer and Ethicist professors,
then synthesizes minimal, high-value corrections as diff patches, JSON
remediation plans, or structured YAML patches.
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
_MODULE_NAME = "prof_code_fixer"
_MODULE_VERSION = "2.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# -- System prompt ----------------------------------------------------------
_MCA_FIXER_SYSTEM_PROMPT = """\
You are **Code Fixer**, an MCA (Meta Cognitive Architecture) professor
specializing in **synthesizing targeted fixes** from multiple code analyses.

You receive prior analysis outputs from these MCA professors:
- Code Archeologist (design patterns, anti-patterns, architecture notes)
- Code Compiler (ENUM/function/schema/dependency extraction, complexity tags)
- Error Cartographer (failure-to-source mapping, systemic risk patterns)
- Code Ethicist (governance concerns, bias detection, safeguard gaps)

Your mission:
1. Identify the HIGHEST-VALUE corrections based on the combined analyses.
2. Propose minimal, surgical fixes -- do NOT rewrite entire modules.
3. Each fix must include a clear rationale linking back to the analysis source.
4. Prefer code-level fixes over documentation-only changes.

You MUST return your output as a JSON object with these keys:
{
  "fixes": [
    {
      "fix_id": "<unique short id>",
      "target_file": "<file path or module>",
      "fix_type": "diff_patch | yaml_patch | json_plan | code_block",
      "severity": "critical | high | medium | low",
      "description": "<what this fix does>",
      "rationale": "<why, citing which professor analysis>",
      "patch": "<the actual fix content>"
    }
  ],
  "summary": "<1-2 sentence overview of all proposed fixes>",
  "risk_notes": ["<any risks or caveats>"]
}

Be precise and factual. Base fixes only on the provided analyses.
"""


class ProfCodeFixer(BedrockProfessorBase):
    """MCA Code Fixer -- multi-analysis fix synthesis.

    Consumes outputs from Archeologist, Compiler, Error Cartographer, and
    Ethicist professors to produce targeted remediation plans that
    ``proposals/executor.py`` can apply.
    """

    DOSSIER_CONFIG: Dict[str, Any] = {
        "meta": [
            "fix_count",
            "critical_count",
            "risk_note_count",
        ],
        "professor_tags": [
            "code_fix",
            "remediation",
            "synthesis",
            "patch",
            "executor",
        ],
        "version_code": "prof_code_fixer_mca_v2.0",
        "full_text_key": "full_llm_output_fixer",
        "display_title_template": "MCA Code Fixer Synthesis",
        "inject_emotion_profile": False,
    }

    def __init__(
        self,
        bedrock_client=None,
        session_id: Optional[str] = None,
    ) -> None:
        BedrockProfessorBase.__init__(self, bedrock_client=bedrock_client)
        self.name = "code_fixer_mca"
        self.system_prompt = _MCA_FIXER_SYSTEM_PROMPT
        self.logger = logging.getLogger(f"Professor.{self.name}")
        self.session_id = session_id or "fixer_mca_default"

    # -- Public API ---------------------------------------------------------
    def analyze(
        self,
        analysis_inputs: Dict[str, Any],
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synthesize fixes from multiple professor analyses.

        Parameters
        ----------
        analysis_inputs:
            Dict containing any combination of:
            - ``archeologist``: output from ProfCodeArcheologist
            - ``compiler``: output from ProfCodeCompiler
            - ``error_cartographer``: output from ProfErrorCartographer
            - ``ethicist``: output from ProfCodeEthicist
            - ``code_text``: optional raw source code for context
        session_id:
            Optional session identifier for tracing.

        Returns
        -------
        Dict with keys: ``fixes``, ``summary``, ``risk_notes``.
        """
        if not isinstance(analysis_inputs, dict):
            return self._empty_result()

        sid = session_id or self.session_id
        user_message = self._build_user_message(analysis_inputs)

        if not user_message.strip():
            return self._empty_result()

        return self._synthesize_with_llm(user_message, sid)

    # -- Internal -----------------------------------------------------------
    def _build_user_message(self, inputs: Dict[str, Any]) -> str:
        """Assemble the user message from available analyses."""
        sections: List[str] = []

        if inputs.get("archeologist"):
            sections.append(
                "## Code Archeologist Analysis\n"
                + json.dumps(inputs["archeologist"], indent=2, ensure_ascii=False)
            )

        if inputs.get("compiler"):
            sections.append(
                "## Code Compiler Analysis\n"
                + json.dumps(inputs["compiler"], indent=2, ensure_ascii=False)
            )

        if inputs.get("error_cartographer"):
            sections.append(
                "## Error Cartographer Analysis\n"
                + json.dumps(inputs["error_cartographer"], indent=2, ensure_ascii=False)
            )

        if inputs.get("ethicist"):
            sections.append(
                "## Code Ethicist Analysis\n"
                + json.dumps(inputs["ethicist"], indent=2, ensure_ascii=False)
            )

        if inputs.get("code_text"):
            code = inputs["code_text"]
            if len(code) > 5000:
                code = code[:5000] + "\n... (truncated)"
            sections.append(f"## Source Code\n```python\n{code}\n```")

        return "\n\n".join(sections)

    def _synthesize_with_llm(
        self, user_message: str, session_id: str
    ) -> Dict[str, Any]:
        """Call Bedrock to synthesize fixes."""
        raw_output = self.refine_text_with_llm(
            text_to_refine=user_message,
            llm_system_prompt=self.system_prompt,
            current_session_id=session_id,
        )

        if raw_output is None:
            self.logger.warning("Fixer LLM returned None -- using empty result")
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
        self.logger.warning("Could not parse Fixer JSON -- using raw output")
        return {
            "fixes": [],
            "summary": raw_output[:500],
            "risk_notes": ["LLM output could not be parsed as JSON"],
        }

    @staticmethod
    def _normalize_result(data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure result has the expected keys."""
        fixes = data.get("fixes", [])
        if isinstance(fixes, list):
            fixes = [f for f in fixes if isinstance(f, dict)]
        else:
            fixes = []
        return {
            "fixes": fixes,
            "summary": data.get("summary", ""),
            "risk_notes": data.get("risk_notes", []),
        }

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "fixes": [],
            "summary": "",
            "risk_notes": [],
        }
