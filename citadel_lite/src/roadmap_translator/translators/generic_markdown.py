"""Generic Markdown translator — fallback for any .md file.

Extracts items from headings (H1-H6), numbered lists, and bullet lists.
Status is determined deterministically via keyword/emoji matching; items
that cannot be classified fall back to ``status=unknown`` with a note.

Blueprint v1.1 §3.5 (generic_markdown).
"""

from __future__ import annotations

import re
import sys
from typing import Dict, List, Optional, Tuple

from src.roadmap_ir.types import (
    EvidenceText,
    Item,
    ItemKindEnum,
    NoteLevelEnum,
    Note,
    StatusEnum,
    VerifyEnum,
)
from src.roadmap_translator.translators.base import BaseTranslator, TranslationPatch

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_generic_markdown"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
_HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<text>.+)$")
_NUMBERED_RE = re.compile(r"^\s*\d+\.\s+(?P<text>.+)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(?P<text>.+)$")

# Status keyword dictionaries (checked in order; first match wins)
_STATUS_DONE_RE = re.compile(
    r"✅|(?:^|[\s\[])(done|完了|完成|DONE)(?:$|[\s\]:])", re.IGNORECASE
)
_STATUS_PLANNED_RE = re.compile(
    r"☐|\[ \]|TODO|PLANNED|計画|予定", re.IGNORECASE
)
_STATUS_BLOCKED_RE = re.compile(
    r"🚫|BLOCKED|blocked|依存待ち|ブロック", re.IGNORECASE
)
_STATUS_IN_PROGRESS_RE = re.compile(
    r"🔄|WIP|IN[_\s]PROGRESS|in[_\s]progress|進行中", re.IGNORECASE
)

_VERIFY_RE = re.compile(
    r"(?:テスト|tested|PASS|passing|検証|verified|合格)", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_status(text: str) -> Tuple[StatusEnum, Optional[str]]:
    """Return (status, reason_if_unknown) for a line of text."""
    if _STATUS_DONE_RE.search(text):
        return StatusEnum.done, None
    if _STATUS_BLOCKED_RE.search(text):
        return StatusEnum.blocked, None
    if _STATUS_IN_PROGRESS_RE.search(text):
        return StatusEnum.in_progress, None
    if _STATUS_PLANNED_RE.search(text):
        return StatusEnum.planned, None
    return StatusEnum.unknown, f"no status marker found in: {text[:80]!r}"


def _clean_title(text: str) -> str:
    """Strip leading checkmarks / emoji from a heading title."""
    text = text.strip()
    # Remove leading ✅, 🚫, 🔄 etc.
    text = re.sub(r"^[✅🚫🔄☐\[\]\s]+", "", text)
    # Remove trailing ✅
    text = re.sub(r"\s*✅\s*$", "", text)
    return text.strip() or text


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------

class GenericMarkdownTranslator(BaseTranslator):
    """Fallback translator for arbitrary Markdown files."""

    def __init__(self, interactive: bool = False) -> None:
        self._interactive = interactive

    @property
    def name(self) -> str:
        return "generic_markdown"

    def translate(
        self, lines: List[str], source_id: str
    ) -> TranslationPatch:
        patch = TranslationPatch(source_id=source_id)

        # Tracks the current heading hierarchy stack: list of (level, text)
        heading_stack: List[Tuple[int, str]] = []

        for line_no, line in enumerate(lines, start=1):
            line_stripped = line.rstrip()
            if not line_stripped:
                continue

            # --- Heading ---
            hm = _HEADING_RE.match(line_stripped)
            if hm:
                level = len(hm.group("level"))
                raw_text = hm.group("text").strip()

                # Update hierarchy stack
                heading_stack = [
                    (lvl, txt) for lvl, txt in heading_stack if lvl < level
                ]
                heading_stack.append((level, raw_text))

                title = _clean_title(raw_text)
                if not title or len(title) < 2:
                    continue

                status, reason = _detect_status(raw_text)
                verify = (
                    VerifyEnum.tested if _VERIFY_RE.search(raw_text)
                    else VerifyEnum.unknown
                )

                if reason and self._interactive:
                    print(
                        f"[generic_markdown] L{line_no} unknown: {reason}",
                        file=sys.stderr,
                    )

                hierarchy_path = [txt for _, txt in heading_stack[:-1]]
                item_id = f"generic-{self.slug(title, 55)}"

                ev = EvidenceText(
                    source_id=source_id,
                    text=f"L{line_no}: {raw_text}"[:800],
                    weight=0.4,
                )
                item = Item(
                    item_id=item_id,
                    kind=ItemKindEnum.feature,
                    phase=self.extract_phase(raw_text),
                    title=title,
                    status=status,
                    verify_status=verify,
                    evidence=[ev],
                    raw={
                        "hierarchy_path": hierarchy_path,
                        "source_line": line_no,
                    },
                )
                patch.items.append(item)
                continue

            # --- Numbered list item ---
            nm = _NUMBERED_RE.match(line_stripped)
            if nm:
                raw_text = nm.group("text").strip()
                self._emit_list_item(
                    patch, source_id, line_no, raw_text, heading_stack
                )
                continue

            # --- Bullet list item ---
            bm = _BULLET_RE.match(line_stripped)
            if bm:
                raw_text = bm.group("text").strip()
                self._emit_list_item(
                    patch, source_id, line_no, raw_text, heading_stack
                )

        return patch

    # ------------------------------------------------------------------
    def _emit_list_item(
        self,
        patch: TranslationPatch,
        source_id: str,
        line_no: int,
        raw_text: str,
        heading_stack: List[Tuple[int, str]],
    ) -> None:
        title = _clean_title(raw_text)
        if not title or len(title) < 2:
            return

        status, reason = _detect_status(raw_text)
        verify = (
            VerifyEnum.tested if _VERIFY_RE.search(raw_text)
            else VerifyEnum.unknown
        )

        if reason and self._interactive:
            print(
                f"[generic_markdown] L{line_no} unknown: {reason}",
                file=sys.stderr,
            )

        hierarchy_path = [txt for _, txt in heading_stack]
        # Prefix with heading context to form a unique slug
        context = heading_stack[-1][1] if heading_stack else "root"
        item_id = f"generic-{self.slug(context + '-' + title, 60)}"

        ev = EvidenceText(
            source_id=source_id,
            text=f"L{line_no}: {raw_text}"[:800],
            weight=0.3,
        )
        item = Item(
            item_id=item_id,
            kind=ItemKindEnum.task,
            phase=self.extract_phase(raw_text),
            title=title,
            status=status,
            verify_status=verify,
            evidence=[ev],
            raw={
                "hierarchy_path": hierarchy_path,
                "source_line": line_no,
            },
        )
        patch.items.append(item)
