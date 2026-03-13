"""Tests for ImplSummaryTranslator."""

from __future__ import annotations

import pytest

from src.roadmap_ir.types import StatusEnum, VerifyEnum
from src.roadmap_translator.translators.implementation_summary import ImplSummaryTranslator

_MODULE_NAME = "test_translator_impl_summary"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

SAMPLE_IMPL = [
    "# Implementation Summary - 2026-02-16",
    "",
    "## Implemented Features",
    "",
    "### 1. CGRF Tier 0-1 Metadata & SRS Format ✅",
    "",
    "**実装時間**: ~2時間",
    "**状態**: 完了・デモ確認済み",
    "",
    "#### 変更ファイル",
    "",
    "- `src/types.py` - CGRFMetadata dataclass 追加 (Lines 65-86)",
    "- `src/agents/sentinel_v2.py` - CGRF metadata 統合 (Tier 1)",
    "",
    "### 2. Orchestrator V3 Verify Retry ✅",
    "",
    "**実装時間**: ~1時間",
    "**状態**: 完了・テスト追加済み",
    "",
    "### 3. Future Feature",
    "",
    "**状態**: 進行中",
    "",
]


class TestImplSummaryTranslator:
    def test_extracts_features(self):
        t = ImplSummaryTranslator()
        patch = t.translate(SAMPLE_IMPL, "impl-src")
        assert len(patch.items) == 3

    def test_done_status_from_checkmark(self):
        t = ImplSummaryTranslator()
        patch = t.translate(SAMPLE_IMPL, "impl-src")
        first = patch.items[0]
        assert first.status == StatusEnum.done

    def test_done_status_from_state_line(self):
        t = ImplSummaryTranslator()
        patch = t.translate(SAMPLE_IMPL, "impl-src")
        second = patch.items[1]
        assert second.status == StatusEnum.done

    def test_in_progress_status(self):
        t = ImplSummaryTranslator()
        patch = t.translate(SAMPLE_IMPL, "impl-src")
        third = patch.items[2]
        assert third.status == StatusEnum.in_progress

    def test_verify_from_state(self):
        t = ImplSummaryTranslator()
        patch = t.translate(SAMPLE_IMPL, "impl-src")
        # "完了・デモ確認済み" matches _VERIFY_RE
        first = patch.items[0]
        assert first.verify_status == VerifyEnum.tested
        # "完了・テスト追加済み" matches too
        second = patch.items[1]
        assert second.verify_status == VerifyEnum.tested

    def test_file_evidence(self):
        t = ImplSummaryTranslator()
        patch = t.translate(SAMPLE_IMPL, "impl-src")
        first = patch.items[0]
        file_evs = [e for e in first.evidence if hasattr(e, "loc")]
        assert len(file_evs) == 2
        # Check line range extraction
        types_ev = [e for e in file_evs if "types.py" in e.loc.path]
        assert len(types_ev) == 1
        assert types_ev[0].loc.line_start == 65
        assert types_ev[0].loc.line_end == 86

    def test_empty_input(self):
        t = ImplSummaryTranslator()
        patch = t.translate([], "impl-src")
        assert len(patch.items) == 0

    def test_name(self):
        assert ImplSummaryTranslator().name == "implementation_summary"
