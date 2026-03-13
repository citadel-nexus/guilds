"""Base translator abstract class for Roadmap IR extraction.

All concrete translators inherit from BaseTranslator and implement
the ``translate()`` method which converts raw document lines into
a TranslationPatch (partial IR items + evidence).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from src.roadmap_ir.types import Evidence, Item

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_base"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# TranslationPatch — the output of a single translator
# ---------------------------------------------------------------------------
@dataclass
class TranslationPatch:
    """Partial extraction result produced by one translator."""

    source_id: str
    items: List[Item] = field(default_factory=list)


# ---------------------------------------------------------------------------
# BaseTranslator ABC
# ---------------------------------------------------------------------------
class BaseTranslator(ABC):
    """Abstract base class for all Roadmap Translators."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable translator name."""

    @abstractmethod
    def translate(
        self, lines: List[str], source_id: str
    ) -> TranslationPatch:
        """Extract items from *lines* and return a TranslationPatch."""

    # -- helpers available to all translators --------------------------------

    @staticmethod
    def slug(text: str, max_len: int = 60) -> str:
        """Convert a title string into a kebab-case item_id slug."""
        s = text.strip().lower()
        s = re.sub(r"[^a-z0-9\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s).strip("-")
        if len(s) < 3:
            s = s + "-item"
        return s[:max_len]

    @staticmethod
    def extract_phase(text: str) -> Optional[int]:
        """Try to extract a phase number from text."""
        m = re.search(r"[Pp]hase\s*(\d+)", text)
        return int(m.group(1)) if m else None
