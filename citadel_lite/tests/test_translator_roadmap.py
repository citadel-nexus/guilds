"""Tests for MarkdownRoadmapTranslator."""

from __future__ import annotations

import pytest

from src.roadmap_ir.types import ItemKindEnum, StatusEnum
from src.roadmap_translator.translators.markdown_roadmap import MarkdownRoadmapTranslator

_MODULE_NAME = "test_translator_roadmap"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

SAMPLE_ROADMAP = [
    "# Citadel Lite RoadMap",
    "",
    "## 📍 現在地: **Phase 27 完了**",
    "",
    "### ✅ Phase 21: CGRF Tier 1 Full Compliance (完成) ✅",
    "",
    "12. **✅ Unit Tests for Main Agents** - 4エージェント Tier 1 テスト完全準拠",
    "    - 根拠: `tests/test_sentinel_v2.py` (9 tests), `tests/test_sherlock_v3.py`",
    "",
    "### ✅ Phase 22: Auto-Execution & Auto-Merge (完成) ✅",
    "",
    "13. **✅ Auto-Execution Pipeline** - 完全自動化システム実装済み",
    "    - 根拠: `src/orchestrator_v3.py:446-592`",
    "",
    "### Phase 28: Future Work (予定)",
    "",
    "## Other Section",
]


class TestMarkdownRoadmapTranslator:
    def test_extracts_phases(self):
        t = MarkdownRoadmapTranslator()
        patch = t.translate(SAMPLE_ROADMAP, "roadmap-src")
        phase_items = [it for it in patch.items if it.kind == ItemKindEnum.phase]
        assert len(phase_items) == 3  # Phase 21, 22, 28

    def test_phase_status(self):
        t = MarkdownRoadmapTranslator()
        patch = t.translate(SAMPLE_ROADMAP, "roadmap-src")
        phase_items = {it.item_id: it for it in patch.items if it.kind == ItemKindEnum.phase}
        assert phase_items["phase-21"].status == StatusEnum.done
        assert phase_items["phase-22"].status == StatusEnum.done
        assert phase_items["phase-28"].status == StatusEnum.planned

    def test_extracts_sub_items(self):
        t = MarkdownRoadmapTranslator()
        patch = t.translate(SAMPLE_ROADMAP, "roadmap-src")
        features = [it for it in patch.items if it.kind == ItemKindEnum.feature]
        assert len(features) == 2

    def test_file_evidence_extraction(self):
        t = MarkdownRoadmapTranslator()
        patch = t.translate(SAMPLE_ROADMAP, "roadmap-src")
        phase21 = next(it for it in patch.items if it.item_id == "phase-21")
        file_evs = [e for e in phase21.evidence if hasattr(e, "loc")]
        assert len(file_evs) >= 1

    def test_line_range_in_evidence(self):
        t = MarkdownRoadmapTranslator()
        patch = t.translate(SAMPLE_ROADMAP, "roadmap-src")
        phase22 = next(it for it in patch.items if it.item_id == "phase-22")
        file_evs = [e for e in phase22.evidence if hasattr(e, "loc")]
        assert any(e.loc.line_start == 446 and e.loc.line_end == 592 for e in file_evs)

    def test_empty_input(self):
        t = MarkdownRoadmapTranslator()
        patch = t.translate([], "roadmap-src")
        assert len(patch.items) == 0

    def test_name(self):
        assert MarkdownRoadmapTranslator().name == "markdown_roadmap"
