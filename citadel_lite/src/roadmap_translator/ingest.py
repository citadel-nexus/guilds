"""File ingestion — read files, compute SHA-256 fingerprint, build Source objects.

Handles reading markdown / plaintext files and producing the Source
metadata needed for the Roadmap IR.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from src.roadmap_ir.types import Source, SourceTypeEnum

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_ingest"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


def ingest_file(
    path: Path,
    source_id: str | None = None,
) -> Tuple[Source, List[str]]:
    """Read a file and return ``(Source, lines)``."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    fingerprint = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    if source_id is None:
        source_id = _path_to_source_id(path)

    source_type = _detect_source_type(path)

    source = Source(
        source_id=source_id,
        type=source_type,
        label=path.name,
        fingerprint=fingerprint,
        path_hint=str(path),
        collected_at=datetime.now(timezone.utc),
    )
    return source, lines


def _path_to_source_id(path: Path) -> str:
    """Derive a valid source_id from a file path."""
    import re

    stem = path.stem.lower()
    sid = re.sub(r"[^a-z0-9]", "-", stem).strip("-")
    # Ensure min length 2 for the portion after the first char
    if len(sid) < 2:
        sid = sid + "-src"
    # Truncate to 64 chars
    return sid[:64]


def _detect_source_type(path: Path) -> SourceTypeEnum:
    """Guess the source type from file extension."""
    suffix = path.suffix.lower()
    if suffix == ".md":
        return SourceTypeEnum.markdown
    elif suffix == ".json":
        return SourceTypeEnum.json
    elif suffix == ".txt":
        return SourceTypeEnum.plaintext
    return SourceTypeEnum.other
