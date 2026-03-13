"""Auto-detection of document type for translator selection.

Uses filename hints and content signatures to pick the right translator.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Type

from src.roadmap_translator.translators.base import BaseTranslator

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_detect"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


def detect_translator(
    path: Path,
    lines: List[str],
    translators: List[Type[BaseTranslator]],
) -> Optional[Type[BaseTranslator]]:
    """Return the best translator class for the given file, or None."""
    name_lower = path.name.lower()

    # Import here to avoid circular imports at module level
    from src.roadmap_translator.translators.readme import ReadmeTranslator
    from src.roadmap_translator.translators.markdown_roadmap import (
        MarkdownRoadmapTranslator,
    )
    from src.roadmap_translator.translators.implementation_summary import (
        ImplSummaryTranslator,
    )
    from src.roadmap_translator.translators.gitlog import GitlogTranslator
    from src.roadmap_translator.translators.generic_markdown import (
        GenericMarkdownTranslator,
    )

    # 1. Filename-based detection
    if name_lower == "readme.md":
        if ReadmeTranslator in translators:
            return ReadmeTranslator

    if "roadmap" in name_lower and name_lower.endswith(".md"):
        if MarkdownRoadmapTranslator in translators:
            return MarkdownRoadmapTranslator

    if "implementation_summary" in name_lower and name_lower.endswith(".md"):
        if ImplSummaryTranslator in translators:
            return ImplSummaryTranslator

    # git log files
    if (
        "gitlog" in name_lower
        or name_lower == "git.log"
        or name_lower.endswith(".gitlog")
    ):
        if GitlogTranslator in translators:
            return GitlogTranslator

    # 2. Content-signature detection
    sample = "\n".join(lines[:100])

    if re.search(r"\*\*最新実装\s*\(\d{4}-\d{2}-\d{2}\)\*\*", sample):
        if ReadmeTranslator in translators:
            return ReadmeTranslator

    if re.search(r"###\s*(?:✅\s*)?Phase\s+\d+", sample):
        if MarkdownRoadmapTranslator in translators:
            return MarkdownRoadmapTranslator

    if re.search(r"###\s*\d+\.\s+.+?✅", sample):
        if ImplSummaryTranslator in translators:
            return ImplSummaryTranslator

    # git log content signature
    if re.search(r"^[0-9a-f]{7,40}\s*$", sample, re.MULTILINE):
        if GitlogTranslator in translators:
            return GitlogTranslator

    # 3. Generic markdown fallback — any remaining .md file
    if path.suffix.lower() == ".md":
        if GenericMarkdownTranslator in translators:
            return GenericMarkdownTranslator

    return None
