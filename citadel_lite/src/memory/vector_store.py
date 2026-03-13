# src/memory/vector_store.py
"""
FAISS-backed vector memory store for semantic incident recall.

Uses OpenAI/Azure OpenAI embeddings to convert incidents into dense vectors,
then uses FAISS for approximate nearest neighbor search. Falls back to
LocalMemoryStore keyword matching if FAISS or embeddings are unavailable.

Usage:
    from src.memory.vector_store import FaissMemoryStore
    store = FaissMemoryStore(config)
    hits = store.recall("CI failed missing dependency", k=5)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.memory.store_v2 import MemoryStore, MemoryHit

logger = logging.getLogger(__name__)

# Optional imports
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore
    _HAS_NUMPY = False

try:
    import faiss
    _HAS_FAISS = True
except ImportError:
    faiss = None  # type: ignore
    _HAS_FAISS = False


class EmbeddingClient:
    """
    Generates text embeddings via Azure OpenAI or OpenAI.
    Falls back to a simple bag-of-words hash if no API is available.
    """

    def __init__(self, config: Any = None) -> None:
        self._config = config
        self._client = None
        self._model = "text-embedding-3-small"
        self._dimension = 1536
        self._init_client()

    def _init_client(self) -> None:
        if self._config is None:
            return
        try:
            import openai
            if self._config.azure_openai_endpoint and self._config.azure_openai_key:
                self._client = openai.AzureOpenAI(
                    azure_endpoint=self._config.azure_openai_endpoint,
                    api_key=self._config.azure_openai_key,
                    api_version="2024-12-01-preview",
                )
                self._model = "text-embedding-3-small"
            elif self._config.openai_api_key:
                self._client = openai.OpenAI(api_key=self._config.openai_api_key)
                self._model = "text-embedding-3-small"
        except Exception as e:
            logger.warning("Embedding client init failed: %s", e)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def is_available(self) -> bool:
        return self._client is not None and _HAS_NUMPY

    def embed(self, texts: List[str]) -> "np.ndarray":
        """Embed a batch of texts. Returns (N, dimension) float32 array."""
        if not _HAS_NUMPY:
            raise RuntimeError("numpy required for embeddings")

        if self._client is not None:
            try:
                resp = self._client.embeddings.create(input=texts, model=self._model)
                vecs = [d.embedding for d in resp.data]
                return np.array(vecs, dtype=np.float32)
            except Exception as e:
                logger.warning("Embedding API call failed, using fallback: %s", e)

        # Fallback: deterministic hash-based pseudo-embeddings (for local dev)
        return self._hash_embed(texts)

    def _hash_embed(self, texts: List[str]) -> "np.ndarray":
        """Deterministic pseudo-embeddings from text hashes. Not semantic, but functional."""
        import hashlib
        vecs = []
        for text in texts:
            h = hashlib.sha512(text.lower().encode()).digest()
            # Repeat hash bytes to fill dimension, normalize
            raw = list(h) * (self._dimension // len(h) + 1)
            vec = np.array(raw[:self._dimension], dtype=np.float32)
            vec = vec / (np.linalg.norm(vec) + 1e-8)
            vecs.append(vec)
        return np.array(vecs, dtype=np.float32)


class FaissMemoryStore(MemoryStore):
    """
    FAISS-backed semantic memory store.

    Maintains a FAISS index alongside the JSON corpus. On recall, the query
    is embedded and searched against the index. New memories are embedded and
    added to the index immediately.

    Falls back to keyword matching if FAISS/numpy are not installed.
    """

    def __init__(
        self,
        config: Any = None,
        corpus_path: Optional[Path] = None,
        index_path: Optional[Path] = None,
    ) -> None:
        self.corpus_path = corpus_path or (
            Path(__file__).parent / "corpus.json"
        )
        self.index_path = index_path or (
            Path(__file__).parent / "faiss.index"
        )
        self._corpus: List[Dict[str, Any]] = []
        self._embedder = EmbeddingClient(config)
        self._index = None
        self._load()

    @property
    def is_vector_enabled(self) -> bool:
        return _HAS_FAISS and _HAS_NUMPY and self._index is not None

    def _load(self) -> None:
        # Load corpus
        if self.corpus_path.exists():
            raw = self.corpus_path.read_text(encoding="utf-8")
            self._corpus = json.loads(raw) if raw.strip() else []
        else:
            self._corpus = []

        # Load or build FAISS index
        if _HAS_FAISS and _HAS_NUMPY:
            if self.index_path.exists():
                try:
                    self._index = faiss.read_index(str(self.index_path))
                    logger.info("FAISS index loaded: %d vectors", self._index.ntotal)
                except Exception as e:
                    logger.warning("FAISS index load failed, rebuilding: %s", e)
                    self._rebuild_index()
            else:
                self._rebuild_index()
        else:
            logger.info("FAISS/numpy not available — using keyword fallback")

    def _rebuild_index(self) -> None:
        """Build FAISS index from entire corpus."""
        if not _HAS_FAISS or not _HAS_NUMPY or len(self._corpus) == 0:
            self._index = faiss.IndexFlatIP(self._embedder.dimension) if _HAS_FAISS else None
            return

        texts = [self._entry_text(e) for e in self._corpus]
        try:
            vecs = self._embedder.embed(texts)
            # Normalize for cosine similarity via inner product
            faiss.normalize_L2(vecs)
            self._index = faiss.IndexFlatIP(self._embedder.dimension)
            self._index.add(vecs)
            self._save_index()
            logger.info("FAISS index rebuilt: %d vectors", self._index.ntotal)
        except Exception as e:
            logger.warning("FAISS index rebuild failed: %s", e)
            self._index = faiss.IndexFlatIP(self._embedder.dimension)

    def _save_index(self) -> None:
        if self._index is not None and _HAS_FAISS:
            try:
                self.index_path.parent.mkdir(parents=True, exist_ok=True)
                faiss.write_index(self._index, str(self.index_path))
            except Exception as e:
                logger.warning("FAISS index save failed: %s", e)

    def _save_corpus(self) -> None:
        self.corpus_path.parent.mkdir(parents=True, exist_ok=True)
        self.corpus_path.write_text(
            json.dumps(self._corpus, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _entry_text(entry: Dict[str, Any]) -> str:
        """Concatenate entry fields into a single searchable string."""
        return " ".join([
            entry.get("title", ""),
            entry.get("snippet", ""),
            " ".join(entry.get("tags", [])),
        ])

    # ---- MemoryStore interface ----

    def recall(self, query: str, k: int = 3) -> List[MemoryHit]:
        """Semantic recall via FAISS, with keyword fallback."""
        if self.is_vector_enabled and len(self._corpus) > 0:
            return self._vector_recall(query, k)
        return self._keyword_recall(query, k)

    def remember(
        self,
        event_id: str,
        summary: str,
        tags: List[str],
        outcome: str,
    ) -> None:
        """Store a new incident and add its embedding to the FAISS index."""
        entry = {
            "id": f"mem-{uuid.uuid4().hex[:8]}",
            "title": summary,
            "snippet": f"Outcome: {outcome}",
            "tags": tags,
            "confidence": 1.0,
            "link": None,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "event_id": event_id,
        }
        self._corpus.append(entry)
        self._save_corpus()

        # Add to FAISS index
        if self.is_vector_enabled:
            try:
                text = self._entry_text(entry)
                vec = self._embedder.embed([text])
                faiss.normalize_L2(vec)
                self._index.add(vec)
                self._save_index()
            except Exception as e:
                logger.warning("Failed to add vector to FAISS: %s", e)

    # ---- Vector recall ----

    def _vector_recall(self, query: str, k: int) -> List[MemoryHit]:
        try:
            q_vec = self._embedder.embed([query])
            faiss.normalize_L2(q_vec)

            actual_k = min(k, self._index.ntotal)
            if actual_k == 0:
                return []

            scores, indices = self._index.search(q_vec, actual_k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._corpus):
                    continue
                entry = self._corpus[idx]
                results.append(MemoryHit(
                    id=entry.get("id", ""),
                    title=entry.get("title", ""),
                    snippet=entry.get("snippet", ""),
                    tags=entry.get("tags", []),
                    confidence=round(float(score), 3),
                    link=entry.get("link"),
                    occurred_at=entry.get("occurred_at"),
                ))
            return results
        except Exception as e:
            logger.warning("FAISS recall failed, falling back to keywords: %s", e)
            return self._keyword_recall(query, k)

    # ---- Keyword fallback ----

    def _keyword_recall(self, query: str, k: int) -> List[MemoryHit]:
        query_tokens = set(query.lower().split())
        scored = []
        for entry in self._corpus:
            text = self._entry_text(entry).lower()
            entry_tokens = set(text.split())
            overlap = query_tokens & entry_tokens
            if not overlap:
                continue
            confidence = len(overlap) / max(len(query_tokens), 1)
            scored.append((confidence, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            MemoryHit(
                id=entry.get("id", ""),
                title=entry.get("title", ""),
                snippet=entry.get("snippet", ""),
                tags=entry.get("tags", []),
                confidence=round(conf, 3),
                link=entry.get("link"),
                occurred_at=entry.get("occurred_at"),
            )
            for conf, entry in scored[:k]
        ]
