# === 🧑‍🏫 COLLEGE PROFESSOR DOSSIER CONFIGURATION (for DossierWriter in CollegeCore) ===
# These define how DossierWriter (when called by CollegeCore) should format entries for each professor's output.
# Each professor module (prof_*.py) should define its own DOSSIER_CONFIG that college_core loads.
# This section here could be a fallback or a place to override, but primary source is prof_*.py files.
PROFESSOR_DOSSIER_CONFIGS_FALLBACK = { # Renamed to avoid confusion with loaded configs
    prof_name: DOSSIER_CONFIG.get(prof_name, { # Example using DOSSIER_CONFIG from prof_architect, needs generalization
        "title": f"Output from Prof. {prof_name.capitalize()}",
        "meta": ["clarity_score", "depth_score"],
        "full_text_key_template": f"full_llm_output_{prof_name}" # Generic fallback template
    }) for prof_name in PROFESSORS.keys()
}