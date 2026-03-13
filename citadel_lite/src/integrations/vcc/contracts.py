"""
Re-export of src/contracts/orders.py for VCC adapter consumers.

Keeping a thin re-export here preserves the ``integrations.vcc.*`` import
path without duplicating dataclass definitions.

CGRF compliance
---------------
_MODULE_NAME    = "vcc_contracts"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "CONTRACT"
"""
from __future__ import annotations

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "vcc_contracts"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "CONTRACT"
# ─────────────────────────────────────────────────────────────────────────────

from src.contracts.orders import BuildRequest, BuildResult  # noqa: F401

__all__ = ["BuildRequest", "BuildResult"]
