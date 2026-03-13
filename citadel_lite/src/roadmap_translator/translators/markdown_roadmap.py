"""RoadMap markdown translator — extracts Phase items from RoadMap files.

Regex rules follow Blueprint v1.1 §3.3.
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
_MODULE_NAME = "translator_markdown_roadmap"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Patterns (Blueprint v1.1 §3.3)
# ---------------------------------------------------------------------------
_PHASE_HEADING_RE = re.compile(
    r"^###\s*(?P<mark>✅)?\s*Phase\s*(?P<phase>\d+):\s*"
    r"(?P<title>.+?)\s*\((?P<state>[^)]+)\)\s*(?P<trailing>✅)?\s*$"
)

_NUMBERED_ITEM_RE = re.compile(
    r"^\s*\d+\.\s*\*\*(?P<mark>✅)?\s*(?P<title>.+?)\*\*\s*-\s*(?P<desc>.+)$"
)

_EVIDENCE_LINE_RE = re.compile(
    r"^\s*-\s*根拠:\s*(?P<body>.+)$"
)

_FILE_REF_RE = re.compile(
    r"`(?P<path>[^`]+\.(?:py|ts|js|json|yaml|toml|md))"
    r"(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?`"
)

_VERIFY_RE = re.compile(
    r"(?:テスト|PASS|passing|tests?\s+passing|検証|verified)", re.IGNORECASE
)


class MarkdownRoadmapTranslator(BaseTranslator):
    """Extracts items from Citadel_lite_RoadMap markdown files."""

    @property
    def name(self) -> str:
        return "markdown_roadmap"

    def translate(
        self, lines: List[str], source_id: str
    ) -> TranslationPatch:
        patch = TranslationPatch(source_id=source_id)

        current_phase: Optional[int] = None
        current_phase_title: Optional[str] = None
        current_phase_done: bool = False
        phase_evidence: List[Evidence] = []
        phase_start_line: int = 0

        for line_no, line in enumerate(lines, start=1):
            # Phase heading
            pm = _PHASE_HEADING_RE.match(line)
            if pm:
                # Flush previous phase
                if current_phase is not None:
                    self._flush_phase(
                        patch, source_id, current_phase,
                        current_phase_title, current_phase_done,
                        phase_evidence, phase_start_line,
                    )

                current_phase = int(pm.group("phase"))
                current_phase_title = pm.group("title").strip()
                state = pm.group("state").strip()
                has_mark = pm.group("mark") or pm.group("trailing")
                current_phase_done = (
                    has_mark is not None
                    or state in ("完了", "完成")
                )
                phase_evidence = []
                phase_start_line = line_no
                continue

            # Next section resets phase context
            if re.match(r"^##\s", line):
                if current_phase is not None:
                    self._flush_phase(
                        patch, source_id, current_phase,
                        current_phase_title, current_phase_done,
                        phase_evidence, phase_start_line,
                    )
                    current_phase = None
                continue

            if current_phase is None:
                continue

            # Numbered sub-item within a phase
            nm = _NUMBERED_ITEM_RE.match(line)
            if nm:
                title = nm.group("title").strip()
                desc = nm.group("desc").strip()
                has_check = nm.group("mark") is not None

                status = StatusEnum.done if has_check else StatusEnum.unknown
                verify = VerifyEnum.unknown
                if _VERIFY_RE.search(desc):
                    verify = VerifyEnum.tested

                sub_id = f"phase-{current_phase:02d}-{self.slug(title, 40)}"

                ev = EvidenceText(
                    source_id=source_id,
                    text=f"L{line_no}: {title} - {desc}"[:800],
                    weight=0.4,
                )

                item = Item(
                    item_id=sub_id,
                    kind=ItemKindEnum.feature,
                    phase=current_phase,
                    title=title,
                    status=status,
                    verify_status=verify,
                    evidence=[ev],
                )
                patch.items.append(item)
                continue

            # Evidence line (根拠:)
            em = _EVIDENCE_LINE_RE.match(line)
            if em:
                body = em.group("body")
                for fm in _FILE_REF_RE.finditer(body):
                    start = int(fm.group("start")) if fm.group("start") else 1
                    end = int(fm.group("end")) if fm.group("end") else start
                    phase_evidence.append(
                        EvidenceFileLoc(
                            source_id=source_id,
                            loc=Loc(
                                path=fm.group("path"),
                                line_start=start,
                                line_end=end,
                            ),
                            weight=0.8,
                        )
                    )

        # Flush last phase
        if current_phase is not None:
            self._flush_phase(
                patch, source_id, current_phase,
                current_phase_title, current_phase_done,
                phase_evidence, phase_start_line,
            )

        return patch

    def _flush_phase(
        self,
        patch: TranslationPatch,
        source_id: str,
        phase: int,
        title: Optional[str],
        done: bool,
        evidence: List[Evidence],
        start_line: int,
    ) -> None:
        """Emit a phase-level item."""
        if not evidence:
            evidence = [
                EvidenceText(
                    source_id=source_id,
                    text=f"L{start_line}: Phase {phase} heading",
                    weight=0.3,
                )
            ]

        item_id = f"phase-{phase:02d}"
        status = StatusEnum.done if done else StatusEnum.planned

        item = Item(
            item_id=item_id,
            kind=ItemKindEnum.phase,
            phase=phase,
            title=title or f"Phase {phase}",
            status=status,
            evidence=evidence,
        )
        patch.items.append(item)
