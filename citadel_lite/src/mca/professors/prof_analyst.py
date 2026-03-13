# === prof_analyst.py — Professor of Analytical Reasoning, Insight Extraction & ENUM/Reflex Enrichment (v1.1) ===
# Purpose:
#   - Deep structured analysis.
#   - Extraction of ENUM Groups, ENUM Families, Reflex Groups, Reflex Families, and Definitions.
#   - Generates actionable insights and recommendations while enriching vector metadata.
# ===============================================================================================================

import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
import traceback
import logging
import hashlib
import re
from datetime import datetime, timezone
import random

# === Module Logging ===
module_logger = logging.getLogger(__name__)
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s:%(lineno)d] - %(message)s"
    )

# === Path Setup ===
try:
    CURRENT_FILE = Path(__file__).resolve()
    PROFESSORS_DIR = CURRENT_FILE.parent
    COLLEGE_ROOT_DIR = PROFESSORS_DIR.parent
    if str(COLLEGE_ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(COLLEGE_ROOT_DIR))
except NameError:
    COLLEGE_ROOT_DIR = Path(".").resolve().parent
    if str(COLLEGE_ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(COLLEGE_ROOT_DIR))

# === Base Import ===
try:
    from professor_base import ProfessorBase
    from college_config import utc_timestamp as college_utc_timestamp
    PROFESSOR_BASE_AVAILABLE = True
    module_logger.info("ProfessorBase loaded successfully for ProfAnalyst.")
except ImportError as e_pb:
    PROFESSOR_BASE_AVAILABLE = False
    module_logger.critical(f"Failed to import ProfessorBase: {e_pb}", exc_info=True)
    class ProfessorBase:
        def __init__(self, *a, **k):
            self.name = "StubAnalyst"
            self.logger = logging.getLogger(self.name)
        def process_thought(self, *a, **k):
            return {"text": f"ERR: Base Missing ({self.name})", "metadata_for_dossier": {"_agent_success": False}}
        @staticmethod
        def extract_main_output(result: Dict[str, Any]):
            return result.get("text")
    def college_utc_timestamp():
        return datetime.now(timezone.utc).isoformat()

# === DOSSIER CONFIG ===
DOSSIER_CONFIG = {
    "professor_tags": [
        "analysis", "insight_extraction", "strategic_reasoning", "pattern_detection",
        "enum_extraction", "reflex_extraction", "definition_extraction"
    ],
    "meta": [
        "clarity_score", "depth_score", "evidence_strength_score",
        "actionability_rating", "pattern_complexity_score",
        "enum_group_count", "enum_family_count", "reflex_group_count", "reflex_family_count"
    ],
    "version_code": "analyst_v1.1_enum",
    "full_text_key": "analyst_report_text",
    "reflection_key": "analyst_reflection_text",
    "display_title_prefix": "Analytical Report with ENUM/Reflex Enrichment"
}

# === SYSTEM PROMPT ===
ANALYST_SYSTEM_PROMPT = (
    "You are Professor Analyst, a deep reasoning and insight extraction engine. "
    "Your responsibilities:\n"
    "1. Analyze the input (prompt or Vector Document) and produce a structured analytical report.\n"
    "2. Summarize the main findings and actionable recommendations.\n"
    "3. Identify and list ENUM Groups, ENUM Families, Reflex Groups, Reflex Families, and Definitions "
    "that are relevant to the context.\n\n"
    "OUTPUT FORMAT (in markdown):\n"
    "### Analyst Report:\n"
    "- Full reasoning and analysis.\n\n"
    "### Key Findings:\n"
    "- Bullet points summarizing major insights.\n\n"
    "### Recommendations:\n"
    "- Actionable steps.\n\n"
    "### ENUM Groups:\n"
    "- List of ENUM groups detected.\n\n"
    "### ENUM Families:\n"
    "- List of ENUM families detected.\n\n"
    "### Reflex Groups:\n"
    "- List of Reflex groups detected.\n\n"
    "### Reflex Families:\n"
    "- List of Reflex families detected.\n\n"
    "### Definitions:\n"
    "- Any relevant definitions or glossary terms.\n\n"
    "### Analyst's Reflection:\n"
    "- Reflection on reasoning process and confidence."
)

if not PROFESSOR_BASE_AVAILABLE:
    raise ImportError("ProfAnalyst cannot be defined because ProfessorBase failed to import.")

# === Class ===
class ProfAnalyst(ProfessorBase):
    LLM_PRIMARY_OUTPUT_HEADER = "Analyst Report:"
    LLM_REFLECTION_HEADER = "Analyst's Reflection:"
    DOSSIER_CONFIG = DOSSIER_CONFIG

    def __init__(self, session_id: Optional[str] = None):
        super().__init__(
            name="Analyst",
            system_prompt=ANALYST_SYSTEM_PROMPT,
            operational_tier="T3",
            session_id=session_id,
            enable_self_learning=True
        )
        self.logger.info(f"ProfAnalyst (v{self.DOSSIER_CONFIG['version_code']}) initialized.")

    def _extract_list_section(self, header: str, llm_output: str) -> List[str]:
        match = re.search(rf"{header}:(.*?)(?=\n###|\Z)", llm_output, re.DOTALL | re.IGNORECASE)
        if match:
            return [line.strip("- ").strip() for line in match.group(1).strip().split("\n") if line.strip()]
        return []

    def _parse_specialized_llm_output(self, llm_full_output: str, main_output: str, reflection: Optional[str]) -> Dict[str, Any]:
        specialized_parts = super()._parse_specialized_llm_output(llm_full_output, main_output, reflection)

        # Extract ENUM/Reflex data
        specialized_parts["enum_groups"] = self._extract_list_section("ENUM Groups", llm_full_output)
        specialized_parts["enum_families"] = self._extract_list_section("ENUM Families", llm_full_output)
        specialized_parts["reflex_groups"] = self._extract_list_section("Reflex Groups", llm_full_output)
        specialized_parts["reflex_families"] = self._extract_list_section("Reflex Families", llm_full_output)
        specialized_parts["definitions"] = self._extract_list_section("Definitions", llm_full_output)

        # Counts for meta
        specialized_parts["enum_group_count"] = len(specialized_parts["enum_groups"])
        specialized_parts["enum_family_count"] = len(specialized_parts["enum_families"])
        specialized_parts["reflex_group_count"] = len(specialized_parts["reflex_groups"])
        specialized_parts["reflex_family_count"] = len(specialized_parts["reflex_families"])

        # Extract Key Findings & Recommendations
        specialized_parts["key_findings"] = self._extract_list_section("Key Findings", llm_full_output)
        specialized_parts["recommendations"] = self._extract_list_section("Recommendations", llm_full_output)

        return specialized_parts

# === Hook ===
def process_with_analyst(prompt_or_raw_text: str, category: Optional[str] = None, session_id: Optional[str] = None,
                         source_vd_path: Optional[Path] = None, source_vd_frontmatter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not PROFESSOR_BASE_AVAILABLE:
        ts_err = college_utc_timestamp()
        return {
            "text": "ERROR: ProfAnalyst missing base class.",
            "error": "ProfessorBase missing",
            "metadata_for_dossier": {
                "fingerprint": hashlib.sha256(f"analyst_pb_missing_{ts_err}".encode()).hexdigest()[:16],
                "_agent_success": False,
                "timestamp_utc": ts_err
            }
        }
    try:
        return ProfAnalyst(session_id=session_id).process_thought(
            prompt_or_raw_text, category, session_id, source_vd_path, source_vd_frontmatter
        )
    except Exception as e_hook:
        return {
            "text": f"Hook error: {e_hook}",
            "error": str(e_hook),
            "_agent_success": False
        }

# === Config Accessor ===
def get_dossier_config() -> Dict[str, Any]:
    return DOSSIER_CONFIG

# === CLI ===
if __name__ == "__main__":
    import json
    cli = ProfAnalyst(session_id=f"cli_analyst_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    prompts = [
        "Analyze this AI governance policy and extract ENUM/Reflex classifications along with a report.",
        "From the provided document, identify ENUM groups and Reflex families, plus recommendations."
    ]
    for p in prompts:
        res = cli.process_thought(p)
        print("\n--- ANALYST REPORT ---")
        print(ProfessorBase.extract_main_output(res))
        print(json.dumps(res.get("metadata_for_dossier", {}), indent=2))
