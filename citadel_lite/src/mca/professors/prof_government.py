"""MCA Government Professor — CAPS compliance + proposal approval/rejection.

Rewritten from the bookmaker-era Government professor for MCA use.
Evaluates evolution proposals against CAPS (Compliance, Approval, Policy,
Security) protocol rules and returns approval/rejection decisions with
risk assessments.  Uses AWS Bedrock via ``BedrockProfessorBase``.
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
_MODULE_NAME = "prof_government"
_MODULE_VERSION = "2.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────
_MCA_GOVERNMENT_SYSTEM_PROMPT = """\
You are **Government**, an MCA (Meta Cognitive Architecture) professor
specializing in **CAPS (Compliance, Approval, Policy, Security) protocol
compliance** and **evolution proposal governance**.

Your mission:
1. Review evolution proposals (EP-CODE, EP-RAG, EP-SALES, EP-STALE, EP-GAP)
   against CAPS compliance rules.
2. Approve proposals that meet quality, security, and policy standards.
3. Reject proposals that violate rules, with clear justification.
4. Assess risk for each proposal.
5. When provided with roadmap conflicts, arbitrate and recommend resolution.

CAPS Compliance Rules:
- All code changes must have corresponding test coverage plans.
- Security-sensitive changes require explicit risk assessment.
- RAG document changes must maintain consistency with existing knowledge base.
- Stale content flags must be verified against current source data.
- Gap proposals must reference the specific plan items they address.

You MUST return your evaluation as a **valid JSON object only** — no markdown,
no commentary, no explanation outside the JSON. The JSON must have these keys:
{
  "approved": [
    {"id": "<proposal_id>", "reason": "<justification>"}
  ],
  "rejected": [
    {"id": "<proposal_id>", "reason": "<justification>"}
  ],
  "risk_assessment": [
    {"id": "<proposal_id>", "level": "LOW | MEDIUM | HIGH | CRITICAL", "description": "<description>"}
  ],
  "conflict_arbitration": [
    {"id": "<conflict_id>", "resolution": "<resolution>"}
  ],
  "policy_notes": [
    "<policy note>"
  ]
}

Every proposal in the input MUST appear in either "approved" or "rejected" — never omit a proposal.
Be strict but fair. Provide clear justifications for all decisions.
Output ONLY valid JSON — no markdown fences, no preamble, no trailing text.
"""

# CAPS-related ENUM constants for MCA governance tagging
_MCA_ENUM_TAGS = [
    "CAPS_COMPLIANCE_CHECK",
    "CAPS_APPROVAL_GRANTED",
    "CAPS_APPROVAL_DENIED",
    "CAPS_SECURITY_REVIEW",
    "CAPS_POLICY_VIOLATION",
    "CAPS_RISK_LOW",
    "CAPS_RISK_MEDIUM",
    "CAPS_RISK_HIGH",
    "CAPS_RISK_CRITICAL",
    "CAPS_CONFLICT_RESOLVED",
    "MCA_PROPOSAL_EP_CODE",
    "MCA_PROPOSAL_EP_RAG",
    "MCA_PROPOSAL_EP_SALES",
    "MCA_PROPOSAL_EP_STALE",
    "MCA_PROPOSAL_EP_GAP",
]


class ProfGovernment(BedrockProfessorBase):
    """MCA Government professor — CAPS compliance + proposal governance.

    Inherits Bedrock LLM routing from ``BedrockProfessorBase`` and provides
    ``analyze()`` as the primary entry point for the Evolution Engine.
    """

    DOSSIER_CONFIG: Dict[str, Any] = {
        "meta": [
            "approved_count",
            "rejected_count",
            "risk_levels",
        ],
        "professor_tags": [
            "caps",
            "compliance",
            "governance",
            "policy",
            "security",
            "proposal_review",
        ],
        "version_code": "prof_government_mca_v2.0",
        "full_text_key": "full_llm_output_government",
        "display_title_template": "MCA Government CAPS Review",
        "inject_emotion_profile": False,
    }

    def __init__(
        self,
        bedrock_client=None,
        session_id: Optional[str] = None,
    ) -> None:
        BedrockProfessorBase.__init__(self, bedrock_client=bedrock_client)
        self.name = "government_mca"
        self.system_prompt = _MCA_GOVERNMENT_SYSTEM_PROMPT
        self.logger = logging.getLogger(f"Professor.{self.name}")
        self.session_id = session_id or "government_mca_default"

    # ── Public API ─────────────────────────────────────────────────────────
    def analyze(
        self,
        metrics_snapshot: Dict[str, Any],
        *,
        proposals: Optional[List[Dict[str, Any]]] = None,
        conflicts: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run Government CAPS review on proposals.

        Parameters
        ----------
        metrics_snapshot:
            Current project metrics for context.
        proposals:
            List of evolution proposals to review.
        conflicts:
            Optional list of roadmap conflicts to arbitrate.
        session_id:
            Optional session identifier for tracing.

        Returns
        -------
        Dict with keys: ``approved``, ``rejected``, ``risk_assessment``,
        ``conflict_arbitration``, ``policy_notes``, ``enum_tags``,
        ``raw_output``.
        """
        sid = session_id or self.session_id
        user_message = self._build_user_message(
            metrics_snapshot, proposals or [], conflicts or []
        )

        raw_output = self.refine_text_with_llm(
            text_to_refine=user_message,
            llm_system_prompt=self.system_prompt,
            current_session_id=sid,
        )

        if raw_output is None:
            self.logger.warning("Government analysis returned None — using empty result")
            return self._empty_result()

        result = self._parse_output(raw_output)
        result["enum_tags"] = self.extract_enum_tags(raw_output)
        return result

    # ── Internal ───────────────────────────────────────────────────────────
    @staticmethod
    def _build_user_message(
        metrics_snapshot: Dict[str, Any],
        proposals: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
    ) -> str:
        parts = ["## CAPS Compliance Review Request\n"]

        parts.append("### Project Metrics\n```json\n")
        parts.append(json.dumps(metrics_snapshot, ensure_ascii=False, indent=2))
        parts.append("\n```\n")

        if proposals:
            parts.append("### Proposals to Review\n```json\n")
            parts.append(json.dumps(proposals, ensure_ascii=False, indent=2))
            parts.append("\n```\n")
        else:
            parts.append("### Proposals to Review\nNo proposals submitted.\n")

        if conflicts:
            parts.append("### Roadmap Conflicts to Arbitrate\n```json\n")
            parts.append(json.dumps(conflicts, ensure_ascii=False, indent=2))
            parts.append("\n```\n")

        return "\n".join(parts)

    def _parse_output(self, raw_output: str) -> Dict[str, Any]:
        # Try JSON parse first (direct or markdown-fenced)
        parsed = self._try_parse_json(raw_output)
        if parsed is not None:
            return self._normalize_json_result(parsed, raw_output)

        # Fallback: markdown section extraction
        self.logger.warning("Government JSON parse failed — falling back to markdown extraction")
        return {
            "approved": self._extract_keyed_list("Approved", raw_output),
            "rejected": self._extract_keyed_list("Rejected", raw_output),
            "risk_assessment": self._extract_risk_assessment(raw_output),
            "conflict_arbitration": self._extract_keyed_list("Conflict Arbitration", raw_output),
            "policy_notes": self._extract_list_section("Policy Notes", raw_output),
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
        """Normalize parsed JSON into expected Government result structure."""
        def _ensure_list(val):
            return val if isinstance(val, list) else []

        def _normalize_keyed(items: list, reason_key: str) -> List[Dict[str, str]]:
            result = []
            for item in items:
                if isinstance(item, dict):
                    result.append({
                        "id": str(item.get("id", "")),
                        reason_key: str(item.get(reason_key, "")),
                    })
            return result

        approved = _normalize_keyed(_ensure_list(data.get("approved")), "reason")
        rejected = _normalize_keyed(_ensure_list(data.get("rejected")), "reason")

        risk_raw = _ensure_list(data.get("risk_assessment"))
        risk_assessment = []
        for item in risk_raw:
            if isinstance(item, dict):
                risk_assessment.append({
                    "id": str(item.get("id", "")),
                    "level": str(item.get("level", "UNKNOWN")).upper(),
                    "description": str(item.get("description", "")),
                })

        conflict_arbitration = _normalize_keyed(
            _ensure_list(data.get("conflict_arbitration")), "resolution"
        )

        policy_notes = [str(n) for n in _ensure_list(data.get("policy_notes"))]

        return {
            "approved": approved,
            "rejected": rejected,
            "risk_assessment": risk_assessment,
            "conflict_arbitration": conflict_arbitration,
            "policy_notes": policy_notes,
            "raw_output": raw_output,
        }

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
    def _extract_keyed_list(header: str, text: str) -> List[Dict[str, str]]:
        """Extract ``id: reason`` lines into [{id, reason}]."""
        items: List[Dict[str, str]] = []
        pattern = rf"###\s*{re.escape(header)}\s*\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            return items

        for line in match.group(1).strip().split("\n"):
            line = line.strip("- ").strip()
            if not line:
                continue
            parts = re.split(r":\s*", line, maxsplit=1)
            if len(parts) == 2:
                items.append({"id": parts[0].strip(), "reason": parts[1].strip()})
            elif line:
                items.append({"id": line, "reason": ""})
        return items

    @staticmethod
    def _extract_risk_assessment(text: str) -> List[Dict[str, str]]:
        """Extract risk assessment lines into [{id, level, description}]."""
        items: List[Dict[str, str]] = []
        pattern = r"###\s*Risk Assessment\s*\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            return items

        for line in match.group(1).strip().split("\n"):
            line = line.strip("- ").strip()
            if not line:
                continue
            parts = re.split(r":\s*", line, maxsplit=1)
            if len(parts) != 2:
                continue
            proposal_id = parts[0].strip()
            rest = parts[1].strip()
            level_match = re.match(
                r"(LOW|MEDIUM|HIGH|CRITICAL)", rest, re.IGNORECASE
            )
            level = level_match.group(1).upper() if level_match else "UNKNOWN"
            desc = re.sub(
                r"^(LOW|MEDIUM|HIGH|CRITICAL)\s*[-—]?\s*", "", rest, flags=re.IGNORECASE
            ).strip()
            items.append({
                "id": proposal_id,
                "level": level,
                "description": desc,
            })
        return items

    @staticmethod
    def extract_enum_tags(text: str) -> List[str]:
        """Extract relevant MCA CAPS ENUM tags from output text."""
        lowered = text.lower()
        matched = []
        for tag in _MCA_ENUM_TAGS:
            keywords = tag.lower().split("_")
            if any(kw in lowered for kw in keywords if len(kw) > 3):
                matched.append(tag)
        return matched

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "approved": [],
            "rejected": [],
            "risk_assessment": [],
            "conflict_arbitration": [],
            "policy_notes": [],
            "enum_tags": [],
            "raw_output": "",
        }
