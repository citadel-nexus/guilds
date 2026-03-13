"""roadmap_translator — deterministic Roadmap IR translation pipeline.

Converts README, RoadMap, and Implementation Summary markdown files
into the canonical Roadmap IR JSON format.
"""

from __future__ import annotations

from src.roadmap_translator.pipeline import run_pipeline

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_translator"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

__all__ = ["run_pipeline"]
