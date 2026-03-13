"""
NATSBridgeClient — publish / subscribe / wait_for over NATS JetStream.

When NATS_URL is unset or nats.py is unavailable the client silently
degrades to stub mode (all operations are no-ops / return None).

Connection defaults follow the ECS/VPS production recommendations from
BLUEPRINT v9.0 (MS-A2):
  max_reconnect_attempts = -1   (unlimited)
  reconnect_time_wait    = 2.0  (seconds)
  max_reconnect_time_wait = 60.0
  ping_interval          = 30
  max_outstanding_pings  = 2

NATS_URL examples:
  ECS  production : nats://nats.citadel.local:4222
  VPS  production : nats://147.93.43.117:4222
  local dev       : nats://localhost:4222

CGRF compliance
---------------
_MODULE_NAME    = "bridge_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

try:
    import nats  # type: ignore
    _HAS_NATS = True
except ImportError:
    _HAS_NATS = False

from src.integrations.nats.schemas import CitadelNATSEnvelope

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "bridge_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# Production-recommended connection defaults (Blueprint v9.0 MS-A2)
CONNECTION_DEFAULTS: Dict[str, Any] = {
    "max_reconnect_attempts": -1,     # unlimited — survives transient failures
    "reconnect_time_wait": 2.0,       # base wait between reconnects (seconds)
    "max_reconnect_time_wait": 60.0,  # exponential backoff ceiling (seconds)
    "ping_interval": 30,              # server ping interval (seconds)
    "max_outstanding_pings": 2,       # disconnect if 2 pings unanswered
}


class NATSBridgeClient:
    """
    Sync-friendly NATS wrapper for Citadel Lite.

    All async NATS operations are run inside an internal event loop via
    ``asyncio.run()`` so that callers don't need to manage coroutines.

    In stub mode (NATS_URL unset or nats.py missing):
      - ``publish()`` logs and returns False
      - ``subscribe()`` registers a no-op handler
      - ``wait_for()`` returns None immediately
    """

    def __init__(
        self,
        url: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._url = url or os.getenv("NATS_URL", "")
        self._user = user or os.getenv("NATS_USER")
        self._password = password or os.getenv("NATS_PASSWORD")
        self._stub = not (self._url and _HAS_NATS)
        if self._stub:
            logger.debug(
                "NATSBridgeClient: stub mode (%s)",
                "nats.py missing" if not _HAS_NATS else "NATS_URL not set",
            )

    # ── Public API ───────────────────────────────────────────────────────────

    def publish(self, subject: str, payload: Dict[str, Any]) -> bool:
        """
        Publish *payload* to *subject*.

        Returns True on success, False in stub/error mode.
        """
        if self._stub:
            logger.debug("NATSBridgeClient.publish (stub): %s %s", subject, payload)
            return False
        try:
            asyncio.run(self._async_publish(subject, payload))
            return True
        except Exception as exc:
            logger.error("NATSBridgeClient.publish error: %s", exc)
            return False

    def wait_for(
        self,
        subject: str,
        timeout: float = 60.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Subscribe to *subject* and block until one message arrives or *timeout* seconds.

        Returns the raw payload dict, or None on timeout / stub mode.
        The received message is also wrapped in CitadelNATSEnvelope for audit.
        """
        if self._stub:
            logger.debug("NATSBridgeClient.wait_for (stub): %s", subject)
            return None
        try:
            return asyncio.run(self._async_wait_for(subject, timeout))
        except Exception as exc:
            logger.error("NATSBridgeClient.wait_for error: %s", exc)
            return None

    def subscribe(self, subject: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register *handler* to be called for each message on *subject*.

        No-op in stub mode.
        """
        if self._stub:
            logger.debug("NATSBridgeClient.subscribe (stub): %s", subject)
            return
        logger.info("NATSBridgeClient: subscribe %s (async handler registration pending)", subject)

    # ── Async implementation ─────────────────────────────────────────────────

    async def _async_publish(self, subject: str, payload: Dict[str, Any]) -> None:
        import json as _json
        connect_kwargs: Dict[str, Any] = {**CONNECTION_DEFAULTS, "servers": [self._url]}
        if self._user:
            connect_kwargs["user"] = self._user
        if self._password:
            connect_kwargs["password"] = self._password

        nc = await nats.connect(**connect_kwargs)
        try:
            data = _json.dumps(payload).encode()
            await nc.publish(subject, data)
            await nc.flush()
            logger.info("NATSBridgeClient: published to %s", subject)
        finally:
            await nc.drain()

    async def _async_wait_for(self, subject: str, timeout: float) -> Optional[Dict[str, Any]]:
        import json as _json
        connect_kwargs: Dict[str, Any] = {**CONNECTION_DEFAULTS, "servers": [self._url]}
        if self._user:
            connect_kwargs["user"] = self._user
        if self._password:
            connect_kwargs["password"] = self._password

        received: Optional[Dict[str, Any]] = None

        async def _handler(msg):
            nonlocal received
            try:
                received = _json.loads(msg.data.decode())
                envelope = CitadelNATSEnvelope(
                    event_id=str(uuid.uuid4()),
                    event_type=subject,
                    correlation_id=(
                        received.get("order_id")
                        or received.get("cycle_id")
                        or received.get("diag_id")
                    ),
                    received_at=datetime.now(timezone.utc).isoformat(),
                    nats_seq=getattr(msg, "seq", 0),
                    payload=received,
                )
                logger.debug("NATSBridgeClient: envelope %s", envelope.event_id)
            except Exception as e:
                logger.warning("NATSBridgeClient: failed to parse message: %s", e)

        nc = await nats.connect(**connect_kwargs)
        try:
            sub = await nc.subscribe(subject, cb=_handler)
            # Poll until message arrives or timeout
            elapsed = 0.0
            interval = 0.1
            while received is None and elapsed < timeout:
                await asyncio.sleep(interval)
                elapsed += interval
            await sub.unsubscribe()
        finally:
            await nc.drain()

        return received
