"""Implementation Summary translator — extracts feature cards.

Regex rules follow Blueprint v1.1 §3.4.
"""

from __future__ import annotations

import re
from typing import List, Optional

from src.roadmap_ir.types import (
    EvidenceFileLoc,
    EvidenceText,
    Evidence,
    Item,
    ItemKindEnum,
    Loc,
    StatusEnum,
    VerifyEnum,
)
from src.roadmap_translator.translators.base import BaseTranslator, TranslationPatch

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_implementation_summary"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Patterns (Blueprint v1.1 §3.4)
# ---------------------------------------------------------------------------
_FEATURE_HEADING_RE = re.compile(
    r"^###\s*(?P<num>\d+)\.\s*(?P<title>.+?)(?:\s*(?P<mark>✅))?\s*$"
)

_STATE_LINE_RE = re.compile(
    r"^\*\*状態\*\*:\s*(?P<state>.+)$"
)

_IMPL_TIME_RE = re.compile(
    r"^\*\*実装時間\*\*:\s*(?P<time>.+)$"
)

_CHANGED_FILES_RE = re.compile(r"^####\s+変更ファイル\s*$")

_FILE_ITEM_RE = re.compile(
    r"^-\s*`(?P<path>[^`]+)`\s*-\s*(?P<desc>.+?)"
    r"(?:\s*\(Lines?\s*(?P<start>\d+)(?:-(?P<end>\d+))?\))?\s*$"
)

_VERIFY_RE = re.compile(
    r"(?:テスト|tested|PASS|passing|検証|verified|デモ確認)", re.IGNORECASE
)


class ImplSummaryTranslator(BaseTranslator):
    """Extracts feature items from IMPLEMENTATION_SUMMARY markdown."""

    @property
    def name(self) -> str:
        return "implementation_summary"

    def translate(
        self, lines: List[str], source_id: str
    ) -> TranslationPatch:
        patch = TranslationPatch(source_id=source_id)

        current_title: Optional[str] = None
        current_num: Optional[int] = None
        current_done: bool = False
        current_state: Optional[str] = None
        current_evidence: List[Evidence] = []
        current_start_line: int = 0
        in_changed_files: bool = False

        for line_no, line in enumerate(lines, start=1):
            # Feature heading
            fm = _FEATURE_HEADING_RE.match(line)
            if fm:
                # Flush previous
                if current_title is not None:
                    self._flush_feature(
                        patch, source_id, current_num, current_title,
                        current_done, current_state, current_evidence,
                        current_start_line,
                    )

                current_num = int(fm.group("num"))
                current_title = fm.group("title").strip()
                current_done = fm.group("mark") is not None
                current_state = None
                current_evidence = []
                current_start_line = line_no
                in_changed_files = False
                continue

            if current_title is None:
                continue

            # Next feature or section heading
            if re.match(r"^##\s", line):
                self._flush_feature(
                    patch, source_id, current_num, current_title,
                    current_done, current_state, current_evidence,
                    current_start_line,
                )
                current_title = None
                in_changed_files = False
                continue

            # State line
            sm = _STATE_LINE_RE.match(line)
            if sm:
                current_state = sm.group("state").strip()
                continue

            # Changed files section
            if _CHANGED_FILES_RE.match(line):
                in_changed_files = True
                continue

            # Next sub-heading ends changed files section
            if re.match(r"^####\s", line) and in_changed_files:
                in_changed_files = False

            # File items in changed files section
            if in_changed_files:
                ffm = _FILE_ITEM_RE.match(line)
                if ffm:
                    start = int(ffm.group("start")) if ffm.group("start") else 1
                    end = int(ffm.group("end")) if ffm.group("end") else start
                    current_evidence.append(
                        EvidenceFileLoc(
                            source_id=source_id,
                            loc=Loc(
                                path=ffm.group("path"),
                                line_start=start,
                                line_end=end,
                            ),
                            quote=ffm.group("desc").strip()[:800],
                            weight=0.8,
                        )
                    )

        # Flush last
        if current_title is not None:
            self._flush_feature(
                patch, source_id, current_num, current_title,
                current_done, current_state, current_evidence,
                current_start_line,
            )

        return patch

    def _flush_feature(
        self,
        patch: TranslationPatch,
        source_id: str,
        num: Optional[int],
        title: str,
        done: bool,
        state: Optional[str],
        evidence: List[Evidence],
        start_line: int,
    ) -> None:
        """Emit a feature item."""
        # Determine status
        status = StatusEnum.unknown
        if done:
            status = StatusEnum.done
        elif state:
            state_lower = state.lower()
            if "完了" in state_lower or "完成" in state_lower:
                status = StatusEnum.done
            elif "進行" in state_lower or "wip" in state_lower:
                status = StatusEnum.in_progress
            elif "blocked" in state_lower or "依存" in state_lower:
                status = StatusEnum.blocked

        # Verify status from state text
        verify = VerifyEnum.unknown
        if state and _VERIFY_RE.search(state):
            verify = VerifyEnum.tested

        if not evidence:
            evidence = [
                EvidenceText(
                    source_id=source_id,
                    text=f"L{start_line}: {title}",
                    weight=0.3,
                )
            ]

        item_id = f"impl-{self.slug(title, 55)}"

        item = Item(
            item_id=item_id,
            kind=ItemKindEnum.feature,
            title=title,
            status=status,
            verify_status=verify,
            evidence=evidence,
        )
        patch.items.append(item)
