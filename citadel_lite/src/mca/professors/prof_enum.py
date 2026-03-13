# === prof_enum.py — Professor of ENUM Generation & Definition (v1.1) ===

import sys
import logging
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any

from college_config import utc_timestamp as college_utc_timestamp

# === Ensure ROOT path for imports ===
try:
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
except NameError:  # Fallback if __file__ is not defined
    ROOT = Path(".").resolve()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

# === Import ProfessorBase Safely ===
try:
    from professor_base import ProfessorBase
    PROFESSOR_BASE_AVAILABLE = True
except ImportError as e:
    logging.getLogger("ProfEnum_Module").critical(f"Failed to import ProfessorBase: {e}", exc_info=True)
    PROFESSOR_BASE_AVAILABLE = False

    class ProfessorBase:
        def __init__(self, *args, **kwargs):
            self.name = "StubProfEnum"
            self.logger = logging.getLogger(self.name)
        def process_thought(self, *args, **kwargs):
            return {"text": "ERROR: ProfessorBase not available.", "metadata_for_dossier": {}}

# === DOSSIER CONFIG ===
DOSSIER_CONFIG = {
    "professor_tags": ["enum", "definitions", "structured_values", "categorization", "metadata_mapping"],
    "meta": ["clarity_score", "completeness_score", "consistency_score"],
    "version_code": "enum_v1.1",
    "full_text_key": "enum_definition_text",
    "reflection_key": "enum_notes_text",
    "display_title_prefix": "ENUM Definition",
    "inject_emotion_profile": False,
    "runtime_flags": "BROADCAST_ENUM"
}

ENUM_SYSTEM_PROMPT = (
    "You are Professor Enum — an expert in defining clear and structured ENUMs for AI systems.\n"
    "Your task:\n"
    "1. Interpret the given concept and generate a clean ENUM definition.\n"
    "2. Include:\n"
    "   - enum_name (SCREAMING_SNAKE_CASE)\n"
    "   - description (concise purpose statement)\n"
    "   - values[] (each with name, description, optional aliases)\n"
    "3. Output **valid JSON only** — no extra commentary."
)

class ProfEnum(ProfessorBase):
    LLM_PRIMARY_OUTPUT_HEADER = "ENUM Definition:"
    LLM_REFLECTION_HEADER = "ENUM Notes:"
    DOSSIER_CONFIG = DOSSIER_CONFIG

    def __init__(self, session_id: Optional[str] = None):
        super().__init__(
            name="Enum",
            system_prompt=ENUM_SYSTEM_PROMPT,
            session_id=session_id,
            operational_tier="T2",
            enable_self_learning=True
        )

    def process_thought(
        self,
        prompt_or_raw_text: str,
        category: Optional[str] = None,
        session_id: Optional[str] = None,
        source_vd_path: Optional[Path] = None,
        source_vd_frontmatter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        effective_session_id = session_id or self.session_id
        self.logger.info(f"Enum processing. Input preview: '{prompt_or_raw_text[:70]}...'")

        # Extract basic keywords from the prompt to help with enum naming
        keywords = []
        try:
            import re
            words = re.findall(r"[A-Za-z]{4,}", prompt_or_raw_text)
            keywords = list({w.upper() for w in words})[:6]  # top unique words
        except Exception:
            pass

        contextual_prompt = (
            f"INPUT CATEGORY: {category or 'general'}\n"
            f"KEY CONCEPTS: {', '.join(keywords) if keywords else 'N/A'}\n\n"
            f"PROMPT CONTENT:\n{prompt_or_raw_text}\n\n"
            "TASK: Create a JSON ENUM definition where:\n"
            "• enum_name is based on the CATEGORY and KEY CONCEPTS, in SCREAMING_SNAKE_CASE.\n"
            "• Do NOT reuse any enum_name from previous unrelated prompts.\n"
            "• description concisely states the ENUM's purpose.\n"
            "• values[] contain distinct, context-relevant entries, each with:\n"
            "    - name\n"
            "    - description\n"
            "    - aliases (if applicable)\n"
            "• Output only valid JSON — no commentary or markdown fences.\n"
        )

        refined_output = self.refine_text_with_llm(
            text_to_refine=contextual_prompt,
            llm_system_prompt=self.prompt,
            current_session_id=effective_session_id
        )

        fingerprint = self.generate_fingerprint(refined_output or prompt_or_raw_text, f"enum_output_{effective_session_id}")
        if not refined_output:
            error_msg = "❌ [Enum] Failed to generate ENUM definition."
            self.logger.error(error_msg)
            return {
                "text": error_msg,
                "professor_id": self.name,
                "session_id": effective_session_id,
                "metadata_for_dossier": {
                    "fingerprint": fingerprint,
                    "entry_type": "prof_enum_error",
                    "display_title_hint": f"ENUM Error for '{prompt_or_raw_text[:30]}...'",
                    "error_message": error_msg,
                    "_agent_success": False,
                    "timestamp_utc": college_utc_timestamp(),
                    "agent_tier": self.operational_tier
                }
            }

        return {
            "text": refined_output,
            "professor_id": self.name,
            "session_id": effective_session_id,
            "timestamp_utc": college_utc_timestamp(),
            "category": category or "enum",
            "metadata_for_dossier": {
                "fingerprint": fingerprint,
                "entry_type": "prof_enum_output",
                "display_title_hint": f"{DOSSIER_CONFIG['display_title_prefix']} for '{prompt_or_raw_text[:25]}...'",
                "professor_output_key": DOSSIER_CONFIG["full_text_key"],
                DOSSIER_CONFIG["full_text_key"]: refined_output,
                "source_vd_path_ref": str(source_vd_path) if source_vd_path else None,
                "refinement_prompt": prompt_or_raw_text,
                "_agent_success": True,
                "agent_tier": self.operational_tier
            }
        }


# === Hook (for runners) ===
def process_with_enum(prompt_or_raw_text: str, category: Optional[str] = None, session_id: Optional[str] = None,
                      source_vd_path: Optional[Path] = None, source_vd_frontmatter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not PROFESSOR_BASE_AVAILABLE:
        return {
            "text": "ERROR: ProfessorBase missing for Enum.",
            "metadata_for_dossier": {"error": "ProfessorBase missing."}
        }
    try:
        return ProfEnum(session_id=session_id).process_thought(
            prompt_or_raw_text=prompt_or_raw_text,
            category=category,
            session_id=session_id,
            source_vd_path=source_vd_path,
            source_vd_frontmatter=source_vd_frontmatter
        )
    except Exception as e:
        logging.getLogger("process_with_enum_hook").error(f"Enum Hook Error: {e}", exc_info=True)
        return {
            "text": f"❌ Hook Error: {e}",
            "error": str(e),
            "professor_id": "Enum_HookError",
            "session_id": session_id,
            "metadata_for_dossier": {
                "fingerprint": hashlib.sha256(f"enum_hook_error_{session_id}".encode()).hexdigest()[:16],
                "entry_type": "prof_enum_hook_error",
                "display_title_hint": f"Hook Error for: {prompt_or_raw_text[:30]}...",
                "timestamp_utc": college_utc_timestamp(),
                "_agent_success": False
            }
        }
