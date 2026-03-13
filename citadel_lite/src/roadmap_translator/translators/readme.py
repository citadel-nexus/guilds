"""README.md translator — extracts items from **最新実装** blocks.

Regex rules follow Blueprint v1.1 §3.2.
"""

from __future__ import annotations

import re
from typing import List, Optional

from src.roadmap_ir.types import (
    EvidenceText,
    Item,
    ItemKindEnum,
    StatusEnum,
    VerifyEnum,
)
from src.roadmap_translator.translators.base import BaseTranslator, TranslationPatch

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_readme"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Patterns (Blueprint v1.1 §3.2)
# ---------------------------------------------------------------------------
_SECTION_RE = re.compile(
    r"^\*\*最新実装\s*\((?P<date>\d{4}-\d{2}-\d{2})\)\*\*:\s*$"
)

_BULLET_RE = re.compile(
    r"^-\s*(?P<mark>✅)?\s*\*\*(?P<title>.+?)\*\*\s*-\s*(?P<desc>.+?)$"
)

_PHASE_REF_RE = re.compile(r"\(Phase\s*(?P<phase>\d+)\)")

_VERIFY_KEYWORDS = {
    VerifyEnum.verified: ["verified", "検証済み"],
    VerifyEnum.tested: ["テスト", "tested", "合格", "PASS", "passing"],
}


class ReadmeTranslator(BaseTranslator):
    """Extracts items from README.md **最新実装** blocks."""

    @property
    def name(self) -> str:
        return "readme"

    def translate(
        self, lines: List[str], source_id: str
    ) -> TranslationPatch:
        patch = TranslationPatch(source_id=source_id)
        in_section = False

        for line_no, line in enumerate(lines, start=1):
            # Detect section start
            if _SECTION_RE.match(line):
                in_section = True
                continue

            # Section ends at next heading or blank-then-heading
            if in_section and re.match(r"^#{1,3}\s", line):
                in_section = False
                continue

            if not in_section:
                continue

            m = _BULLET_RE.match(line)
            if not m:
                continue

            title = m.group("title").strip()
            desc = m.group("desc").strip()
            has_check = m.group("mark") is not None

            # Phase extraction
            phase: Optional[int] = None
            pm = _PHASE_REF_RE.search(desc)
            if pm:
                phase = int(pm.group("phase"))

            # Status
            status = StatusEnum.done if has_check else StatusEnum.unknown

            # Verify status from description
            verify = VerifyEnum.unknown
            desc_lower = desc.lower()
            for v_status, keywords in _VERIFY_KEYWORDS.items():
                if any(kw.lower() in desc_lower for kw in keywords):
                    verify = v_status
                    break

            # Item ID
            if phase is not None:
                item_id = f"phase-{phase:02d}-{self.slug(title, 40)}"
            else:
                item_id = f"readme-{self.slug(title, 50)}"

            evidence = EvidenceText(
                source_id=source_id,
                text=f"L{line_no}: {title} - {desc}"[:800],
                weight=0.4,
            )

            item = Item(
                item_id=item_id,
                kind=ItemKindEnum.feature,
                phase=phase,
                title=title,
                status=status,
                verify_status=verify,
                evidence=[evidence],
            )
            patch.items.append(item)

        return patch
