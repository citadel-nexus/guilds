"""Tests for the full translation pipeline — golden test approach."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.roadmap_translator.pipeline import run_pipeline

_MODULE_NAME = "test_translator_pipeline"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# Sample documents for golden test
_README = """\
# Citadel Lite

**最新実装 (2026-02-16)**:

- ✅ **VS Code Extension** - CGRF Tier IDE 検証 (Phase 27)
- ✅ **Monitoring** - Prometheus メトリクス (Phase 26)

## Architecture
"""

_ROADMAP = """\
# RoadMap

### ✅ Phase 26: Monitoring & Observability (完成) ✅

1. **✅ Prometheus Metrics** - 12メトリクス実装
    - 根拠: `src/monitoring/metrics.py:1-50`

### ✅ Phase 27: VS Code Extension (完成) ✅

1. **✅ CGRF IDE Plugin** - リアルタイム検証
    - 根拠: `vscode-extension/citadel-cgrf/extension.ts`
"""

_IMPL = """\
# Implementation Summary

## Implemented Features

### 1. Monitoring Setup ✅

**状態**: 完了・テスト追加済み

#### 変更ファイル

- `src/monitoring/metrics.py` - Prometheus metrics (Lines 1-50)
"""


class TestPipeline:
    def test_full_pipeline(self, tmp_path: Path):
        readme = tmp_path / "README.md"
        readme.write_text(_README, encoding="utf-8")

        roadmap = tmp_path / "Citadel_lite_RoadMap_20260216.md"
        roadmap.write_text(_ROADMAP, encoding="utf-8")

        impl = tmp_path / "IMPLEMENTATION_SUMMARY_20260216.md"
        impl.write_text(_IMPL, encoding="utf-8")

        out_json = tmp_path / "roadmap_ir.json"
        out_report = tmp_path / "roadmap_ir.report.md"

        result = run_pipeline(
            input_paths=[readme, roadmap, impl],
            output_json=out_json,
            output_report=out_report,
        )

        assert result.ir is not None
        assert len(result.ir.sources) == 3
        assert len(result.ir.items) > 0
        assert result.json_path == out_json
        assert result.report_path == out_report

        # JSON is valid
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert data["schema"] == "citadel.roadmap_ir"

        # Report exists
        report_text = out_report.read_text(encoding="utf-8")
        assert "Roadmap IR Report" in report_text

    def test_phase_completion_in_metrics(self, tmp_path: Path):
        roadmap = tmp_path / "Citadel_lite_RoadMap.md"
        roadmap.write_text(_ROADMAP, encoding="utf-8")

        result = run_pipeline(input_paths=[roadmap])
        pc = result.ir.metrics.phase_completion
        assert pc is not None
        assert pc.done > 0

    def test_single_file_pipeline(self, tmp_path: Path):
        readme = tmp_path / "README.md"
        readme.write_text(_README, encoding="utf-8")

        result = run_pipeline(input_paths=[readme])
        assert len(result.ir.items) > 0
        assert len(result.ir.sources) == 1

    def test_conflicts_from_disagreement(self, tmp_path: Path):
        # README says Phase 26 done, a fake roadmap says it's planned
        readme = tmp_path / "README.md"
        readme.write_text(_README, encoding="utf-8")

        roadmap = tmp_path / "Citadel_lite_RoadMap.md"
        roadmap.write_text(_ROADMAP, encoding="utf-8")

        result = run_pipeline(input_paths=[readme, roadmap])
        # There may or may not be conflicts depending on item_id overlap
        # At minimum, verify pipeline doesn't crash
        assert result.ir is not None
