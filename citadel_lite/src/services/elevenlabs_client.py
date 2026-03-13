# src/services/elevenlabs_client.py
"""
ElevenLabs API client for Sentinel — fetches conversation transcripts
and agent metadata needed by the FAISS indexing worker.

Usage:
    client = ElevenLabsClient()
    transcript = await client.get_transcript(conversation_id)
    convos = await client.list_conversations(agent_id, since_date="2026-02-01")
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentinel.elevenlabs")

# ── Optional httpx dep ────────────────────────────────────────────────────────
try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


class ElevenLabsClient:
    """Async ElevenLabs Conversational AI API client."""

    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        if not self._api_key:
            logger.warning("[ElevenLabs] API key not configured")

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }

    async def get_transcript(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full conversation transcript from ElevenLabs.

        Returns the conversation object with transcript messages, or None on error.
        """
        if not _HAS_HTTPX or not self._api_key:
            return None
        url = f"{self.BASE_URL}/convai/conversations/{conversation_id}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=self._headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("[ElevenLabs] get_transcript(%s) failed: %s", conversation_id, e)
            return None

    async def list_conversations(
        self,
        agent_id: str,
        since_date: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List conversations for *agent_id*, optionally filtered by date.

        Returns a list of conversation metadata dicts (no full transcripts).
        """
        if not _HAS_HTTPX or not self._api_key:
            return []

        params: Dict[str, Any] = {
            "agent_id": agent_id,
            "page_size": min(limit, 100),
        }
        if since_date:
            params["created_after"] = since_date

        url = f"{self.BASE_URL}/convai/conversations"
        conversations = []
        cursor = None

        while len(conversations) < limit:
            if cursor:
                params["cursor"] = cursor
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url, headers=self._headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as e:
                logger.warning("[ElevenLabs] list_conversations page failed: %s", e)
                break

            page = data.get("conversations", [])
            conversations.extend(page)

            cursor = data.get("next_cursor")
            if not cursor or not page:
                break

        return conversations[:limit]

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Fetch agent configuration from ElevenLabs."""
        if not _HAS_HTTPX or not self._api_key:
            return None
        url = f"{self.BASE_URL}/convai/agents/{agent_id}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("[ElevenLabs] get_agent(%s) failed: %s", agent_id, e)
            return None

    def extract_transcript_text(self, conversation: Dict[str, Any]) -> str:
        """
        Flatten a conversation object into a single readable transcript string.
        Handles both 'messages' and 'transcript' array shapes.
        """
        lines = []
        messages = conversation.get("transcript", conversation.get("messages", []))
        for msg in messages:
            role = msg.get("role", msg.get("source", "unknown")).upper()
            text = msg.get("message", msg.get("content", "")).strip()
            if text:
                lines.append(f"{role}: {text}")
        return "\n".join(lines)
