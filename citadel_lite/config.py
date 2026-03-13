# config.py  (citadel_lite root — importable as `from config import ...`)
"""
Sentinel-specific constants and environment lookups.

Re-exports the CitadelConfig factory for code that uses
`from config import get_config`.  Adds Sentinel memory-loop
constants that are not part of the main CitadelConfig class.
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Re-export core config factory ────────────────────────────────────────────
from src.config import get_config, CitadelConfig  # noqa: F401

# ── Sentinel / ElevenLabs ─────────────────────────────────────────────────────
SENTINEL_AGENT_ID: str = os.environ.get("SENTINEL_AGENT_ID", "")
ELEVENLABS_API_KEY: str = os.environ.get("ELEVENLABS_API_KEY", "")

# ── MCP Server ────────────────────────────────────────────────────────────────
MCP_API_VERSION: str = "2026-02-22"

# ── FAISS ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
FAISS_INDEX_DIR: str = str(_HERE / "data" / "faiss_domains")
FAISS_DIMENSION: int = 1536  # text-embedding-3-small / Amazon Titan

# Domain names used by FAISSDomainManager and the indexing worker
SENTINEL_DOMAINS: list[str] = [
    "sentinel:personal",
    "sentinel:technical",
    "sentinel:promises",
    "sentinel:emotional",
    "sentinel:growth",
    "sentinel:all",
]
