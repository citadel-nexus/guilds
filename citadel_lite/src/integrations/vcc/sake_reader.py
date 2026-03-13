"""
VCCSakeReader — thin adapter that reads ``.sake`` profile files and maps
CAPS trust_score to a citadel_lite health grade (T1–T5).

This is a read-only adapter.  It does NOT generate .sake files
(that responsibility belongs to F941 SAKEBuilder in CITADEL_LLM).

Grade mapping (from BLUEPRINT v9.0 / CLAUDE.md):
  trust_score >= 0.90  →  T1 (最高信頼)
  trust_score >= 0.75  →  T2 (高信頼)
  trust_score >= 0.60  →  T3 (標準)
  trust_score >= 0.40  →  T4 (要注意)
  trust_score <  0.40  →  T5 (低信頼)

CGRF compliance
---------------
_MODULE_NAME    = "sake_reader"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "sake_reader"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ENV: directory where .sake profiles are stored
_SAKE_PROFILE_DIR = os.getenv("VCC_SAKE_PROFILE_DIR", "sake_profiles")


@dataclass
class SakeCapsProfile:
    """Minimal CAPS profile extracted from a .sake file."""
    trust_score: float = 0.0
    confidence: float = 0.0
    cost: float = 0.0
    latency_ms: float = 0.0
    risk: float = 0.0
    precision: float = 0.0
    grade: str = "UNKNOWN"   # T1–T5 as declared in the .sake file


@dataclass
class SakeFile:
    """
    Minimal representation of a .sake profile consumed by citadel_lite.

    Only fields needed by the VCC/health integration are extracted.
    Unknown fields are preserved in ``extra`` for forward compatibility.
    """
    filetype: str = ""
    version: str = ""
    task_name: str = ""
    purpose: str = ""
    language: str = ""
    framework: str = ""
    caps_profile: SakeCapsProfile = field(default_factory=SakeCapsProfile)
    extra: Dict[str, Any] = field(default_factory=dict)


class VCCSakeReader:
    """
    Reads .sake profile files and maps CAPS data to citadel_lite grades.

    Usage
    -----
    reader = VCCSakeReader()
    sake   = reader.load("sake_profiles/dashboard_widget.sake")
    grade  = reader.to_health_grade(sake.caps_profile)
    """

    # ── CAPS grade thresholds (T1–T5) ────────────────────────────────────────
    _GRADE_THRESHOLDS: List[tuple] = [
        (0.90, "T1"),
        (0.75, "T2"),
        (0.60, "T3"),
        (0.40, "T4"),
    ]

    def load(self, path: str) -> SakeFile:
        """
        Load a .sake JSON file from *path* and return a SakeFile.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If the content is not valid JSON or the filetype is not "SAKE".
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"VCCSakeReader: file not found: {path}")

        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"VCCSakeReader: invalid JSON in {path}: {e}") from e

        if not isinstance(raw, dict):
            raise ValueError(f"VCCSakeReader: expected a JSON object in {path}")

        if raw.get("filetype") != "SAKE":
            raise ValueError(
                f"VCCSakeReader: filetype must be 'SAKE', got {raw.get('filetype')!r}"
            )

        return self._parse(raw)

    def load_dir(self, directory: Optional[str] = None) -> List[SakeFile]:
        """
        Load all .sake files from *directory* (defaults to VCC_SAKE_PROFILE_DIR).

        Returns an empty list if the directory does not exist.
        """
        dir_path = Path(directory or _SAKE_PROFILE_DIR)
        if not dir_path.exists():
            logger.debug("VCCSakeReader.load_dir: directory not found: %s", dir_path)
            return []

        results = []
        for f in sorted(dir_path.glob("*.sake")):
            try:
                results.append(self.load(str(f)))
            except (ValueError, FileNotFoundError) as e:
                logger.warning("VCCSakeReader.load_dir: skipping %s — %s", f.name, e)
        return results

    def to_health_grade(self, caps_profile: SakeCapsProfile) -> str:
        """
        Map a CAPS trust_score to a T1–T5 health grade.

        Returns
        -------
        str
            One of "T1", "T2", "T3", "T4", "T5".
        """
        score = caps_profile.trust_score
        for threshold, grade in self._GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return "T5"

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse(raw: Dict[str, Any]) -> SakeFile:
        """Parse raw dict into SakeFile dataclass."""
        # Extract caps_profile from sake_layers if present
        caps_raw = (
            raw.get("sake_layers", {}).get("caps_profile", {})
            or raw.get("caps_profile", {})
        )
        caps = SakeCapsProfile(
            trust_score=float(caps_raw.get("trust_score", 0.0)),
            confidence=float(caps_raw.get("confidence", 0.0)),
            cost=float(caps_raw.get("cost", 0.0)),
            latency_ms=float(caps_raw.get("latency_ms", 0.0)),
            risk=float(caps_raw.get("risk", 0.0)),
            precision=float(caps_raw.get("precision", 0.0)),
            grade=caps_raw.get("grade", "UNKNOWN"),
        )

        # Extract task_name / purpose from taskir_blocks if present
        taskir = raw.get("taskir_blocks", {})
        backend_layer = (
            raw.get("sake_layers", {}).get("backend_layer", {})
            or raw.get("backend_layer", {})
        )

        known_keys = {"filetype", "version", "taskir_blocks", "sake_layers",
                      "caps_profile", "backend_layer"}
        extra = {k: v for k, v in raw.items() if k not in known_keys}

        return SakeFile(
            filetype=raw.get("filetype", ""),
            version=str(raw.get("version", "")),
            task_name=taskir.get("task_name", ""),
            purpose=taskir.get("purpose", ""),
            language=backend_layer.get("language", ""),
            framework=backend_layer.get("framework", ""),
            caps_profile=caps,
            extra=extra,
        )
