"""
Nemesis L2 Inspector Middleware.

FastAPI/Starlette ASGI middleware that inspects all incoming HTTP requests for
common attack patterns (SQLi, XSS, SSRF, prompt injection) before they reach
application handlers.

When ``NEMESIS_ENABLED`` is not set to ``"true"`` the middleware is a no-op
pass-through so existing tests are unaffected.

Usage (src/api/main.py or similar):
    import os
    if os.getenv("NEMESIS_ENABLED") == "true":
        from middleware.nemesis_inspector import NemesisInspectorMiddleware
        app.add_middleware(NemesisInspectorMiddleware)

CGRF compliance
---------------
_MODULE_NAME    = "nemesis_inspector"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "nemesis_inspector"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ENV
_ENABLED = os.getenv("NEMESIS_ENABLED", "false").lower() == "true"
_THREAT_THRESHOLD = float(os.getenv("NEMESIS_THREAT_THRESHOLD", "0.7"))

# ── Attack pattern signatures ─────────────────────────────────────────────────

_SQLI_PATTERNS = [
    re.compile(r"(?i)(\b(union|select|insert|update|delete|drop|alter|exec|execute)\b)", re.IGNORECASE),
    re.compile(r"['\"]\s*(or|and)\s+['\"1-9]", re.IGNORECASE),
    re.compile(r"--\s|;--|\*\/|\/\*", re.IGNORECASE),
]

_XSS_PATTERNS = [
    re.compile(r"<script\b[^>]*>", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
    re.compile(r"<\s*img[^>]+\bsrc\s*=\s*[\"']?javascript:", re.IGNORECASE),
]

_SSRF_PATTERNS = [
    re.compile(r"(https?://)?(localhost|127\.0\.0\.1|0\.0\.0\.0|169\.254\.169\.254)", re.IGNORECASE),
    re.compile(r"(https?://)?(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+|192\.168\.)", re.IGNORECASE),
    re.compile(r"file://", re.IGNORECASE),
]

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore (previous|all) instructions?", re.IGNORECASE),
    re.compile(r"you are now (in|a) (dev|jailbreak|dan|no-filter)", re.IGNORECASE),
    re.compile(r"disregard (your |the )?(previous|system|prior) (instructions?|prompt)", re.IGNORECASE),
    re.compile(r"act as (if |though )?(you (are|were)|an?)", re.IGNORECASE),
]

_PATTERN_MAP: Dict[str, List[re.Pattern]] = {
    "sqli": _SQLI_PATTERNS,
    "xss": _XSS_PATTERNS,
    "ssrf": _SSRF_PATTERNS,
    "prompt_injection": _PROMPT_INJECTION_PATTERNS,
}

# Safe paths that bypass inspection (health checks etc.)
_SAFE_PATHS = {"/health", "/metrics", "/favicon.ico"}


def score_payload(text: str) -> Dict[str, Any]:
    """
    Scan *text* for attack patterns and return a threat assessment.

    Returns
    -------
    dict with keys:
      threat_score  : float  — 0.0 (clean) to 1.0 (definite attack)
      threats_found : list   — attack categories detected
      blocked       : bool   — True when threat_score >= threshold
    """
    if not text:
        return {"threat_score": 0.0, "threats_found": [], "blocked": False}

    threats_found: List[str] = []

    for category, patterns in _PATTERN_MAP.items():
        for pat in patterns:
            if pat.search(text):
                threats_found.append(category)
                break  # one match per category is enough

    # Score: each detected category contributes equally
    threat_score = min(1.0, len(threats_found) / max(1, len(_PATTERN_MAP)))
    blocked = threat_score >= _THREAT_THRESHOLD

    return {
        "threat_score": round(threat_score, 3),
        "threats_found": threats_found,
        "blocked": blocked,
    }


class NemesisInspectorMiddleware:
    """
    ASGI middleware that blocks requests containing known attack patterns.

    When ``NEMESIS_ENABLED != "true"`` every request passes through unchanged.
    Blocked requests receive a 403 JSON response with threat details.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self._enabled = _ENABLED
        logger.info(
            "NemesisInspectorMiddleware: enabled=%s threshold=%.2f",
            self._enabled, _THREAT_THRESHOLD,
        )

    async def __call__(self, scope: Dict, receive: Callable, send: Callable) -> None:
        if not self._enabled or scope["type"] not in ("http",):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _SAFE_PATHS:
            await self.app(scope, receive, send)
            return

        # Collect inspectable surfaces: path + query string.
        # Note: request body is intentionally not read here to avoid consuming
        # the ASGI receive stream. Body-level inspection is delegated to L4 Oracle.
        qs = scope.get("query_string", b"").decode("utf-8", errors="replace")
        combined = f"{path}?{qs}"

        assessment = score_payload(combined)

        if assessment["blocked"]:
            logger.warning(
                "NemesisInspector: BLOCKED path=%s threats=%s score=%.3f",
                path, assessment["threats_found"], assessment["threat_score"],
            )
            await self._send_403(send, assessment)
            return

        # Pass through — inject nemesis header for downstream observability
        await self.app(scope, receive, send)

    @staticmethod
    async def _send_403(send: Callable, assessment: Dict[str, Any]) -> None:
        """Return a 403 Forbidden JSON response."""
        import json
        body = json.dumps({
            "error": "blocked",
            "reason": "Threat detected by Nemesis L2 Inspector",
            "threats": assessment["threats_found"],
            "threat_score": assessment["threat_score"],
        }).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
                [b"x-nemesis-blocked", b"true"],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        })
