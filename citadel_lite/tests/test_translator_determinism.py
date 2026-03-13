"""Determinism test — same input must produce same output (excluding timestamps)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.roadmap_translator.pipeline import run_pipeline

_MODULE_NAME = "test_translator_determinism"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

_SAMPLE = """\
# Citadel Lite

**最新実装 (2026-02-16)**:

- ✅ **Feature A** - Description A (Phase 1)
- ✅ **Feature B** - Description B (Phase 2)
"""


def _strip_timestamps(data: dict) -> dict:
    """Remove generated_at and collected_at for comparison."""
    data.pop("generated_at", None)
    for s in data.get("sources", []):
        s.pop("collected_at", None)
    return data


class TestDeterminism:
    def test_same_input_same_output(self, tmp_path: Path):
        readme = tmp_path / "README.md"
        readme.write_text(_SAMPLE, encoding="utf-8")

        out1 = tmp_path / "ir1.json"
        out2 = tmp_path / "ir2.json"

        run_pipeline(input_paths=[readme], output_json=out1)
        run_pipeline(input_paths=[readme], output_json=out2)

        d1 = _strip_timestamps(json.loads(out1.read_text(encoding="utf-8")))
        d2 = _strip_timestamps(json.loads(out2.read_text(encoding="utf-8")))

        assert d1 == d2

    def test_item_order_stable(self, tmp_path: Path):
        readme = tmp_path / "README.md"
        readme.write_text(_SAMPLE, encoding="utf-8")

        r1 = run_pipeline(input_paths=[readme])
        r2 = run_pipeline(input_paths=[readme])

        ids1 = [it.item_id for it in r1.ir.items]
        ids2 = [it.item_id for it in r2.ir.items]
        assert ids1 == ids2
