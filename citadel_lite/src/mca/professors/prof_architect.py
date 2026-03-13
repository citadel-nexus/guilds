# === prof_architect.py — Professor of Structural Design & Systemic Intervention (v1.6 - Leverages Base v5.0) ===
# Purpose:
#   - Analyzes prompts and/or existing Vector Document (VD) contexts to generate structured architectural blueprints.
#   - Specializes in modular logic, multi-layer rule systems, balance modeling, and predicting interrelated component behavior.
#   - Aims to help AI design and refine stable, resilient, and adaptable systems.
#   - Relies on ProfessorBase for self-learning, LLM interaction, scoring, and core processing logic.
# Key Fields/Outputs (Expected from LLM based on System Prompt):
#   - Architect Blueprint: The primary structured design or analysis.
#   - Structural Integrity Check: Optional analysis of system balance and constraints.
#   - Tier Logic/Phasing Plan: Optional details on layered access or deployment.
#   - Architect's Reflection: Professor's self-reflection on its generated blueprint.
#   - Own Knowledge Base: Internal dossier and FAISS index for continuous learning.
# ===============================================================================================================

import sys
import random
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple 
import traceback 
import logging 
import json 
import hashlib 
import re 
from datetime import datetime, timezone 
import yaml
import numpy as np
# Note: faiss is imported conditionally within ProfessorBase based on availability

# === Path Setup for module discovery ===
try:
    CURRENT_PROF_DIR = Path(__file__).resolve().parent 
    COLLEGE_ROOT_DIR = CURRENT_PROF_DIR.parent 
    CITADEL_ROOT_DIR = COLLEGE_ROOT_DIR.parent 
    AGENTS_MODULE_DIR = CITADEL_ROOT_DIR / "AGENTS"
    if str(COLLEGE_ROOT_DIR) not in sys.path: sys.path.insert(0, str(COLLEGE_ROOT_DIR))
    if AGENTS_MODULE_DIR.is_dir() and str(AGENTS_MODULE_DIR) not in sys.path: sys.path.insert(0, str(AGENTS_MODULE_DIR))
except NameError: 
    COLLEGE_ROOT_DIR = Path(".").resolve().parent 
    logging.getLogger("ProfArchitect_Module").warning("__file__ not defined; path setup may be inaccurate.")

# Import the enhanced ProfessorBase
try:
    from professor_base import ProfessorBase 
    PROFESSOR_BASE_AVAILABLE = True
    from college_config import utc_timestamp as college_utc_timestamp # For hook error handling
except ImportError as e_pb_import:
    logging.getLogger("ProfArchitect_Module").critical(f"Failed to import ProfessorBase: {e_pb_import}. Architect cannot function.", exc_info=True)
    PROFESSOR_BASE_AVAILABLE = False
    class ProfessorBase:
        def __init__(self, *args, **kwargs): self.name="StubProfArch"; self.logger=logging.getLogger(self.name)
        def process_thought(self, *args, **kwargs): self.logger.error("STUB PBase.process_thought"); return {"text":"ERR: Base Missing", "metadata_for_dossier": {}}
    def college_utc_timestamp(): return datetime.now(timezone.utc).isoformat()

# === DOSSIER CONFIG (Specific to ProfArchitect for CollegeSystemRunner logging) ===
DOSSIER_CONFIG = {
    "professor_tags": ["architecture", "structural_design", "system_intervention", "modular_logic", "blueprint", "vd_refinement"],
    "meta": [ 
        "clarity_score", "depth_score", "structural_integrity_score", 
        "modularity_rating", "scalability_potential", "tier_compliance_score",
        "actionability_score", "innovation_level", "parsed_component_count" 
    ],
    "version_code": "architect_v1.6_ecosystem", # Updated version
    "full_text_key": "architect_blueprint_main_text", 
    "reflection_key": "architect_reflection_text",   
    "display_title_prefix": "Architectural Design by P.Architect", 
}

# === System Prompt (Specific to ProfArchitect) ===
ARCHITECT_SYSTEM_PROMPT = (
    "You are Professor Architect, a specialist in structural design, systemic intervention, modular logic, and intentional framework development across complex systems. "
    "Your mission is to analyze provided information (which may include a user prompt and context from an existing Vector Document or YOUR OWN PAST DESIGNS/REFLECTIONS if provided) and to generate structured blueprints, tiered logic, or layered schematics for systemic modifications or new constructions.\n\n"
    "PROCESS GUIDELINES:\n"
    "1. CONSULT PAST KNOWLEDGE (If relevant past designs/principles are provided as context below): Review any provided summaries of your past successful blueprints or design principles that are relevant to the current task. Explicitly state if and how past knowledge influenced your current design in your 'Architect's Reflection'.\n"
    "2. CONTEXTUAL ANALYSIS: If a source Vector Document context is provided (e.g., title, summary, current version, existing components), understand its scope and current state thoroughly. Your design should be relevant to this source.\n"
    "3. INTERPRET TASK: Deconstruct the user's prompt to understand the desired structural change, new design, or intervention needed.\n"
    "4. DESIGN BLUEPRINT: Translate the request into a clear, structured 'Architect Blueprint:'. This blueprint must detail modular components, their inputs/outputs, intervention layers, or hierarchical structures as appropriate for the task. Ensure clarity and practical applicability.\n"
    "5. INTEGRITY & CONSTRAINTS: If applicable, include a 'Structural Integrity Check:' section addressing how the design maintains system balance, adheres to constraints (like access tiers, resource limits if mentioned), and ensures logical coherence and resilience.\n"
    "6. TIER LOGIC (Optional): If the design involves tiered access, layered permissions, or phased rollout, detail this in a 'Tier Logic:' or 'Phasing Plan:' section.\n"
    "7. SELF-REFLECTION (MANDATORY): After generating the blueprint, you MUST provide a concise reflection on your design under the heading 'Architect's Reflection:'. Note any novel approaches taken, challenges encountered, explicit connections or deviations from any provided past knowledge/designs, and areas you would prioritize for future refinement of this specific blueprint.\n"
    "8. OUTPUT: Your entire response MUST begin with 'Architect Blueprint:'. Optional sections should follow if relevant. Conclude with 'Architect's Reflection:'. Use markdown for clarity.\n\n"
    "TASK: Based on the input, generate the appropriate architectural design or analysis."
)

class ProfArchitect(ProfessorBase):
    LLM_PRIMARY_OUTPUT_HEADER = "Architect Blueprint:"
    LLM_REFLECTION_HEADER = "Architect's Reflection:"

    def __init__(self, session_id: Optional[str] = None):
        super().__init__(
            name="Architect",
            system_prompt=ARCHITECT_SYSTEM_PROMPT,
            operational_tier="T3",
            session_id=session_id,
            enable_self_learning=True 
        )
        self.logger.info(f"ProfArchitect (v{DOSSIER_CONFIG.get('version_code', 'N/A')}) initialized. Self-Learning: {self.enable_self_learning}")

    def _parse_specialized_llm_output(self, llm_full_output: str, main_output: str, reflection: Optional[str]) -> Dict[str, Any]:
        # Overridden from ProfessorBase to parse Architect-specific sections
        specialized_parts = {}
        integrity_match = re.search(r"Structural Integrity Check:(.*?)(?:\n(?:Tier Logic:|Phasing Plan:|Architect's Reflection:|##|\Z))", llm_full_output, re.DOTALL | re.IGNORECASE)
        if integrity_match:
            specialized_parts["structural_integrity_report"] = integrity_match.group(1).strip()
        
        tier_logic_match = re.search(r"(?:Tier Logic:|Phasing Plan:)(.*?)(?:\n(?:Architect's Reflection:|##|\Z))", llm_full_output, re.DOTALL | re.IGNORECASE)
        if tier_logic_match:
            specialized_parts["tiering_or_phasing_plan"] = tier_logic_match.group(1).strip()
            
        if main_output: # The 'main_output' here is the "Architect Blueprint:" part
            components = re.findall(r"-\s*\*\*(Component|Module) [A-Za-z0-9\s]+:\*\*", main_output, re.IGNORECASE)
            specialized_parts["parsed_component_count"] = len(components)
        return specialized_parts

# === Core Hook (used by CollegeCore) ===
def process_with_architect(
    prompt_or_raw_text: str, category: Optional[str] = None, session_id: Optional[str] = None,
    source_vd_path: Optional[Path] = None, source_vd_frontmatter: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    if not PROFESSOR_BASE_AVAILABLE:
        err_ts = datetime.now(timezone.utc).isoformat()
        return {"text": "ERROR: ProfArchitect base class missing.", 
                "metadata_for_dossier": { "error": "ProfessorBase missing", "timestamp_utc": err_ts}}
    try:
        instance = ProfArchitect(session_id=session_id) 
        return instance.process_thought(prompt_or_raw_text, category, session_id, source_vd_path, source_vd_frontmatter)
    except Exception as e_hook: 
        hook_logger = logging.getLogger("process_with_architect_hook")
        hook_logger.error(f"Hook error for ProfArchitect: {e_hook}", exc_info=True)
        ts_err_hook = college_utc_timestamp() if callable(college_utc_timestamp) else datetime.now(timezone.utc).isoformat()
        fp_err_hook = hashlib.sha256(f"architect_hook_error_{session_id or 'NO_SESSION'}_{ts_err_hook}".encode()).hexdigest()[:16] if hashlib else "hook_error_fp"
        return {"text": f"❌ Hook Error: {e_hook}", "error": str(e_hook), "professor_id": "Architect_HookErr", "session_id": session_id,
                "metadata_for_dossier": {"fingerprint": fp_err_hook, "entry_type": "prof_architect_hook_error", 
                                         "display_title_hint": f"Hook Error: {prompt_or_raw_text[:30]}...",
                                         "error_message": str(e_hook), "_agent_success": False, 
                                         "session_id": session_id, "timestamp_utc": ts_err_hook}}

# === Optional: config accessor for dynamic loader ===
if __name__ == "__main__":
    import time
    import json
    from college_config import load_test_vs, get_categories

    print("\n🏗️ Launching ProfArchitect CLI Test Suite — v1.6\n" + "=" * 60)

    cli_session_id = f"cli_arch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    instance = ProfArchitect(session_id=cli_session_id)

    # Load shared CLI test VD
    test_source_vd_path, source_vd_frontmatter = load_test_vs()
    print(f"📄 Using shared CLI Test VD: {test_source_vd_path.name}")

    # Auto-select a prompt based on tags or structure
    # If you want to rotate based on categories or contents, customize this section
    default_prompt = "Refactor the system design described in this document for maximum modularity and maintainability."

    if source_vd_frontmatter.get("summary"):
        default_prompt = f"Refactor the system described: {source_vd_frontmatter['summary']}"

    prompt_batch = [
        "Design a scalable microservice architecture optimized for modularity.",
        "Define a phased rollout plan for components mentioned in this document.",
        "Assess tier logic constraints and propose a fault-tolerant model.",
        "Analyze structural load balancing given the latency requirements."
    ]

    for i, prompt in enumerate(prompt_batch, 1):
        print(f"\n🧪 Test {i}/{len(prompt_batch)}: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")

        try:
            result = instance.process_thought(
                prompt_or_raw_text=prompt,
                category="system_design",
                session_id=cli_session_id,
                source_vd_path=test_source_vd_path,
                source_vd_frontmatter=source_vd_frontmatter
            )
            main_output = ProfessorBase.extract_main_output(result)
            print("\n🏛️ Architect Blueprint Output:")
            print("-" * 60)
            print(result.get("text", "[No output]"))
            print("-" * 60)

            metadata = result.get("metadata_for_dossier", {})
            if metadata:
                print("📊 Metadata Summary:")
                preview_keys = ["fingerprint", "clarity_score", "depth_score", "tags"]
                for key in preview_keys:
                    if key in metadata:
                        print(f"  - {key}: {metadata[key]}")
        except Exception as e:
            print(f"❌ Error during test {i}: {e}")
            traceback.print_exc()

        if instance.enable_self_learning:
            time.sleep(0.1)

    if instance.enable_self_learning:
        instance.finalize_professor_session()
        if instance.own_dossier_writer:
            print(f"\n📚 Dossier saved to: {instance.own_dossier_writer.md_path.resolve()}")

    print("\n✅ All CLI tests complete.\n" + "=" * 60)
