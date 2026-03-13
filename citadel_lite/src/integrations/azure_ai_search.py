# src/integrations/azure_ai_search.py
"""
Azure AI Search integration for enterprise-grade memory and incident search.

Uses Azure AI Search (formerly Cognitive Search) as a vector + full-text
hybrid search backend. Indexes incident data with embeddings for semantic
recall plus keyword filters for exact matching.

This is the enterprise-grade replacement for FAISS + local keyword search.

Falls back gracefully if Azure AI Search is not configured.

Usage:
    from src.integrations.azure_ai_search import AzureSearchMemory
    search = AzureSearchMemory(endpoint, key, index_name)
    hits = search.recall("CI failed missing dependency", k=5)
    search.index_incident(event_id, summary, tags, outcome)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.memory.store_v2 import MemoryStore, MemoryHit

logger = logging.getLogger(__name__)

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

_API_VERSION = "2024-07-01"


class AzureSearchMemory(MemoryStore):
    """
    Azure AI Search as a MemoryStore backend.

    Index schema:
      - id (string, key)
      - title (string, searchable)
      - snippet (string, searchable)
      - tags (Collection(string), filterable, facetable)
      - event_type (string, filterable)
      - event_id (string, filterable)
      - confidence (double)
      - occurred_at (DateTimeOffset)
      - content_vector (Collection(single), dimension=1536)  # for vector search
    """

    def __init__(
        self,
        endpoint: str = "",
        api_key: str = "",
        index_name: str = "citadel-incidents",
        embedding_client: Any = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._index_name = index_name
        self._embedding_client = embedding_client
        self._headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }

    @property
    def is_available(self) -> bool:
        return bool(self._endpoint and self._api_key and _HAS_HTTPX)

    # ---- MemoryStore Interface ----

    def recall(self, query: str, k: int = 3) -> List[MemoryHit]:
        """Hybrid search: vector + keyword with semantic ranking."""
        if not self.is_available:
            return []

        body: Dict[str, Any] = {
            "search": query,
            "top": k,
            "queryType": "semantic",
            "semanticConfiguration": "default",
            "searchFields": "title,snippet,tags",
            "select": "id,title,snippet,tags,confidence,occurred_at,event_id",
        }

        # Add vector query if embeddings available
        if self._embedding_client and self._embedding_client.is_available:
            try:
                import numpy as np
                vec = self._embedding_client.embed([query])
                body["vectorQueries"] = [{
                    "kind": "vector",
                    "vector": vec[0].tolist(),
                    "fields": "content_vector",
                    "k": k,
                }]
            except Exception as e:
                logger.warning("Vector embedding for search failed: %s", e)

        try:
            url = f"{self._endpoint}/indexes/{self._index_name}/docs/search?api-version={_API_VERSION}"
            resp = httpx.post(url, headers=self._headers, json=body, timeout=10.0)
            if resp.status_code != 200:
                logger.warning("Azure AI Search query failed: %s", resp.status_code)
                return []

            results = resp.json().get("value", [])
            return [
                MemoryHit(
                    id=r.get("id", ""),
                    title=r.get("title", ""),
                    snippet=r.get("snippet", ""),
                    tags=r.get("tags", []),
                    confidence=r.get("@search.score", 0.0),
                    occurred_at=r.get("occurred_at"),
                )
                for r in results
            ]
        except Exception as e:
            logger.warning("Azure AI Search recall failed: %s", e)
            return []

    def remember(
        self,
        event_id: str,
        summary: str,
        tags: List[str],
        outcome: str,
    ) -> None:
        """Index a new incident in Azure AI Search."""
        if not self.is_available:
            return

        doc: Dict[str, Any] = {
            "id": f"mem-{uuid.uuid4().hex[:8]}",
            "title": summary,
            "snippet": f"Outcome: {outcome}",
            "tags": tags,
            "event_id": event_id,
            "confidence": 1.0,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }

        # Add vector embedding
        if self._embedding_client and self._embedding_client.is_available:
            try:
                text = f"{summary} {' '.join(tags)} {outcome}"
                import numpy as np
                vec = self._embedding_client.embed([text])
                import faiss
                faiss.normalize_L2(vec)
                doc["content_vector"] = vec[0].tolist()
            except Exception:
                pass

        try:
            url = f"{self._endpoint}/indexes/{self._index_name}/docs/index?api-version={_API_VERSION}"
            body = {"value": [{"@search.action": "mergeOrUpload", **doc}]}
            resp = httpx.post(url, headers=self._headers, json=body, timeout=10.0)
            if resp.status_code not in (200, 201):
                logger.warning("Azure AI Search index failed: %s", resp.status_code)
        except Exception as e:
            logger.warning("Azure AI Search remember failed: %s", e)

    # ---- Index Management ----

    def ensure_index(self) -> bool:
        """Create the search index if it doesn't exist."""
        if not self.is_available:
            return False

        index_def = {
            "name": self._index_name,
            "fields": [
                {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
                {"name": "title", "type": "Edm.String", "searchable": True, "analyzer": "en.microsoft"},
                {"name": "snippet", "type": "Edm.String", "searchable": True, "analyzer": "en.microsoft"},
                {"name": "tags", "type": "Collection(Edm.String)", "filterable": True, "facetable": True, "searchable": True},
                {"name": "event_type", "type": "Edm.String", "filterable": True},
                {"name": "event_id", "type": "Edm.String", "filterable": True},
                {"name": "confidence", "type": "Edm.Double"},
                {"name": "occurred_at", "type": "Edm.DateTimeOffset", "filterable": True, "sortable": True},
                {
                    "name": "content_vector",
                    "type": "Collection(Edm.Single)",
                    "searchable": True,
                    "dimensions": 1536,
                    "vectorSearchProfile": "default-vector",
                },
            ],
            "vectorSearch": {
                "algorithms": [{"name": "hnsw-algo", "kind": "hnsw"}],
                "profiles": [{"name": "default-vector", "algorithm": "hnsw-algo"}],
            },
            "semantic": {
                "configurations": [{
                    "name": "default",
                    "prioritizedFields": {
                        "titleField": {"fieldName": "title"},
                        "contentFields": [{"fieldName": "snippet"}],
                        "keywordsFields": [{"fieldName": "tags"}],
                    },
                }],
            },
        }

        try:
            url = f"{self._endpoint}/indexes/{self._index_name}?api-version={_API_VERSION}"
            resp = httpx.put(url, headers=self._headers, json=index_def, timeout=15.0)
            if resp.status_code in (200, 201, 204):
                logger.info("Azure AI Search index ensured: %s", self._index_name)
                return True
            else:
                logger.warning("Azure AI Search index creation failed: %s %s", resp.status_code, resp.text[:200])
                return False
        except Exception as e:
            logger.warning("Azure AI Search ensure_index failed: %s", e)
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        if not self.is_available:
            return {"available": False}
        try:
            url = f"{self._endpoint}/indexes/{self._index_name}/stats?api-version={_API_VERSION}"
            resp = httpx.get(url, headers=self._headers, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "available": True,
                    "document_count": data.get("documentCount", 0),
                    "storage_size": data.get("storageSize", 0),
                }
            return {"available": True, "error": resp.status_code}
        except Exception as e:
            return {"available": False, "error": str(e)}
