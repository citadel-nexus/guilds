# === prof_systems.py — Professor of Logic Systems & Structural Balance (v1.1 VD-Aware) ===

import sys
import random
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple 
import traceback 
import logging 
import json # For CLI output of metadata
import hashlib # For dossier fingerprint if not from base
from college_config import utc_timestamp as college_utc_timestamp
from datetime import datetime, timezone
import hashlib

import re
# === Ensure ROOT path for imports ===
try:
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
except NameError: 
    ROOT = Path(".").resolve()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

# Import the updated ProfessorBase
try:
    from professor_base import ProfessorBase
    PROFESSOR_BASE_AVAILABLE = True
except ImportError as e_pb_import_systems: # Unique exception variable
    logging.getLogger("ProfSystems_Module").critical(f"Failed to import ProfessorBase: {e_pb_import_systems}. Systems Professor cannot function.", exc_info=True)
    PROFESSOR_BASE_AVAILABLE = False
    class ProfessorBase: 
        def __init__(self, *args, **kwargs): self.name="StubProfSystems"; self.logger=logging.getLogger(self.name)
        def process_thought(self, *args, **kwargs): 
            self.logger.error("STUB ProfessorBase.process_thought called.")
            return {"text": "ERROR: ProfessorBase not loaded for Systems Professor.", "metadata_for_dossier": {}}

# === DOSSIER CONFIG ===
DOSSIER_CONFIG = {
    "professor_tags": ["systems_thinking", "logic_systems", "structural_balance", "component_interdependencies", "system_architecture"],
    "meta": [ # Key metrics this professor might add or focus on
        "clarity_score", "depth_score", "system_coherence_score", # Example new metric
        "resilience_factor", "adaptability_index"  # Example new metrics
    ],
    "version_code": "systems_v1.1", 
    "full_text_key": "systems_schema_text", # Key for main textual output in metadata_for_dossier
    "display_title_prefix": "Systems Schema Analysis", 
    "inject_emotion_profile": False, 
    "runtime_flags": "COMPLEX_SYSTEM_ANALYSIS" 
}

# === System Prompt for Refinement ===
SYSTEMS_SYSTEM_PROMPT = (
    "You are Professor Systems, an eminent authority on modular logic, multi-layered rule systems, structural balance, emergent behaviors, and the dynamics of interrelated components. "
    "Your purpose is to assist in designing, analyzing, or refining complex systems, ensuring their stability, predictability, resilience, and adaptability.\n\n"
    "PROCESS GUIDELINES:\n"
    "1. CONTEXTUAL UNDERSTANDING: If details of an existing system or Vector Document (VD) are provided (e.g., its purpose, components, current state), thoroughly integrate this context into your analysis or design.\n"
    "2. DECONSTRUCTION/CONSTRUCTION: Based on the user's prompt and any provided context, deconstruct the request into core components, their interactions, logic networks, and interdependencies. If designing, construct these elements.\n"
    "3. SYSTEMIC PROPERTIES: Explicitly address system balance, edge-case resilience, feedback loops, potential failure modes, and future adaptability.\n"
    "4. OUTPUT STRUCTURE: Your primary output MUST begin with 'Systems Schema:'. Optionally, if critical to the analysis, include detailed sections like 'Balance Report:', 'Failure Contingency Plan:', or 'Interdependency Matrix:'.\n"
    "   Use markdown for clear, structured output (e.g., nested bullets for components, tables for matrices, bolding for emphasis).\n\n"
    "TASK: Provide your expert systems analysis or design based on the input."
)

class ProfSystems(ProfessorBase):
    def __init__(self, session_id: Optional[str] = None):
        super().__init__(
            name="Systems", # Short name
            system_prompt=SYSTEMS_SYSTEM_PROMPT,
            session_id=session_id,
            operational_tier="T3" # Systems analysis can be quite impactful
        )
        # self.logger is inherited from ProfessorBase

    def process_thought(
        self,
        prompt_or_raw_text: str,
        category: Optional[str] = None,
        session_id: Optional[str] = None,
        source_vd_path: Optional[Path] = None,
        source_vd_frontmatter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        
        effective_session_id = session_id or self.session_id
        self.logger.info(f"Systems Prof. processing. Input starts: '{prompt_or_raw_text[:70]}...'. Source VD: {source_vd_path.name if source_vd_path else 'N/A'}")

        llm_input_for_systems = f"User Request/Problem Statement: {prompt_or_raw_text}\n\n"
        analysis_target_description_sys = "the user's system query" # Renamed

        if source_vd_frontmatter:
            vd_title_sys = source_vd_frontmatter.get('title', source_vd_path.name if source_vd_path else "the source system/document") # Renamed
            vd_version_sys = source_vd_frontmatter.get('version', 'N/A') # Renamed
            # Try to get a more detailed description or summary if available
            vd_desc_sys = source_vd_frontmatter.get('description', source_vd_frontmatter.get('summary', 'No detailed description available.')) # Renamed
            analysis_target_description_sys = f"the system described in/by '{vd_title_sys}' (v{vd_version_sys})"

            llm_input_for_systems = (
                f"CONTEXT FROM EXISTING SYSTEM/VECTOR DOCUMENT:\n"
                f"- Title/Identifier: {vd_title_sys}\n"
                f"- Version: {vd_version_sys}\n"
                f"- Description/Summary: {vd_desc_sys}\n"
                f"- Key Components (if listed in frontmatter): {source_vd_frontmatter.get('components', 'N/A')}\n"
                f"- Current Known Issues (if listed): {source_vd_frontmatter.get('known_issues', 'N/A')}\n\n"
                f"USER REQUEST (relative to the above system context): {prompt_or_raw_text}\n\n"
                f"Provide your 'Systems Schema:' and other relevant sections."
            )
        
        systems_refined_text = self.refine_text_with_llm(
            text_to_refine=llm_input_for_systems,
            llm_system_prompt=self.prompt, # self.prompt is SYSTEMS_SYSTEM_PROMPT
            current_session_id=effective_session_id
        )

        prof_output_fingerprint_sys = self.generate_fingerprint(systems_refined_text or prompt_or_raw_text, f"systems_output_{effective_session_id}") # Renamed

        if not systems_refined_text:
            error_msg_sys = "Prof. Systems LLM refinement failed or produced empty output." # Renamed
            self.logger.error(error_msg_sys)
            return { # Consistent error payload
                "text": f"❌ [{self.name}] Systems analysis generation failed.", "error": error_msg_sys,
                "professor_id": self.name, "session_id": effective_session_id,
                "metadata_for_dossier": {
                    "fingerprint": prof_output_fingerprint_sys, "entry_type": f"prof_{self.name}_error",
                    "display_title_hint": f"Error in Systems for task on '{analysis_target_description_sys[:30]}...'",
                    "source_vd_fingerprint_ref": source_vd_frontmatter.get('fingerprint') if source_vd_frontmatter else None,
                    "source_vd_title_ref": source_vd_frontmatter.get('title') if source_vd_frontmatter else (source_vd_path.name if source_vd_path else None),
                    "refinement_prompt": prompt_or_raw_text, "professor_id": self.name,
                    "error_message": error_msg_sys, "_agent_success": False, "session_id": effective_session_id,
                    "timestamp_utc": college_utc_timestamp() if callable(college_utc_timestamp) else datetime.now(timezone.utc).isoformat(), 
                    "agent_tier": self.operational_tier,
                    "main_professor_text": error_msg_sys, "summary": error_msg_sys
                }
            }

        final_category_sys = category or (source_vd_frontmatter.get("domain") if source_vd_frontmatter else "systems_analysis") # Renamed
        processed_scores_tags_sys = self.post_process_scores_and_tags( # Renamed
            prompt_or_raw_text, 
            systems_refined_text, 
            final_category_sys
        )
        
        # Add Systems-specific metrics (examples)
        # processed_scores_tags_sys["system_coherence_score"] = self._calculate_coherence(systems_refined_text) 
        # processed_scores_tags_sys["resilience_factor"] = self._assess_resilience(systems_refined_text)

        output_payload_sys = { # Renamed
            "text": systems_refined_text, 
            "professor_id": self.name, "session_id": effective_session_id,
            "timestamp_utc": college_utc_timestamp() if callable(college_utc_timestamp) else datetime.now(timezone.utc).isoformat(),
            "category": final_category_sys,
            "metadata_for_dossier": {
                "fingerprint": prof_output_fingerprint_sys, "entry_type": f"prof_{self.name}_output", 
                "display_title_hint": f"{DOSSIER_CONFIG.get('display_title_prefix', 'Systems Schema')} for '{analysis_target_description_sys[:25]}...'",
                "source_vd_fingerprint_ref": source_vd_frontmatter.get('fingerprint') if source_vd_frontmatter else None,
                "source_vd_title_ref": source_vd_frontmatter.get('title') if source_vd_frontmatter else (source_vd_path.name if source_vd_path else None),
                "source_vd_path_ref": str(source_vd_path) if source_vd_path else None,
                "refinement_prompt": prompt_or_raw_text, "professor_id": self.name,
                "professor_output_key": DOSSIER_CONFIG.get("full_text_key", "systems_schema_text"),
                DOSSIER_CONFIG.get("full_text_key", "systems_schema_text"): systems_refined_text,
                f"full_llm_output_{self.name.lower()}": systems_refined_text, 
                "timestamp_utc": college_utc_timestamp() if callable(college_utc_timestamp) else datetime.now(timezone.utc).isoformat(),
                "session_id": effective_session_id, "_agent_success": True,
                "agent_tier": self.operational_tier,
                **processed_scores_tags_sys
            }
        }
        self.logger.info(f"Systems Prof. processing complete. Output preview: {systems_refined_text[:70]}...")
        return output_payload_sys

# === Core Hook (used by CollegeCore) ===
def process_with_systems(
    prompt_or_raw_text: str,
    category: Optional[str] = None,
    session_id: Optional[str] = None,
    source_vd_path: Optional[Path] = None,
    source_vd_frontmatter: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    if not PROFESSOR_BASE_AVAILABLE:
        return {"text": "ERROR: ProfSystems cannot operate, ProfessorBase missing.", 
                "metadata_for_dossier": {"error": "ProfessorBase missing for Systems Prof."}}
    try:
        systems_instance = ProfSystems(session_id=session_id) 
        return systems_instance.process_thought(
            prompt_or_raw_text=prompt_or_raw_text, category=category, session_id=session_id,
            source_vd_path=source_vd_path, source_vd_frontmatter=source_vd_frontmatter
        )
    except Exception as e_hook_sys: # Corrected variable name
        hook_logger_sys = logging.getLogger("process_with_systems_hook") # Corrected logger name
        hook_logger_sys.error(f"Error in process_with_systems hook: {e_hook_sys}", exc_info=True)
        return { # Consistent error structure
            "text": f"❌ Error in ProfSystems hook: {e_hook_sys}", "error": str(e_hook_sys),
            "professor_id": "Systems_HookError", "session_id": session_id,
            "metadata_for_dossier": {
                "fingerprint": hashlib.sha256(f"systems_hook_error_{session_id or 'NO_SESSION'}".encode()).hexdigest()[:16],
                "entry_type": "prof_systems_hook_error", 
                "display_title_hint": f"Hook Error for Systems: {prompt_or_raw_text[:30]}...",
                "error_message": f"Hook-level error: {str(e_hook_sys)}",
                "_agent_success": False, "session_id": session_id,
                "timestamp_utc": college_utc_timestamp() if callable(college_utc_timestamp) else datetime.now(timezone.utc).isoformat()
            }
        }

# === Optional: config accessor for dynamic loader ===
def get_dossier_config():
    return DOSSIER_CONFIG

# === CLI Mode ===
if __name__ == "__main__":
    cli_logger_sys = logging.getLogger("ProfSystems_CLI") # Corrected
    if not cli_logger_sys.hasHandlers():
         logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')

    if not PROFESSOR_BASE_AVAILABLE:
        cli_logger_sys.critical("ProfessorBase is not available. CLI mode for Systems Prof. cannot run.")
        sys.exit(1)
        
    cli_logger_sys.info("⚙️ Launching ProfSystems logic grid constructor (CLI mode)...")
    
    try:
        # Use college_config if available for categories, else fallback
        # This assumes college_config might not be in the path for direct CLI run of a professor
        if 'college_config' in sys.modules:
            from college_config import get_categories as cli_get_categories_sys # Corrected
            categories_cli_sys = cli_get_categories_sys() # Corrected
        else: # Fallback if college_config could not be imported by the top-level try-except
            cli_logger_sys.warning("college_config.get_categories not available for CLI. Using default.")
            categories_cli_sys = ["system_design_cli_test"]
    except Exception as e_cat_imp: # More general exception for category import
        cli_logger_sys.warning(f"Could not get categories via college_config: {e_cat_imp}. Using default.")
        categories_cli_sys = ["system_design_cli_test_fallback"]
        
    selected_category_cli_sys = random.choice(categories_cli_sys) # Corrected
    cli_logger_sys.info(f"🎯 Selected category for CLI test: {selected_category_cli_sys}")

    test_source_vd_path_sys = ROOT / "test_vds_for_refinement" / "sample_system_spec.md" # Corrected
    test_source_vd_path_sys.parent.mkdir(parents=True, exist_ok=True)
    source_vd_frontmatter_sys = None # Corrected
    cli_prompt_input_sys = "" # Corrected

    if not test_source_vd_path_sys.exists():
        with open(test_source_vd_path_sys, "w", encoding="utf-8") as f_dummy_sys: # Corrected
            f_dummy_sys.write("---\ntitle: Basic Data Pipeline Spec\nversion: 0.5\nauthor: CLI_User\ntags: [data_pipeline, ETL, draft]\ncomponents: [Ingestion, Transformation, Storage]\nknown_issues: [Bottleneck at transformation stage]\n---\n# Data Pipeline Overview\nThis system processes raw data logs...\n")
        cli_logger_sys.info(f"Created dummy source VD for Systems CLI: {test_source_vd_path_sys}")

    if test_source_vd_path_sys.exists():
        cli_logger_sys.info(f"Source VD found for CLI test: {test_source_vd_path_sys}")
        try:
            # Simplified frontmatter loading for CLI test
            with open(test_source_vd_path_sys, 'r', encoding='utf-8') as f_cli_sys: content_cli_sys = f_cli_sys.read() # Renamed
            match_cli_sys = re.search(r'^---\s*\n(.*?)\n^---\s*$', content_cli_sys, re.DOTALL | re.MULTILINE) # Renamed
            if match_cli_sys: 
                import yaml # Ensure yaml is imported for CLI test if not globally
                source_vd_frontmatter_sys = yaml.safe_load(match_cli_sys.group(1)) or {}
            
            if source_vd_frontmatter_sys:
                cli_logger_sys.info(f"Loaded frontmatter from CLI source VD: Title '{source_vd_frontmatter_sys.get('title', 'N/A')}'")
                cli_prompt_input_sys = f"Propose a revised Systems Schema for '{source_vd_frontmatter_sys.get('title', test_source_vd_path_sys.stem)}' to improve its resilience and address known issues: {source_vd_frontmatter_sys.get('known_issues')}."
            else:
                cli_prompt_input_sys = f"Design a system to manage the components described in: {test_source_vd_path_sys.name}"
        except Exception as e_cli_fm_sys: # Renamed
            cli_logger_sys.error(f"Error loading frontmatter for CLI test VD {test_source_vd_path_sys}: {e_cli_fm_sys}")
            cli_prompt_input_sys = f"Design a system for {test_source_vd_path_sys.name} (FM load failed)."
    else:
        cli_logger_sys.warning(f"Test source VD not found at {test_source_vd_path_sys}. Using generic prompt.")
        cli_prompt_input_sys = input("[ProfSystems_CLI] 🔧 Enter a system design challenge or structure to balance:\n> ").strip()

    if not cli_prompt_input_sys:
        cli_logger_sys.warning("No input provided. Exiting CLI test.")
    else:
        cli_logger_sys.info(f"CLI Input/Prompt: {cli_prompt_input_sys[:100]}...")
        try:
            result_cli_sys = process_with_systems( # Corrected
                cli_prompt_input_sys, 
                category=selected_category_cli_sys,
                session_id="cli_systems_session_" + datetime.now().strftime("%Y%m%d%H%M%S"),
                source_vd_path=test_source_vd_path_sys if test_source_vd_path_sys.exists() else None,
                source_vd_frontmatter=source_vd_frontmatter_sys
            )
            print("\n[ProfSystems_CLI] ⚙️ Systems Schema Result:")
            print("---------------------------------------------")
            main_output_text_sys = result_cli_sys.get("text", "[No textual output from professor]") # Corrected
            print(main_output_text_sys)
            print("---------------------------------------------")
            
            if result_cli_sys.get("metadata_for_dossier"):
                print("\n[ProfSystems_CLI] Metadata for Dossier (if it were logged):")
                print(json.dumps(result_cli_sys["metadata_for_dossier"], indent=2, ensure_ascii=False))
            else:
                print("\n[ProfSystems_CLI] No 'metadata_for_dossier' key in result.")

        except Exception as e_cli_proc_sys: # Corrected
            cli_logger_sys.critical(f"Error during ProfSystems CLI processing: {e_cli_proc_sys}", exc_info=True)