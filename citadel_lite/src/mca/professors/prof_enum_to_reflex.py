# === prof_enum_to_reflex.py — Professor of ENUM to Reflex Mapping ===

import re
import json
import logging
import hashlib
import traceback
from typing import Dict, Any, Optional
from pathlib import Path

from college_config import utc_timestamp as college_utc_timestamp

# === Try importing ProfessorBase ===
try:
    from professor_base import ProfessorBase
    PROFESSOR_BASE_AVAILABLE = True
except ImportError as e:
    logging.getLogger("ProfEnumToReflex_Module").critical(f"Failed to import ProfessorBase: {e}", exc_info=True)
    PROFESSOR_BASE_AVAILABLE = False

    class ProfessorBase:
        def __init__(self, *args, **kwargs):
            self.name = "StubProfEnumToReflex"
            self.logger = logging.getLogger(self.name)
        def process_thought(self, *args, **kwargs):
            return {"text": "ERROR: ProfessorBase not available.", "metadata_for_dossier": {}}

# === DOSSIER CONFIG ===
DOSSIER_CONFIG = {
    "professor_tags": ["enum", "reflex_mapping", "systems_logic", "automation_triggers"],
    "meta": ["reflex_detected", "reflex_data"],
    "version_code": "enum_to_reflex_v1.0",
    "full_text_key": "enum_to_reflex_output",
    "display_title_prefix": "ENUM → Reflex Mapping",
    "inject_emotion_profile": False,
    "runtime_flags": "BROADCAST_SYSTEM"
}

SYSTEM_PROMPT = (
    "You are Professor EnumToReflex — an expert at transforming enumerations into Reflex System definitions.\n"
    "Your tasks:\n"
    "1. Take the provided ENUM JSON definition (enum_name, description, values[]).\n"
    "2. For each ENUM value, create a Reflex mapping object with:\n"
    "   - reflex_name (based on ENUM value, SCREAMING_SNAKE_CASE)\n"
    "   - trigger_condition (logical condition that activates this reflex)\n"
    "   - reflex_action (description of the system's response)\n"
    "   - importance_level (LOW, MEDIUM, HIGH, CRITICAL)\n"
    "   - notes (optional clarifications)\n"
    "3. Output a valid JSON object in the format:\n"
    "{\n"
    "  \"reflex_set_name\": \"...\",\n"
    "  \"linked_enum\": \"...\",\n"
    "  \"reflexes\": [\n"
    "    {\n"
    "      \"reflex_name\": \"...\",\n"
    "      \"trigger_condition\": \"...\",\n"
    "      \"reflex_action\": \"...\",\n"
    "      \"importance_level\": \"...\",\n"
    "      \"notes\": \"...\"\n"
    "    }\n"
    "  ]\n"
    "}\n"
    "Only output JSON — no extra commentary."
)

class ProfEnumToReflex(ProfessorBase):
    LLM_PRIMARY_OUTPUT_HEADER = "Reflex Mapping:"
    DOSSIER_CONFIG = DOSSIER_CONFIG

    def __init__(self, session_id: Optional[str] = None, operational_tier: str = "T2"):
        super().__init__(
            name="EnumToReflex",
            system_prompt=SYSTEM_PROMPT,
            session_id=session_id,
            operational_tier=operational_tier,
            enable_self_learning=True
        )
        self.prompt = SYSTEM_PROMPT

    def _augment_llm_input_with_specific_expertise(
        self, llm_input: str, source_vd_frontmatter: Optional[Dict[str, Any]]
    ) -> str:
        guidelines = (
            "\n\nENUM → REFLEX CONVERSION RULES:\n"
            "- reflex_name matches ENUM value name exactly.\n"
            "- trigger_condition is a boolean/logical phrase.\n"
            "- reflex_action describes a concrete system behavior.\n"
            "- importance_level reflects urgency (LOW, MEDIUM, HIGH, CRITICAL).\n"
            "- notes add clarity if needed.\n"
            "- Ensure JSON is syntactically valid."
        )
        return llm_input + guidelines

    def _parse_specialized_llm_output(
        self, llm_full_output: str, main_output: str, reflection: Optional[str]
    ) -> Dict[str, Any]:
        json_match = re.search(r"\{[\s\S]*\}", main_output)
        parsed_json = {}
        if json_match:
            try:
                parsed_json = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                parsed_json = {"error": "Invalid JSON format in Reflex output."}

        return {
            "reflex_detected": bool(parsed_json),
            "reflex_data": parsed_json
        }

    def convert_enum_to_reflex(self, enum_definition: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            f"Convert the following ENUM definition into Reflex System mappings:\n"
            f"{json.dumps(enum_definition, indent=2)}\n"
            "Follow the JSON format described in your system prompt."
        )
        result = self.process_thought(prompt)
        return result["metadata_for_dossier"].get("reflex_data", {})

# === Hook for College runner ===
def process_with_enum_to_reflex(prompt_or_raw_text: str, category: Optional[str] = None, session_id: Optional[str] = None,
                                source_vd_path: Optional[Path] = None, source_vd_frontmatter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not PROFESSOR_BASE_AVAILABLE:
        return {
            "text": "ERROR: ProfessorBase missing for EnumToReflex.",
            "metadata_for_dossier": {"error": "ProfessorBase missing."}
        }
    try:
        return ProfEnumToReflex(session_id=session_id).process_thought(
            prompt_or_raw_text=prompt_or_raw_text,
            category=category,
            session_id=session_id,
            source_vd_path=source_vd_path,
            source_vd_frontmatter=source_vd_frontmatter
        )
    except Exception as e:
        logging.getLogger("process_with_enum_to_reflex_hook").error(f"EnumToReflex Hook Error: {e}", exc_info=True)
        return {
            "text": f"❌ Hook Error: {e}",
            "error": str(e),
            "professor_id": "EnumToReflex_HookError",
            "session_id": session_id,
            "metadata_for_dossier": {
                "fingerprint": hashlib.sha256(f"enum_to_reflex_hook_error_{session_id}".encode()).hexdigest()[:16],
                "entry_type": "prof_enum_to_reflex_hook_error",
                "display_title_hint": f"Hook Error for: {prompt_or_raw_text[:30]}...",
                "timestamp_utc": college_utc_timestamp(),
                "_agent_success": False
            }
        }
