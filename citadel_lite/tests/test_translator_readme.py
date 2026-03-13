"""Tests for ReadmeTranslator."""

from __future__ import annotations

import pytest

from src.roadmap_ir.types import StatusEnum, VerifyEnum
from src.roadmap_translator.translators.readme import ReadmeTranslator

_MODULE_NAME = "test_translator_readme"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

SAMPLE_README = [
    "# Citadel Lite",
    "",
    "**最新実装 (2026-02-16)**:",
    "",
    "- ✅ **VS Code Extension** - CGRF Tier リアルタイム IDE 検証 (Phase 27)",
    "- ✅ **Monitoring** - Prometheus 12メトリクス + Grafana テスト合格 (Phase 26)",
    "- ✅ **V2→V3 統合** - 全レガシーファイル old/ 退避",
    "",
    "## Architecture",
    "Some other content",
]


class TestReadmeTranslator:
    def test_extracts_items(self):
        t = ReadmeTranslator()
        patch = t.translate(SAMPLE_README, "readme-src")
        assert len(patch.items) == 3

    def test_phase_extraction(self):
        t = ReadmeTranslator()
        patch = t.translate(SAMPLE_README, "readme-src")
        phases = {it.item_id: it.phase for it in patch.items}
        assert any(v == 27 for v in phases.values())
        assert any(v == 26 for v in phases.values())

    def test_status_done_with_checkmark(self):
        t = ReadmeTranslator()
        patch = t.translate(SAMPLE_README, "readme-src")
        for item in patch.items:
            assert item.status == StatusEnum.done

    def test_verify_from_keywords(self):
        t = ReadmeTranslator()
        patch = t.translate(SAMPLE_README, "readme-src")
        monitoring = [it for it in patch.items if "monitoring" in it.item_id.lower()
                      or "monitoring" in it.title.lower()]
        assert len(monitoring) == 1
        assert monitoring[0].verify_status == VerifyEnum.tested

    def test_item_without_phase(self):
        t = ReadmeTranslator()
        patch = t.translate(SAMPLE_README, "readme-src")
        no_phase = [it for it in patch.items if it.phase is None]
        assert len(no_phase) == 1
        assert "readme-" in no_phase[0].item_id

    def test_stops_at_next_heading(self):
        t = ReadmeTranslator()
        extended = SAMPLE_README + [
            "- ✅ **Should Not Appear** - outside section",
        ]
        patch = t.translate(extended, "readme-src")
        assert len(patch.items) == 3

    def test_empty_input(self):
        t = ReadmeTranslator()
        patch = t.translate([], "readme-src")
        assert len(patch.items) == 0

    def test_name(self):
        assert ReadmeTranslator().name == "readme"
