# src/services/embedding.py
"""
Async text embedding service.

Wraps the existing synchronous EmbeddingClient from src/memory/vector_store.py
in asyncio.to_thread so all callers can use a clean async interface.

Usage:
    from src.services.embedding import embed_text, embed_batch
    vec = await embed_text("some text")            # returns list[float]
    vecs = await embed_batch(["text1", "text2"])   # returns list[list[float]]
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import List

import numpy as np

logger = logging.getLogger("sentinel.embedding")

# ── Lazy singleton embedder ───────────────────────────────────────────────────

_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder

    try:
        from src.memory.vector_store import EmbeddingClient

        class _ConfigShim:
            azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
            azure_openai_key = os.environ.get("AZURE_OPENAI_KEY", "")
            openai_api_key = os.environ.get("OPENAI_API_KEY", "")

        _embedder = EmbeddingClient(_ConfigShim())
    except Exception as e:
        logger.warning("EmbeddingClient init failed: %s", e)
        _embedder = None
    return _embedder


# ── Public API ────────────────────────────────────────────────────────────────

async def embed_text(text: str) -> List[float]:
    """Embed a single string and return a float list (len=1536)."""
    vecs = await embed_batch([text])
    return vecs[0]


async def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a list of strings. Returns list of float vectors."""
    def _sync_embed(batch: List[str]) -> np.ndarray:
        embedder = _get_embedder()
        if embedder is None:
            # Fallback: zero vector
            import numpy as _np
            return _np.zeros((len(batch), 1536), dtype="float32")
        return embedder.embed(batch)

    arr = await asyncio.to_thread(_sync_embed, texts)
    return [row.tolist() for row in arr]
