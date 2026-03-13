# src/services/nats_client.py
"""
Async NATS publisher for Citadel event bus.

Falls back to structured logging when NATS is unavailable so the
pipeline continues without a broker in local / test environments.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger("sentinel.nats")

# ── Optional nats-py dependency ───────────────────────────────────────────────
try:
    import nats as _nats_lib
    _HAS_NATS = True
except ImportError:
    _nats_lib = None  # type: ignore
    _HAS_NATS = False

_nc = None  # module-level connection, lazily initialised


async def _get_connection():
    """Return (or lazily create) the NATS connection."""
    global _nc
    if _nc is not None and not _nc.is_closed:
        return _nc
    if not _HAS_NATS:
        return None
    url = os.environ.get("NATS_URL", "nats://localhost:4222")
    try:
        _nc = await _nats_lib.connect(url)
        logger.info("[NATS] Connected to %s", url)
        return _nc
    except Exception as e:
        logger.warning("[NATS] Connection failed (%s) — events will be logged only", e)
        return None


async def nats_publish(subject: str, payload: Dict[str, Any]) -> bool:
    """
    Publish *payload* (dict) to *subject* on the NATS event bus.

    Returns True on success, False on any failure (non-fatal).
    """
    data = json.dumps(payload, default=str).encode()

    nc = await _get_connection()
    if nc is None:
        logger.debug("[NATS] %s → %s", subject, payload)
        return False

    try:
        await nc.publish(subject, data)
        logger.debug("[NATS] published %s (%d bytes)", subject, len(data))
        return True
    except Exception as e:
        logger.warning("[NATS] publish failed for %s: %s", subject, e)
        return False
