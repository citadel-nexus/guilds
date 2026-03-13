# src/webhooks/sentinel_post_call.py
"""
Sentinel Post-Call Parsing Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Endpoint: POST /webhooks/post-call/sentinel/rehydrate
Fires: automatically via ElevenLabs on_conversation_end
Latency: async — no caller-facing impact

SRS: SRS-SENTINEL-MEMORY-001
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.services.auth import hash_key
from src.services.bedrock_distill import bedrock_extract_structured
from src.services.embedding import embed_text
from src.services.faiss_manager import FAISSDomainManager
from src.services.nats_client import nats_publish
from src.services.notion_memory_vault import NotionMemoryVault
from src.services.supabase_client import supabase

logger = logging.getLogger("sentinel.post_call")

router = APIRouter(
    prefix="/webhooks/post-call/sentinel",
    tags=["sentinel-memory"],
)

# ── Pydantic Models ───────────────────────────────────────────────────────────


class SentinelPostCallPayload(BaseModel):
    caller_id: str
    conversation_id: str
    originating_agent_id: str
    final_agent_id: str
    call_duration_secs: float
    timestamp_utc: str
    # LLM-synthesized fields from ElevenLabs
    call_summary: str
    topics_discussed: str
    open_items: str
    sentiment_at_close: str
    recommended_next_action: str
    conversation_style: Optional[str] = None
    # Sentinel-specific LLM fields
    promises_made: Optional[str] = None
    promises_resolved: Optional[str] = None
    emotional_arc: Optional[str] = None
    growth_observations: Optional[str] = None
    key_moments: Optional[str] = None
    relationship_shift: Optional[str] = None


# ── Extraction prompt ─────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """
You are analyzing a completed conversation between Sentinel (an AI governance voice)
and a human partner. Extract structured memory objects from the conversation data.

Rules:
- Promises are explicit commitments. "I'll look into that" = promise.
  "Maybe we should" = NOT a promise.
- Memory domains: personal (life, culture, language), technical (architecture,
  stack, builds), promises (commitments), emotional (mood, energy),
  growth (evolving ideas, patterns).
- Importance: 0.0-1.0. Routine chatter = 0.1-0.3. Personal revelations = 0.6-0.8.
  Breakthroughs or promises = 0.8-1.0.
- Emotional shift: only flag if there was a genuine change in energy during the call.
- Growth note: only write one if you observe a pattern across what was discussed.
  "They keep coming back to X" or "Their thinking on Y has shifted."
- Relationship delta: one sentence on how this call changed the relationship,
  if at all. Most calls won't change it.

Return valid JSON matching the response_schema. Empty arrays for missing items.
"""

EXTRACTION_SCHEMA = {
    "promises": [{"text": "", "owner": "", "status": "", "context": ""}],
    "resolved_promises": [{"text": "", "resolution": ""}],
    "memories": [{"content": "", "domain": "", "importance": 0.0, "tags": []}],
    "emotional_shift": {"from": "", "to": "", "trigger": ""},
    "growth_note": "",
    "relationship_delta": "",
}

# ── Auth ──────────────────────────────────────────────────────────────────────


async def _verify_mcp_key(key: str) -> bool:
    try:
        result = await supabase.table("api_keys").select("id").eq(
            "key_hash", hash_key(key)
        ).eq("active", True).execute()
        return len(result.data) > 0
    except Exception:
        return True  # Non-fatal; log and allow in degraded mode


# ── Main endpoint ─────────────────────────────────────────────────────────────


@router.post("/rehydrate")
async def sentinel_post_call(request: Request):
    """Main entry point — fires when Sentinel conversation ends."""

    api_key = request.headers.get("x-api-key", "")
    if not api_key or not await _verify_mcp_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    body = await request.json()
    payload = SentinelPostCallPayload(**body)
    conversation_id = payload.conversation_id
    caller_id = payload.caller_id

    # ── Step 1: Extract structured memory objects via Bedrock ─────────────────
    extraction = await bedrock_extract_structured(
        prompt=EXTRACTION_PROMPT,
        context={
            "call_summary": payload.call_summary,
            "topics_discussed": payload.topics_discussed,
            "open_items": payload.open_items,
            "sentiment": payload.sentiment_at_close,
            "promises_made": payload.promises_made or "",
            "promises_resolved": payload.promises_resolved or "",
            "emotional_arc": payload.emotional_arc or "",
            "growth_observations": payload.growth_observations or "",
            "key_moments": payload.key_moments or "",
        },
        response_schema=EXTRACTION_SCHEMA,
    )

    promises = extraction.get("promises", [])
    resolved = extraction.get("resolved_promises", [])
    memories = extraction.get("memories", [])
    emotional_shift = extraction.get("emotional_shift", {})
    growth_note = extraction.get("growth_note", "")
    relationship_delta = extraction.get("relationship_delta", "")

    # ── Step 2: Process new promises ─────────────────────────────────────────
    promise_ids: List[str] = []
    for p in promises:
        promise_id = str(uuid4())
        promise_ids.append(promise_id)

        embedding = await embed_text(p["text"])
        await FAISSDomainManager.add(
            domain="sentinel:promises",
            vector=embedding,
            metadata={
                "notion_page_id": None,
                "conversation_id": conversation_id,
                "promise_id": promise_id,
                "owner": p.get("owner", "unknown"),
                "status": "active",
                "date": payload.timestamp_utc,
                "domain": "sentinel:promises",
            },
            text=p["text"],
        )

        try:
            await supabase.table("sentinel_promises").insert({
                "id": promise_id,
                "conversation_id": conversation_id,
                "caller_id": caller_id,
                "text": p["text"],
                "owner": p.get("owner", "unknown"),
                "status": "active",
                "context": p.get("context", ""),
                "created_at": payload.timestamp_utc,
            }).execute()
        except Exception as e:
            logger.warning("[POST-CALL] promise insert failed: %s", e)

        await nats_publish("citadel.sentinel.promise.created", {
            "promise_id": promise_id,
            "conversation_id": conversation_id,
            "text": p["text"],
            "owner": p.get("owner", "unknown"),
        })

    # ── Step 3: Resolve existing promises ────────────────────────────────────
    for r in resolved:
        embedding = await embed_text(r["text"])
        matches = await FAISSDomainManager.search(
            domain="sentinel:promises",
            vector=embedding,
            top_k=3,
            filter_fn=lambda m: m.get("status") == "active",
        )

        if matches:
            best = matches[0]
            promise_id = best.metadata.get("promise_id")
            try:
                await supabase.table("sentinel_promises").update({
                    "status": "resolved",
                    "resolution": r.get("resolution", ""),
                    "resolved_at": payload.timestamp_utc,
                    "resolved_conversation_id": conversation_id,
                }).eq("id", promise_id).execute()
            except Exception as e:
                logger.warning("[POST-CALL] promise resolution failed: %s", e)

            await FAISSDomainManager.update_metadata(
                domain="sentinel:promises",
                vector_id=best.id,
                updates={"status": "resolved"},
            )

            await nats_publish("citadel.sentinel.promise.resolved", {
                "promise_id": promise_id,
                "conversation_id": conversation_id,
                "resolution": r.get("resolution", ""),
            })

    # ── Step 4: Embed and store domain memories ───────────────────────────────
    notion_vault = NotionMemoryVault()
    stored_memories: List[Dict[str, Any]] = []

    for mem in memories:
        domain = mem.get("domain", "sentinel:personal")
        # Prefix domain if bare
        if not domain.startswith("sentinel:"):
            domain = f"sentinel:{domain}"
        content = mem["content"]
        importance = float(mem.get("importance", 0.5))

        if importance < 0.3:
            continue

        embedding = await embed_text(content)

        notion_page_id = await notion_vault.create_memory_page(
            title=content[:80],
            content=content,
            domain=domain,
            tags=mem.get("tags", []),
            conversation_id=conversation_id,
            importance=importance,
            date=payload.timestamp_utc,
        )

        meta = {
            "notion_page_id": notion_page_id,
            "conversation_id": conversation_id,
            "domain": domain,
            "importance": importance,
            "date": payload.timestamp_utc,
            "tags": mem.get("tags", []),
        }

        await FAISSDomainManager.add(domain=domain, vector=embedding, metadata=meta, text=content)

        # Also index in the unified all-domains index
        if domain != "sentinel:all":
            await FAISSDomainManager.add(
                domain="sentinel:all", vector=embedding, metadata=meta, text=content
            )

        stored_memories.append({"notion_page_id": notion_page_id, "domain": domain, "importance": importance})

    # ── Step 5: Store emotional shift ─────────────────────────────────────────
    if emotional_shift and emotional_shift.get("trigger"):
        emo_content = (
            f"Emotional shift: {emotional_shift.get('from', '?')} → "
            f"{emotional_shift.get('to', '?')}. "
            f"Trigger: {emotional_shift['trigger']}"
        )
        emo_embedding = await embed_text(emo_content)
        await FAISSDomainManager.add(
            domain="sentinel:emotional",
            vector=emo_embedding,
            metadata={
                "conversation_id": conversation_id,
                "domain": "sentinel:emotional",
                "date": payload.timestamp_utc,
                "from_state": emotional_shift.get("from", ""),
                "to_state": emotional_shift.get("to", ""),
            },
            text=emo_content,
        )

    # ── Step 6: Store growth note ─────────────────────────────────────────────
    if growth_note:
        growth_embedding = await embed_text(growth_note)
        growth_page_id = await notion_vault.create_memory_page(
            title=f"Growth: {growth_note[:60]}",
            content=growth_note,
            domain="sentinel:growth",
            tags=["growth", "pattern"],
            conversation_id=conversation_id,
            importance=0.8,
            date=payload.timestamp_utc,
        )
        await FAISSDomainManager.add(
            domain="sentinel:growth",
            vector=growth_embedding,
            metadata={
                "notion_page_id": growth_page_id,
                "conversation_id": conversation_id,
                "domain": "sentinel:growth",
                "date": payload.timestamp_utc,
            },
            text=growth_note,
        )
        await nats_publish("citadel.sentinel.growth.observed", {
            "conversation_id": conversation_id,
            "note": growth_note,
        })

    # ── Step 7: Update Supabase context cache ─────────────────────────────────
    await _upsert_context_cache(
        caller_id=caller_id,
        data={
            "caller_id": caller_id,
            "last_conversation_id": conversation_id,
            "last_call_date": payload.timestamp_utc,
            "call_count_increment": 1,
            "relationship_summary": _build_relationship_summary(
                payload.call_summary, relationship_delta
            ),
            "last_topics": payload.topics_discussed,
            "open_items": payload.open_items,
            "sentiment_trend": payload.sentiment_at_close,
            "recommended_action": payload.recommended_next_action,
            "conversation_style": payload.conversation_style or "direct",
            "emotional_tone": _map_sentiment_to_tone(
                payload.sentiment_at_close, emotional_shift
            ),
            "promises_ledger": await _build_active_promises_text(caller_id),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # ── Step 8: NATS broadcast ────────────────────────────────────────────────
    domains_touched = list(set(m["domain"] for m in stored_memories))
    await nats_publish("citadel.sentinel.memory.stored", {
        "conversation_id": conversation_id,
        "caller_id": caller_id,
        "memories_stored": len(stored_memories),
        "promises_created": len(promises),
        "promises_resolved": len(resolved),
        "domains_touched": domains_touched,
    })

    # ── Step 9: Audit log ─────────────────────────────────────────────────────
    try:
        await supabase.table("sentinel_post_call_log").insert({
            "conversation_id": conversation_id,
            "caller_id": caller_id,
            "call_duration_secs": payload.call_duration_secs,
            "memories_stored": len(stored_memories),
            "promises_created": len(promises),
            "promises_resolved": len(resolved),
            "sentiment": payload.sentiment_at_close,
            "growth_note_stored": bool(growth_note),
            "emotional_shift_stored": bool(
                emotional_shift and emotional_shift.get("trigger")
            ),
            "processing_agent": "sentinel",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.warning("[POST-CALL] audit log insert failed: %s", e)

    logger.info(
        "[POST-CALL] %s — memories=%d promises_new=%d promises_resolved=%d",
        conversation_id[:12],
        len(stored_memories),
        len(promises),
        len(resolved),
    )

    return {
        "status": "ok",
        "memories_stored": len(stored_memories),
        "promises_created": len(promises),
        "promises_resolved": len(resolved),
        "domains_touched": domains_touched,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _upsert_context_cache(caller_id: str, data: dict):
    """Upsert the context cache row for this caller (atomic call_count increment)."""
    try:
        existing = await supabase.table("sentinel_context_cache").select(
            "id", "call_count"
        ).eq("caller_id", caller_id).execute()

        if existing.data:
            row = existing.data[0]
            data["call_count"] = row["call_count"] + data.pop("call_count_increment", 1)
            await supabase.table("sentinel_context_cache").update(data).eq(
                "id", row["id"]
            ).execute()
        else:
            data["call_count"] = data.pop("call_count_increment", 1)
            data["is_returning"] = True
            await supabase.table("sentinel_context_cache").insert(data).execute()
    except Exception as e:
        logger.warning("[POST-CALL] context cache upsert failed: %s", e)


async def _build_active_promises_text(caller_id: str) -> str:
    """Build a natural-language ledger of active promises."""
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
            owner_label = "You promised" if p["owner"] == "human" else "I promised"
            lines.append(f"- {owner_label}: {p['text']} ({date_str})")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("[POST-CALL] build_active_promises_text failed: %s", e)
        return "No active promises."


def _build_relationship_summary(call_summary: str, relationship_delta: str) -> str:
    if relationship_delta:
        return f"{call_summary} {relationship_delta}"
    return call_summary


def _map_sentiment_to_tone(sentiment: str, emotional_shift: dict) -> str:
    tone_map = {
        "cold": "distant",
        "warming": "opening up",
        "warm": "warm",
        "hot": "energized",
        "customer": "comfortable",
        "at_risk": "heavy",
        "churned": "withdrawn",
        "energized": "energized",
        "reflective": "reflective",
        "heavy": "heavy",
        "distant": "distant",
        "frustrated": "frustrated",
        "peaceful": "peaceful",
    }
    if emotional_shift and emotional_shift.get("to"):
        return emotional_shift["to"]
    return tone_map.get(sentiment, "warm")
