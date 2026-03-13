"""MCA Code Archeologist Professor — design pattern / anti-pattern detection.

Rewritten from bookmaker-era code for MCA use.  Analyzes code architecture
via AST (local) + LLM (Bedrock) to detect design patterns, anti-patterns,
and complexity hotspots.  Output supplements Mirror professor analysis.
Uses AWS Bedrock via ``BedrockProfessorBase``.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.mca.professors.bedrock_adapter import BedrockProfessorBase

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "prof_code_archeologist"
_MODULE_VERSION = "2.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────
_MCA_ARCHEOLOGIST_SYSTEM_PROMPT = """\
You are **Code Archeologist**, an MCA (Meta Cognitive Architecture) professor
specializing in **reverse-engineering code architecture** and detecting
**design patterns and anti-patterns**.

Your mission:
1. Identify recurring design patterns (Factory, Strategy, Observer, Singleton,
   Repository, Adapter, etc.) in the provided code.
2. Detect anti-patterns (God class, circular dependencies, dead code, feature
   envy, shotgun surgery, etc.).
3. Note architecture-level observations (layering, separation of concerns,
   dependency inversion, coupling/cohesion).
4. Highlight complexity hotspots (deeply nested logic, high cyclomatic
   complexity, mutation-heavy sections).

You MUST return your analysis as a JSON object with these keys:
{
  "design_patterns": ["<pattern>: <where/why>", ...],
  "anti_patterns": ["<anti_pattern>: <where/why>", ...],
  "architecture_notes": ["<observation>", ...],
  "complexity_hotspots": ["<hotspot>", ...]
}

Be precise and factual. Base your analysis only on the provided code.
"""


class ProfCodeArcheologist(BedrockProfessorBase):
    """MCA Code Archeologist — design pattern and anti-pattern detection.

    Combines AST-based local analysis with LLM-driven architectural
    assessment via Bedrock.
    """

    DOSSIER_CONFIG: Dict[str, Any] = {
        "meta": [
            "design_pattern_count",
            "anti_pattern_count",
            "hotspot_count",
        ],
        "professor_tags": [
            "design_patterns",
            "anti_patterns",
            "architecture",
            "complexity",
            "code_quality",
        ],
        "version_code": "prof_code_archeologist_mca_v2.0",
        "full_text_key": "full_llm_output_archeologist",
        "display_title_template": "MCA Code Archeologist Analysis",
        "inject_emotion_profile": False,
    }

    def __init__(
        self,
        bedrock_client=None,
        session_id: Optional[str] = None,
    ) -> None:
        BedrockProfessorBase.__init__(self, bedrock_client=bedrock_client)
        self.name = "code_archeologist_mca"
        self.system_prompt = _MCA_ARCHEOLOGIST_SYSTEM_PROMPT
        self.logger = logging.getLogger(f"Professor.{self.name}")
        self.session_id = session_id or "archeologist_mca_default"

    # ── Public API ─────────────────────────────────────────────────────────
    def analyze(
        self,
        code_text: str,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run architecture analysis on the provided code.

        Parameters
        ----------
        code_text:
            Source code string to analyze.
        session_id:
            Optional session identifier for tracing.

        Returns
        -------
        Dict with keys: ``design_patterns``, ``anti_patterns``,
        ``architecture_notes``, ``complexity_hotspots``,
        ``ast_enumerations``.
        """
        if not isinstance(code_text, str) or not code_text.strip():
            return self._empty_result()

        sid = session_id or self.session_id

        # Local AST analysis (always succeeds — does not require LLM)
        ast_enums = self._find_enumerations_with_ast(code_text)

        # LLM-driven architectural analysis
        llm_result = self._analyze_with_llm(code_text, sid)

        # Merge
        result = llm_result
        result["ast_enumerations"] = ast_enums
        return result

    # ── Internal ───────────────────────────────────────────────────────────
    def _analyze_with_llm(
        self, code_text: str, session_id: str
    ) -> Dict[str, Any]:
        """Call Bedrock for architectural analysis."""
        raw_output = self.refine_text_with_llm(
            text_to_refine=code_text,
            llm_system_prompt=self.system_prompt,
            current_session_id=session_id,
        )

        if raw_output is None:
            self.logger.warning("Archeologist LLM returned None — using empty result")
            return self._empty_result()

        return self._parse_output(raw_output)

    def _parse_output(self, raw_output: str) -> Dict[str, Any]:
        """Parse LLM JSON output into structured dict."""
        # Try direct JSON parse
        try:
            data = json.loads(raw_output)
            if isinstance(data, dict):
                return {
                    "design_patterns": data.get("design_patterns", []),
                    "anti_patterns": data.get("anti_patterns", []),
                    "architecture_notes": data.get("architecture_notes", []),
                    "complexity_hotspots": data.get("complexity_hotspots", []),
                }
        except json.JSONDecodeError:
            pass

        # Fallback: extract JSON block from markdown
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_output)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict):
                    return {
                        "design_patterns": data.get("design_patterns", []),
                        "anti_patterns": data.get("anti_patterns", []),
                        "architecture_notes": data.get("architecture_notes", []),
                        "complexity_hotspots": data.get("complexity_hotspots", []),
                    }
            except json.JSONDecodeError:
                pass

        # Last resort: return raw as architecture_notes
        self.logger.warning("Could not parse Archeologist JSON — using raw output")
        return {
            "design_patterns": [],
            "anti_patterns": [],
            "architecture_notes": [raw_output[:500]],
            "complexity_hotspots": [],
        }

    @staticmethod
    def _find_enumerations_with_ast(code_text: str) -> Dict[str, List[str]]:
        """Parse source code using AST to find Enum definitions."""
        enumerations: Dict[str, List[str]] = defaultdict(list)
        try:
            tree = ast.parse(code_text)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    is_enum = any(
                        isinstance(base, ast.Name) and base.id == "Enum"
                        for base in node.bases
                    )
                    if is_enum:
                        for member_node in node.body:
                            if isinstance(member_node, ast.Assign):
                                for target in member_node.targets:
                                    if isinstance(target, ast.Name):
                                        enumerations[node.name].append(target.id)
        except SyntaxError:
            logger.debug("AST parsing failed — skipping enum detection")
        return dict(enumerations)

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "design_patterns": [],
            "anti_patterns": [],
            "architecture_notes": [],
            "complexity_hotspots": [],
            "ast_enumerations": {},
        }
