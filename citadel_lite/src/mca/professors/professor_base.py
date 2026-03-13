
# === professor_base.py — UNIVERSAL PROFESSOR SUPERCLASS v5.2 (Stabilized - Enhanced Self-Log Diagnostics) ===
# Purpose:
# - Provides a highly integrated and robust base for all College Professors.
# - Handles core imports, LLM interaction, scoring, tagging, and detailed logging.
# - Implements a full self-learning loop (own Dossier & FAISS KB with consent awareness).
# - Standardizes output structure for College Core and external DossierWriter instances.
# - Designed for lean subclasses that focus on their specific expertise (system_prompt).
# ===========================================================================================
import sys
import time
import random
import secrets
import json
import hashlib
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Union
import re
from collections import Counter
import logging
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import inspect # or fallback to OpenAI embeddings for keyword extraction
# --- Module-Level Overrides & Configuration ---
SELF_FAISS_VECTOR_DIM = 1536 # System-aligned embedding dimension for self-KB
# self_embedding_model is initialized to None in __init__ and uses college_embed_text
# --- Module-Level Logging Setup ---
module_logger = logging.getLogger("ProfessorBaseModule")
if not logging.getLogger().hasHandlers(): # Ensure root logger has a handler if not configured elsewhere
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
# --- Path Setup ---
try:
    CURRENT_PROF_MODULE_DIR = Path(__file__).resolve().parent
    COLLEGE_ROOT_DIR = CURRENT_PROF_MODULE_DIR.parent
    CITADEL_ROOT_DIR = COLLEGE_ROOT_DIR.parent
    AGENTS_MODULE_DIR = CITADEL_ROOT_DIR / "AGENTS"
    # Ensure paths are added to sys.path if they are directories and not already present
    for p_dir_str in [str(COLLEGE_ROOT_DIR), str(AGENTS_MODULE_DIR)]:
        p_dir = Path(p_dir_str)
        if p_dir.is_dir() and p_dir_str not in sys.path:
            sys.path.insert(0, p_dir_str)
    module_logger.debug(f"ProfessorBase sys.path configured. College Root: {COLLEGE_ROOT_DIR}, Agents Dir: {AGENTS_MODULE_DIR}")
except NameError:
    COLLEGE_ROOT_DIR = Path(".").resolve().parent
    module_logger.warning(f"__file__ not defined. Path setup for ProfessorBase might be inaccurate. Using CWD-relative: {COLLEGE_ROOT_DIR}")
# --- Attempt Core College System Imports ---
try:
    from college_config import (utc_timestamp as college_utc_timestamp, DATA_PATHS as COLLEGE_DATA_PATHS, MEMORY as COLLEGE_MEMORY, get_categories as get_college_categories, PROFESSORS as COLLEGE_PROFESSORS_REGISTRY)
    from college_keys import API_KEYS as COLLEGE_API_KEYS, COMPLETION_MODEL as COLLEGE_COMPLETION_MODEL
    _CORE_COLLEGE_UTILS_AVAILABLE = True
    module_logger.info("Core College config and keys successfully imported into ProfessorBase.")
except ImportError as e:
    print("⚠️ [ProfessorBase] Failed to import core college_config or college_keys: {e}. Using stubs.")
    _CORE_COLLEGE_UTILS_AVAILABLE = False
    def college_utc_timestamp(): return datetime.now(timezone.utc).isoformat()
    COLLEGE_DATA_PATHS = {"logs": Path("./stub_logs_prof_base"), "professors_memory_dossiers": Path("./stub_prof_mem_base"), "error_log_db": Path("./db/error_log.db")}
    COLLEGE_MEMORY = {"vector_dimension": 1536, "default_index_name":"stub.index"}
    COLLEGE_API_KEYS = ["STUB_API_KEY_BASE_CRITICAL_FALLBACK"]
    COLLEGE_COMPLETION_MODEL = "stub_model_base_critical_fallback"
    def get_college_categories(): return ["general_stub_base_fallback"]
    COLLEGE_PROFESSORS_REGISTRY = {}
# Attempt to import extract_keywords from college_config first
try:
    from college_config import extract_keywords as college_extract_keywords
    module_logger.info("Using extract_keywords from college_config.")
except ImportError:
    module_logger.warning("college_config.extract_keywords not found. Will use TF-IDF fallback defined in ProfessorBase.")
    college_extract_keywords = None
if college_extract_keywords is None:
    def tfidf_extract_keywords_fallback(text: str, top_n: int = 10) -> List[str]:
        if not text or not isinstance(text, str): return []
        keyword_count = 0
        vectorizer = TfidfVectorizer(stop_words='english', max_features=top_n*2)
        try:
            tfidf_matrix = vectorizer.fit_transform([text])
            feature_array = np.array(vectorizer.get_feature_names_out())
            if not feature_array.any(): return []
            scores = tfidf_matrix.toarray()[0]
            top_indices = np.argsort(scores)[-top_n:][::-1]
            return [feature_array[i] for i in top_indices if scores[i] > 0.05]
        except ValueError as ve:
            module_logger.debug(f"TF-IDF fallback for extract_keywords encountered ValueError: {ve}. Text: '{text[:50]}...'")
            return []
        except Exception as e:
            module_logger.error(f"TF-IDF fallback for extract_keywords failed: {e}. Text: '{text[:50]}...'")
            return []
    extract_keywords = tfidf_extract_keywords_fallback
    module_logger.info("Initialized TF-IDF fallback for extract_keywords in ProfessorBase.")
else:
    extract_keywords = college_extract_keywords
# --- Attempt LLM Utilities (OpenAI, httpx) ---
try:
    import httpx
    from openai import OpenAI, RateLimitError, APIConnectionError, APITimeoutError, APIStatusError
    if _CORE_COLLEGE_UTILS_AVAILABLE and \
       COLLEGE_API_KEYS and isinstance(COLLEGE_API_KEYS, list) and len(COLLEGE_API_KEYS) > 0 and \
       COLLEGE_API_KEYS[0] and "STUB" not in str(COLLEGE_API_KEYS[0]).upper() and \
       COLLEGE_COMPLETION_MODEL:
        _LLM_UTILS_AVAILABLE = True
        module_logger.info("OpenAI client library and API keys appear configured for ProfessorBase.")
    else:
        _LLM_UTILS_AVAILABLE = False
        module_logger.warning("OpenAI library loaded, but API keys/model might be missing/stubbed. LLM calls from ProfessorBase disabled.")
except ImportError:
    _LLM_UTILS_AVAILABLE = False
    OpenAI = None; httpx = None
    RateLimitError = APIConnectionError = APITimeoutError = APIStatusError = Exception
    module_logger.warning("OpenAI or httpx library not found. LLM-based refinement disabled in ProfessorBase.")
# === 📦 Vector Store & Embedding Utilities (FAISS, embedder, vector_store) ===
SentenceTransformer = None
try:
    import faiss
    from embedder import embed_text as college_embed_text
    from vector_store import add_to_index as prof_add_to_index, get_index as prof_get_index
    _VECTOR_STORE_UTILS_AVAILABLE = True
    module_logger.info("✅ Vector Store utilities loaded: FAISS, embedder.py, vector_store.py.")
except ImportError as e:
    module_logger.warning(f"⚠️ Vector Store components (FAISS/embedder/vector_store) not fully available: {e}. Vector ops will be stubbed.", exc_info=True)
    _VECTOR_STORE_UTILS_AVAILABLE = False
    def college_embed_text(text, model_name=None): module_logger.error("STUB: college_embed_text called."); return np.zeros(SELF_FAISS_VECTOR_DIM, dtype=np.float32) if SELF_FAISS_VECTOR_DIM else np.array([])
    def prof_add_to_index(*args, **kwargs): module_logger.error("STUB: prof_add_to_index called."); return None
    def prof_get_index(*args, **kwargs):
        class StubIndex: ntotal = 0; d = SELF_FAISS_VECTOR_DIM
        module_logger.error("STUB: prof_get_index called."); return (StubIndex(), None, Path("./stub.faiss"), Path("./stub_map.json"))
    faiss = None
# --- Attempt DossierWriter for Self-Logging ---
try:
    from md_writer import DossierWriter
    _SELF_DOSSIER_UTILS_AVAILABLE = True
    module_logger.info("DossierWriter (md_writer) loaded for ProfessorBase self-logging.")
except ImportError:
    _SELF_DOSSIER_UTILS_AVAILABLE = False
    class DossierWriter:
        def __init__(self, *args, **kwargs):
            self.md_path = Path(kwargs.get("base_dir", "./stub_dossiers_prof_base")) / f"{kwargs.get('domain','stub_domain_prof_base')}.md"
            self.logger = logging.getLogger(f"StubDossierProfBase.{kwargs.get('domain','stub_domain_prof_base')}")
            self.logger.warning(f"STUB DossierWriter initialized for domain '{kwargs.get('domain','stub_domain_prof_base')}' at {self.md_path}")
        def add_entry(self, *args, **kwargs): self.logger.warning(f"STUB: DossierWriter.add_entry called for '{self.md_path.name}'."); return "stub_fp_on_add_entry_success" # Return a mock FP
        def finalize_dossier(self, *args, **kwargs): self.logger.warning(f"STUB: DossierWriter.finalize_dossier called for '{self.md_path.name}'.")
    module_logger.warning("md_writer.DossierWriter not found. Professor self-dossiering will use stubs.")
# ──────────────────────────────────────────────────────────────────────────────
# 🔐 Attempt to Load Citadel Security Utilities
# ──────────────────────────────────────────────────────────────────────────────
try:
    from citadel_security import (
        Guardian, load_vd_metadata_from_file, VDFormatError, ConsentViolationError, CitadelSecurityError
    )
    _CITADEL_SECURITY_UTILS_AVAILABLE = True
    module_logger.info("Citadel Security (Guardian, etc.) loaded for ProfessorBase.")
except ImportError:
    # Fallback stubs if Citadel security tools are not available
    _CITADEL_SECURITY_UTILS_AVAILABLE = False
    Guardian = None
    def load_vd_metadata_from_file(path): module_logger.warning(f"STUB: load_vd_metadata_from_file({path})"); return {}
    class CitadelSecurityError(Exception): pass
    class VDFormatError(CitadelSecurityError): pass
    class ConsentViolationError(CitadelSecurityError): pass
    module_logger.warning("citadel_security components not found. "
                          "VD loading and internal Guardian checks limited in ProfessorBase.")
ALL_CATEGORIES = get_college_categories() if _CORE_COLLEGE_UTILS_AVAILABLE and callable(get_college_categories) else ["general_fallback_prof_base"]
class ProfessorBase:
    IS_CORE_COLLEGE_UTILS_LOADED: bool = _CORE_COLLEGE_UTILS_AVAILABLE
    IS_LLM_ENABLED: bool = _LLM_UTILS_AVAILABLE
    IS_VECTOR_STORE_ENABLED: bool = _VECTOR_STORE_UTILS_AVAILABLE
    CAN_SELF_DOSSIER: bool = _SELF_DOSSIER_UTILS_AVAILABLE
    CAN_TAG_KEYWORDS: bool = callable(extract_keywords)
    CAN_USE_CITADEL_SECURITY: bool = _CITADEL_SECURITY_UTILS_AVAILABLE
    BASE_DOSSIER_CONFIG: Dict[str, Any] = {
        "professor_tags": ["base_professor", "ai_refined"],
        "meta": ["clarity_score", "depth_score", "word_count", "token_count_llm_output"],
        "version_code": "prof_base_v5.2_diagnostics", # Updated version
        "full_text_key": "main_professor_output_text",
        "reflection_key": "professor_reflection_text",
        "display_title_prefix": "Refined Output from Professor",
        "inject_emotion_profile": False,
        "runtime_flags": "STANDARD_PROCESSING"
    }
    LLM_PRIMARY_OUTPUT_HEADER: str = "Refined Output:"
    LLM_REFLECTION_HEADER: str = "Self-Reflection:"
    SELF_FAISS_VECTOR_DIM: int = SELF_FAISS_VECTOR_DIM
    def __init__(self, name: str, system_prompt: str, operational_tier: str = 'T2', session_id: Optional[str] = None, enable_self_learning: bool = True, guardian_instance_for_self_kb: Optional['Guardian'] = None ):
        self.name = name
        self.system_prompt = system_prompt
        self.prompt = system_prompt # Legacy support for old professors
        self.operational_tier = operational_tier
        self.logger = logging.getLogger(f"Professor.{self.name}")
        ts_format = college_utc_timestamp().replace(":", "").replace("-", "").replace(".", "")[:19]
        self.session_id = session_id or f"prof_{self.name.replace(' ', '_')}_{ts_format}"
        self.max_retries_llm = 3
        self.log_path_activity: Optional[Path] = None
        try:
            log_dir_base = COLLEGE_DATA_PATHS.get("logs", Path("./professor_logs_fallback_base"))
            prof_log_dir = log_dir_base / "professor_activity" / self.name.lower().replace(" ", "_")
            prof_log_dir.mkdir(parents=True, exist_ok=True)
            self.log_path_activity = prof_log_dir / f"activity_{self.session_id}.jsonl"
        except Exception as e_mkdir:
            self.logger.error(f"Could not create activity log directory: {e_mkdir}", exc_info=True)
            self.log_path_activity = Path(f"./prof_{self.name.lower().replace(' ', '_')}_activity_fallback.jsonl")
        self.enable_self_learning = (
            enable_self_learning
            and self.IS_CORE_COLLEGE_UTILS_LOADED
            and self.CAN_SELF_DOSSIER
            and self.IS_VECTOR_STORE_ENABLED
            and callable(college_embed_text)
        )
        if enable_self_learning and not self.enable_self_learning:
            self.logger.warning("Self-learning requested but initially disabled due to missing core utilities/prerequisites.")
        self.knowledge_base_domain = f"prof_{self.name.lower().replace(' ', '_')}_internal_kb"
        self.own_dossier_writer: Optional[DossierWriter] = None
        self.own_faiss_index: Optional[Any] = None
        self.own_faiss_id_map: Dict[int, Dict[str, str]] = {}
        self.own_faiss_index_path: Optional[Path] = None
        self.own_faiss_id_map_path: Optional[Path] = None
        self.self_embedding_model = None
        self.guardian_internal: Optional['Guardian'] = guardian_instance_for_self_kb
        self._ensure_error_log_schema()
        if self.enable_self_learning:
            self._initialize_self_learning_resources()
        if self.enable_self_learning and not self.guardian_internal and self.CAN_USE_CITADEL_SECURITY and Guardian:
            try:
                self.guardian_internal = Guardian(default_system_tier=self.operational_tier)
                self.logger.info("Initialized internal Guardian for self-KB.")
            except Exception as e_g_int:
                self.logger.error(f"Failed to initialize internal Guardian: {e_g_int}", exc_info=True)
                self.enable_self_learning = False
                self.logger.warning("Self-learning disabled due to internal Guardian initialization failure.")
        self.logger.info(f"Professor '{self.name}' Initialized. Session: {self.session_id}, Tier: {self.operational_tier}, Self-Learning Active: {self.enable_self_learning}")
    def _ensure_error_log_schema(self):
        try:
            db_path = COLLEGE_DATA_PATHS.get("error_log_db", Path("./college_data/db/error_log.db"))
            db_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
            if not db_path: return
            import sqlite3
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                professor TEXT,
                error_type TEXT,
                error_message TEXT,
                context TEXT,
                session_id TEXT
            );
            """)
            conn.commit()
            # Check for missing columns and add if necessary
            cur.execute("PRAGMA table_info(error_log)")
            cols = {row[1] for row in cur.fetchall()}
            if "error_type" not in cols:
                cur.execute("ALTER TABLE error_log ADD COLUMN error_type TEXT;")
                conn.commit()
                self.logger.info("Added missing column 'error_type' to error_log table.")
            if "context" not in cols:
                cur.execute("ALTER TABLE error_log ADD COLUMN context TEXT;")
                conn.commit()
                self.logger.info("Added missing column 'context' to error_log table.")
            if "session_id" not in cols:
                cur.execute("ALTER TABLE error_log ADD COLUMN session_id TEXT;")
                conn.commit()
                self.logger.info("Added missing column 'session_id' to error_log table.")
            conn.close()
            self.logger.info(f"Ensured error_log schema in {db_path}")
        except Exception as e:
            self.logger.error(f"Could not ensure error_log schema: {e}")
    def _initialize_self_learning_resources(self):
        if not self.enable_self_learning:
            self.logger.debug(f"[{self.name}] Skipping self-learning resource initialization as it's disabled.")
            return
        # DossierWriter for Self-KB
        if self.CAN_SELF_DOSSIER and DossierWriter:
            try:
                base_prof_mem_path = COLLEGE_DATA_PATHS.get("professors_memory_dossiers")
                if not (base_prof_mem_path and isinstance(base_prof_mem_path, Path) and base_prof_mem_path.is_dir()):
                    fallback_base = (COLLEGE_ROOT_DIR or Path(".")) / "data_fallback_prof_base" / "prof_memory"
                    fallback_base.mkdir(parents=True, exist_ok=True)
                    self.logger.warning(f"[{self.name}] 'professors_memory_dossiers' path error or not a dir. Using fallback: {fallback_base}")
                    base_prof_mem_path = fallback_base
                prof_dossier_dir_name = self.name.lower().replace(" ", "_")
                prof_dossier_dir = base_prof_mem_path / prof_dossier_dir_name
                prof_dossier_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"[{self.name}] Ensured self-dossier directory exists: {prof_dossier_dir}")
                self.own_dossier_writer = DossierWriter(
                    domain=self.knowledge_base_domain,
                    agent_id=f"Prof_{self.name}_KMSelf",
                    base_dir=str(prof_dossier_dir),
                    citadel_schema_version=f"ProfKB_{self.name}_v1.2",
                    guardian_instance=self.guardian_internal
                )
                self.logger.info(f"[{self.name}] Initialized self-dossier at {self.own_dossier_writer.md_path.resolve() if self.own_dossier_writer else 'N/A'}")
            except Exception as e:
                self.logger.error(f"[{self.name}] Failed to initialize self-dossier: {e}", exc_info=True)
                self.own_dossier_writer = None
                self.enable_self_learning = False
                self.logger.warning(f"[{self.name}] Self-learning disabled due to DossierWriter initialization failure.")
        else:
            self.logger.warning(f"[{self.name}] DossierWriter class not available or CAN_SELF_DOSSIER is false. Self-dossiering disabled.")
            self.enable_self_learning = False
        if self.enable_self_learning and self.IS_VECTOR_STORE_ENABLED and faiss and callable(prof_get_index) and callable(college_embed_text):
            try:
                # Ensure the directory for this specific professor's FAISS index exists
                # This aligns with how DossierWriter might create its path
                faiss_index_base_dir = COLLEGE_DATA_PATHS.get("vector_indexes", Path("./vector_indexes_fallback"))
                prof_faiss_dir = faiss_index_base_dir / self.name.lower().replace(" ", "_") # Subdirectory per professor
                prof_faiss_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"[{self.name}] Ensured FAISS index directory: {prof_faiss_dir} for domain '{self.knowledge_base_domain}'")
                # Pass the specific directory to prof_get_index if it supports a base_path argument,
                # otherwise prof_get_index needs to be aware of this structure or use a global dir.
                # For this example, assuming prof_get_index handles domain-to-path mapping within a configured global dir.
                index_data = prof_get_index(self.knowledge_base_domain, dim=self.SELF_FAISS_VECTOR_DIM)
                if index_data is None:
                    raise ValueError(f"prof_get_index returned None for own KB '{self.knowledge_base_domain}'.")
                idx, lock, path_obj, id_map_path_obj = None, None, None, None
                if len(index_data) == 4:
                    idx, lock, path_obj, id_map_path_obj = index_data
                    if isinstance(path_obj, str): path_obj = Path(path_obj)
                    if isinstance(id_map_path_obj, str): id_map_path_obj = Path(id_map_path_obj)
                else:
                    raise ValueError(f"prof_get_index returned unexpected number of items: {len(index_data)}")
                self.own_faiss_index = idx
                self.own_faiss_index_path = path_obj
                self.own_faiss_id_map_path = id_map_path_obj
                self.logger.info(f"[{self.name}] Attempting to load FAISS ID map from: {self.own_faiss_id_map_path}")
                if self.own_faiss_id_map_path and self.own_faiss_id_map_path.exists():
                    try:
                        with open(self.own_faiss_id_map_path, 'r', encoding='utf-8') as f_map:
                            self.own_faiss_id_map = {int(k):v for k,v in json.load(f_map).items()}
                        self.logger.info(f"[{self.name}] FAISS ID map loaded {len(self.own_faiss_id_map)} entries.")
                    except (json.JSONDecodeError, ValueError) as e_json_map:
                        self.logger.error(f"[{self.name}] Error loading or parsing FAISS ID map {self.own_faiss_id_map_path}: {e_json_map}. Re-initializing map.")
                        self.own_faiss_id_map = {}
                if self.own_faiss_index and hasattr(self.own_faiss_index, 'd') and self.own_faiss_index.d != self.SELF_FAISS_VECTOR_DIM:
                    self.logger.warning(
                        f"[{self.name}] Existing FAISS index dimension ({self.own_faiss_index.d}) for '{self.knowledge_base_domain}' "
                        f"does not match SELF_FAISS_VECTOR_DIM ({self.SELF_FAISS_VECTOR_DIM}). Re-initializing index."
                    )
                    if faiss:
                        self.own_faiss_index = faiss.IndexFlatL2(self.SELF_FAISS_VECTOR_DIM)
                        self.own_faiss_id_map = {}
                elif not self.own_faiss_index and faiss:
                    self.logger.info(f"[{self.name}] No existing FAISS index found by prof_get_index for '{self.knowledge_base_domain}'. Initializing new index.")
                    self.own_faiss_index = faiss.IndexFlatL2(self.SELF_FAISS_VECTOR_DIM)
                    self.own_faiss_id_map = {}
                self.logger.info(
                    f"[{self.name}] Own FAISS index '{self.knowledge_base_domain}' "
                    f"(Size: {self.own_faiss_index.ntotal if self.own_faiss_index else 'N/A'}, "
                    f"Dim: {self.own_faiss_index.d if self.own_faiss_index else 'N/A'}) "
                    f"loaded/initialized. Path: {self.own_faiss_index_path}"
                )
            except Exception as e_f:
                self.logger.error(f"[{self.name}] Failed to initialize/load own FAISS resources for '{self.knowledge_base_domain}': {e_f}", exc_info=True)
                self.own_faiss_index = None
                self.enable_self_learning = False
                self.logger.warning(f"[{self.name}] Self-learning disabled due to FAISS initialization failure.")
        elif self.enable_self_learning:
            self.logger.warning(f"[{self.name}] FAISS utilities not available or other pre-conditions not met. FAISS for self-learning disabled.")
            self.enable_self_learning = False
        self.logger.info(f"[{self.name}] Post _initialize_self_learning_resources: self.enable_self_learning = {self.enable_self_learning}")
    def generate_fingerprint(self, text: str, context: str = "") -> str:
        return hashlib.sha256(f"{text}{context}{self.name}{self.session_id}".encode("utf-8")).hexdigest()[:24]
    def _log_activity(self, event_type: str, data: Dict[str, Any]):
        if not self.log_path_activity:
            self.logger.debug(f"[{self.name}] Activity log path not set, cannot log event: {event_type}")
            return
        log_entry = {
            "timestamp": college_utc_timestamp(),
            "session_id": self.session_id,
            "professor_name": self.name,
            "event_type": event_type,
            "data": data
        }
        try:
            self.log_path_activity.parent.mkdir(parents=True, exist_ok=True) # Ensure dir exists
            with open(self.log_path_activity, "a", encoding="utf-8") as f:
                json.dump(log_entry, f, ensure_ascii=False) # ensure_ascii=False for broader char support
                f.write("\n")
        except Exception as e:
            self.logger.error(f"[{self.name}] Failed to write to activity log {self.log_path_activity}: {e}")
    # ... (Scoring methods: _semantic_density, _sentence_complexity, _lexical_diversity, _generate_self_grade_feedback remain the same) ...
    # ... (post_process_scores_and_tags remains the same) ...
    # ... (refine_text_with_llm remains the same) ...
    # ... (_parse_llm_output remains the same) ...
    # ... (embed_text_for_self_kb remains the same) ...
    # ... (_query_own_knowledge remains the same) ...
    def _semantic_density(self, text: str) -> float:
        words = text.split()
        if not words: return 0.0
        keyword_count = 0
        keyword_count = 0
        if self.CAN_TAG_KEYWORDS and callable(extract_keywords):
            try:
                sig = inspect.signature(extract_keywords)
                num_k_to_extract = min(max(5, int(len(words) * 0.3)), 20)
                kwargs_extract = {}
                if "top_n" in sig.parameters: kwargs_extract["top_n"] = num_k_to_extract
                elif "num_keywords" in sig.parameters: kwargs_extract["num_keywords"] = num_k_to_extract
                extracted_kws = extract_keywords(text, **kwargs_extract)
                keyword_count = len(extracted_kws)
            except Exception as e:
                self.logger.warning(f"Keyword extraction failed in _semantic_density for '{self.name}': {e}", exc_info=False)
                keyword_count = len(re.findall(r'\b[A-Z][a-z]{3,}\b', text))
        else:
            keyword_count = len(re.findall(r'\b[A-Z][a-z]{3,}\b', text))
        density_score = round(min(1.0, keyword_count / max(1, len(words)) * 3.5), 2) * 10.0
        return density_score
    def _sentence_complexity(self, text: str) -> float:
        sentences = re.split(r'[.!?]+', text)
        words = text.split()
        num_sentences = max(1, len([s for s in sentences if s.strip()]))
        num_words = len(words)
        if num_words == 0: return 0.0
        avg_len = num_words / num_sentences
        if avg_len <= 6: return round((avg_len / 6.0) * 3.0, 2)
        elif avg_len >= 30: return round(max(0.5, (45.0 - avg_len) / 15.0) * 4.0, 2)
        else: return round(min(1.0, (avg_len - 6.0) / 19.0) * 10.0, 2)
    def _lexical_diversity(self, text: str) -> float:
        words = re.findall(r'\b\w{3,}\b', text.lower())
        total_words = len(words)
        if total_words < 15: return 3.0
        unique_words = len(set(words))
        ttr = unique_words / total_words
        normalized_ttr = max(0.0, min(1.0, (ttr - 0.15) / 0.65))
        return round(normalized_ttr * 10.0, 2)
    def _generate_self_grade_feedback(self, scores: Dict[str, float]) -> List[str]:
        feedback = []
        clarity = scores.get("clarity_score", 0.0)
        depth = scores.get("depth_score", 0.0)
        diversity = scores.get("lexical_diversity_score", 0.0)
        if clarity < 4: feedback.append("Clarity significantly impaired; review structure and specialized vocabulary use.")
        elif clarity < 7: feedback.append("Clarity is moderate; aim for more direct phrasing and clearer topic sentences.")
        else: feedback.append("Content is generally clear and well-expressed.")
        if depth < 4: feedback.append("Lacks depth or is overly simplistic; consider adding more detail, examples, or supporting arguments.")
        elif depth < 7: feedback.append("Depth is adequate but could be enhanced with further exploration or more complex sentence structures.")
        else: feedback.append("Content demonstrates good depth and structural substance.")
        if diversity < 3: feedback.append("Lexical diversity is low; try to use a wider range of vocabulary and avoid repetition.")
        elif diversity < 6: feedback.append("Vocabulary is somewhat repetitive; aim for more varied word choices and synonyms.")
        else: feedback.append("Good lexical diversity observed.")
        if not feedback: feedback.append("Self-grade heuristics applied. Output appears generally sound based on these metrics.")
        return feedback
    def post_process_scores_and_tags(self, raw_text_prompt: str, refined_text_output: str, fallback_category: str) -> Dict[str, Any]:
        tags = [str(fallback_category).lower().replace(" ", "_").strip(), f"prof:{self.name.lower().replace(' ', '_')}"]
        if self.CAN_TAG_KEYWORDS and callable(extract_keywords):
            try:
                sig = inspect.signature(extract_keywords)
                kwargs_extract = {}
                if 'num_keywords' in sig.parameters: kwargs_extract["num_keywords"] = 7
                elif 'top_n' in sig.parameters: kwargs_extract["top_n"] = 7
                keyword_tags = extract_keywords(refined_text_output, **kwargs_extract)
                if isinstance(keyword_tags, list): tags.extend(str(t).strip().lower().replace(" ", "_") for t in keyword_tags if isinstance(t, str) and str(t).strip())
                self.logger.debug(f"Applied {len(keyword_tags if isinstance(keyword_tags, list) else [])} keyword tags using '{extract_keywords.__name__}'.")
            except Exception as e_tag:
                self.logger.warning(f"Tagging error with '{extract_keywords.__name__}': {e_tag}", exc_info=True)
                tags.extend([w for w, c in Counter(re.findall(r'\b[a-zA-Z]{5,}\b', refined_text_output.lower())).most_common(3)])
        else:
            self.logger.debug("Using basic regex tagging due to CAN_TAG_KEYWORDS=False or uncallable extract_keywords.")
            tags.extend([w for w, c in Counter(re.findall(r'\b[a-zA-Z]{5,}\b', refined_text_output.lower())).most_common(3)])
        wc_refined = len(refined_text_output.split())
        sc_refined = len(re.findall(r'[.!?]+', refined_text_output))
        scores = {
            "clarity_score": self._semantic_density(refined_text_output),
            "depth_score": self._sentence_complexity(refined_text_output),
            "lexical_diversity_score": self._lexical_diversity(refined_text_output),
            "word_count": wc_refined,
            "sentence_count": sc_refined,
            "avg_sentence_length": round(wc_refined / max(1, sc_refined), 1)
        }
        scores["self_grade_feedback"] = self._generate_self_grade_feedback(scores)
        self._log_activity("scores_and_tags_generated", {"scores": scores, "tags_count": len(tags)})
        return {"tags": sorted(list(set(tags))), **scores}
    def refine_text_with_llm(self, text_to_refine: str, llm_system_prompt: str, current_session_id: Optional[str] = None) -> Optional[str]:
        if not self.IS_LLM_ENABLED or not OpenAI or not httpx:
            self.logger.error("LLM utilities (OpenAI/httpx) not available. Cannot refine text.")
            return None
        session_log_id = current_session_id or self.session_id
        refined_output = None
        llm_call_data = {"model": COLLEGE_COMPLETION_MODEL, "input_length": len(text_to_refine), "attempts": 0, "success": False}
        for attempt in range(self.max_retries_llm):
            llm_call_data["attempts"] = attempt + 1
            try:
                if not COLLEGE_API_KEYS: raise ValueError("COLLEGE_API_KEYS is empty or not configured.")
                key_to_use = secrets.choice(COLLEGE_API_KEYS)
                if not key_to_use or "STUB" in str(key_to_use).upper():
                    self.logger.warning(f"LLM Call (Attempt {attempt+1}): Using a STUB or empty API key. Call will likely fail.")
                client = OpenAI(api_key=key_to_use, timeout=httpx.Timeout(20.0, read=90.0))
                messages = [{"role": "system", "content": llm_system_prompt}, {"role": "user", "content": text_to_refine}]
                self.logger.info(f"LLM Call (Attempt {attempt+1}/{self.max_retries_llm}) to {COLLEGE_COMPLETION_MODEL}. Session: {session_log_id}")
                response = client.chat.completions.create(
                    model=COLLEGE_COMPLETION_MODEL,
                    messages=messages,
                    temperature=0.55,
                    max_tokens=3500,
                    top_p=0.95
                )
                refined_output_candidate = response.choices[0].message.content.strip() if response.choices and response.choices[0].message else ""
                if not refined_output_candidate:
                    self.logger.warning(f"OpenAI returned empty content (Attempt {attempt+1}) for session {session_log_id}.")
                else:
                    self.logger.info(f"LLM refinement successful (Attempt {attempt+1}) for session {session_log_id}.")
                    llm_call_data["success"] = True
                    refined_output = refined_output_candidate
                    break
            except RateLimitError as rle:
                self.logger.error(f"OpenAI Rate Limit Error (Attempt {attempt+1}): {rle}. Session: {session_log_id}", exc_info=False)
                llm_call_data["error"] = f"RateLimitError: {str(rle)}"
                if attempt < self.max_retries_llm - 1: time.sleep(random.uniform(5,10) * (attempt + 1))
                else: self.logger.error(f"LLM failed after {self.max_retries_llm} attempts due to RateLimitError."); break
            except (APIConnectionError, APITimeoutError) as net_err:
                self.logger.error(f"OpenAI Network Error (Attempt {attempt+1}): {type(net_err).__name__} - {net_err}. Session: {session_log_id}", exc_info=False)
                llm_call_data["error"] = f"NetworkError: {str(net_err)}"
                if attempt < self.max_retries_llm - 1: time.sleep(random.uniform(3,7) * (attempt + 1))
                else: self.logger.error(f"LLM failed after {self.max_retries_llm} attempts due to NetworkError."); break
            except APIStatusError as stat_err:
                self.logger.error(f"OpenAI API Status Error (Attempt {attempt+1}): {stat_err.status_code} - {stat_err.message}. Session: {session_log_id}", exc_info=False)
                llm_call_data["error"] = f"APIStatusError {stat_err.status_code}: {str(stat_err.message)}"
                if stat_err.status_code == 401: self.logger.critical("OpenAI API Key Unauthorized (401). Check keys."); break
                if stat_err.status_code == 429:
                    if attempt < self.max_retries_llm - 1: time.sleep(random.uniform(5,10) * (attempt + 1))
                    else: break
                elif stat_err.status_code >= 500:
                    if attempt < self.max_retries_llm - 1: time.sleep(random.uniform(2,5) * (attempt + 1))
                    else: break
                else: break
            except Exception as e:
                self.logger.error(f"General OpenAI Error (Attempt {attempt+1}) for session {session_log_id}: {type(e).__name__} - {e}", exc_info=True)
                llm_call_data["error"] = f"GeneralError: {str(e)}"
                if attempt < self.max_retries_llm - 1: time.sleep(random.uniform(2,5) * (attempt + 1))
                else: self.logger.error(f"LLM failed after {self.max_retries_llm} attempts due to general errors."); break
        self._log_activity("llm_refinement_attempt_completed", llm_call_data)
        return refined_output
    def _parse_llm_output(self, llm_full_output: str) -> Tuple[str, Optional[str]]:
        main_output_text = llm_full_output.strip()
        reflection_text = None
        reflection_match = re.search(f"^(.*?)({re.escape(self.LLM_REFLECTION_HEADER)})(.*)$", main_output_text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        if reflection_match:
            main_output_text = reflection_match.group(1).strip()
            reflection_text = reflection_match.group(3).strip()
        primary_match = re.match(f"^{re.escape(self.LLM_PRIMARY_OUTPUT_HEADER)}(.*)$", main_output_text, re.DOTALL | re.IGNORECASE)
        if primary_match:
            main_output_text = primary_match.group(1).strip()
        return main_output_text, reflection_text
    def embed_text_for_self_kb(self, text: str) -> Optional[np.ndarray]:
        if not self.enable_self_learning or not callable(college_embed_text):
            self.logger.debug("Self-KB embedding skipped: self-learning disabled or college_embed_text unavailable.")
            return None
        try:
            vector = college_embed_text(text)
            if isinstance(vector, np.ndarray):
                if vector.ndim == 1 and vector.shape[0] == self.SELF_FAISS_VECTOR_DIM:
                    return vector.astype(np.float32)
                elif vector.ndim == 2 and vector.shape[0] == 1 and vector.shape[1] == self.SELF_FAISS_VECTOR_DIM:
                    return vector.squeeze(axis=0).astype(np.float32)
                else:
                    self.logger.warning(
                        f"Self-KB embedding dimension/shape mismatch for '{self.name}'. "
                        f"Expected ({self.SELF_FAISS_VECTOR_DIM},) or (1, {self.SELF_FAISS_VECTOR_DIM}), got {vector.shape}. "
                        f"Text (first 50): '{text[:50]}...'"
                    )
            else:
                self.logger.warning(
                    f"Self-KB embedding from college_embed_text was not a numpy array for '{self.name}'. Type: {type(vector)}. "
                    f"Text (first 50): '{text[:50]}...'"
                )
        except Exception as e:
            self.logger.error(f"Error during self-embedding text for '{self.name}': {e}", exc_info=True)
        return None
    def _query_own_knowledge(self, current_prompt_or_task: str, top_k: int = 3) -> List[str]:
        if not self.enable_self_learning or not self.own_faiss_index or self.own_faiss_index.ntotal == 0:
            self.logger.debug("Own KB query skipped: self-learning disabled or FAISS index is empty/unavailable.")
            return []
        try:
            query_embedding_1d = self.embed_text_for_self_kb(current_prompt_or_task)
            if query_embedding_1d is None or query_embedding_1d.size == 0:
                self.logger.warning("No valid embedding generated for own KB query.")
                return []
            query_embedding_2d = query_embedding_1d.reshape(1, -1)
            if query_embedding_2d.shape[1] != self.SELF_FAISS_VECTOR_DIM:
                self.logger.warning(f"Embedding shape mismatch for FAISS search: {query_embedding_2d.shape}. Expected (1, {self.SELF_FAISS_VECTOR_DIM})")
                return []
            distances, indices = self.own_faiss_index.search(query_embedding_2d, top_k)
            insights = []
            for i, faiss_idx_val in enumerate(indices[0]):
                if faiss_idx_val == -1: continue
                entry_info = self.own_faiss_id_map.get(int(faiss_idx_val))
                if not entry_info:
                    self.logger.warning(f"FAISS index hit {faiss_idx_val} has no associated metadata in ID map.")
                    continue
                similarity_score = max(0.0, 1.0 - (float(distances[0][i]) / 4.0))
                title = entry_info.get("title", f"Entry {faiss_idx_val}")
                snippet = entry_info.get("summary_snippet", "No summary available.")
                insights.append(f"📎 Past Work: **{title}** (Similarity: {similarity_score:.2f})\n↳ {snippet}")
            self.logger.info(f"{len(insights)} prior insights retrieved for task: '{current_prompt_or_task[:50]}...'")
            self._log_activity("own_kb_query_completed", {"query": current_prompt_or_task[:50], "insights_found": len(insights)})
            return insights
        except Exception as e:
            self.logger.error(f"Exception while querying self-KB: {e}", exc_info=True)
            return []
    def _log_output_to_own_kb(
        self, main_output_text: str, reflection_text: Optional[str], prompt_info: str, source_vd_info: Optional[Dict[str, Any]] = None
    ):
        self.logger.debug(f"[{self.name}] Attempting _log_output_to_own_kb. Self-learning: {self.enable_self_learning}, DossierWriter: {self.own_dossier_writer is not None}")
        if not self.enable_self_learning or not self.own_dossier_writer:
            self.logger.warning(
                f"[{self.name}] Self-KB logging skipped. enable_self_learning={self.enable_self_learning}, "
                f"own_dossier_writer_exists={self.own_dossier_writer is not None}."
            )
            return None
        dossier_entry_written = False
        safe_log_title = "Unknown Title (Error before title gen)" # Default in case of early error
        entry_fp = "fp_error_before_gen"
        try:
            ts_log = college_utc_timestamp()
            entry_fp_context = (reflection_text or "") + prompt_info + self.session_id + "_ownKB_entry"
            entry_fp = self.generate_fingerprint(main_output_text, entry_fp_context)
            log_title = f"{self.name} Log: {prompt_info[:35].replace(chr(0xFFFD), '')}... {entry_fp[:6]}"
            safe_log_title = re.sub(r'[^\x00-\x7F]+', '', log_title)
            tags_kb = [self.name.lower().replace(" ","_"), "self_log", "kb_entry", self.operational_tier.lower()]
            if source_vd_info and isinstance(source_vd_info.get("tags"), list):
                tags_kb.extend(t for t in source_vd_info["tags"] if isinstance(t, str))
            # --- METADATA PREPARATION FOR SELF-LOGGING ---
            metadata_for_dossier = {
                "fingerprint": entry_fp,
                "timestamp_utc": ts_log,
                "session_id_processed": self.session_id,
                "original_prompt_info": prompt_info,
                "professor_id": self.name,
                "category": self.knowledge_base_domain,
                "entry_type": f"{self.name.lower().replace(' ','_')}_self_reflection",
                "display_title_hint": safe_log_title,
                "tags": sorted(list(set(tags_kb))),
            }
            if source_vd_info:
                metadata_for_dossier.update({
                    "source_vd_title_ref": source_vd_info.get("title"),
                    "source_vd_fingerprint_ref": source_vd_info.get("fingerprint"),
                    "source_vd_path_ref": str(source_vd_info.get("file_path", source_vd_info.get("source_vd_path")))
                })
            # === CRITICAL CONSENT OVERRIDE FOR SELF-KB LOGGING ===
            # The Guardian (via DossierWriter) will evaluate consent based on the
            # ROOT-LEVEL fields of the metadata it receives as 'vd_metadata_override'.
            # 1. Define the consent parameters for self-logging
            self_consent_scope = ["internal_knowledge_capture", "self_improvement_data_logging"]
            self_consent_domains = [self.knowledge_base_domain]
            # 2. Place them at the ROOT of metadata_for_dossier
            metadata_for_dossier["consent"] = True # Explicitly grant general consent
            metadata_for_dossier["consent_scope"] = self_consent_scope
            metadata_for_dossier["consent_domains"] = self_consent_domains
            # Optional: other root-level consent fields if your Guardian checks them for overrides
            # metadata_for_dossier["consent_owner"] = f"self_system:{self.name}"
            # metadata_for_dossier["consent_expires"] = None # No expiration for internal logs
            # 3. Also include the 'guardian_check' block for informational purposes or if other systems inspect it.
            # Its 'consent_flag', 'consent_scope', etc. here are for this specific block's notation.
            metadata_for_dossier["guardian_check"] = {
                "verified_by_override": True, # Indicates this block is an intended override
                "consent_flag": True,
                "consent_scope": self_consent_scope, # Mirrored for clarity within this block
                "consent_domains": self_consent_domains, # Mirrored
                "consent_grantor": f"self_system:{self.name}", # System granting consent for itself
                "consent_notes": "Auto-consent override applied by ProfessorBase for internal self-KB logging and improvement. Consent is evaluated based on root-level fields in this metadata."
            }
            self.logger.debug(
                f"[{self.name}] Self-KB log metadata prepared for DossierWriter. Root consent fields:\n"
                f" consent: {metadata_for_dossier.get('consent')}\n"
                f" consent_scope: {metadata_for_dossier.get('consent_scope')}\n"
                f" consent_domains: {metadata_for_dossier.get('consent_domains')}"
            )
            # Attach scores and tags
            processed_scores_tags = self.post_process_scores_and_tags(prompt_info, main_output_text, self.knowledge_base_domain)
            metadata_for_dossier.update(processed_scores_tags)
            # Prepare content body
            content_sections = [f"## {self.LLM_PRIMARY_OUTPUT_HEADER}\n{main_output_text.strip()}"]
            if reflection_text:
                content_sections.append(f"\n## {self.LLM_REFLECTION_HEADER}\n{reflection_text.strip()}")
            full_md_body = "\n\n".join(content_sections)
            # This key is used by DossierWriter to get the main content if Guardian check passes.
            metadata_for_dossier["raw_text_body_for_dossier"] = full_md_body
            self.logger.info(f"[{self.name}] Calling self.own_dossier_writer.add_entry for title: {safe_log_title}")
            self.own_dossier_writer.add_entry(
                metadata=metadata_for_dossier, # This metadata now has root-level consent fields
                entry_type=metadata_for_dossier["entry_type"],
                display_title=metadata_for_dossier["display_title_hint"],
                requested_dossier_action="internal_knowledge_capture" # This action will be checked against root consent_scope
            )
            dossier_entry_written = True
            self.logger.info(f"[{self.name}] Call to self.own_dossier_writer.add_entry completed for: {safe_log_title}")
            # --- FAISS Embedding (Only if dossier entry was successful) ---
            if dossier_entry_written and self.own_faiss_index is not None and callable(prof_add_to_index):
                # ... (rest of FAISS logic as it was, it's likely fine) ...
                self.logger.info(f"[{self.name}] Proceeding with FAISS embedding for: {safe_log_title}")
                snippet_for_faiss = main_output_text.strip().split("\n")[0][:200]
                embed_payload = (
                    f"Title: {safe_log_title}\nOutput Snippet: {snippet_for_faiss}\n"
                    f"Reflection Snippet: {reflection_text[:250] if reflection_text else 'N/A'}\n"
                    f"Keywords: {', '.join(processed_scores_tags.get('tags',[]))}"
                )
                vector_1d = self.embed_text_for_self_kb(embed_payload)
                if vector_1d is not None and vector_1d.ndim == 1 and vector_1d.shape[0] == self.SELF_FAISS_VECTOR_DIM:
                    vector_2d_for_faiss = vector_1d.reshape(1, -1)
                    faiss_metadata_payload = {"fingerprint": entry_fp, "summary_snippet": snippet_for_faiss, "timestamp_utc": ts_log}
                    returned_faiss_id = prof_add_to_index(
                        index_name=self.knowledge_base_domain,
                        title=safe_log_title,
                        embedded=vector_2d_for_faiss,
                        metadata=faiss_metadata_payload
                    )
                    if returned_faiss_id is not None:
                        try:
                            idx_key = int(returned_faiss_id)
                            self.own_faiss_id_map[idx_key] = {
                                "fingerprint": entry_fp,
                                "title": safe_log_title,
                                "summary_snippet": snippet_for_faiss,
                                "timestamp_utc": ts_log
                            }
                            if self.own_faiss_id_map_path:
                                with open(self.own_faiss_id_map_path, "w", encoding="utf-8") as f_map_w:
                                    json.dump({str(k): v for k, v in self.own_faiss_id_map.items()}, f_map_w, indent=2)
                            if self.own_faiss_index_path and faiss and hasattr(self.own_faiss_index, 'ntotal') and self.own_faiss_index.ntotal > 0:
                                if hasattr(faiss, 'write_index'):
                                    faiss.write_index(self.own_faiss_index, str(self.own_faiss_index_path))
                            self.logger.info(f"[{self.name}] Self-KB FAISS entry added (ID: {idx_key}), Title: {safe_log_title}")
                        except ValueError:
                            self.logger.warning(f"[{self.name}] FAISS ID from prof_add_to_index ('{returned_faiss_id}') not an int. Map not updated for this entry.")
                    else:
                        self.logger.warning(f"[{self.name}] Self-KB FAISS save failed: prof_add_to_index returned None or error. Title: {safe_log_title}")
                else:
                    self.logger.warning(f"[{self.name}] Invalid embedding or shape for Self-KB FAISS injection. FP: {entry_fp}. Shape: {vector_1d.shape if vector_1d is not None else 'None'}")
                    # Text: '{embed_payload[:50]}...'")
            elif dossier_entry_written:
                self.logger.info(f"[{self.name}] FAISS part of self-KB logging skipped (own_faiss_index: {self.own_faiss_index is not None}, prof_add_to_index callable: {callable(prof_add_to_index)})")
            self._log_activity("self_kb_log_completed", {"fingerprint": entry_fp, "title": safe_log_title, "dossier_written": dossier_entry_written})
            return entry_fp
        except Exception as e:
            # Use safe_log_title if defined, otherwise a generic message
            title_for_error = safe_log_title if safe_log_title in locals() else f"Unknown Title (FP: {entry_fp if 'entry_fp' in locals() else 'Unset'})"
            self.logger.error(f"[{self.name}] Exception during self-KB logging for '{title_for_error}': {e}", exc_info=True)
            self._log_activity("self_kb_log_failed", {"error": str(e)})
            return None
    # ... (rest of ProfessorBase class)
    def _augment_llm_input_with_specific_expertise(
        self, llm_input: str, source_vd_frontmatter: Optional[Dict[str, Any]]
    ) -> str:
        return llm_input
    def _parse_specialized_llm_output(
        self, llm_full_output: str, main_output: str, reflection: Optional[str]
    ) -> Dict[str, Any]:
        return {}
    def _perform_self_assessment(
        self, main_output: str, reflection: Optional[str], scores: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        assessment = {}
        if scores.get("clarity_score", 0) < 3: assessment["flag_low_clarity_critical"] = True
        if scores.get("depth_score", 0) < 3: assessment["flag_low_depth_critical"] = True
        return assessment if assessment else None
    # In ProfessorBase class (professor_base.py)
    def _prepare_llm_input(self, prompt_or_raw_text: str, # This is the primary task/prompt for the professor
                           source_vd_frontmatter: Optional[Dict[str, Any]], # Can be frontmatter of a full VD or metadata of a parent dossier entry
                           source_vd_path: Optional[Path] # Path to the full VD or the dossier containing the parent entry
                           ) -> Tuple[str, str]:
        """ Prepares the full input string for the LLM.
        It incorporates:
        1. Context from a source Vector Document or a parent dossier entry.
        2. The specific user request or task for the professor.
        3. Relevant insights retrieved from the professor's own knowledge base (if self-learning is active).
        4. Potential augmentations from professor-specific expertise methods.
        """
        llm_input_parts = []
        # Default description; will be refined if context is available
        analysis_target_description = "the user's direct request or provided text"
        self.logger.debug(f"[{self.name}] Preparing LLM input. Initial prompt/task: '{prompt_or_raw_text[:100]}...'")
        if source_vd_frontmatter:
            self.logger.debug(f"[{self.name}] Source VD/Parent Entry frontmatter provided. Keys: {list(source_vd_frontmatter.keys())}")
            # Check for specific keys indicating context from a parent dossier entry (set by CollegeCore)
            parent_full_markdown = source_vd_frontmatter.get("_parent_entry_full_markdown")
            parent_main_text = source_vd_frontmatter.get("_parent_entry_main_text")
            is_enriching_specific_entry = bool(parent_full_markdown or parent_main_text)
            if is_enriching_specific_entry:
                parent_title_hint = source_vd_frontmatter.get("display_title_hint", source_vd_frontmatter.get("title", "the parent entry"))
                analysis_target_description = f"enrichment task related to parent entry: '{parent_title_hint}'"
                self.logger.info(f"[{self.name}] Identified as enriching a specific entry: {analysis_target_description}")
                # Add context from the parent entry
                if parent_full_markdown:
                    markdown_context_preview = str(parent_full_markdown)
                    # Truncate thoughtfully to avoid overly long prompts, ensuring crucial parts are kept.
                    # Future Upgrade: Could use summarization here for very long parent entries.
                    if len(markdown_context_preview) > 2500:
                        markdown_context_preview = markdown_context_preview[:1250] + "\n...\n[Parent Entry Content Truncated for Brevity]\n...\n" + markdown_context_preview[-1000:]
                    llm_input_parts.append(
                        f"CONTEXT FROM PARENT DOSSIER ENTRY (Full Markdown Section of entry with fingerprint '{source_vd_frontmatter.get('fingerprint', 'N/A')}'):\n"
                        f"------------------------------------------------------------------\n"
                        f"{markdown_context_preview}\n"
                        f"------------------------------------------------------------------\n"
                        f"(End of Parent Dossier Entry Context)\n"
                    )
                elif parent_main_text:
                    # Fallback to just main text
                    text_context_preview = str(parent_main_text)
                    if len(text_context_preview) > 2000:
                        text_context_preview = text_context_preview[:1000] + "\n...\n[Parent Entry Text Truncated]\n...\n" + text_context_preview[-750:]
                    llm_input_parts.append(
                        f"CONTEXT FROM PARENT DOSSIER ENTRY (Main Text of entry with fingerprint '{source_vd_frontmatter.get('fingerprint', 'N/A')}'):\n"
                        f"--------------------------------------------\n"
                        f"{text_context_preview}\n"
                        f"--------------------------------------------\n"
                        f"(End of Parent Dossier Entry Main Text)\n"
                    )
            else:
                # Standard source VD context (not a specific parent entry from within a dossier)
                title = source_vd_frontmatter.get("title", "Unnamed Document")
                summary = source_vd_frontmatter.get("summary", source_vd_frontmatter.get("description", "No summary available."))
                analysis_target_description = f"the source document titled '{title}'"
                self.logger.info(f"[{self.name}] Using context from source document: {analysis_target_description}")
                source_context_text = f"SOURCE DOCUMENT CONTEXT:\nTitle: {title}\nSummary: {summary}\n"
                if source_vd_path:
                    source_context_text += f"Path Hint: {source_vd_path.name}\n"
                # Future Prof Upgrade: Add more fields from frontmatter if relevant (e.g., keywords, version)
                # existing_keywords = source_vd_frontmatter.get("tags", [])
                # if existing_keywords: source_context_text += f"Existing Keywords: {', '.join(existing_keywords)}\n"
                llm_input_parts.append(source_context_text)
        # Add the main user request / task for the professor
        llm_input_parts.append(f"YOUR PRIMARY TASK / USER REQUEST:\n{prompt_or_raw_text}\n")
        # Add relevant knowledge from the professor's own self-learning KB
        if self.enable_self_learning:
            self.logger.debug(f"[{self.name}] Self-learning enabled, attempting to query own knowledge base.")
            # Construct a query that combines the task and available context for better KB retrieval
            query_for_self_kb_parts = [prompt_or_raw_text]
            if source_vd_frontmatter:
                kb_query_title = source_vd_frontmatter.get("title", source_vd_frontmatter.get("display_title_hint"))
                if kb_query_title:
                    query_for_self_kb_parts.insert(0, f"Regarding '{kb_query_title}':")
            query_for_self_kb = " ".join(query_for_self_kb_parts)
            self.logger.debug(f"[{self.name}] Querying self-KB with: '{query_for_self_kb[:150]}...'")
            prior_insights = self._query_own_knowledge(query_for_self_kb, top_k=3) # top_k can be configurable
            if prior_insights:
                retrieved_knowledge_str = "\n\n".join(prior_insights) # Use double newline for better separation
                llm_input_parts.append(
                    f"ADDITIONAL CONTEXT - RELEVANT INSIGHTS FROM MY PREVIOUS WORK (Internal Knowledge Base):\n"
                    f"Consider these past insights as you formulate your response. You may build upon them, "
                    f"critique them, or note how your current thinking diverges, if relevant.\n"
                    f"------------------------------------------------------------------\n"
                    f"{retrieved_knowledge_str}\n"
                    f"------------------------------------------------------------------\n"
                    f"(End of Internal Knowledge Base Insights)\n"
                )
                self.logger.info(f"[{self.name}] Added {len(prior_insights)} prior insights to LLM prompt.")
            else:
                self.logger.info(f"[{self.name}] No prior insights found or added from self-KB for this task.")
        # Join all parts with a clear separator
        # Using a more distinct separator than just "---" which might appear in content.
        # Future Prof Upgrade: Could add a section here for "Operational Constraints" or "Output Format Requirements"
        # if these are passed dynamically (e.g., max word count, specific JSON structure needed).
        # === JOINING PROMPT PARTS ===
        # Use a more distinct separator that's less likely to be in the content itself
        separator = "\n\n<<<<<< SECTION BREAK >>>>>>\n\n"
        base_llm_input = separator.join(llm_input_parts).strip()
        # Allow subclasses to augment the input with their specific expertise
        # This method is defined in ProfessorBase as a placeholder for subclasses to override.
        final_llm_input = self._augment_llm_input_with_specific_expertise(base_llm_input, source_vd_frontmatter)
        if final_llm_input != base_llm_input:
            self.logger.info(f"[{self.name}] LLM input was augmented by specific expertise method.")
        self.logger.debug(f"[{self.name}] Final prepared LLM input (first 300 chars): '{final_llm_input[:300]}...'")
        self._log_activity("llm_input_prepared", {
            "analysis_target": analysis_target_description,
            "input_length": len(final_llm_input),
            "includes_source_context": bool(source_vd_frontmatter),
            "includes_parent_entry_context": is_enriching_specific_entry if 'is_enriching_specific_entry' in locals() else False,
            "includes_self_kb_insights": 'prior_insights' in locals() and bool(prior_insights)
        })
        return final_llm_input, analysis_target_description
    # ... (rest of ProfessorBase class)
    def process_thought(
        self, prompt_or_raw_text: str, category: Optional[str] = None, session_id: Optional[str] = None,
        source_vd_path: Optional[Path] = None, source_vd_frontmatter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        effective_session_id = session_id or self.session_id
        self.logger.info(
            f"'{self.name}' starting processing. Session: {effective_session_id}. "
            f"Source VD: {source_vd_path.name if source_vd_path else 'N/A'}. Self-Learning: {self.enable_self_learning}"
        )
        self._log_activity("process_thought_start", {
            "prompt_preview": prompt_or_raw_text[:100], "category": category,
            "source_vd_path": str(source_vd_path) if source_vd_path else None,
            "self_learning_status_at_start": self.enable_self_learning
        })
        llm_input_text, analysis_target_description = self._prepare_llm_input(prompt_or_raw_text, source_vd_frontmatter, source_vd_path)
        full_llm_output = self.refine_text_with_llm(llm_input_text, self.system_prompt, effective_session_id)
        output_fp_context = f"output_{effective_session_id}_{self.name}"
        output_fingerprint = self.generate_fingerprint(full_llm_output or prompt_or_raw_text, output_fp_context)
        if not full_llm_output:
            error_msg = f"Professor '{self.name}' LLM refinement failed for target: {analysis_target_description}. Input text preview: '{llm_input_text[:100]}...'"
            self.logger.error(error_msg)
            ts_err = college_utc_timestamp()
            failure_payload = {
                "text": f"❌ [{self.name}] Failed to generate refined output.",
                "error": error_msg,
                "professor_id": self.name,
                "session_id": effective_session_id,
                "metadata_for_dossier": {
                    "fingerprint": output_fingerprint,
                    "entry_type": f"prof_{self.name}_error",
                    "display_title_hint": f"Error by {self.name} for: '{analysis_target_description[:30]}...'",
                    "error_message": error_msg,
                    "_agent_success": False,
                    "session_id": effective_session_id,
                    "timestamp_utc": ts_err,
                    "agent_tier": self.operational_tier,
                    "source_vd_fingerprint_ref": source_vd_frontmatter.get('fingerprint') if source_vd_frontmatter else None,
                    "source_vd_title_ref": source_vd_frontmatter.get('title') if source_vd_frontmatter else (source_vd_path.name if source_vd_path else None),
                    "failed_input_preview": llm_input_text[:300]
                }
            }
            self._log_activity("process_thought_failed_llm", {"error": error_msg, "fingerprint": output_fingerprint})
            return failure_payload
        main_output_text, reflection_text = self._parse_llm_output(full_llm_output)
        final_category = category or (source_vd_frontmatter.get("domain") if source_vd_frontmatter else None) or self.name.lower().replace(" ", "_") + "_generated"
        processed_scores_tags = self.post_process_scores_and_tags(prompt_or_raw_text, main_output_text, final_category)
        self_assessment_metrics = self._perform_self_assessment(main_output_text, reflection_text, processed_scores_tags)
        if self.enable_self_learning:
            # Check again, as it might have been disabled by a failure in _initialize
            self.logger.info(f"[{self.name}] Proceeding to _log_output_to_own_kb as enable_self_learning is True.")
            self._log_output_to_own_kb(main_output_text, reflection_text, prompt_or_raw_text, source_vd_frontmatter)
        else:
            self.logger.info(f"[{self.name}] Skipping _log_output_to_own_kb as enable_self_learning is False.")
        ts_payload_final = college_utc_timestamp()
        dossier_config_to_use = getattr(self, 'DOSSIER_CONFIG', self.BASE_DOSSIER_CONFIG)
        full_text_key = dossier_config_to_use.get("full_text_key", "main_professor_output_text")
        reflection_key = dossier_config_to_use.get("reflection_key", "professor_reflection_text")
        display_prefix = dossier_config_to_use.get("display_title_prefix", f"Output from {self.name}")
        metadata_for_external_dossier = {
            "fingerprint": output_fingerprint,
            "entry_type": f"prof_{self.name.lower().replace(' ','_')}_output",
            "display_title_hint": f"{display_prefix} re: '{analysis_target_description[:25]}...' (FP: {output_fingerprint[:6]})",
            "source_vd_fingerprint_ref": source_vd_frontmatter.get('fingerprint') if source_vd_frontmatter else None,
            "source_vd_title_ref": source_vd_frontmatter.get('title') if source_vd_frontmatter else (source_vd_path.name if source_vd_path else None),
            "source_vd_path_ref": str(source_vd_path) if source_vd_path else None,
            "refinement_prompt_preview": prompt_or_raw_text[:200],
            "professor_id": self.name,
            "professor_system_prompt_hash": hashlib.sha256(self.system_prompt.encode()).hexdigest()[:12],
            "professor_output_key": full_text_key,
            full_text_key: main_output_text,
            reflection_key: reflection_text if reflection_text else "",
            f"raw_llm_output_{self.name.lower().replace(' ','_')}": full_llm_output,
            "timestamp_utc": ts_payload_final,
            "session_id": effective_session_id,
            "_agent_success": True,
            "agent_tier": self.operational_tier,
            **processed_scores_tags
        }
        if source_vd_frontmatter and source_vd_frontmatter.get('fingerprint'):
            metadata_for_external_dossier['elaborates_on_fingerprint'] = source_vd_frontmatter.get('fingerprint')
            metadata_for_external_dossier['entry_type'] = f"prof_{self.name.lower().replace(' ','_')}_elaboration"
            metadata_for_external_dossier['display_title_hint'] = f"Elaboration by {self.name} on '{analysis_target_description[:20]}...' (FP: {output_fingerprint[:6]})"
        if self_assessment_metrics and isinstance(self_assessment_metrics, dict):
            metadata_for_external_dossier.update({f"self_assess_{k.lower()}": v for k,v in self_assessment_metrics.items()})
        specialized_parsed_output = self._parse_specialized_llm_output(full_llm_output, main_output_text, reflection_text)
        if specialized_parsed_output:
            metadata_for_external_dossier.update({f"spec_{k.lower()}": v for k,v in specialized_parsed_output.items()})
        final_output_payload = {
            "text": main_output_text,
            "professor_id": self.name,
            "session_id": effective_session_id,
            "timestamp_utc": ts_payload_final,
            "category": final_category,
            "metadata_for_dossier": metadata_for_external_dossier
        }
        self.logger.info(f"'{self.name}' processing complete. Output FP: {output_fingerprint}. Preview: {main_output_text[:70].replace(chr(0xFFFD), '')}...")
        self._log_activity("process_thought_completed", {"fingerprint": output_fingerprint, "main_output_preview": main_output_text[:70]})
        return final_output_payload
    @staticmethod
    def extract_main_output(result: Dict[str, Any]) -> Optional[str]:
        if not isinstance(result, dict): return None
        main_text = result.get("text")
        if isinstance(main_text, str):
            if ProfessorBase.LLM_REFLECTION_HEADER.lower() not in main_text.lower() and \
               ProfessorBase.LLM_PRIMARY_OUTPUT_HEADER.lower() not in main_text.lower():
                return main_text
        metadata = result.get("metadata_for_dossier")
        if isinstance(metadata, dict):
            output_key_in_meta = metadata.get("professor_output_key")
            if output_key_in_meta and isinstance(metadata.get(output_key_in_meta), str):
                return metadata.get(output_key_in_meta)
            base_full_text_key = ProfessorBase.BASE_DOSSIER_CONFIG.get("full_text_key")
            if base_full_text_key and isinstance(metadata.get(base_full_text_key), str):
                return metadata.get(base_full_text_key)
            if isinstance(metadata.get("text"), str):
                return metadata.get("text")
        if isinstance(main_text, str):
            temp_prof_for_parse = ProfessorBase(name="TempParser", system_prompt="parsing")
            parsed_main, _ = temp_prof_for_parse._parse_llm_output(main_text)
            if parsed_main: return parsed_main
        module_logger.warning(f"Could not reliably extract main output using known keys from result: {list(result.keys())}")
        return None
    def finalize_professor_session(self):
        self.logger.info(f"Finalizing session for Professor '{self.name}' (ID: {self.session_id}).")
        if self.enable_self_learning: # Check the final status of this flag
            if self.own_dossier_writer and hasattr(self.own_dossier_writer, 'finalize_dossier'):
                try:
                    self.logger.info(f"[{self.name}] Calling finalize_dossier on own_dossier_writer for {self.own_dossier_writer.md_path}")
                    self.own_dossier_writer.finalize_dossier()
                    self.logger.info(f"Finalized self-dossier for '{self.name}' at {self.own_dossier_writer.md_path.resolve()}.")
                except Exception as e:
                    self.logger.error(f"Error finalizing self-dossier for '{self.name}': {e}", exc_info=True)
            elif not self.own_dossier_writer:
                self.logger.warning(f"[{self.name}] Cannot finalize self-dossier as own_dossier_writer is None (self-learning might have failed to init fully).")
            if self.own_faiss_index is not None and self.own_faiss_index_path and \
               self.IS_VECTOR_STORE_ENABLED and faiss and hasattr(faiss, 'write_index'):
                try:
                    if self.own_faiss_id_map_path:
                        self.own_faiss_id_map_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(self.own_faiss_id_map_path, 'w', encoding='utf-8') as f_map_final:
                            json.dump({str(k): v for k, v in self.own_faiss_id_map.items()}, f_map_final, indent=2)
                        self.logger.info(f"Saved own FAISS ID map to {self.own_faiss_id_map_path} ({len(self.own_faiss_id_map)} entries).")
                    self.own_faiss_index_path.parent.mkdir(parents=True, exist_ok=True)
                    faiss.write_index(self.own_faiss_index, str(self.own_faiss_index_path))
                    self.logger.info(f"Saved own FAISS index to {self.own_faiss_index_path} (Size: {self.own_faiss_index.ntotal}).")
                except Exception as e:
                    self.logger.error(f"Error saving own FAISS index/map for '{self.name}': {e}", exc_info=True)
            elif self.own_faiss_index is None:
                self.logger.warning(f"[{self.name}] Cannot save self-FAISS index as own_faiss_index is None.")
        else:
            self.logger.info(f"[{self.name}] Self-learning was not active for this session, no self-KB data to finalize.")
        self._log_activity("finalize_professor_session", {"self_learning_enabled_at_finalize": self.enable_self_learning, "dossier_writer_exists": bool(self.own_dossier_writer)})
        self.logger.info(f"Professor '{self.name}' session finalized completely.")