"""
NATS JetStream integration package for Citadel Lite.

Provides:
  - NATSBridgeClient  (bridge_client.py)  — publish / subscribe / wait_for
  - Pydantic schemas  (schemas.py)        — typed event payloads

CGRF compliance
---------------
_MODULE_NAME    = "nats"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "nats"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────
