# src/services/supabase_client.py
"""
Async-compatible Supabase client for the Sentinel memory loop.

The official supabase-py v2 ships both sync and async clients.
We expose an async-first interface here; all callers use:

    from src.services.supabase_client import supabase
    await supabase.table("my_table").select("*").execute()

Implementation: wraps the synchronous client in asyncio.to_thread so
the same SDK works whether or not the async client is available.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, List, Optional

logger = logging.getLogger("sentinel.supabase")

# ── SDK import ────────────────────────────────────────────────────────────────
try:
    from supabase import create_client, Client as _SyncClient
    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False
    _SyncClient = None  # type: ignore


class _AsyncQueryProxy:
    """Wraps a synchronous supabase-py query builder and makes it awaitable."""

    def __init__(self, query):
        self._q = query

    def select(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.select(*args, **kwargs))

    def insert(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.insert(*args, **kwargs))

    def upsert(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.upsert(*args, **kwargs))

    def update(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.update(*args, **kwargs))

    def delete(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.delete(*args, **kwargs))

    def eq(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.eq(*args, **kwargs))

    def neq(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.neq(*args, **kwargs))

    def order(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.order(*args, **kwargs))

    def limit(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.limit(*args, **kwargs))

    def single(self, *args, **kwargs):
        return _AsyncQueryProxy(self._q.single(*args, **kwargs))

    def __getattr__(self, name):
        attr = getattr(self._q, name)
        if callable(attr):
            def _wrap(*a, **kw):
                return _AsyncQueryProxy(attr(*a, **kw))
            return _wrap
        return attr

    async def execute(self):
        """Run the query in a thread pool and return the result."""
        return await asyncio.to_thread(self._q.execute)


class _AsyncSupabase:
    """Minimal async façade over the synchronous supabase-py client."""

    def __init__(self, url: str, key: str):
        self._client: Optional[Any] = None
        if url and key and _HAS_SUPABASE:
            try:
                self._client = create_client(url, key)
                logger.info("[Supabase] Connected: %s…", url[:40])
            except Exception as e:
                logger.warning("[Supabase] Connection failed: %s", e)

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def table(self, name: str) -> _AsyncQueryProxy:
        if self._client is None:
            raise RuntimeError("Supabase not configured")
        return _AsyncQueryProxy(self._client.table(name))

    async def rpc(self, fn: str, params: dict = None) -> Any:
        if self._client is None:
            return None
        return await asyncio.to_thread(
            lambda: self._client.rpc(fn, params or {}).execute()
        )


# ── Module-level singleton ────────────────────────────────────────────────────

def _build_client() -> _AsyncSupabase:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        # Try loading from workspace.env
        try:
            from src.config import get_config
            cfg = get_config()
            url = getattr(cfg, "supabase_url", "") or url
            key = getattr(cfg, "supabase_key", "") or key
        except Exception:
            pass
    return _AsyncSupabase(url, key)


supabase: _AsyncSupabase = _build_client()
