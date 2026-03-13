# engine/embedding_tools.py

import openai
import os
import numpy as np
from dotenv import load_dotenv

# === Load env ===
load_dotenv()

# === LLM用 (localhost) ===
openai.api_base = os.getenv("OPENAI_BASE_URL")
openai.api_key = os.getenv("OPENAI_API_KEY")



# === Embedding用 (OpenAI) ===
embedding_api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

if not embedding_api_key:
    raise EnvironmentError("❌ EMBEDDING_API_KEY (or OPENAI_API_KEY) not set in environment.")

def get_embedding(text: str) -> np.ndarray | None:
    """Generate embedding vector from text using OpenAI API."""
    if not text or not text.strip():
        print("[WARN] Empty or whitespace-only text provided to get_embedding().")
        return None

    try:
        client = openai.OpenAI(
            api_key=embedding_api_key,
            base_url=embedding_base_url
        )
        response = client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL
        )
        vector = response.data[0].embedding

        # Sanity check
        if not isinstance(vector, list):
            print(f"[ERROR] Invalid embedding format: expected list, got {type(vector)}")
            return None
        if len(vector) != EMBEDDING_DIM:
            print(f"[ERROR] Invalid embedding dimension: expected {EMBEDDING_DIM}, got {len(vector)}")
            return None

        return np.array(vector, dtype="float32")
    except Exception as e:
        print(f"[ERROR] Embedding API call failed: {e}")
        return None

def get_payload_embedding(payload: dict, field_priority=("refined_text", "input_text", "response_text")) -> np.ndarray | None:
    """
    Extracts text from payload and returns embedding vector.
    Prioritizes fields in given order.
    """
    for field in field_priority:
        text = payload.get(field)
        if text and isinstance(text, str) and text.strip():
            return get_embedding(text)

    print("[ERROR] No valid text field found in payload for embedding.")
    return None