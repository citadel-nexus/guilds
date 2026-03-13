# src/services/notion_memory_vault.py
"""
Notion Memory Vault — async Notion page writer for Sentinel memories.

Creates structured pages in the configured Notion database with
domain tags, importance scores, conversation backlinks, and date stamps.
Falls back gracefully when Notion is not configured.

Usage:
    vault = NotionMemoryVault()
    page_id = await vault.create_memory_page(
        title="Talked about FAISS indexer",
        content="Full text of the memory...",
        domain="sentinel:technical",
        tags=["faiss", "architecture"],
        conversation_id="conv_abc",
        importance=0.8,
        date="2026-02-22T00:00:00Z",
    )
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional

logger = logging.getLogger("sentinel.notion_vault")

# ── Optional notion-client dep ────────────────────────────────────────────────
try:
    from notion_client import Client as _NotionClient
    _HAS_NOTION = True
except ImportError:
    _HAS_NOTION = False
    _NotionClient = None  # type: ignore


class NotionMemoryVault:
    """Async Notion page creator for Sentinel memory objects."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        database_id: Optional[str] = None,
    ):
        self._api_key = api_key or os.environ.get("NOTION_API_KEY", "")
        self._database_id = database_id or os.environ.get(
            "NOTION_SENTINEL_DB_ID",
            os.environ.get("NOTION_DATABASE_ID", ""),
        )
        self._client = None
        if _HAS_NOTION and self._api_key:
            try:
                self._client = _NotionClient(auth=self._api_key)
            except Exception as e:
                logger.warning("[Notion] Client init failed: %s", e)

    @property
    def is_available(self) -> bool:
        return self._client is not None and bool(self._database_id)

    async def create_memory_page(
        self,
        title: str,
        content: str,
        domain: str,
        tags: List[str],
        conversation_id: str,
        importance: float,
        date: str,
    ) -> str:
        """
        Write a Sentinel memory to Notion.

        Returns the Notion page ID (or a placeholder if unavailable).
        """
        if not self.is_available:
            logger.debug(
                "[Notion] vault not configured — skipping page: %s", title[:60]
            )
            return f"notion_unavailable_{conversation_id[:8]}"

        properties = {
            "Name": {
                "title": [{"text": {"content": title[:200]}}]
            },
            "Domain": {
                "select": {"name": domain}
            },
            "Tags": {
                "multi_select": [{"name": t} for t in tags[:10]]
            },
            "Importance": {
                "number": round(importance, 2)
            },
            "Conversation ID": {
                "rich_text": [{"text": {"content": conversation_id}}]
            },
            "Date": {
                "date": {"start": date[:10]}
            },
        }

        body_block = {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": content[:2000]}}]
            },
        }

        def _create():
            return self._client.pages.create(
                parent={"database_id": self._database_id},
                properties=properties,
                children=[body_block],
            )

        try:
            result = await asyncio.to_thread(_create)
            page_id = result.get("id", "")
            logger.debug("[Notion] created page %s in %s", page_id[:8], domain)
            return page_id
        except Exception as e:
            logger.warning("[Notion] create_memory_page failed: %s", e)
            return f"notion_error_{conversation_id[:8]}"
