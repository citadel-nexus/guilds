"""
Nemesis L3 Hunter — Honeypot Routes.

Decoy endpoints that detect reconnaissance / scanning activity.  Every hit is:
  1. Logged to Supabase ``nemesis_honeypot_hits`` table (when SUPABASE_URL set)
  2. Published to NATS ``citadel.nemesis.l3.honeypot_hit`` (when NATS_URL set)
  3. Responded to with a plausible-but-useless 403 JSON to slow scanners down

All honeypot paths return 403 so legitimate clients are never confused —
they are only ever reached by scanners / attackers probing well-known paths.

Mount (src/api/main.py):
    import os
    if os.getenv("NEMESIS_ENABLED") == "true":
        from routes.nemesis_honeypots import honeypot_router
        app.include_router(honeypot_router)

CGRF compliance
---------------
_MODULE_NAME    = "nemesis_honeypots"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "nemesis_honeypots"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ── Try FastAPI / Starlette imports (graceful no-op when absent) ─────────────

try:
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore
    Request = None    # type: ignore
    JSONResponse = None  # type: ignore

# ── ENV ───────────────────────────────────────────────────────────────────────

_SUPABASE_URL = os.getenv("SUPABASE_URL")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
_NATS_SUBJECT = "citadel.nemesis.l3.honeypot_hit"

# ── Honeypot path list ────────────────────────────────────────────────────────

_HONEYPOT_PATHS = [
    "/admin",
    "/admin/login",
    "/.env",
    "/.git/HEAD",
    "/wp-login.php",
    "/wp-admin",
    "/phpmyadmin",
    "/config.php",
    "/etc/passwd",
    "/api/v1/admin",
    "/actuator/env",
    "/console",
]

_DECOY_RESPONSE = {
    "error": "Forbidden",
    "detail": "Access denied",
    "request_id": None,  # filled in per-request
}


def _build_hit_record(path: str, client_ip: str, method: str) -> Dict[str, Any]:
    return {
        "hit_id": str(uuid.uuid4()),
        "path": path,
        "client_ip": client_ip,
        "method": method,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "threat_label": "L3_HONEYPOT",
    }


def _record_hit_supabase(record: Dict[str, Any]) -> None:
    """Write hit to Supabase nemesis_honeypot_hits table."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return
    try:
        import requests as _req
        url = f"{_SUPABASE_URL}/rest/v1/nemesis_honeypot_hits"
        headers = {
            "apikey": _SUPABASE_KEY,
            "Authorization": f"Bearer {_SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        _req.post(url, headers=headers, json=record, timeout=3)
    except Exception as e:
        logger.debug("nemesis_honeypots: supabase write failed: %s", e)


def _publish_nats_hit(record: Dict[str, Any]) -> None:
    """Publish hit event to NATS citadel.nemesis.l3.honeypot_hit subject."""
    try:
        from src.integrations.nats.bridge_client import NATSBridgeClient
        client = NATSBridgeClient()
        client.publish(_NATS_SUBJECT, record)
    except Exception as e:
        logger.debug("nemesis_honeypots: nats publish failed: %s", e)


def _handle_honeypot_hit(path: str, client_ip: str, method: str) -> None:
    """Log, record, and publish a honeypot hit (side-effect only)."""
    record = _build_hit_record(path, client_ip, method)
    logger.warning(
        "Nemesis L3 honeypot HIT: path=%s ip=%s method=%s",
        path, client_ip, method,
    )
    _record_hit_supabase(record)
    _publish_nats_hit(record)


# ── Router factory ────────────────────────────────────────────────────────────

def _make_router() -> Any:
    """Build and return the FastAPI honeypot router."""
    if not _FASTAPI_AVAILABLE:
        logger.warning("nemesis_honeypots: FastAPI not installed — router not created")
        return None

    router = APIRouter(tags=["nemesis-honeypots"])

    async def _decoy_handler(request: Request) -> JSONResponse:
        client_ip = request.client.host if request.client else "unknown"
        _handle_honeypot_hit(request.url.path, client_ip, request.method)
        req_id = str(uuid.uuid4())
        body = {**_DECOY_RESPONSE, "request_id": req_id}
        return JSONResponse(status_code=403, content=body)

    for hp_path in _HONEYPOT_PATHS:
        # Register same handler for GET and POST on each honeypot path
        router.add_api_route(hp_path, _decoy_handler, methods=["GET", "POST"])

    return router


honeypot_router = _make_router()
