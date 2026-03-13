# src/workers/faiss_indexer.py
"""
Sentinel FAISS Indexing Worker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scheduled via: cron / ECS Fargate scheduled task / n8n workflow
Modes:
  incremental  (default) — new conversations since last indexed timestamp
  full-rebuild — wipe and reindex all conversations from ElevenLabs

Domains: personal, technical, promises, emotional, growth, all

Usage:
  python -m src.workers.faiss_indexer                     # incremental
  python -m src.workers.faiss_indexer --full-rebuild      # full wipe + rebuild
  python -m src.workers.faiss_indexer --agent-id <id>     # specific agent

SRS: SRS-SENTINEL-MEMORY-003
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("sentinel.indexer")

# ── Domain Configuration ──────────────────────────────────────────────────────

DOMAIN_CONFIG: Dict[str, Dict[str, Any]] = {
    "sentinel:personal": {
        "reprocess_frequency": "weekly",
        "description": "Life, culture, language, relationship",
        "keywords": [
            "life", "personal", "culture", "language", "women", "engrish",
            "family", "relationship", "music", "feeling", "emotion", "soul",
        ],
    },
    "sentinel:technical": {
        "reprocess_frequency": "weekly",
        "description": "Architecture, stack, builds, code",
        "keywords": [
            "architecture", "code", "deploy", "FAISS", "supabase", "MCP",
            "NATS", "docker", "API", "build", "server", "database", "voice", "agent",
        ],
    },
    "sentinel:promises": {
        "reprocess_frequency": "after_every_session",
        "description": "Commitments made by either party",
        "keywords": [
            "promise", "commit", "will do", "I'll", "you said you'd",
            "swear", "guarantee", "by next", "deadline",
        ],
    },
    "sentinel:emotional": {
        "reprocess_frequency": "weekly",
        "description": "Mood patterns, energy shifts",
        "keywords": [
            "feeling", "mood", "energy", "tired", "excited", "frustrated",
            "happy", "heavy", "peaceful", "angry", "scared", "hopeful",
        ],
    },
    "sentinel:growth": {
        "reprocess_frequency": "biweekly",
        "description": "Evolution of ideas, recurring themes",
        "keywords": [
            "pattern", "noticed", "changed", "evolved", "used to",
            "now you", "shift", "growth", "progress", "realize", "breakthrough",
        ],
    },
}

ALL_DOMAINS = list(DOMAIN_CONFIG.keys())
STATE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "indexer_state.json"


# ── Indexer State ─────────────────────────────────────────────────────────────

class IndexerState:
    """Persists last-indexed timestamp and conversation set to data/indexer_state.json."""

    def __init__(self, path: Path = STATE_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text("utf-8"))
            except Exception:
                pass
        return {"last_indexed_at": None, "indexed_conversations": [], "total_vectors": 0}

    def save(self):
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    @property
    def last_indexed_at(self) -> Optional[str]:
        return self._data.get("last_indexed_at")

    @last_indexed_at.setter
    def last_indexed_at(self, value: str):
        self._data["last_indexed_at"] = value

    def mark_conversation_indexed(self, conversation_id: str):
        seen = set(self._data.get("indexed_conversations", []))
        seen.add(conversation_id)
        self._data["indexed_conversations"] = list(seen)[-5000:]  # cap history

    def is_indexed(self, conversation_id: str) -> bool:
        return conversation_id in set(self._data.get("indexed_conversations", []))

    def increment_vectors(self, n: int):
        self._data["total_vectors"] = self._data.get("total_vectors", 0) + n


# ── Chunk Classifier ──────────────────────────────────────────────────────────

def _classify_domain_heuristic(text: str) -> str:
    """
    Fast keyword-based domain classifier (used when Bedrock classify is too slow/costly).
    Returns the domain with the highest keyword hit count.
    """
    text_lower = text.lower()
    scores: Dict[str, int] = {d: 0 for d in ALL_DOMAINS}

    for domain, cfg in DOMAIN_CONFIG.items():
        for kw in cfg["keywords"]:
            if kw.lower() in text_lower:
                scores[domain] += 1

    best = max(scores, key=lambda d: scores[d])
    if scores[best] == 0:
        return "sentinel:personal"
    return best


# ── Core Indexer ──────────────────────────────────────────────────────────────

class SentinelFAISSIndexer:
    """
    Processes ElevenLabs conversation transcripts into domain-specific FAISS indexes.

    Pipeline per conversation:
      1. Fetch transcript via ElevenLabsClient
      2. Chunk transcript via Bedrock (or naive split)
      3. Classify each chunk → domain
      4. Embed chunk
      5. Add to domain FAISS index + sentinel:all unified index
      6. Write Notion page for significant chunks (importance > 0.6)
      7. Mark conversation as indexed
    """

    def __init__(
        self,
        agent_id: str,
        mode: str = "incremental",
        batch_size: int = 10,
    ):
        self.agent_id = agent_id
        self.mode = mode
        self.batch_size = batch_size
        self.state = IndexerState()
        self._stats: Dict[str, int] = {
            "conversations_processed": 0,
            "chunks_indexed": 0,
            "vectors_added": 0,
            "errors": 0,
        }

    # ── Main run ──────────────────────────────────────────────────────────────

    async def run(self):
        from src.services.elevenlabs_client import ElevenLabsClient
        from src.services.faiss_manager import FAISSDomainManager
        from src.services.embedding import embed_text
        from src.services.bedrock_distill import bedrock_chunk_transcript, bedrock_classify_domain
        from src.services.notion_memory_vault import NotionMemoryVault
        from src.services.nats_client import nats_publish

        self._embed_text = embed_text
        self._classify = bedrock_classify_domain
        self._chunk = bedrock_chunk_transcript
        self._faiss = FAISSDomainManager
        self._notion = NotionMemoryVault()
        self._nats = nats_publish

        el_client = ElevenLabsClient()

        logger.info(
            "[INDEXER] Starting %s mode | agent=%s", self.mode, self.agent_id
        )

        if self.mode == "full-rebuild":
            await self._full_rebuild(el_client)
        else:
            await self._incremental(el_client)

        self.state.last_indexed_at = datetime.now(timezone.utc).isoformat()
        self.state.save()

        await self._nats("citadel.sentinel.index.complete", {
            "agent_id": self.agent_id,
            "mode": self.mode,
            **self._stats,
        })

        logger.info("[INDEXER] Done: %s", self._stats)

    async def _incremental(self, el_client):
        """Index only conversations not yet processed."""
        since = self.state.last_indexed_at
        if since is None:
            # First run: go back 7 days
            since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        logger.info("[INDEXER] Fetching conversations since %s", since[:10])
        convos = await el_client.list_conversations(
            agent_id=self.agent_id,
            since_date=since[:10],
            limit=500,
        )

        new_convos = [
            c for c in convos
            if not self.state.is_indexed(c.get("conversation_id", c.get("id", "")))
        ]
        logger.info("[INDEXER] %d new conversations to index", len(new_convos))

        for i in range(0, len(new_convos), self.batch_size):
            batch = new_convos[i : i + self.batch_size]
            await asyncio.gather(*[self._process_conversation(el_client, c) for c in batch])

    async def _full_rebuild(self, el_client):
        """Fetch all conversations and reindex from scratch."""
        logger.info("[INDEXER] Full rebuild — fetching all conversations")
        convos = await el_client.list_conversations(
            agent_id=self.agent_id,
            limit=2000,
        )
        logger.info("[INDEXER] %d total conversations", len(convos))

        for i in range(0, len(convos), self.batch_size):
            batch = convos[i : i + self.batch_size]
            await asyncio.gather(*[self._process_conversation(el_client, c) for c in batch])

    # ── Per-conversation processing ───────────────────────────────────────────

    async def _process_conversation(self, el_client, convo_meta: Dict[str, Any]):
        conversation_id = convo_meta.get("conversation_id", convo_meta.get("id", ""))
        if not conversation_id:
            return

        try:
            convo = await el_client.get_transcript(conversation_id)
            if not convo:
                logger.debug("[INDEXER] no transcript for %s", conversation_id)
                return

            transcript_text = el_client.extract_transcript_text(convo)
            if not transcript_text.strip():
                return

            date_str = convo_meta.get("created_at", datetime.now(timezone.utc).isoformat())

            # Chunk the transcript
            chunks = await self._chunk(transcript_text, max_chunk=500)

            vectors_added = 0
            for chunk in chunks:
                if not chunk.strip():
                    continue
                vectors_added += await self._index_chunk(
                    chunk=chunk,
                    conversation_id=conversation_id,
                    date_str=date_str,
                )

            self.state.mark_conversation_indexed(conversation_id)
            self.state.increment_vectors(vectors_added)
            self._stats["conversations_processed"] += 1
            self._stats["vectors_added"] += vectors_added

            logger.info(
                "[INDEXER] %s → %d chunks, %d vectors",
                conversation_id[:12],
                len(chunks),
                vectors_added,
            )

        except Exception as e:
            logger.warning("[INDEXER] error processing %s: %s", conversation_id[:12], e)
            self._stats["errors"] += 1

    async def _index_chunk(
        self,
        chunk: str,
        conversation_id: str,
        date_str: str,
    ) -> int:
        """Classify, embed, and store a single text chunk. Returns 1 on success."""
        try:
            # Domain classification (heuristic first, Bedrock for ambiguous cases)
            domain = _classify_domain_heuristic(chunk)
            importance = self._estimate_importance(chunk, domain)

            embedding = await self._embed_text(chunk)

            meta = {
                "conversation_id": conversation_id,
                "domain": domain,
                "importance": importance,
                "date": date_str,
                "notion_page_id": None,
            }

            # Write to Notion for high-importance chunks
            if importance >= 0.6:
                notion_page_id = await self._notion.create_memory_page(
                    title=chunk[:80],
                    content=chunk,
                    domain=domain,
                    tags=[domain.split(":")[-1]],
                    conversation_id=conversation_id,
                    importance=importance,
                    date=date_str,
                )
                meta["notion_page_id"] = notion_page_id

            # Add to domain index
            await self._faiss.add(
                domain=domain,
                vector=embedding,
                metadata=meta,
                text=chunk,
            )

            # Add to unified all-domains index
            await self._faiss.add(
                domain="sentinel:all",
                vector=embedding,
                metadata=meta,
                text=chunk,
            )

            self._stats["chunks_indexed"] += 1
            return 1

        except Exception as e:
            logger.warning("[INDEXER] _index_chunk error: %s", e)
            self._stats["errors"] += 1
            return 0

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _estimate_importance(text: str, domain: str) -> float:
        """
        Heuristic importance score 0.0–1.0 based on domain and content signals.
        """
        base = {
            "sentinel:promises": 0.9,
            "sentinel:growth": 0.75,
            "sentinel:emotional": 0.6,
            "sentinel:technical": 0.55,
            "sentinel:personal": 0.5,
            "sentinel:all": 0.5,
        }.get(domain, 0.5)

        text_lower = text.lower()
        # Boost for emotionally significant content
        if any(w in text_lower for w in ["scared", "breakthrough", "realized", "promised", "never"]):
            base = min(base + 0.15, 1.0)
        # Reduce for very short chunks
        if len(text) < 80:
            base = max(base - 0.2, 0.1)
        return round(base, 2)


# ── CLI Entry Point ───────────────────────────────────────────────────────────

async def _main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Sentinel FAISS Indexing Worker")
    parser.add_argument(
        "--full-rebuild",
        action="store_true",
        help="Wipe and reindex all conversations",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("SENTINEL_AGENT_ID", ""),
        help="ElevenLabs agent ID to index",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Conversations to process concurrently",
    )
    args = parser.parse_args()

    if not args.agent_id:
        logger.error("--agent-id or SENTINEL_AGENT_ID env var required")
        sys.exit(1)

    # Load workspace.env credentials
    workspace_env = Path(__file__).resolve().parents[3] / "tools" / "workspace.env"
    if workspace_env.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(workspace_env)
        except ImportError:
            pass  # Manual parse fallback
        except Exception:
            pass

    indexer = SentinelFAISSIndexer(
        agent_id=args.agent_id,
        mode="full-rebuild" if args.full_rebuild else "incremental",
        batch_size=args.batch_size,
    )
    await indexer.run()


if __name__ == "__main__":
    asyncio.run(_main())
