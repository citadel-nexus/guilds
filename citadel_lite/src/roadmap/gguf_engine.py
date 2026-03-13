"""GGUF local inference engine with rule-based fallback.

Uses ``llama-cpp-python`` when available and a model path is configured
via the ``CITADEL_GGUF_MODEL`` environment variable.  Falls back to
deterministic rule-based generation when the library is absent or the
model file is not found.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "gguf_engine"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Optional llama-cpp-python import
# ---------------------------------------------------------------------------
_HAS_LLAMA = False
try:
    from llama_cpp import Llama  # type: ignore
    _HAS_LLAMA = True
except ImportError:
    Llama = None  # type: ignore

# ---------------------------------------------------------------------------
# Risk / recommendation keyword maps
# ---------------------------------------------------------------------------
_RISK_KEYWORDS = [
    ("blocked", "Item is blocked — check dependencies before proceeding."),
    ("依存", "Dependency detected — verify upstream availability."),
    ("未実装", "Implementation pending — priority review recommended."),
    ("TODO", "TODO marker present — item requires action."),
    ("deprecated", "Deprecated reference — consider updating."),
]

_RECOMMEND_MAP = {
    ("done", "verified"): "Item is complete and verified. No action needed.",
    ("done", "tested"): "Item is complete and tested. Consider final verification.",
    ("done", "unknown"): "Item is marked done but lacks test evidence. Add tests.",
    ("done", "not_tested"): "Item done but untested. Add regression tests.",
    ("in_progress", "tested"): "Item in progress with tests. Keep coverage updated.",
    ("in_progress", "unknown"): "Item in progress. Add tests as you develop.",
    ("blocked", "unknown"): "Unblock this item — identify and resolve dependencies.",
    ("planned", "unknown"): "Item is planned. Assign to a sprint and track progress.",
    ("unknown", "unknown"): "Status unclear. Review and assign a definitive status.",
}


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------

def load_model() -> Optional[Any]:
    """Load a GGUF model from ``CITADEL_GGUF_MODEL`` env var.

    Returns:
        A ``Llama`` instance if the library is installed and the model
        file exists; ``None`` otherwise.
    """
    if not _HAS_LLAMA:
        return None

    model_path = os.environ.get("CITADEL_GGUF_MODEL", "")
    if not model_path or not os.path.isfile(model_path):
        return None

    try:
        return Llama(model_path=model_path, n_ctx=512, verbose=False)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Generation functions
# ---------------------------------------------------------------------------

def generate_text(
    prompt: str,
    model: Optional[Any] = None,
    max_tokens: int = 200,
) -> str:
    """Generate text from *prompt*.

    Uses the GGUF model when available; falls back to rule-based summarise.
    """
    if model is not None and _HAS_LLAMA:
        try:
            result = model.create_completion(
                prompt,
                max_tokens=max_tokens,
                stop=["\n\n"],
                temperature=0.2,
            )
            return result["choices"][0]["text"].strip()
        except Exception:
            pass  # Fall through to rule-based

    return summarize(prompt)


def summarize(text: str, max_chars: int = 150) -> str:
    """Rule-based summary: return the first *max_chars* characters, cleaned up."""
    # Strip markdown symbols
    cleaned = re.sub(r"[#*`>_~|]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    # Truncate at last word boundary
    truncated = cleaned[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        truncated = truncated[:last_space]
    return truncated + "..."


def generate_risk(text: str) -> str:
    """Return a risk note string based on keyword detection in *text*."""
    notes = []
    text_lower = text.lower()
    for keyword, note in _RISK_KEYWORDS:
        if keyword.lower() in text_lower:
            notes.append(note)
    if notes:
        return " | ".join(notes)
    return ""


def recommend(status: str, verify: str) -> str:
    """Return a recommendation string for a given (status, verify) pair."""
    key = (status, verify)
    if key in _RECOMMEND_MAP:
        return _RECOMMEND_MAP[key]
    # Partial match on status
    for (s, _v), rec in _RECOMMEND_MAP.items():
        if s == status:
            return rec
    return "Review item status and verification evidence."
