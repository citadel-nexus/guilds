# src/webhooks/sentinel_pre_call.py
"""
Sentinel Pre-Call Rehydration Endpoint
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Endpoint: POST /webhooks/pre-call/sentinel
Fires: immediately at conversation start (execution_mode: immediate)
Target latency: <200ms cache hit / <2s cache miss with Bedrock distill

SRS: SRS-SENTINEL-MEMORY-002
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.services.auth import hash_key
from src.services.bedrock_distill import bedrock_distill_memories
from src.services.embedding import embed_text
from src.services.faiss_manager import FAISSDomainManager
from src.services.nats_client import nats_publish
from src.services.supabase_client import supabase

logger = logging.getLogger("sentinel.pre_call")

router = APIRouter(
    prefix="/webhooks/pre-call/sentinel",
    tags=["sentinel-rehydration"],
)

# ── Default payload for new callers ──────────────────────────────────────────

_DEFAULT_CONTEXT = {
    "response": {
        "is_returning": "false",
        "profile": {"name": "", "caller_id": ""},
        "memory": {
            "session_count": "0",
            "last_session_date": "",
            "emotional_tone": "neutral",
            "relationship_summary": "",
            "last_topics": "getting to know each other",
            "open_threads": "",
            "promises_ledger": "No promises yet — this is the beginning.",
            "memory_fragments": "",
            "growth_notes": "",
            "recommended_action": "Introduce yourself. Learn who they are.",
            "conversation_style": "unknown",
            "days_since_last_call": "0",
        },
    }
}


class PreCallRequest(BaseModel):
    caller_id: str
    called_number: Optional[str] = None
    agent_id: str
    conversation_id: str
    current_agent_id: Optional[str] = None
    timestamp_utc: Optional[str] = None


# ── Auth ──────────────────────────────────────────────────────────────────────


async def _verify_mcp_key(key: str) -> bool:
    try:
        result = await supabase.table("api_keys").select("id").eq(
            "key_hash", hash_key(key)
        ).eq("active", True).execute()
        return len(result.data) > 0
    except Exception:
        return True  # Degrade gracefully


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("")
async def sentinel_pre_call(request: Request):
    """Rehydrate Sentinel's context at conversation start."""

    api_key = request.headers.get("x-api-key", "")
    if not api_key or not await _verify_mcp_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    body = await request.json()
    payload = PreCallRequest(**body)
    caller_id = payload.caller_id
    conversation_id = payload.conversation_id

    # ── Step 1: Lookup context cache ─────────────────────────────────────────
    try:
        cache_result = await supabase.table(
            "sentinel_context_cache"
        ).select("*").eq("caller_id", caller_id).execute()
    except Exception as e:
        logger.warning("[PRE-CALL] context cache lookup failed: %s", e)
        cache_result = type("R", (), {"data": []})()

    if not cache_result.data:
        import copy
        defaults = copy.deepcopy(_DEFAULT_CONTEXT)
        defaults["response"]["profile"]["caller_id"] = caller_id
        await _log_pre_call(conversation_id, caller_id, is_returning=False, cache_hit=False)
        return defaults

    cache = cache_result.data[0]
    is_returning = cache.get("is_returning", True)
    call_count = cache.get("call_count", 0)

    # ── Step 2: Seed memory fragments from FAISS ─────────────────────────────
    memory_fragments = ""
    if call_count > 1:
        seed_query = (
            f"{cache.get('last_topics', '')} "
            f"{cache.get('relationship_summary', '')}"
        ).strip()

        if seed_query:
            try:
                seed_embedding = await embed_text(seed_query)
                raw_memories = await FAISSDomainManager.search(
                    domain="sentinel:all",
                    vector=seed_embedding,
                    top_k=5,
                )
                if raw_memories:
                    memory_pages = [
                        {
                            "content_chunk": m.text,
                            "similarity": m.score,
                            "domain": m.metadata.get("domain", "unknown"),
                            "date": m.metadata.get("date", ""),
                        }
                        for m in raw_memories
                    ]
                    memory_fragments = await bedrock_distill_memories(
                        query=seed_query,
                        memories=memory_pages,
                        prompt=(
                            "Distill these memory fragments into a brief, "
                            "emotionally-aware narrative that Sentinel can "
                            "reference naturally in conversation. Preserve "
                            "dates, promises, and emotional context. Write "
                            "as compact bullet points. Max 200 words."
                        ),
                    )
            except Exception as e:
                logger.warning("[PRE-CALL] FAISS/Bedrock memory fragment error: %s", e)

    # ── Step 3: Active promises ledger ───────────────────────────────────────
    promises_text = await _build_active_promises_text(caller_id)

    # ── Step 4: Growth notes (after 5+ calls) ────────────────────────────────
    growth_notes = ""
    if call_count > 5:
        try:
            growth_vec = await embed_text(cache.get("relationship_summary", "growth"))
            growth_results = await FAISSDomainManager.search(
                domain="sentinel:growth",
                vector=growth_vec,
                top_k=2,
            )
            if growth_results:
                growth_notes = "; ".join(r.text for r in growth_results)
        except Exception:
            growth_notes = ""

    # ── Step 5: Days since last call ─────────────────────────────────────────
    last_date = cache.get("last_call_date", "")
    days_since = 0
    last_session_str = ""
    if last_date:
        try:
            last_dt = datetime.fromisoformat(last_date.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - last_dt).days
            last_session_str = last_date[:10]
        except Exception:
            last_session_str = last_date[:10] if last_date else ""

    # ── Step 6: Build response ────────────────────────────────────────────────
    response = {
        "response": {
            "is_returning": str(is_returning).lower(),
            "profile": {"name": "", "caller_id": caller_id},
            "memory": {
                "session_count": str(call_count),
                "last_session_date": last_session_str,
                "emotional_tone": cache.get("emotional_tone", "warm"),
                "relationship_summary": cache.get("relationship_summary", ""),
                "last_topics": cache.get("last_topics", ""),
                "open_threads": cache.get("open_items", ""),
                "promises_ledger": promises_text,
                "memory_fragments": memory_fragments,
                "growth_notes": growth_notes,
                "recommended_action": cache.get("recommended_action", ""),
                "conversation_style": cache.get("conversation_style", "direct"),
                "days_since_last_call": str(days_since),
            },
        }
    }

    # ── Step 7: Audit + NATS ──────────────────────────────────────────────────
    await _log_pre_call(
        conversation_id,
        caller_id,
        is_returning=True,
        cache_hit=True,
        call_count=call_count,
        fragments_count=memory_fragments.count("\n") + 1 if memory_fragments else 0,
    )

    await nats_publish("citadel.sentinel.context.distilled", {
        "conversation_id": conversation_id,
        "caller_id": caller_id,
        "call_count": call_count,
        "fragments_seeded": bool(memory_fragments),
        "promises_active": promises_text.count("- "),
    })

    return response


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _build_active_promises_text(caller_id: str) -> str:
    try:
        result = await supabase.table("sentinel_promises").select(
            "text", "owner", "created_at", "context"
        ).eq("caller_id", caller_id).eq("status", "active").order(
            "created_at", desc=True
        ).limit(10).execute()

        if not result.data:
            return "No active promises."

        lines = []
        for p in result.data:
            date_str = p["created_at"][:10]
            if p["owner"] == "human":
                lines.append(f"- You promised: {p['text']} ({date_str})")
            else:
                lines.append(f"- I promised: {p['text']} ({date_str})")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("[PRE-CALL] build_active_promises_text failed: %s", e)
        return "No active promises."


async def _log_pre_call(
    conversation_id: str,
    caller_id: str,
    is_returning: bool,
    cache_hit: bool,
    call_count: int = 0,
    fragments_count: int = 0,
):
    try:
        await supabase.table("sentinel_pre_call_log").insert({
            "conversation_id": conversation_id,
            "caller_id": caller_id,
            "is_returning": is_returning,
            "cache_hit": cache_hit,
            "call_count": call_count,
            "fragments_seeded": fragments_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.warning("[PRE-CALL] audit log insert failed: %s", e)
