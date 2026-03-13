# src/ingest/webhook.py
"""
FastAPI webhook endpoints for receiving events from external sources.

Endpoints:
- POST /webhook/github   — GitHub Actions webhook
- POST /webhook/azure    — Azure Monitor alert
- POST /webhook/event    — Pre-formatted EventJsonV1
- GET  /webhook/health   — Health check

Each endpoint normalizes the payload to EventJsonV1 and pushes to the outbox.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import JSONResponse
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

from src.ingest.normalizer import normalize
from src.ingest.outbox import FileOutbox, OutboxAdapter


def create_webhook_router(outbox: OutboxAdapter | None = None) -> "APIRouter":
    """Create and return the webhook router. Requires FastAPI."""
    if not _HAS_FASTAPI:
        raise ImportError("FastAPI is required for webhook endpoints. Install with: pip install fastapi")

    router = APIRouter(prefix="/webhook", tags=["ingest"])
    _outbox = outbox or FileOutbox()

    @router.post("/github")
    async def github_webhook(request: Request) -> JSONResponse:
        raw = await request.json()
        event = normalize(raw, source="github_actions")
        _outbox.push(event)
        return JSONResponse(
            status_code=202,
            content={"status": "accepted", "event_id": event.event_id},
        )

    @router.post("/azure")
    async def azure_webhook(request: Request) -> JSONResponse:
        raw = await request.json()
        event = normalize(raw, source="azure_alert")
        _outbox.push(event)
        return JSONResponse(
            status_code=202,
            content={"status": "accepted", "event_id": event.event_id},
        )

    @router.post("/event")
    async def manual_event(request: Request) -> JSONResponse:
        raw = await request.json()
        event = normalize(raw, source="manual")
        _outbox.push(event)
        return JSONResponse(
            status_code=202,
            content={"status": "accepted", "event_id": event.event_id},
        )

    @router.get("/health")
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "service": "citadel-lite-ingest"}

    return router
