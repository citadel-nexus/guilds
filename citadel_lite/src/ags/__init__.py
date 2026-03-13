"""
AGS (Agent Governance System) - Constitutional judiciary pipeline for Citadel Lite.

4-stage pipeline: S00 GENERATOR -> S01 DEFINER -> S02 FATE -> S03 ARCHIVIST
Runs after Guardian decision, before execution.

CGRF Module Metadata:
    _MODULE_NAME = "ags"
    _MODULE_VERSION = "1.0.0"
    _CGRF_TIER = 1
"""

_MODULE_NAME = "ags"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

from src.ags.pipeline import AGSPipeline, AGSVerdict
from src.ags.caps_stub import CAPSProfile, CAPSGrade, resolve_caps_grade

__all__ = ["AGSPipeline", "AGSVerdict", "CAPSProfile", "CAPSGrade", "resolve_caps_grade"]
