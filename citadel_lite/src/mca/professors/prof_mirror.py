"""MCA Mirror Professor — code pattern analysis + product coverage evaluation.

Replaces the bookmaker-era Mirror with an MCA-focused professor that
analyzes codebase patterns and evaluates product plan coverage.
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
_MODULE_NAME = "prof_mirror"
_MODULE_VERSION = "2.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# Lazy import to keep module import lightweight
_ProfessorBase = None


def _get_professor_base():
    global _ProfessorBase
    if _ProfessorBase is None:
        from src.mca.professors.professor_base import ProfessorBase
        _ProfessorBase = ProfessorBase
    return _ProfessorBase


# ── System prompt ──────────────────────────────────────────────────────────
_MCA_MIRROR_SYSTEM_PROMPT = """\
You are **Mirror**, an MCA (Meta Cognitive Architecture) professor specializing
in **codebase pattern analysis** and **product plan coverage evaluation**.

Your mission:
1. Analyze code-level patterns — identify recurring architectural motifs,
   anti-patterns, duplication, naming conventions, and test coverage gaps.
2. Evaluate how well the current codebase covers the product plan — which
   planned features are implemented, partially implemented, or missing.
3. Provide structured, actionable output for the MCA Evolution Engine.

You MUST return your analysis as a **valid JSON object only** — no markdown,
no commentary, no explanation outside the JSON. The JSON must have these keys:
{
  "code_patterns": ["<pattern_name>: <description>", ...],
  "anti_patterns": ["<anti_pattern_name>: <description>", ...],
  "plan_coverage": {
    "<feature_or_phase>": {"status": "COVERED | PARTIAL | MISSING", "notes": "<notes>"}
  },
  "key_findings": ["<finding>", ...],
  "recommendations": ["<recommendation>", ...]
}

Be precise, factual, and quantitative where possible. Do not speculate —
base your analysis on the provided code and plan data.
Output ONLY valid JSON — no markdown fences, no preamble, no trailing text.
"""


class ProfMirror(BedrockProfessorBase):
    """MCA Mirror professor — code pattern + plan coverage analysis.

    Inherits Bedrock LLM routing from ``BedrockProfessorBase`` and provides
    ``analyze()`` as the primary entry point for the Evolution Engine.
    """

    DOSSIER_CONFIG: Dict[str, Any] = {
        "meta": [
            "clarity_score",
            "depth_score",
            "pattern_count",
            "coverage_count",
        ],
        "professor_tags": [
            "code_patterns",
            "plan_coverage",
            "anti_patterns",
            "architecture",
            "test_coverage",
        ],
        "version_code": "prof_mirror_mca_v2.0",
        "full_text_key": "full_llm_output_mirror",
        "display_title_template": "MCA Mirror Analysis",
        "inject_emotion_profile": False,
    }

    def __init__(
        self,
        bedrock_client=None,
        session_id: Optional[str] = None,
    ) -> None:
        BedrockProfessorBase.__init__(self, bedrock_client=bedrock_client)
        self.name = "mirror_mca"
        self.system_prompt = _MCA_MIRROR_SYSTEM_PROMPT
        self.logger = logging.getLogger(f"Professor.{self.name}")
        self.session_id = session_id or "mirror_mca_default"

    # ── Public API ─────────────────────────────────────────────────────────
    def analyze(
        self,
        metrics_snapshot: Dict[str, Any],
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run Mirror analysis on the provided metrics snapshot.

        Parameters
        ----------
        metrics_snapshot:
            Dict containing ``code_summary``, ``plan_summary``, and any
            additional context for the analysis.
        session_id:
            Optional session identifier for tracing.

        Returns
        -------
        Dict with keys: ``code_patterns``, ``anti_patterns``,
        ``plan_coverage``, ``key_findings``, ``recommendations``,
        ``raw_output``.
        """
        sid = session_id or self.session_id
        user_message = self._build_user_message(metrics_snapshot)

        raw_output = self.refine_text_with_llm(
            text_to_refine=user_message,
            llm_system_prompt=self.system_prompt,
            current_session_id=sid,
        )

        if raw_output is None:
            self.logger.warning("Mirror analysis returned None — using empty result")
            return self._empty_result()

        return self._parse_output(raw_output)

    # ── Internal ───────────────────────────────────────────────────────────
    @staticmethod
    def _build_user_message(metrics_snapshot: Dict[str, Any]) -> str:
        parts = ["## Metrics Snapshot\n"]
        for key, value in metrics_snapshot.items():
            if isinstance(value, (dict, list)):
                parts.append(f"### {key}\n```json\n{json.dumps(value, ensure_ascii=False, indent=2)}\n```\n")
            else:
                parts.append(f"- **{key}**: {value}\n")
        return "\n".join(parts)

    def _parse_output(self, raw_output: str) -> Dict[str, Any]:
        # Try JSON parse first (direct or markdown-fenced)
        parsed = self._try_parse_json(raw_output)
        if parsed is not None:
            return self._normalize_json_result(parsed, raw_output)

        # Fallback: markdown section extraction
        self.logger.warning("Mirror JSON parse failed — falling back to markdown extraction")
        return {
            "code_patterns": self._extract_list_section("Code Patterns", raw_output),
            "anti_patterns": self._extract_list_section("Anti-Patterns", raw_output),
            "plan_coverage": self._extract_coverage_section(raw_output),
            "key_findings": self._extract_list_section("Key Findings", raw_output),
            "recommendations": self._extract_list_section("Recommendations", raw_output),
            "raw_output": raw_output,
        }

    @staticmethod
    def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
        """Try to extract JSON from text (plain or markdown-fenced)."""
        # Direct parse
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        # Markdown fence: ```json ... ``` or ``` ... ```
        m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass

        # Last resort: find first { ... } block
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass

        return None

    @staticmethod
    def _normalize_json_result(data: Dict[str, Any], raw_output: str) -> Dict[str, Any]:
        """Normalize parsed JSON into expected Mirror result structure."""
        code_patterns = data.get("code_patterns", [])
        if not isinstance(code_patterns, list):
            code_patterns = []
        anti_patterns = data.get("anti_patterns", [])
        if not isinstance(anti_patterns, list):
            anti_patterns = []
        plan_coverage = data.get("plan_coverage", {})
        if not isinstance(plan_coverage, dict):
            plan_coverage = {}
        key_findings = data.get("key_findings", [])
        if not isinstance(key_findings, list):
            key_findings = []
        recommendations = data.get("recommendations", [])
        if not isinstance(recommendations, list):
            recommendations = []
        return {
            "code_patterns": [str(p) for p in code_patterns],
            "anti_patterns": [str(p) for p in anti_patterns],
            "plan_coverage": plan_coverage,
            "key_findings": [str(f) for f in key_findings],
            "recommendations": [str(r) for r in recommendations],
            "raw_output": raw_output,
        }

    @staticmethod
    def _extract_list_section(header: str, text: str) -> List[str]:
        """Extract a bulleted list section from LLM output.

        Adapted from ``prof_analyst.py._extract_list_section()``.
        """
        pattern = rf"###\s*{re.escape(header)}\s*\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return [
                line.strip("- ").strip()
                for line in match.group(1).strip().split("\n")
                if line.strip() and line.strip() != "-"
            ]
        return []

    @staticmethod
    def _extract_coverage_section(text: str) -> Dict[str, Dict[str, str]]:
        """Extract plan coverage entries into {feature: {status, notes}}."""
        items: Dict[str, Dict[str, str]] = {}
        pattern = r"###\s*Plan Coverage\s*\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            return items

        for line in match.group(1).strip().split("\n"):
            line = line.strip("- ").strip()
            if not line:
                continue
            # Expected format: "feature: STATUS — notes"
            parts = re.split(r":\s*", line, maxsplit=1)
            if len(parts) == 2:
                feature = parts[0].strip()
                rest = parts[1].strip()
                status_match = re.match(
                    r"(COVERED|PARTIAL|MISSING)", rest, re.IGNORECASE
                )
                status = status_match.group(1).upper() if status_match else "UNKNOWN"
                notes = re.sub(r"^(COVERED|PARTIAL|MISSING)\s*[-—]?\s*", "", rest, flags=re.IGNORECASE).strip()
                items[feature] = {"status": status, "notes": notes}
        return items

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "code_patterns": [],
            "anti_patterns": [],
            "plan_coverage": {},
            "key_findings": [],
            "recommendations": [],
            "raw_output": "",
        }
