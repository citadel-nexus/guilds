"""
Supabase REST mirror for MCA evolution cycle data.

Writes to two tables:
  - ``automation_events``  (existing, shared with pipeline audit)
  - ``mca_proposals``      (new, MCA-specific)

All public functions are safe to call when ``SUPABASE_URL`` / ``SUPABASE_SERVICE_KEY``
are unset — they log a warning and return None/[] (dry-run safe).

Uses the Supabase REST API directly (no supabase-py dependency) so it can coexist
with the existing ``SupabaseStore`` in ``src/integrations/supabase_client.py``.

CGRF compliance
---------------
_MODULE_NAME    = "supabase_mca_mirror"
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
_MODULE_NAME = "supabase_mca_mirror"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

def _base_url() -> Optional[str]:
    return os.getenv("SUPABASE_URL")


def _service_key() -> Optional[str]:
    return os.getenv("SUPABASE_SERVICE_KEY")


def _headers() -> Dict[str, str]:
    return {
        "apikey": _service_key() or "",
        "Authorization": f"Bearer {_service_key() or ''}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _is_configured() -> bool:
    """Return True when both SUPABASE_URL and SUPABASE_SERVICE_KEY are available."""
    if not _base_url() or not _service_key():
        logger.warning("[supabase_mca] SUPABASE_URL or SUPABASE_SERVICE_KEY not set — skipping write")
        return False
    return True


def _table_url(table: str) -> str:
    return f"{_base_url()}/rest/v1/{table}"


# --------------------------------------------------------------------------- #
# Internal low-level helpers
# --------------------------------------------------------------------------- #

def _post_row(table: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """INSERT a single row and return the inserted row, or None on error."""
    try:
        resp = requests.post(_table_url(table), headers=_headers(), json=row, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if isinstance(data, list) and data else data
    except requests.RequestException as exc:
        logger.error("[supabase_mca] POST %s failed: %s", table, exc)
        return None


def _post_rows(table: str, rows: List[Dict[str, Any]]) -> int:
    """INSERT multiple rows; returns the count of successfully inserted rows."""
    if not rows:
        return 0
    try:
        resp = requests.post(_table_url(table), headers=_headers(), json=rows, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return len(data) if isinstance(data, list) else 0
    except requests.RequestException as exc:
        logger.error("[supabase_mca] POST %s (batch %d rows) failed: %s", table, len(rows), exc)
        return 0


def _get_rows(
    table: str,
    params: Optional[Dict[str, str]] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """SELECT rows from a table with optional query params."""
    try:
        p = dict(params or {})
        p["limit"] = str(limit)
        resp = requests.get(_table_url(table), headers=_headers(), params=p, timeout=15)
        resp.raise_for_status()
        return resp.json() if isinstance(resp.json(), list) else []
    except requests.RequestException as exc:
        logger.error("[supabase_mca] GET %s failed: %s", table, exc)
        return []


# --------------------------------------------------------------------------- #
# Public API — Evolution cycles
# --------------------------------------------------------------------------- #

def mirror_evo_cycle(
    cycle_id: str,
    event_type: str,
    domain: str,
    health_score: float,
    proposal_count: int,
    approved_count: int,
    duration_seconds: float,
    notion_page_id: Optional[str] = None,
    extra_payload: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Optional[str]:
    """
    Write an EVO cycle record to the ``automation_events`` table.

    This mirrors the ``write_supabase_audit()`` pattern from perplexity_control_loop:
    one row per pipeline run, with structured ``payload`` JSONB.

    Parameters
    ----------
    cycle_id        : Unique cycle identifier, e.g. ``"evo-2026-02-25-001"``
    event_type      : e.g. ``"market_expansion"``
    domain          : Primary domain, e.g. ``"sales"``
    health_score    : Float 0–100
    proposal_count  : Total proposals generated
    approved_count  : Proposals auto-approved
    duration_seconds: End-to-end pipeline duration
    notion_page_id  : Notion page ID if created (may be None)
    extra_payload   : Optional extra fields merged into ``payload``
    dry_run         : When True, log the row but skip the INSERT

    Returns the row ``id`` (UUID string) on success, or None.
    """
    if not dry_run and not _is_configured():
        return None

    payload: Dict[str, Any] = {
        "cycle_id": cycle_id,
        "domain": domain,
        "health_score": health_score,
        "proposal_count": proposal_count,
        "approved_count": approved_count,
        "duration_seconds": duration_seconds,
        "notion_page_id": notion_page_id,
        **(extra_payload or {}),
    }

    row: Dict[str, Any] = {
        "event_type": "mca_evo_cycle",
        "source": "citadel_mca",
        "scope": event_type,
        "event": f"EVO cycle completed: {cycle_id}",
        "status": "completed",
        "payload": payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        logger.info("[supabase_mca] dry_run: would insert automation_events row for %s", cycle_id)
        return "dry-run-row-id"

    inserted = _post_row("automation_events", row)
    if inserted:
        row_id = inserted.get("id", "")
        logger.info("[supabase_mca] Mirrored EVO cycle %s → automation_events (id=%s)", cycle_id, row_id)
        return row_id
    return None


def mirror_proposals(
    cycle_id: str,
    proposals: List[Dict[str, Any]],
    dry_run: bool = False,
) -> int:
    """
    Bulk-insert proposals into the ``mca_proposals`` table.

    Each dict in ``proposals`` should contain at minimum:
      - ``title``     (str)
      - ``priority``  (str)  — e.g. ``"P1"``
      - ``ep_type``   (str)  — e.g. ``"new_feature"``
      - ``domain``    (str)
      - ``status``    (str)  — e.g. ``"pending"``

    Additional keys are serialised into the ``metadata`` JSONB column.

    Parameters
    ----------
    cycle_id    : Parent cycle identifier
    proposals   : List of proposal dicts
    dry_run     : When True, log but skip the INSERT

    Returns the count of rows successfully inserted.
    """
    if not proposals:
        return 0

    if not dry_run and not _is_configured():
        return 0

    KNOWN_COLS = {"title", "priority", "ep_type", "domain", "status"}
    ts = datetime.now(timezone.utc).isoformat()

    rows: List[Dict[str, Any]] = []
    for prop in proposals:
        meta = {k: v for k, v in prop.items() if k not in KNOWN_COLS}
        rows.append({
            "cycle_id": cycle_id,
            "title": prop.get("title", ""),
            "priority": prop.get("priority", "P3"),
            "ep_type": prop.get("ep_type", ""),
            "domain": prop.get("domain", ""),
            "status": prop.get("status", "pending"),
            "metadata": meta,
            "created_at": ts,
        })

    if dry_run:
        logger.info("[supabase_mca] dry_run: would insert %d rows into mca_proposals for %s", len(rows), cycle_id)
        return len(rows)

    inserted = _post_rows("mca_proposals", rows)
    logger.info("[supabase_mca] Inserted %d/%d proposals for cycle %s", inserted, len(proposals), cycle_id)
    return inserted


# --------------------------------------------------------------------------- #
# Public API — Reads
# --------------------------------------------------------------------------- #

def get_recent_cycles(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch recent MCA evolution cycle records from ``automation_events``.

    Returns a list of dicts, each with keys from the ``automation_events`` schema
    plus the decoded ``payload`` dict.

    Parameters
    ----------
    limit   : Max rows to return (default 10, max 100)
    """
    if not _is_configured():
        return []

    params = {
        "event_type": "eq.mca_evo_cycle",
        "order": "created_at.desc",
    }
    rows = _get_rows("automation_events", params=params, limit=min(limit, 100))

    result: List[Dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        result.append({**row, "payload": payload or {}})
    return result


def get_proposals_for_cycle(cycle_id: str) -> List[Dict[str, Any]]:
    """
    Fetch all proposals for a specific cycle from ``mca_proposals``.

    Parameters
    ----------
    cycle_id    : The cycle identifier to filter by
    """
    if not _is_configured():
        return []

    params = {
        "cycle_id": f"eq.{cycle_id}",
        "order": "priority.asc",
    }
    return _get_rows("mca_proposals", params=params, limit=100)


def get_domain_health_summary(domain: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Return recent health_score values from ``automation_events`` payload.

    Useful for computing domain health trends.

    Parameters
    ----------
    domain  : If provided, filter by payload->domain value using PostgREST JSON path
    limit   : Max rows

    Returns list of dicts with ``cycle_id``, ``domain``, ``health_score``, ``created_at``.
    """
    if not _is_configured():
        return []

    params: Dict[str, str] = {
        "event_type": "eq.mca_evo_cycle",
        "order": "created_at.desc",
        "select": "payload,created_at",
    }
    if domain:
        params["payload->>domain"] = f"eq.{domain}"

    rows = _get_rows("automation_events", params=params, limit=min(limit, 100))

    summary: List[Dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        summary.append({
            "cycle_id": payload.get("cycle_id", ""),
            "domain": payload.get("domain", ""),
            "health_score": payload.get("health_score", 0.0),
            "created_at": row.get("created_at", ""),
        })
    return summary
