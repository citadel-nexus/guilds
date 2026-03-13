# src/approval/response.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


ALLOWED_DECISIONS = {"approve", "reject", "request_changes"}


def build_approval_response_template(event_id: str) -> Dict[str, Any]:
    """
    Human (or demo script) fills this and saves as:
      out/<event_id>/approval_response.json
    """
    return {
        "schema_version": "approval_response_v0",
        "event_id": event_id,
        "decision_id": "approve",  # approve | reject | request_changes
        "by": "kohei",
        "comment": "LGTM",
        "responded_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
    }


def load_approval_response(path: Path) -> Dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    schema = raw.get("schema_version")
    if schema != "approval_response_v0":
        raise ValueError(f"invalid schema_version: {schema}")

    decision_id = raw.get("decision_id")
    if decision_id not in ALLOWED_DECISIONS:
        raise ValueError(f"invalid decision_id: {decision_id}")

    # minimal normalization
    return {
        "schema_version": "approval_response_v0",
        "event_id": raw.get("event_id"),
        "decision_id": decision_id,
        "by": raw.get("by"),
        "comment": raw.get("comment"),
        "responded_at": raw.get("responded_at"),
    }