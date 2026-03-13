"""
Nemesis L4 Admin API routes.

Endpoints:
  GET  /api/nemesis/health              — Nemesis subsystem health check
  GET  /api/nemesis/dashboard/summary   — Aggregate threat summary
  GET  /api/nemesis/threats             — List recent threats

Authentication: Bearer token via ``NEMESIS_ADMIN_TOKEN`` env var.
When the token is unset all endpoints return 503 (misconfigured).

Mount (src/api/main.py):
    if os.getenv("NEMESIS_ENABLED") == "true":
        from routes.nemesis_api import nemesis_router
        app.include_router(nemesis_router, prefix="/api")

CGRF compliance
---------------
_MODULE_NAME    = "nemesis_api"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "nemesis_api"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

_ADMIN_TOKEN = os.getenv("NEMESIS_ADMIN_TOKEN", "")

# ── Try FastAPI imports ───────────────────────────────────────────────────────

try:
    from fastapi import APIRouter, Depends, HTTPException, Request, Security
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from fastapi.responses import JSONResponse
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore


# ── Auth helper ───────────────────────────────────────────────────────────────

def _check_token(token: str) -> None:
    """Raise HTTPException 401 if token is invalid."""
    if not _ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="NEMESIS_ADMIN_TOKEN not configured")
    if not secrets.compare_digest(token, _ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid admin token")


# ── Router factory ────────────────────────────────────────────────────────────

def _make_router() -> Any:
    if not _FASTAPI_AVAILABLE:
        logger.warning("nemesis_api: FastAPI not installed — router not created")
        return None

    router = APIRouter(prefix="/nemesis", tags=["nemesis-admin"])
    bearer = HTTPBearer(auto_error=False)

    def _auth(credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer)):
        if credentials is None:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        _check_token(credentials.credentials)

    @router.get("/health")
    async def health(auth=Depends(_auth)) -> Dict[str, Any]:
        """Nemesis subsystem health check."""
        return {
            "status": "ok",
            "nemesis_enabled": os.getenv("NEMESIS_ENABLED") == "true",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "layers": {
                "l2_inspector": "active",
                "l3_honeypots": "active",
                "l4_oracle": "active",
            },
        }

    @router.get("/dashboard/summary")
    async def dashboard_summary(auth=Depends(_auth)) -> Dict[str, Any]:
        """Aggregate threat summary for the Nemesis dashboard."""
        # Stub: returns zero-counts until Supabase is connected.
        return {
            "summary_period": "24h",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "l2_blocks": 0,
            "l3_honeypot_hits": 0,
            "l4_quarantined_ips": 0,
            "top_threat_categories": [],
            "top_source_countries": [],
        }

    @router.get("/threats")
    async def list_threats(
        limit: int = 20,
        quarantined_only: bool = False,
        auth=Depends(_auth),
    ) -> Dict[str, Any]:
        """List recent threats from Supabase (stub when DB unavailable)."""
        return {
            "threats": [],
            "total": 0,
            "limit": limit,
            "quarantined_only": quarantined_only,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return router


nemesis_router = _make_router()
