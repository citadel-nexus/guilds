# src/services/faiss_manager.py
"""
Multi-domain FAISS index manager for Sentinel memory.

Each domain (sentinel:personal, sentinel:technical, sentinel:promises,
sentinel:emotional, sentinel:growth, sentinel:all) maintains its own
FAISS IndexIDMap alongside JSON metadata and text stores on disk.

Usage:
    from src.services.faiss_manager import FAISSDomainManager

    # Add a vector
    await FAISSDomainManager.add(
        domain="sentinel:personal",
        vector=[...],          # list[float] len=1536
        metadata={"date": "2026-02-22", ...},
        text="raw text content"
    )

    # Search
    results = await FAISSDomainManager.search(
        domain="sentinel:all",
        vector=[...],
        top_k=5,
        filter_fn=lambda m: m.get("importance", 0) > 0.5
    )
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("sentinel.faiss")

# ── Optional deps ─────────────────────────────────────────────────────────────
try:
    import numpy as np
    import faiss
    _HAS_FAISS = True
except ImportError:
    np = None  # type: ignore
    faiss = None  # type: ignore
    _HAS_FAISS = False

DIMENSION = 1536  # text-embedding-3-small / Amazon Titan
INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "faiss_domains"


@dataclass
class SearchResult:
    id: int
    score: float
    text: str
    metadata: Dict[str, Any]


class _DomainIndex:
    """Per-domain FAISS index with metadata + text sidecar files."""

    def __init__(self, domain: str, base_dir: Path):
        self.domain = domain
        safe = domain.replace(":", "_")
        base_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = base_dir / f"{safe}.index"
        self._meta_path = base_dir / f"{safe}_meta.json"
        self._text_path = base_dir / f"{safe}_text.json"
        self._lock = threading.Lock()
        self._index = None
        self._meta: Dict[str, Dict] = {}
        self._texts: Dict[str, str] = {}
        self._next_id: int = 0
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        if not _HAS_FAISS:
            return
        if self._index_path.exists():
            try:
                self._index = faiss.read_index(str(self._index_path))
                logger.debug("[FAISS] loaded %s: %d vectors", self.domain, self._index.ntotal)
            except Exception as e:
                logger.warning("[FAISS] index load failed for %s: %s", self.domain, e)
                self._index = self._new_index()
        else:
            self._index = self._new_index()

        for path, store in [(self._meta_path, "_meta"), (self._text_path, "_texts")]:
            if path.exists():
                try:
                    setattr(self, store, json.loads(path.read_text("utf-8")))
                except Exception:
                    setattr(self, store, {})

        # Infer next_id from existing metadata keys
        if self._meta:
            self._next_id = max(int(k) for k in self._meta.keys()) + 1

    def _new_index(self):
        flat = faiss.IndexFlatIP(DIMENSION)
        return faiss.IndexIDMap(flat)

    def _save(self):
        if self._index is not None:
            faiss.write_index(self._index, str(self._index_path))
        self._meta_path.write_text(json.dumps(self._meta), encoding="utf-8")
        self._text_path.write_text(json.dumps(self._texts), encoding="utf-8")

    # ── Write ─────────────────────────────────────────────────────────────────

    def add(
        self,
        vector: List[float],
        metadata: Dict[str, Any],
        text: str,
    ) -> int:
        """Add a vector and return its integer ID."""
        if not _HAS_FAISS:
            vid = self._next_id
            self._next_id += 1
            self._meta[str(vid)] = metadata
            self._texts[str(vid)] = text
            return vid

        with self._lock:
            vid = self._next_id
            self._next_id += 1

            arr = np.array([vector], dtype="float32")
            faiss.normalize_L2(arr)
            ids = np.array([vid], dtype="int64")
            self._index.add_with_ids(arr, ids)

            self._meta[str(vid)] = metadata
            self._texts[str(vid)] = text
            self._save()
            return vid

    def update_metadata(self, vector_id: int, updates: Dict[str, Any]):
        with self._lock:
            if str(vector_id) in self._meta:
                self._meta[str(vector_id)].update(updates)
                self._save()

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        vector: List[float],
        top_k: int = 5,
        filter_fn: Optional[Callable[[Dict], bool]] = None,
    ) -> List[SearchResult]:
        if not _HAS_FAISS or self._index is None or self._index.ntotal == 0:
            return []

        with self._lock:
            arr = np.array([vector], dtype="float32")
            faiss.normalize_L2(arr)
            k = min(top_k * 3, self._index.ntotal)  # over-fetch for post-filter
            scores, ids = self._index.search(arr, k)

        results = []
        for score, vid in zip(scores[0], ids[0]):
            if vid < 0:
                continue
            meta = self._meta.get(str(vid), {})
            if filter_fn and not filter_fn(meta):
                continue
            results.append(SearchResult(
                id=int(vid),
                score=float(score),
                text=self._texts.get(str(vid), ""),
                metadata=meta,
            ))
            if len(results) >= top_k:
                break
        return results


class _FAISSDomainManager:
    """
    Singleton manager — one _DomainIndex per domain, shared across
    all async callers with per-domain threading locks.
    """

    def __init__(self):
        self._indexes: Dict[str, _DomainIndex] = {}
        self._init_lock = threading.Lock()

    def _get_or_create(self, domain: str) -> _DomainIndex:
        if domain not in self._indexes:
            with self._init_lock:
                if domain not in self._indexes:
                    self._indexes[domain] = _DomainIndex(domain, INDEX_DIR)
        return self._indexes[domain]

    # ── Async public API ──────────────────────────────────────────────────────

    async def add(
        self,
        domain: str,
        vector: List[float],
        metadata: Dict[str, Any],
        text: str,
    ) -> int:
        idx = self._get_or_create(domain)
        return await asyncio.to_thread(idx.add, vector, metadata, text)

    async def search(
        self,
        domain: str,
        vector: List[float],
        top_k: int = 5,
        filter_fn: Optional[Callable[[Dict], bool]] = None,
    ) -> List[SearchResult]:
        idx = self._get_or_create(domain)
        return await asyncio.to_thread(idx.search, vector, top_k, filter_fn)

    async def update_metadata(
        self,
        domain: str,
        vector_id: int,
        updates: Dict[str, Any],
    ):
        idx = self._get_or_create(domain)
        await asyncio.to_thread(idx.update_metadata, vector_id, updates)


# Module-level singleton
FAISSDomainManager = _FAISSDomainManager()
