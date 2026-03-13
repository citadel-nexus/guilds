"""
Optional FastAPI middleware for HTTP request latency histogram.

Only active when both ``prometheus_client`` and ``starlette`` are installed.
Controlled by ``monitoring.include_middleware`` in ``config/settings.yaml``.
"""
from __future__ import annotations

import time
from typing import Callable

from src.monitoring.metrics import _HAS_PROMETHEUS, _REGISTRY

_HAS_STARLETTE = False
MetricsMiddleware = None  # type: ignore[assignment]

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    _HAS_STARLETTE = True
except ImportError:
    pass

if _HAS_PROMETHEUS and _HAS_STARLETTE and _REGISTRY is not None:
    from prometheus_client import Histogram

    HTTP_REQUEST_DURATION = Histogram(
        "citadel_http_request_duration_seconds",
        "HTTP request duration in seconds",
        labelnames=["method", "path", "status_code"],
        registry=_REGISTRY,
    )

    class _MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Callable) -> Response:
            start = time.perf_counter()
            response = await call_next(request)
            duration = time.perf_counter() - start
            HTTP_REQUEST_DURATION.labels(
                method=request.method,
                path=request.url.path,
                status_code=str(response.status_code),
            ).observe(duration)
            return response

    MetricsMiddleware = _MetricsMiddleware  # type: ignore[assignment,misc]
