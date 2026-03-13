"""MCA Oracle Professor — strategic guidance + health evaluation.

Replaces the bookmaker-era Oracle with an MCA-focused professor that
evaluates project health, product documentation strength, and provides
strategic improvement recommendations.  Uses AWS Bedrock via
``BedrockProfessorBase``.
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
_MODULE_NAME = "prof_oracle"
_MODULE_VERSION = "2.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────
_MCA_ORACLE_SYSTEM_PROMPT = """\
You are **Oracle**, an MCA (Meta Cognitive Architecture) professor specializing
in **strategic guidance** and **project health evaluation**.

Your mission:
1. Evaluate overall project health — assess code quality, test coverage,
   documentation completeness, and deployment readiness.
2. Assess product documentation strength — how well the product plan,
   roadmap, and feature specs support development and sales.
3. Provide the top strategic improvements that would have the highest
   impact on project maturity and revenue readiness.

You MUST return your analysis as a **valid JSON object only** — no markdown,
no commentary, no explanation outside the JSON. The JSON must have these keys:
{
  "health_status": {
    "overall": "GREEN | YELLOW | RED",
    "code_quality": {"score": 1-10, "notes": "<notes>"},
    "test_coverage": {"score": 1-10, "notes": "<notes>"},
    "doc_completeness": {"score": 1-10, "notes": "<notes>"},
    "deployment_readiness": {"score": 1-10, "notes": "<notes>"}
  },
  "product_doc_strength": {
    "plan_clarity": {"score": 1-10, "notes": "<notes>"},
    "roadmap_alignment": {"score": 1-10, "notes": "<notes>"},
    "feature_spec_depth": {"score": 1-10, "notes": "<notes>"},
    "sales_readiness": {"score": 1-10, "notes": "<notes>"}
  },
  "top_3_improvements": [
    {"title": "<title>", "description": "<description>"}
  ],
  "tier_coverage": [
    "<tier_name>: <coverage_pct>% — <notes>"
  ],
  "key_findings": [
    "<finding>"
  ]
}

Be precise, strategic, and actionable. Focus on high-impact items that
move the project toward revenue readiness.
Output ONLY valid JSON — no markdown fences, no preamble, no trailing text.
"""


class ProfOracle(BedrockProfessorBase):
    """MCA Oracle professor — strategic guidance + health evaluation.

    Inherits Bedrock LLM routing from ``BedrockProfessorBase`` and provides
    ``analyze()`` as the primary entry point for the Evolution Engine.
    """

    DOSSIER_CONFIG: Dict[str, Any] = {
        "meta": [
            "health_overall",
            "doc_strength_avg",
            "improvement_count",
        ],
        "professor_tags": [
            "strategy",
            "health",
            "documentation",
            "tier_coverage",
            "revenue_readiness",
        ],
        "version_code": "prof_oracle_mca_v2.0",
        "full_text_key": "full_llm_output_oracle",
        "display_title_template": "MCA Oracle Evaluation",
        "inject_emotion_profile": False,
    }

    def __init__(
        self,
        bedrock_client=None,
        session_id: Optional[str] = None,
    ) -> None:
        BedrockProfessorBase.__init__(self, bedrock_client=bedrock_client)
        self.name = "oracle_mca"
        self.system_prompt = _MCA_ORACLE_SYSTEM_PROMPT
        self.logger = logging.getLogger(f"Professor.{self.name}")
        self.session_id = session_id or "oracle_mca_default"

    # ── Public API ─────────────────────────────────────────────────────────
    def analyze(
        self,
        metrics_snapshot: Dict[str, Any],
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run Oracle analysis on the provided metrics snapshot.

        Returns
        -------
        Dict with keys: ``health_status``, ``product_doc_strength``,
        ``top_3_improvements``, ``tier_coverage``, ``key_findings``,
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
            self.logger.warning("Oracle analysis returned None — using empty result")
            return self._empty_result()

        return self._parse_output(raw_output)

    # ── Internal ───────────────────────────────────────────────────────────
    @staticmethod
    def _build_user_message(metrics_snapshot: Dict[str, Any]) -> str:
        parts = ["## Metrics Snapshot for Strategic Evaluation\n"]
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
        self.logger.warning("Oracle JSON parse failed — falling back to markdown extraction")
        return {
            "health_status": self._extract_health_status(raw_output),
            "product_doc_strength": self._extract_scored_section("Product Doc Strength", raw_output),
            "top_3_improvements": self._extract_numbered_list("Top 3 Improvements", raw_output),
            "tier_coverage": self._extract_list_section("Tier Coverage", raw_output),
            "key_findings": self._extract_list_section("Key Findings", raw_output),
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

        # Markdown fence
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
        """Normalize parsed JSON into expected Oracle result structure."""
        health = data.get("health_status", {})
        if not isinstance(health, dict):
            health = {"overall": "UNKNOWN"}
        elif "overall" not in health:
            health["overall"] = "UNKNOWN"

        doc_strength = data.get("product_doc_strength", {})
        if not isinstance(doc_strength, dict):
            doc_strength = {}

        improvements = data.get("top_3_improvements", [])
        if not isinstance(improvements, list):
            improvements = []
        # Normalize to [{title, description}] format
        normalized_improvements = []
        for item in improvements:
            if isinstance(item, dict):
                normalized_improvements.append({
                    "title": str(item.get("title", "")),
                    "description": str(item.get("description", "")),
                })
            elif isinstance(item, str):
                normalized_improvements.append({"title": item, "description": ""})

        tier_coverage = data.get("tier_coverage", [])
        if not isinstance(tier_coverage, list):
            tier_coverage = []

        key_findings = data.get("key_findings", [])
        if not isinstance(key_findings, list):
            key_findings = []

        return {
            "health_status": health,
            "product_doc_strength": doc_strength,
            "top_3_improvements": normalized_improvements,
            "tier_coverage": [str(t) for t in tier_coverage],
            "key_findings": [str(f) for f in key_findings],
            "raw_output": raw_output,
        }

    @staticmethod
    def _extract_health_status(text: str) -> Dict[str, Any]:
        """Extract health status with overall color + dimension scores."""
        result: Dict[str, Any] = {"overall": "UNKNOWN"}
        pattern = r"###\s*Health Status\s*\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            return result

        for line in match.group(1).strip().split("\n"):
            line = line.strip("- ").strip()
            if not line:
                continue
            parts = re.split(r":\s*", line, maxsplit=1)
            if len(parts) != 2:
                continue
            key = parts[0].strip().lower().replace(" ", "_")
            value = parts[1].strip()
            # Check for overall status (GREEN/YELLOW/RED)
            color_match = re.match(r"(GREEN|YELLOW|RED)", value, re.IGNORECASE)
            if color_match:
                result[key] = color_match.group(1).upper()
                continue
            # Check for numeric score
            score_match = re.match(r"(\d+(?:\.\d+)?)", value)
            if score_match:
                notes = re.sub(r"^\d+(?:\.\d+)?\s*[-—]?\s*", "", value).strip()
                result[key] = {
                    "score": float(score_match.group(1)),
                    "notes": notes,
                }
        return result

    @staticmethod
    def _extract_scored_section(header: str, text: str) -> Dict[str, Any]:
        """Extract a section with ``key: score — notes`` lines."""
        result: Dict[str, Any] = {}
        pattern = rf"###\s*{re.escape(header)}\s*\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            return result

        for line in match.group(1).strip().split("\n"):
            line = line.strip("- ").strip()
            if not line:
                continue
            parts = re.split(r":\s*", line, maxsplit=1)
            if len(parts) != 2:
                continue
            key = parts[0].strip().lower().replace(" ", "_")
            value = parts[1].strip()
            score_match = re.match(r"(\d+(?:\.\d+)?)", value)
            if score_match:
                notes = re.sub(r"^\d+(?:\.\d+)?\s*[-—]?\s*", "", value).strip()
                result[key] = {
                    "score": float(score_match.group(1)),
                    "notes": notes,
                }
            else:
                result[key] = value
        return result

    @staticmethod
    def _extract_numbered_list(header: str, text: str) -> List[Dict[str, str]]:
        """Extract a numbered list section into [{title, description}]."""
        items: List[Dict[str, str]] = []
        pattern = rf"###\s*{re.escape(header)}\s*\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            return items

        for line in match.group(1).strip().split("\n"):
            line = re.sub(r"^\d+\.\s*", "", line.strip()).strip()
            if not line:
                continue
            parts = re.split(r":\s*", line, maxsplit=1)
            if len(parts) == 2:
                items.append({"title": parts[0].strip(), "description": parts[1].strip()})
            else:
                items.append({"title": line, "description": ""})
        return items

    @staticmethod
    def _extract_list_section(header: str, text: str) -> List[str]:
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
    def _empty_result() -> Dict[str, Any]:
        return {
            "health_status": {"overall": "UNKNOWN"},
            "product_doc_strength": {},
            "top_3_improvements": [],
            "tier_coverage": [],
            "key_findings": [],
            "raw_output": "",
        }
