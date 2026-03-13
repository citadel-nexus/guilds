# src/azure/cosmos_memory.py
"""
Azure Cosmos DB implementation of the MemoryStore interface.

Stores incident memories in a Cosmos DB container for scalable recall.
Partition key: /event_type (groups incidents by type for efficient queries).

Requires: pip install azure-cosmos azure-identity
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.memory.store_v2 import MemoryStore, MemoryHit
from src.azure.config import AzureConfig

try:
    from azure.cosmos import CosmosClient, PartitionKey
    _HAS_COSMOS = True
except ImportError:
    _HAS_COSMOS = False


class CosmosMemoryStore(MemoryStore):
    """
    Cosmos DB-backed memory store.
    Falls back gracefully if SDK is not installed.
    """

    def __init__(self, config: AzureConfig) -> None:
        if not _HAS_COSMOS:
            raise ImportError("azure-cosmos is required. Install with: pip install azure-cosmos")
        if not config.cosmos_connection:
            raise ValueError("AZURE_COSMOS_CONNECTION is required")

        self._client = CosmosClient.from_connection_string(config.cosmos_connection)
        self._db = self._client.create_database_if_not_exists(id=config.cosmos_database)
        self._container = self._db.create_container_if_not_exists(
            id=config.cosmos_container,
            partition_key=PartitionKey(path="/event_type"),
        )

    def recall(self, query: str, k: int = 3) -> List[MemoryHit]:
        """Query Cosmos DB for similar incidents using keyword matching."""
        query_tokens = query.lower().split()
        if not query_tokens:
            return []

        # Build a CONTAINS query for the top tokens
        conditions = " OR ".join(
            f"CONTAINS(LOWER(c.title), '{token}')" for token in query_tokens[:5]
        )
        sql = f"SELECT TOP {k} * FROM c WHERE {conditions} ORDER BY c._ts DESC"

        items = list(self._container.query_items(query=sql, enable_cross_partition_query=True))

        return [
            MemoryHit(
                id=item.get("id", ""),
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                tags=item.get("tags", []),
                confidence=item.get("confidence", 0.5),
                link=item.get("link"),
                occurred_at=item.get("occurred_at"),
            )
            for item in items
        ]

    def remember(
        self,
        event_id: str,
        summary: str,
        tags: List[str],
        outcome: str,
    ) -> None:
        """Store a new incident memory in Cosmos DB."""
        event_type = tags[0] if tags else "unknown"

        doc = {
            "id": f"mem-{uuid.uuid4().hex[:8]}",
            "event_id": event_id,
            "event_type": event_type,
            "title": summary,
            "snippet": f"Outcome: {outcome}",
            "tags": tags,
            "confidence": 1.0,
            "link": None,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        self._container.upsert_item(doc)
