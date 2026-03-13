# src/integrations/supabase_client.py
"""
Supabase integration for persistent state rehydration.

Stores pipeline state, agent outputs, decisions, and execution outcomes
in Supabase (PostgreSQL) for cross-session persistence and team visibility.
On startup, can rehydrate recent pipeline state from Supabase.

Falls back gracefully if Supabase is not configured.

Usage:
    from src.integrations.supabase_client import SupabaseStore
    store = SupabaseStore(config)
    store.save_pipeline_run(event_id, handoff_packet, decision, outcome)
    recent = store.get_recent_runs(limit=20)
    run = store.rehydrate(event_id)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False


class SupabaseStore:
    """
    Persistent pipeline state in Supabase PostgreSQL.

    Tables (auto-created if using Supabase migrations):
      - pipeline_runs: event_id, event_type, status, decision, risk_score, created_at
      - agent_outputs: event_id, agent_name, payload (JSONB), latency_ms, created_at
      - memory_entries: id, title, snippet, tags (text[]), embedding (vector?), created_at
      - skill_executions: skill_id, agent_name, event_id, success, latency_ms, created_at
    """

    def __init__(self, url: str = "", key: str = "") -> None:
        self._client: Optional[Any] = None
        if url and key and _HAS_SUPABASE:
            try:
                self._client = create_client(url, key)
                logger.info("Supabase client connected: %s", url[:40])
            except Exception as e:
                logger.warning("Supabase connection failed: %s", e)

    @property
    def is_available(self) -> bool:
        return self._client is not None

    # ---- Pipeline Runs ----

    def save_pipeline_run(
        self,
        event_id: str,
        event_type: str,
        status: str,
        decision: str = "",
        risk_score: float = 0.0,
        summary: str = "",
        handoff_packet: Optional[Dict] = None,
        execution_outcome: Optional[Dict] = None,
    ) -> bool:
        """Upsert a pipeline run record."""
        if not self._client:
            return False
        try:
            row = {
                "event_id": event_id,
                "event_type": event_type,
                "status": status,
                "decision": decision,
                "risk_score": risk_score,
                "summary": summary,
                "handoff_packet": json.dumps(handoff_packet) if handoff_packet else None,
                "execution_outcome": json.dumps(execution_outcome) if execution_outcome else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._client.table("pipeline_runs").upsert(row, on_conflict="event_id").execute()
            return True
        except Exception as e:
            logger.warning("Supabase save_pipeline_run failed: %s", e)
            return False

    def save_agent_output(
        self,
        event_id: str,
        agent_name: str,
        payload: Dict[str, Any],
        latency_ms: float = 0.0,
    ) -> bool:
        """Store an individual agent's output."""
        if not self._client:
            return False
        try:
            row = {
                "event_id": event_id,
                "agent_name": agent_name,
                "payload": json.dumps(payload),
                "latency_ms": latency_ms,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._client.table("agent_outputs").insert(row).execute()
            return True
        except Exception as e:
            logger.warning("Supabase save_agent_output failed: %s", e)
            return False

    # ---- Rehydration ----

    def rehydrate(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Load full pipeline state from Supabase for session restoration."""
        if not self._client:
            return None
        try:
            resp = (
                self._client.table("pipeline_runs")
                .select("*")
                .eq("event_id", event_id)
                .single()
                .execute()
            )
            run = resp.data
            if not run:
                return None

            # Load agent outputs
            outputs_resp = (
                self._client.table("agent_outputs")
                .select("*")
                .eq("event_id", event_id)
                .order("created_at")
                .execute()
            )

            run["agent_outputs"] = outputs_resp.data or []

            # Parse JSON fields
            for field_name in ("handoff_packet", "execution_outcome"):
                if run.get(field_name) and isinstance(run[field_name], str):
                    try:
                        run[field_name] = json.loads(run[field_name])
                    except Exception:
                        pass

            return run
        except Exception as e:
            logger.warning("Supabase rehydrate failed: %s", e)
            return None

    def get_recent_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent pipeline runs for dashboard history view."""
        if not self._client:
            return []
        try:
            resp = (
                self._client.table("pipeline_runs")
                .select("event_id, event_type, status, decision, risk_score, summary, updated_at")
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.warning("Supabase get_recent_runs failed: %s", e)
            return []

    # ---- Memory Sync ----

    def sync_memory(self, entries: List[Dict[str, Any]]) -> int:
        """Bulk upsert memory entries to Supabase for cross-instance sharing."""
        if not self._client or not entries:
            return 0
        try:
            rows = []
            for e in entries:
                rows.append({
                    "memory_id": e.get("id", ""),
                    "title": e.get("title", ""),
                    "snippet": e.get("snippet", ""),
                    "tags": e.get("tags", []),
                    "confidence": e.get("confidence", 1.0),
                    "occurred_at": e.get("occurred_at"),
                    "event_id": e.get("event_id", ""),
                })
            self._client.table("memory_entries").upsert(rows, on_conflict="memory_id").execute()
            return len(rows)
        except Exception as e:
            logger.warning("Supabase sync_memory failed: %s", e)
            return 0

    # ---- Skill History ----

    def save_skill_execution(self, execution: Dict[str, Any]) -> bool:
        if not self._client:
            return False
        try:
            self._client.table("skill_executions").insert(execution).execute()
            return True
        except Exception as e:
            logger.warning("Supabase save_skill_execution failed: %s", e)
            return False
