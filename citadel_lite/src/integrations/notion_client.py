# src/integrations/notion_client.py
"""
Notion integration for knowledge base sync and incident documentation.

Syncs pipeline outcomes to a Notion database for team visibility.
Can also pull KB articles from Notion to enrich agent memory.

Falls back gracefully if Notion is not configured.

Usage:
    from src.integrations.notion_client import NotionClient
    client = NotionClient(api_key="...", database_id="...")
    client.create_incident_page(event_id, event_type, summary, decision, ...)
    articles = client.pull_kb_articles(limit=50)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

_NOTION_API = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


class NotionClient:
    """
    Notion API client for incident documentation and KB sync.

    Requires a Notion integration token and database ID.
    The database should have properties:
      - Title (title): Incident summary
      - Event ID (rich_text): Pipeline event ID
      - Type (select): Event type
      - Decision (select): approve/block/need_approval
      - Risk Score (number): 0-1
      - Status (status): Open/Resolved/Blocked
      - Tags (multi_select): Event tags
      - Created (date): Timestamp
    """

    def __init__(self, api_key: str = "", database_id: str = "") -> None:
        self._api_key = api_key
        self._database_id = database_id
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

    @property
    def is_available(self) -> bool:
        return bool(self._api_key and self._database_id and _HAS_HTTPX)

    # ---- Create Incident Page ----

    def create_incident_page(
        self,
        event_id: str,
        event_type: str,
        summary: str,
        decision: str = "",
        risk_score: float = 0.0,
        rationale: str = "",
        fix_description: str = "",
        pr_url: str = "",
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Create a Notion page documenting a pipeline incident. Returns page ID."""
        if not self.is_available:
            return None

        properties: Dict[str, Any] = {
            "Title": {"title": [{"text": {"content": summary[:200]}}]},
            "Event ID": {"rich_text": [{"text": {"content": event_id}}]},
            "Type": {"select": {"name": event_type}},
            "Risk Score": {"number": round(risk_score, 3)},
            "Created": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        }

        if decision:
            properties["Decision"] = {"select": {"name": decision}}

        if tags:
            properties["Tags"] = {
                "multi_select": [{"name": t} for t in tags[:10]]
            }

        # Build page content blocks
        children = []

        if rationale:
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "Rationale"}}]},
            })
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": rationale[:2000]}}]},
            })

        if fix_description:
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "Proposed Fix"}}]},
            })
            children.append({
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"text": {"content": fix_description[:2000]}}],
                    "language": "plain text",
                },
            })

        if pr_url:
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "Pull Request"}}]},
            })
            children.append({
                "object": "block",
                "type": "bookmark",
                "bookmark": {"url": pr_url},
            })

        body = {
            "parent": {"database_id": self._database_id},
            "properties": properties,
            "children": children,
        }

        try:
            resp = httpx.post(
                f"{_NOTION_API}/pages",
                headers=self._headers,
                json=body,
                timeout=15.0,
            )
            if resp.status_code in (200, 201):
                page_id = resp.json().get("id", "")
                logger.info("Notion page created: %s", page_id)
                return page_id
            else:
                logger.warning("Notion create failed: %s %s", resp.status_code, resp.text[:200])
                return None
        except Exception as e:
            logger.warning("Notion API error: %s", e)
            return None

    # ---- Pull KB Articles ----

    def pull_kb_articles(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Query the Notion database for existing KB articles.
        Returns simplified entries suitable for memory store injection.
        """
        if not self.is_available:
            return []

        body = {
            "page_size": min(limit, 100),
            "sorts": [{"property": "Created", "direction": "descending"}],
        }

        try:
            resp = httpx.post(
                f"{_NOTION_API}/databases/{self._database_id}/query",
                headers=self._headers,
                json=body,
                timeout=15.0,
            )
            if resp.status_code != 200:
                logger.warning("Notion query failed: %s", resp.status_code)
                return []

            results = resp.json().get("results", [])
            articles = []
            for page in results:
                props = page.get("properties", {})
                title = self._extract_title(props.get("Title", {}))
                event_id = self._extract_rich_text(props.get("Event ID", {}))
                event_type = self._extract_select(props.get("Type", {}))
                decision = self._extract_select(props.get("Decision", {}))
                risk = props.get("Risk Score", {}).get("number", 0.0)
                tags = self._extract_multi_select(props.get("Tags", {}))
                created = self._extract_date(props.get("Created", {}))

                articles.append({
                    "id": page.get("id", ""),
                    "title": title,
                    "snippet": f"Decision: {decision}, Risk: {risk:.2f}",
                    "tags": tags + [event_type] if event_type else tags,
                    "confidence": 1.0,
                    "link": page.get("url", ""),
                    "occurred_at": created,
                    "event_id": event_id,
                })

            return articles
        except Exception as e:
            logger.warning("Notion pull_kb_articles error: %s", e)
            return []

    # ---- Helpers ----

    @staticmethod
    def _extract_title(prop: Dict) -> str:
        items = prop.get("title", [])
        return items[0].get("text", {}).get("content", "") if items else ""

    @staticmethod
    def _extract_rich_text(prop: Dict) -> str:
        items = prop.get("rich_text", [])
        return items[0].get("text", {}).get("content", "") if items else ""

    @staticmethod
    def _extract_select(prop: Dict) -> str:
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""

    @staticmethod
    def _extract_multi_select(prop: Dict) -> List[str]:
        items = prop.get("multi_select", [])
        return [i.get("name", "") for i in items]

    @staticmethod
    def _extract_date(prop: Dict) -> str:
        date = prop.get("date")
        return date.get("start", "") if date else ""
