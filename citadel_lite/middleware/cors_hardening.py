"""
CORS Hardening helper for Citadel Lite FastAPI application.

Applies strict CORS policy via FastAPI/Starlette CORSMiddleware when
``NEMESIS_ENABLED=true``.  Defaults to a narrow allowlist; override via
``CORS_ALLOWED_ORIGINS`` env var (comma-separated).

CGRF compliance
---------------
_MODULE_NAME    = "cors_hardening"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import os
from typing import Any, List

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "cors_hardening"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

_DEFAULT_ORIGINS = [
    "https://citadel-lite.example.com",
    "https://localhost:3000",
]


def _get_allowed_origins() -> List[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return _DEFAULT_ORIGINS


def add_cors(app: Any) -> None:
    """
    Mount Starlette CORSMiddleware with hardened settings on *app*.

    Safe to call when ``starlette`` / ``fastapi`` is not installed —
    logs a warning and returns without error.
    """
    try:
        from starlette.middleware.cors import CORSMiddleware
    except ImportError:
        logger.warning("cors_hardening: starlette not installed — CORS not added")
        return

    origins = _get_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Nemesis-Blocked"],
        max_age=600,
    )
    logger.info("cors_hardening: CORS applied (origins=%s)", origins)
