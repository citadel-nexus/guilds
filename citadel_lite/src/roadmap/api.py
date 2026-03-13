"""Roadmap API — FastAPI router for Roadmap Tracker (MS-3).

Endpoints:
    GET /roadmap/snapshot       — Full aggregate snapshot
    GET /roadmap/finance-guild  — Revenue-gate completion report
    GET /roadmap/health         — Lightweight health probe
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

try:
    from fastapi import APIRouter, HTTPException
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

from .models import FinancePhase, RoadmapSnapshot
from .tracker import RoadmapTracker

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_api"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)


def create_roadmap_router(ir_path: Path) -> "APIRouter":
    """Create and return the roadmap API router.

    Parameters
    ----------
    ir_path:
        Path to ``roadmap_ir.json``.  The tracker will be lazily
        initialised on first request so the app can still start even
        when the file does not exist yet.
    """
    if not _HAS_FASTAPI:
        raise ImportError(
            "FastAPI is required for roadmap endpoints. "
            "Install with: pip install fastapi"
        )

    router = APIRouter(prefix="/roadmap", tags=["roadmap"])

    # Lazy singleton — created on first request
    _tracker_cache: dict[str, RoadmapTracker] = {}

    def _get_tracker() -> RoadmapTracker:
        if "t" not in _tracker_cache:
            resolved = ir_path.resolve()
            if not resolved.is_file():
                raise HTTPException(
                    status_code=503,
                    detail=f"Roadmap IR file not found: {resolved.name}. "
                    "Run the roadmap_translator pipeline first.",
                )
            try:
                _tracker_cache["t"] = RoadmapTracker(resolved)
            except Exception as exc:
                logger.exception("Failed to load Roadmap IR")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to load Roadmap IR: {exc}",
                ) from exc
        return _tracker_cache["t"]

    # ---- Endpoints ---------------------------------------------------------

    @router.get("/snapshot", response_model=RoadmapSnapshot)
    async def roadmap_snapshot() -> RoadmapSnapshot:
        """Build and return a point-in-time aggregate snapshot."""
        tracker = _get_tracker()
        return tracker.build_snapshot()

    @router.get("/finance-guild", response_model=List[FinancePhase])
    async def finance_guild_report() -> List[FinancePhase]:
        """Revenue-gate completion report for Finance Guild."""
        tracker = _get_tracker()
        return tracker.get_finance_guild_report()

    @router.get("/health")
    async def roadmap_health() -> Dict[str, Any]:
        """Lightweight health probe for the roadmap subsystem."""
        try:
            tracker = _get_tracker()
            snapshot = tracker.build_snapshot()
            return {
                "status": "ok",
                "health_score": snapshot.health_score,
                "total_items": snapshot.total_items,
                "schema_version": snapshot.schema_version,
            }
        except HTTPException:
            return {
                "status": "unavailable",
                "health_score": 0.0,
                "detail": "Roadmap IR not loaded",
            }

    return router
