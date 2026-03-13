# tests/test_sake_reader.py
"""
Tests for VCCSakeReader.

CGRF v3.0: MS-C3 / Tier 1
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.integrations.vcc.sake_reader import SakeCapsProfile, SakeFile, VCCSakeReader


# ── Fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_SAKE = {
    "filetype": "SAKE",
    "version": "1.0.0",
    "taskir_blocks": {"task_name": "TestWidget", "purpose": "Test widget purpose"},
    "sake_layers": {
        "backend_layer": {"language": "Python", "framework": "FastAPI"},
        "caps_profile": {
            "trust_score": 0.92,
            "confidence": 0.88,
            "cost": 0.05,
            "latency_ms": 120.0,
            "risk": 0.08,
            "precision": 0.91,
            "grade": "T1",
        },
    },
}

FLAT_CAPS_SAKE = {
    "filetype": "SAKE",
    "version": "1.0.0",
    "caps_profile": {
        "trust_score": 0.76,
        "grade": "T2",
    },
}


def _write_sake(tmp: Path, name: str, content: dict) -> Path:
    p = tmp / name
    p.write_text(json.dumps(content), encoding="utf-8")
    return p


# ── TestVCCSakeReaderLoad ──────────────────────────────────────────────────────

class TestVCCSakeReaderLoad:
    def test_load_valid_sake_file(self, tmp_path):
        p = _write_sake(tmp_path, "test.sake", MINIMAL_SAKE)
        reader = VCCSakeReader()
        sake = reader.load(str(p))
        assert isinstance(sake, SakeFile)
        assert sake.filetype == "SAKE"
        assert sake.task_name == "TestWidget"

    def test_load_caps_profile_from_sake_layers(self, tmp_path):
        p = _write_sake(tmp_path, "nested.sake", MINIMAL_SAKE)
        reader = VCCSakeReader()
        sake = reader.load(str(p))
        assert sake.caps_profile.trust_score == pytest.approx(0.92)
        assert sake.caps_profile.grade == "T1"

    def test_load_flat_caps_profile(self, tmp_path):
        p = _write_sake(tmp_path, "flat.sake", FLAT_CAPS_SAKE)
        reader = VCCSakeReader()
        sake = reader.load(str(p))
        assert sake.caps_profile.trust_score == pytest.approx(0.76)

    def test_load_language_and_framework_extracted(self, tmp_path):
        p = _write_sake(tmp_path, "lang.sake", MINIMAL_SAKE)
        reader = VCCSakeReader()
        sake = reader.load(str(p))
        assert sake.language == "Python"
        assert sake.framework == "FastAPI"

    def test_load_missing_file_raises_file_not_found(self, tmp_path):
        reader = VCCSakeReader()
        with pytest.raises(FileNotFoundError):
            reader.load(str(tmp_path / "nonexistent.sake"))

    def test_load_invalid_json_raises_value_error(self, tmp_path):
        p = tmp_path / "bad.sake"
        p.write_text("NOT JSON", encoding="utf-8")
        reader = VCCSakeReader()
        with pytest.raises(ValueError, match="invalid JSON"):
            reader.load(str(p))

    def test_load_wrong_filetype_raises_value_error(self, tmp_path):
        content = {**MINIMAL_SAKE, "filetype": "NOT_SAKE"}
        p = _write_sake(tmp_path, "wrong.sake", content)
        reader = VCCSakeReader()
        with pytest.raises(ValueError, match="filetype must be 'SAKE'"):
            reader.load(str(p))


# ── TestVCCSakeReaderLoadDir ──────────────────────────────────────────────────

class TestVCCSakeReaderLoadDir:
    def test_load_dir_returns_all_sake_files(self, tmp_path):
        _write_sake(tmp_path, "a.sake", MINIMAL_SAKE)
        _write_sake(tmp_path, "b.sake", FLAT_CAPS_SAKE)
        reader = VCCSakeReader()
        results = reader.load_dir(str(tmp_path))
        assert len(results) == 2

    def test_load_dir_empty_dir_returns_empty(self, tmp_path):
        reader = VCCSakeReader()
        results = reader.load_dir(str(tmp_path))
        assert results == []

    def test_load_dir_missing_dir_returns_empty(self):
        reader = VCCSakeReader()
        results = reader.load_dir("/nonexistent/path/does/not/exist")
        assert results == []

    def test_load_dir_skips_invalid_files(self, tmp_path):
        _write_sake(tmp_path, "good.sake", MINIMAL_SAKE)
        bad = tmp_path / "bad.sake"
        bad.write_text("INVALID", encoding="utf-8")
        reader = VCCSakeReader()
        results = reader.load_dir(str(tmp_path))
        assert len(results) == 1
        assert results[0].task_name == "TestWidget"


# ── TestVCCSakeReaderToHealthGrade ────────────────────────────────────────────

class TestVCCSakeReaderToHealthGrade:
    def test_score_0_90_returns_t1(self):
        reader = VCCSakeReader()
        grade = reader.to_health_grade(SakeCapsProfile(trust_score=0.90))
        assert grade == "T1"

    def test_score_0_95_returns_t1(self):
        reader = VCCSakeReader()
        grade = reader.to_health_grade(SakeCapsProfile(trust_score=0.95))
        assert grade == "T1"

    def test_score_0_75_returns_t2(self):
        reader = VCCSakeReader()
        grade = reader.to_health_grade(SakeCapsProfile(trust_score=0.75))
        assert grade == "T2"

    def test_score_0_80_returns_t2(self):
        reader = VCCSakeReader()
        grade = reader.to_health_grade(SakeCapsProfile(trust_score=0.80))
        assert grade == "T2"

    def test_score_0_60_returns_t3(self):
        reader = VCCSakeReader()
        grade = reader.to_health_grade(SakeCapsProfile(trust_score=0.60))
        assert grade == "T3"

    def test_score_0_40_returns_t4(self):
        reader = VCCSakeReader()
        grade = reader.to_health_grade(SakeCapsProfile(trust_score=0.40))
        assert grade == "T4"

    def test_score_0_39_returns_t5(self):
        reader = VCCSakeReader()
        grade = reader.to_health_grade(SakeCapsProfile(trust_score=0.39))
        assert grade == "T5"

    def test_score_0_00_returns_t5(self):
        reader = VCCSakeReader()
        grade = reader.to_health_grade(SakeCapsProfile(trust_score=0.00))
        assert grade == "T5"


# ── TestSakeCapsProfileDefault ────────────────────────────────────────────────

class TestSakeCapsProfileDefault:
    def test_default_trust_score_is_zero(self):
        caps = SakeCapsProfile()
        assert caps.trust_score == 0.0

    def test_default_grade_is_unknown(self):
        caps = SakeCapsProfile()
        assert caps.grade == "UNKNOWN"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
