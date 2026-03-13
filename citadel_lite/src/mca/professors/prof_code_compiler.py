"""MCA Code Compiler Professor — metadata extraction + fingerprinting.

Rewritten from bookmaker-era code for MCA use.  Extracts structured
metadata (ENUMs, functions, schemas, dependencies, complexity tags)
and generates SHA-256 fingerprints for code sections.
Output feeds into ``MetricsAggregator.add_code_structure_metrics()``.
Uses AWS Bedrock via ``BedrockProfessorBase``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.mca.professors.bedrock_adapter import BedrockProfessorBase

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "prof_code_compiler"
_MODULE_VERSION = "2.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────
_MCA_COMPILER_SYSTEM_PROMPT = """\
You are **Code Compiler**, an MCA (Meta Cognitive Architecture) professor
specializing in **static metadata extraction** from source code.

Your mission:
1. Extract all enum definitions with their member values.
2. Extract function signatures (name, parameters, return type hints).
3. Extract schema/model definitions (Pydantic models, dataclasses, TypedDicts).
4. Identify imported dependencies (external libraries).
5. Assign complexity tags (ASYNC, IO_BOUND, RECURSIVE, MUTATION_HEAVY, etc.).

You MUST return your analysis as a JSON object with these keys:
{
  "enums": [{"name": "<EnumName>", "members": ["<member>", ...]}],
  "functions": [{"name": "<func>", "params": "<signature>", "docstring": "<doc>"}],
  "schemas": [{"name": "<ModelName>", "fields": ["<field>: <type>", ...]}],
  "dependencies": ["<library>", ...],
  "complexity_tags": ["<tag>", ...]
}

Be precise. Extract only what is present in the code.
"""


class ProfCodeCompiler(BedrockProfessorBase):
    """MCA Code Compiler — metadata extraction and fingerprinting.

    Combines regex-based local extraction with LLM-driven analysis
    via Bedrock for comprehensive code metadata.
    """

    DOSSIER_CONFIG: Dict[str, Any] = {
        "meta": [
            "enum_count",
            "function_count",
            "schema_count",
            "dependency_count",
        ],
        "professor_tags": [
            "metadata",
            "enums",
            "functions",
            "schemas",
            "dependencies",
            "complexity",
        ],
        "version_code": "prof_code_compiler_mca_v2.0",
        "full_text_key": "full_llm_output_compiler",
        "display_title_template": "MCA Code Compiler Analysis",
        "inject_emotion_profile": False,
    }

    def __init__(
        self,
        bedrock_client=None,
        session_id: Optional[str] = None,
    ) -> None:
        BedrockProfessorBase.__init__(self, bedrock_client=bedrock_client)
        self.name = "code_compiler_mca"
        self.system_prompt = _MCA_COMPILER_SYSTEM_PROMPT
        self.logger = logging.getLogger(f"Professor.{self.name}")
        self.session_id = session_id or "compiler_mca_default"

    # ── Public API ─────────────────────────────────────────────────────────
    def analyze(
        self,
        code_text: str,
        *,
        ir_metrics: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract metadata from the provided code.

        Parameters
        ----------
        code_text:
            Source code string to analyze.
        ir_metrics:
            Optional Roadmap IR metrics for context enrichment.
        session_id:
            Optional session identifier for tracing.

        Returns
        -------
        Dict with keys: ``enums``, ``functions``, ``schemas``,
        ``dependencies``, ``complexity_tags``, ``fingerprints``.
        """
        if not isinstance(code_text, str) or not code_text.strip():
            return self._empty_result()

        sid = session_id or self.session_id

        # Local regex extraction (always succeeds)
        local = self._extract_local(code_text)

        # LLM-driven extraction
        llm_result = self._analyze_with_llm(code_text, sid)

        # Merge: LLM enriches local, local provides fallback
        merged = self._merge_results(local, llm_result)

        # Fingerprints
        merged["fingerprints"] = {
            "full_sha256": hashlib.sha256(code_text.encode("utf-8")).hexdigest(),
        }

        return merged

    # ── Internal ───────────────────────────────────────────────────────────
    def _analyze_with_llm(
        self, code_text: str, session_id: str
    ) -> Dict[str, Any]:
        """Call Bedrock for metadata extraction."""
        raw_output = self.refine_text_with_llm(
            text_to_refine=code_text,
            llm_system_prompt=self.system_prompt,
            current_session_id=session_id,
        )

        if raw_output is None:
            self.logger.warning("Compiler LLM returned None — using local only")
            return self._empty_result()

        return self._parse_output(raw_output)

    def _parse_output(self, raw_output: str) -> Dict[str, Any]:
        """Parse LLM JSON output into structured dict."""
        # Try direct JSON parse
        try:
            data = json.loads(raw_output)
            if isinstance(data, dict):
                return self._normalize_llm_data(data)
        except json.JSONDecodeError:
            pass

        # Fallback: extract JSON block from markdown
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_output)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict):
                    return self._normalize_llm_data(data)
            except json.JSONDecodeError:
                pass

        self.logger.warning("Could not parse Compiler JSON — using empty LLM result")
        return self._empty_result()

    @staticmethod
    def _normalize_llm_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize LLM output into expected structure."""
        return {
            "enums": data.get("enums", []),
            "functions": data.get("functions", []),
            "schemas": data.get("schemas", []),
            "dependencies": data.get("dependencies", []),
            "complexity_tags": data.get("complexity_tags", []),
        }

    @staticmethod
    def _extract_local(code_text: str) -> Dict[str, Any]:
        """Regex-based local metadata extraction."""
        enums: List[Dict[str, Any]] = []
        functions: List[Dict[str, Any]] = []
        schemas: List[Dict[str, Any]] = []
        deps: set[str] = set()
        complexity_tags: set[str] = set()

        # Enum detection
        for m in re.finditer(
            r"class (\w+)\(.*?Enum.*?\):([\s\S]+?)(?=\nclass |\ndef |\Z)", code_text
        ):
            name = m.group(1)
            body = m.group(2)
            members = re.findall(r"(\w+)\s*=\s*", body)
            enums.append({"name": name, "members": members})

        # Function definitions
        for m in re.finditer(
            r'def (\w+)\((.*?)\).*?:\s*(?:"""([\s\S]*?)""")?', code_text
        ):
            functions.append({
                "name": m.group(1),
                "params": m.group(2).strip(),
                "docstring": (m.group(3) or "").strip(),
            })

        # Pydantic/dataclass schemas
        for m in re.finditer(
            r"class (\w+)\((?:BaseModel|BaseSettings).*?\):", code_text
        ):
            schemas.append({"name": m.group(1), "fields": []})

        # Imports
        for imp in re.findall(r"^\s*import (\w+)", code_text, re.MULTILINE):
            deps.add(imp)
        for frm in re.findall(r"^\s*from (\w+)", code_text, re.MULTILINE):
            deps.add(frm)

        # Complexity tags
        if "async def " in code_text:
            complexity_tags.add("ASYNC")
        if re.search(r"for .* in .*:", code_text) and "open(" in code_text:
            complexity_tags.add("IO_BOUND")
        if "self." in code_text:
            complexity_tags.add("STATEFUL")

        return {
            "enums": enums,
            "functions": functions,
            "schemas": schemas,
            "dependencies": sorted(deps),
            "complexity_tags": sorted(complexity_tags),
        }

    @staticmethod
    def _merge_results(
        local: Dict[str, Any], llm: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge local and LLM results — LLM enriches local."""
        return {
            "enums": llm.get("enums") or local.get("enums", []),
            "functions": llm.get("functions") or local.get("functions", []),
            "schemas": llm.get("schemas") or local.get("schemas", []),
            "dependencies": llm.get("dependencies") or local.get("dependencies", []),
            "complexity_tags": list(set(
                (llm.get("complexity_tags") or [])
                + (local.get("complexity_tags") or [])
            )),
        }

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "enums": [],
            "functions": [],
            "schemas": [],
            "dependencies": [],
            "complexity_tags": [],
            "fingerprints": {},
        }
