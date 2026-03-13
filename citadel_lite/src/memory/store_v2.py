# src/memory/store.py
"""
Memory store for past incident recall and learning.

Provides:
- recall(query, k) -> List[MemoryHit]  — find similar past incidents
- remember(event_id, summary, tags, outcome) — store a new incident

LocalMemoryStore uses keyword matching on a JSON corpus file (stdlib only).
CosmosMemoryStore (in src/azure/) will implement the same interface with Azure Cosmos DB.
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class MemoryHit:
    """A single memory recall result."""
    id: str = ""
    # Compatibility: many parts of the pipeline expect "memory_id"
    memory_id: str = ""
    title: str = ""
    snippet: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.0
    link: Optional[str] = None
    occurred_at: Optional[str] = None
    # Compatibility: some callers attach evidence; LocalMemoryStore can ignore it
    evidence: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Keep id and memory_id consistent
        if self.memory_id and not self.id:
            self.id = self.memory_id
        if self.id and not self.memory_id:
            self.memory_id = self.id

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MemoryStore(ABC):
    """Abstract interface for the memory layer."""

    @abstractmethod
    def recall(
        self,
        query: str,
        k: int = 3,
        *,
        top_k: Optional[int] = None,
        evidence: Optional[Sequence[str]] = None,
        tags: Optional[Sequence[str]] = None,
        **kwargs: Any,
    ) -> List[MemoryHit]:
        """
        Find up to k similar past incidents.

        Compatibility notes:
        - Newer agents call recall(query=..., top_k=..., tags=..., evidence=...)
        - Older code calls recall(query, k)
        This signature accepts both and ignores unsupported extras deterministically.
        """
        ...

    @abstractmethod
    def remember(
        self,
        event_id: str,
        summary: str,
        tags: Optional[Sequence[str]] = None,
        outcome: str = "",
        **kwargs: Any,
    ) -> None:
        """Store a new incident for future recall."""
        ...


class LocalMemoryStore(MemoryStore):
    """
    File-based memory store using keyword matching.
    Corpus is loaded from a JSON file and new memories are appended to it.
    """

    def __init__(self, corpus_path: Optional[Path] = None) -> None:
        self.corpus_path = corpus_path or (
            Path(__file__).parent / "corpus.json"
        )
        self._corpus: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self.corpus_path.exists():
            raw = self.corpus_path.read_text(encoding="utf-8")
            self._corpus = json.loads(raw) if raw.strip() else []
        else:
            self._corpus = []

    def _save(self) -> None:
        self.corpus_path.parent.mkdir(parents=True, exist_ok=True)
        self.corpus_path.write_text(
            json.dumps(self._corpus, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def recall(
        self,
        query: str,
        k: int = 3,
        *,
        top_k: Optional[int] = None,
        evidence: Optional[Sequence[str]] = None,
        tags: Optional[Sequence[str]] = None,
        **kwargs: Any,
    ) -> List[MemoryHit]:
        """Keyword matching: score each corpus entry by overlap with query tokens."""
        # Normalize requested K
        k_eff = int(top_k) if top_k is not None else int(k)
        k_eff = max(k_eff, 0)

        # Normalize optional inputs
        query_tokens = set(query.lower().split())
        filter_tags = [t.lower() for t in (tags or [])]
        ev_list = list(evidence or [])

        query_tokens = set(query.lower().split())
        scored = []

        for entry in self._corpus:
            # Optional tag filter (deterministic): if tags are provided,
            # keep entries that share at least one tag.
            if filter_tags:
                entry_tags_lc = [t.lower() for t in entry.get("tags", [])]
                if not set(filter_tags) & set(entry_tags_lc):
                    continue

            # Build token set from title, snippet, and tags
            text = " ".join([
                entry.get("title", ""),
                entry.get("snippet", ""),
                " ".join(entry.get("tags", [])),
            ]).lower()
            entry_tokens = set(text.split())

            overlap = query_tokens & entry_tokens
            if not overlap:
                continue

            # Confidence = fraction of query tokens matched
            confidence = len(overlap) / max(len(query_tokens), 1)

            scored.append((confidence, entry))

        # Sort by confidence descending, take top k
        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            MemoryHit(
                id=entry.get("id", ""),
                memory_id=entry.get("id", ""),
                title=entry.get("title", ""),
                snippet=entry.get("snippet", ""),
                tags=entry.get("tags", []),
                confidence=round(conf, 3),
                link=entry.get("link"),
                occurred_at=entry.get("occurred_at"),
                evidence=ev_list,
            )
            for conf, entry in scored[:k_eff]
        ]

    def remember(
        self,
        event_id: str,
        summary: str,
        tags: Optional[Sequence[str]] = None,
        outcome: str = "",
        **kwargs: Any,
    ) -> None:
        """Append a new incident to the corpus."""
        # Optional richer fields for LEARN (kept deterministic + backward compatible)
        sherlock_label = str(kwargs.get("sherlock_label", "") or "")
        fix_summary = str(kwargs.get("fix_summary", "") or "")
        verify_success = kwargs.get("verify_success", None)
        try:
            verify_success_norm = bool(verify_success) if verify_success is not None else None
        except Exception:
            verify_success_norm = None
        risk_score = kwargs.get("risk_score", None)
        try:
            risk_score_norm = float(risk_score) if risk_score is not None else None
        except Exception:
            risk_score_norm = None

        verification_steps = kwargs.get("verification_steps", None)
        if not isinstance(verification_steps, list):
            verification_steps = None

        entry = {
            "id": f"mem-{uuid.uuid4().hex[:8]}",
            "title": summary,
            "snippet": f"Outcome: {outcome}",
            "tags": list(tags or []),
            "confidence": 1.0,
            "link": None,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "event_id": event_id,
            # --- LEARN fields (optional) ---
            "sherlock_label": sherlock_label,
            "fix_summary": fix_summary,
            "verify_success": verify_success_norm,
            "risk_score": risk_score_norm,
            "verification_steps": verification_steps,
            # Keep raw extras (namespaced) for forward compatibility
            "extras": {
                k: v
                for k, v in kwargs.items()
                if k not in {"sherlock_label", "fix_summary", "verify_success", "risk_score", "verification_steps"}
            },
        }
        self._corpus.append(entry)
        self._save()
