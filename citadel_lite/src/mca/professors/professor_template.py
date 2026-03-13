# professor_template.py — Modular Professor Class Template (v1.0)
import os
import sys
import time
import json
import random
import secrets
from datetime import datetime
from pathlib import Path

# === Bootstrap project root ===
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# === Internal Imports ===
from embedder import embed_text
from vector_store import add_to_index, get_index
from metadata_store import save_refined_vector
from status import set_online_status
from college_keys import API_KEYS, COMPLETION_MODEL
from college_categories import ALL_CATEGORIES
from openai import OpenAI
import httpx

# === === CONFIGURE HERE FOR NEW PROFESSORS === ===
PROF_NAME = "ProfTemplate"  # Override this
SYSTEM_PROMPT = (
    "You are Prof. Template, a specialist in refining knowledge into its most elegant, "
    "insightful, and actionable form. Focus on clarity, precision, and high cognitive value."
)
PERSONAL_INDEX = f"prof_{PROF_NAME.lower()}"
OPENAI_MAX_RETRIES = 3

# === Logging Path ===
LOG_PATH = Path(f"college_data/logs/{PROF_NAME.lower()}_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# === Local Logging Function ===
def log_professor_event(name, vector_id, text, category):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "professor": name,
        "vector_id": vector_id,
        "category": category,
        "refined_text": text[:300]
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, indent=2) + "\n")
        f.flush()
    print(f"[{PROF_NAME}] 📝 Logged event to {LOG_PATH.name}", flush=True)

# === OpenAI Refinement ===
def refine(raw_text: str) -> str:
    user_prompt = f"Original idea: {raw_text}"

    for attempt in range(OPENAI_MAX_RETRIES):
        try:
            api_key = secrets.choice(API_KEYS)
            print(f"[{PROF_NAME}] 🔑 Using API key: {api_key[:6]}...", flush=True)

            client = OpenAI(api_key=api_key, timeout=httpx.Timeout(10.0, read=20.0))

            response = client.chat.completions.create(
                model=COMPLETION_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.6,
            )

            set_online_status(True)
            print(f"[{PROF_NAME}] ✅ OpenAI call succeeded.", flush=True)
            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"[{PROF_NAME}] ❌ OpenAI Error (attempt {attempt+1}): {e}", flush=True)
            time.sleep(2)

    set_online_status(False)
    return raw_text

# === Primary Processing Function ===
def process_with_professor(raw_text: str, original_vector_id: int = None):
    print(f"[{PROF_NAME}] 🔍 Processing: {raw_text[:60]}...", flush=True)

    refined_text = refine(raw_text)
    if not refined_text:
        print(f"[{PROF_NAME}] ❌ Refinement failed or empty.", flush=True)
        return

    print(f"[{PROF_NAME}] 📤 Refinement complete. Proceeding to embedding...", flush=True)
    embedded = embed_text(refined_text)
    print(f"[{PROF_NAME}] 📥 Embedding complete.", flush=True)

    if embedded is None:
        print(f"[{PROF_NAME}] ❌ Embedding failed.", flush=True)
        return

    category = random.choice(ALL_CATEGORIES)
    index, _, path = get_index(PERSONAL_INDEX)
    vector_id = index.ntotal
    add_to_index(index, None, embedded, path)

    save_refined_vector(
        vector_id=vector_id,
        refined_text=refined_text,
        confidence=0.95,
        index_name=PERSONAL_INDEX,
        tags=[category, PROF_NAME]
    )

    log_professor_event(PROF_NAME, vector_id, refined_text, category)
    print(f"[{PROF_NAME}] ✅ Saved vector ID {vector_id} to '{PERSONAL_INDEX}' index.", flush=True)

    return {
        "vector_id": vector_id,
        "text": refined_text,
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "origin_id": original_vector_id
    }

# === Run Standalone ===
if __name__ == "__main__":
    test_input = "How do AI systems evolve trust mechanisms during human-AI collaboration?"
    process_with_professor(test_input)
