"""
Notion API client for MCA (Market Coverage & Automation) evolution tracking.

Manages two Notion surfaces:
  1. Evolution Tracker page  — one callout block per EVO cycle (create + patch)
  2. ZES RAG database        — query existing docs, create draft pages, update status

All public functions are safe to call when ``NOTION_TOKEN`` is unset —
they log a warning and return an empty/None result (dry-run safe).

CGRF compliance
---------------
_MODULE_NAME    = "notion_mca_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
# CGRF metadata
# --------------------------------------------------------------------------- #
_MODULE_NAME = "notion_mca_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
_BASE_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _token() -> Optional[str]:
    return os.getenv("NOTION_TOKEN")


def _evo_tracker_id() -> Optional[str]:
    return os.getenv("NOTION_EVO_TRACKER_PAGE_ID")


def _rag_db_id() -> Optional[str]:
    return os.getenv("NOTION_ZES_RAG_DB_ID")


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _is_configured() -> bool:
    """Return True when the Notion token is available."""
    tok = _token()
    if not tok:
        logger.warning("[notion_mca] NOTION_TOKEN not set — skipping Notion write")
        return False
    return True


# --------------------------------------------------------------------------- #
# Block builders  (mirrors control_loop _rt / _heading / _bullet / _code_block)
# --------------------------------------------------------------------------- #

def _rt(text: str, bold: bool = False, code: bool = False) -> Dict[str, Any]:
    """Rich-text object for a single text run."""
    ann: Dict[str, Any] = {"bold": bold, "code": code}
    return {"type": "text", "text": {"content": text}, "annotations": ann}


def _heading(level: int, text: str) -> Dict[str, Any]:
    """heading_1 / heading_2 / heading_3 block."""
    key = f"heading_{min(max(level, 1), 3)}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": [_rt(text, bold=True)]},
    }


def _bullet(text: str, bold: bool = False) -> Dict[str, Any]:
    """Bulleted list item block."""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [_rt(text, bold=bold)]},
    }


def _numbered(text: str) -> Dict[str, Any]:
    """Numbered list item block."""
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": [_rt(text)]},
    }


def _code_block(content: str, language: str = "json") -> Dict[str, Any]:
    """Code block."""
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": [_rt(content)],
            "language": language,
        },
    }


def _divider() -> Dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _callout(text: str, emoji: str = "📊", color: str = "blue_background") -> Dict[str, Any]:
    """Callout block — used as the cycle summary header."""
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [_rt(text, bold=True)],
            "icon": {"type": "emoji", "emoji": emoji},
            "color": color,
        },
    }


def _paragraph(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [_rt(text)]},
    }


# --------------------------------------------------------------------------- #
# Low-level API helpers
# --------------------------------------------------------------------------- #

def _post(path: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = f"{_BASE_URL}{path}"
    try:
        resp = requests.post(url, headers=_headers(), json=body, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.error("[notion_mca] POST %s failed: %s", path, exc)
        return None


def _patch(path: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = f"{_BASE_URL}{path}"
    try:
        resp = requests.patch(url, headers=_headers(), json=body, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.error("[notion_mca] PATCH %s failed: %s", path, exc)
        return None


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    url = f"{_BASE_URL}{path}"
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.error("[notion_mca] GET %s failed: %s", path, exc)
        return None


def _db_query(database_id: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _post(f"/databases/{database_id}/query", body)


# --------------------------------------------------------------------------- #
# Evolution Tracker  (EVO cycle pages under NOTION_EVO_TRACKER_PAGE_ID)
# --------------------------------------------------------------------------- #

def create_evo_cycle_page(
    cycle_id: str,
    event_type: str,
    domain: str,
    proposal_count: int,
    top_proposals: List[Dict[str, Any]],
    health_score: float,
    duration_seconds: float,
    raw_payload: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Optional[str]:
    """
    Create a new child page under the EVO Tracker page for one evolution cycle.

    Returns the Notion page ID on success, or None.

    Parameters
    ----------
    cycle_id        : Unique cycle identifier, e.g. ``"evo-2026-02-25-001"``
    event_type      : e.g. ``"market_expansion"``
    domain          : Primary domain, e.g. ``"sales"``
    proposal_count  : Total proposals generated
    top_proposals   : List of up to 5 dicts with keys ``title``, ``priority``, ``ep_type``
    health_score    : Float 0–100 MCA domain health score
    duration_seconds: Pipeline duration in seconds
    raw_payload     : Optional full result dict serialised into a code block
    dry_run         : When True, build blocks but skip the API call
    """
    if not dry_run and not _is_configured():
        return None

    parent_id = _evo_tracker_id()
    if not dry_run and not parent_id:
        logger.warning("[notion_mca] NOTION_EVO_TRACKER_PAGE_ID not set")
        return None

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    grade = _score_to_grade(health_score)
    color = _grade_to_callout_color(grade)

    blocks: List[Dict[str, Any]] = [
        _callout(
            f"[{grade}] Cycle {cycle_id} — {event_type} / {domain} "
            f"| score={health_score:.1f} | proposals={proposal_count} | {ts}",
            emoji=_grade_to_emoji(grade),
            color=color,
        ),
        _divider(),
        _heading(2, "Top Proposals"),
    ]

    for i, prop in enumerate(top_proposals[:5], 1):
        title = prop.get("title", "—")
        priority = prop.get("priority", "?")
        ep_type = prop.get("ep_type", "?")
        blocks.append(_numbered(f"[{priority}] {title}  (EP: {ep_type})"))

    blocks += [
        _divider(),
        _heading(2, "Metrics"),
        _bullet(f"Health score: {health_score:.1f} / 100  (Grade {grade})"),
        _bullet(f"Proposals generated: {proposal_count}"),
        _bullet(f"Pipeline duration: {duration_seconds:.2f} s"),
        _bullet(f"Domain: {domain}"),
        _bullet(f"Event type: {event_type}"),
    ]

    if raw_payload:
        blocks += [
            _divider(),
            _heading(2, "Raw Payload"),
            _code_block(json.dumps(raw_payload, ensure_ascii=False, indent=2)),
        ]

    page_title = f"[EVO] {cycle_id} — {event_type}"

    if dry_run:
        logger.info("[notion_mca] dry_run: would create page '%s' with %d blocks", page_title, len(blocks))
        return "dry-run-page-id"

    body = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {"title": [{"text": {"content": page_title}}]}
        },
        "children": blocks,
    }
    result = _post("/pages", body)
    if result:
        page_id = result.get("id", "")
        logger.info("[notion_mca] Created EVO cycle page: %s (%s)", page_title, page_id)
        return page_id
    return None


def patch_evo_tracker_callout(
    page_id: str,
    cycle_id: str,
    health_score: float,
    status: str,
    note: str = "",
) -> bool:
    """
    Append a status update callout to an existing EVO cycle page.

    Parameters
    ----------
    page_id     : Notion page ID returned by ``create_evo_cycle_page``
    cycle_id    : Cycle identifier for logging
    health_score: Updated health score
    status      : e.g. ``"approved"``, ``"rejected"``, ``"pending"``
    note        : Optional free-text note

    Returns True on success.
    """
    if not _is_configured():
        return False

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    grade = _score_to_grade(health_score)

    new_blocks: List[Dict[str, Any]] = [
        _divider(),
        _callout(
            f"[UPDATE {ts}] Status={status} | score={health_score:.1f} (Grade {grade})"
            + (f" — {note}" if note else ""),
            emoji="🔄",
            color="gray_background",
        ),
    ]

    result = _patch(f"/blocks/{page_id}/children", {"children": new_blocks})
    if result:
        logger.info("[notion_mca] Patched EVO page %s with status=%s", cycle_id, status)
        return True
    return False


# --------------------------------------------------------------------------- #
# ZES RAG Database  (NOTION_ZES_RAG_DB_ID)
# --------------------------------------------------------------------------- #

def query_rag_database(
    domain_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    page_size: int = 20,
) -> List[Dict[str, Any]]:
    """
    Query the ZES RAG Notion database and return simplified document dicts.

    Each returned dict has keys: ``id``, ``title``, ``domain``, ``status``,
    ``tags``, ``last_edited``.

    Parameters
    ----------
    domain_filter   : Filter by the ``domain`` select property value
    status_filter   : Filter by the ``status`` select property value
    page_size       : Max number of results (Notion API max 100)
    """
    if not _is_configured():
        return []

    db_id = _rag_db_id()
    if not db_id:
        logger.warning("[notion_mca] NOTION_ZES_RAG_DB_ID not set")
        return []

    filters: List[Dict[str, Any]] = []
    if domain_filter:
        filters.append({
            "property": "domain",
            "select": {"equals": domain_filter},
        })
    if status_filter:
        filters.append({
            "property": "status",
            "select": {"equals": status_filter},
        })

    body: Dict[str, Any] = {"page_size": min(page_size, 100)}
    if len(filters) == 1:
        body["filter"] = filters[0]
    elif len(filters) > 1:
        body["filter"] = {"and": filters}

    result = _db_query(db_id, body)
    if not result:
        return []

    docs: List[Dict[str, Any]] = []
    for page in result.get("results", []):
        props = page.get("properties", {})
        docs.append({
            "id": page.get("id", ""),
            "title": _extract_title(props),
            "domain": _extract_select(props, "domain"),
            "status": _extract_select(props, "status"),
            "tags": _extract_multi_select(props, "tags"),
            "last_edited": page.get("last_edited_time", ""),
        })
    return docs


def create_rag_draft_page(
    title: str,
    domain: str,
    content_blocks: List[Dict[str, Any]],
    tags: Optional[List[str]] = None,
    dry_run: bool = False,
) -> Optional[str]:
    """
    Create a new draft page in the ZES RAG database.

    Returns the new page ID on success, or None.

    Parameters
    ----------
    title           : Page title
    domain          : Domain select value, e.g. ``"sales"``
    content_blocks  : List of Notion block dicts
    tags            : Optional list of tag strings
    dry_run         : When True, skip the API call
    """
    if not dry_run and not _is_configured():
        return None

    db_id = _rag_db_id()
    if not dry_run and not db_id:
        logger.warning("[notion_mca] NOTION_ZES_RAG_DB_ID not set")
        return None

    if dry_run:
        logger.info("[notion_mca] dry_run: would create RAG draft '%s' in domain='%s'", title, domain)
        return "dry-run-rag-id"

    multi_select = [{"name": t} for t in (tags or [])]
    properties: Dict[str, Any] = {
        "title": {"title": [{"text": {"content": title}}]},
        "domain": {"select": {"name": domain}},
        "status": {"select": {"name": "draft"}},
    }
    if multi_select:
        properties["tags"] = {"multi_select": multi_select}

    body = {
        "parent": {"database_id": db_id},
        "properties": properties,
        "children": content_blocks,
    }
    result = _post("/pages", body)
    if result:
        page_id = result.get("id", "")
        logger.info("[notion_mca] Created RAG draft page: '%s' (%s)", title, page_id)
        return page_id
    return None


def update_rag_page_status(page_id: str, new_status: str) -> bool:
    """
    Update the ``status`` select property of a ZES RAG page.

    Parameters
    ----------
    page_id     : Notion page ID
    new_status  : e.g. ``"published"``, ``"archived"``, ``"draft"``

    Returns True on success.
    """
    if not _is_configured():
        return False

    body = {"properties": {"status": {"select": {"name": new_status}}}}
    result = _patch(f"/pages/{page_id}", body)
    if result:
        logger.info("[notion_mca] Updated RAG page %s → status=%s", page_id, new_status)
        return True
    return False


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "S"
    if score >= 75:
        return "A"
    if score >= 60:
        return "B"
    if score >= 45:
        return "C"
    return "D"


def _grade_to_callout_color(grade: str) -> str:
    return {
        "S": "green_background",
        "A": "blue_background",
        "B": "yellow_background",
        "C": "orange_background",
        "D": "red_background",
    }.get(grade, "gray_background")


def _grade_to_emoji(grade: str) -> str:
    return {
        "S": "🌟",
        "A": "✅",
        "B": "🔵",
        "C": "⚠️",
        "D": "🔴",
    }.get(grade, "📊")


def _extract_title(props: Dict[str, Any]) -> str:
    for key in ("title", "Name", "Title"):
        if key in props:
            rt = props[key].get("title", [])
            if rt:
                return rt[0].get("plain_text", "")
    return ""


def _extract_select(props: Dict[str, Any], key: str) -> str:
    prop = props.get(key, {})
    sel = prop.get("select")
    return sel.get("name", "") if sel else ""


def _extract_multi_select(props: Dict[str, Any], key: str) -> List[str]:
    prop = props.get(key, {})
    items = prop.get("multi_select", [])
    return [item.get("name", "") for item in items]
