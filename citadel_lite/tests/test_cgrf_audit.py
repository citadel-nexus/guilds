# tests/test_cgrf_audit.py
"""
Tests for CGRF v3.0 compliance audit tool.

CGRF v3.0: MS-C1 / Tier 1
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add tools/ to path for import
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from cgrf_audit import (
    AuditReport,
    FileAuditResult,
    _audit_file,
    _should_skip,
    audit_directory,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.write_text(content, encoding="utf-8")
    return p


FULL_HEADER = """\
\"\"\"Module docstring.\"\"\"
from __future__ import annotations

_MODULE_NAME    = "test_mod"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""

MISSING_ROLE = """\
\"\"\"Module docstring.\"\"\"
_MODULE_NAME    = "test_mod"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
"""

MISSING_ALL = """\
\"\"\"Module docstring.\"\"\"

def foo(): pass
"""

PARTIAL = """\
_MODULE_NAME    = "partial_mod"
_CGRF_TIER      = 2
"""


# ── Unit tests: _audit_file ───────────────────────────────────────────────────

class TestAuditFile:
    def test_compliant_file(self, tmp_path):
        f = _write(tmp_path, "good.py", FULL_HEADER)
        result = _audit_file(f)
        assert result.compliant is True
        assert result.missing == []

    def test_missing_execution_role(self, tmp_path):
        f = _write(tmp_path, "no_role.py", MISSING_ROLE)
        result = _audit_file(f)
        assert result.compliant is False
        assert "_EXECUTION_ROLE" in result.missing

    def test_missing_all_fields(self, tmp_path):
        f = _write(tmp_path, "empty.py", MISSING_ALL)
        result = _audit_file(f)
        assert result.compliant is False
        assert len(result.missing) == 4

    def test_partial_fields(self, tmp_path):
        f = _write(tmp_path, "partial.py", PARTIAL)
        result = _audit_file(f)
        assert result.compliant is False
        assert "_MODULE_NAME" in result.present
        assert result.present["_MODULE_NAME"] is True
        assert result.present["_MODULE_VERSION"] is False
        assert result.present["_EXECUTION_ROLE"] is False

    def test_values_extracted(self, tmp_path):
        f = _write(tmp_path, "good2.py", FULL_HEADER)
        result = _audit_file(f)
        assert result.values["_MODULE_NAME"] == "test_mod"
        assert result.values["_MODULE_VERSION"] == "1.0.0"
        assert result.values["_CGRF_TIER"] == "1"
        assert result.values["_EXECUTION_ROLE"] == "INTEGRATION"

    def test_unreadable_file(self, tmp_path):
        p = tmp_path / "ghost.py"
        # File doesn't exist — should not raise, all fields missing
        result = _audit_file(p)
        assert result.compliant is False
        assert len(result.missing) == 4


# ── Unit tests: _should_skip ──────────────────────────────────────────────────

class TestShouldSkip:
    def test_init_skipped(self, tmp_path):
        p = tmp_path / "__init__.py"
        assert _should_skip(p) is True

    def test_conftest_skipped(self, tmp_path):
        p = tmp_path / "conftest.py"
        assert _should_skip(p) is True

    def test_regular_module_not_skipped(self, tmp_path):
        p = tmp_path / "my_module.py"
        assert _should_skip(p) is False


# ── Integration tests: audit_directory ───────────────────────────────────────

class TestAuditDirectory:
    def test_empty_dir_yields_zero_results(self, tmp_path):
        report = audit_directory(tmp_path)
        assert report.scanned == 0
        assert report.violations == 0

    def test_all_compliant(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(src, "mod_a.py", FULL_HEADER)
        _write(src, "mod_b.py", FULL_HEADER.replace("test_mod", "mod_b"))
        report = audit_directory(src)
        assert report.scanned == 2
        assert report.violations == 0
        assert report.compliant == 2

    def test_mixed_compliance(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(src, "good.py", FULL_HEADER)
        _write(src, "bad.py", MISSING_ROLE)
        report = audit_directory(src)
        assert report.scanned == 2
        assert report.compliant == 1
        assert report.violations == 1

    def test_init_files_skipped(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(src, "__init__.py", MISSING_ALL)
        _write(src, "real.py", FULL_HEADER)
        report = audit_directory(src)
        assert report.scanned == 1
        assert report.skipped == 1
        assert report.violations == 0

    def test_nested_directories_scanned(self, tmp_path):
        src = tmp_path / "src"
        sub = src / "sub"
        sub.mkdir(parents=True)
        _write(src, "top.py", FULL_HEADER)
        _write(sub, "nested.py", MISSING_ALL)
        report = audit_directory(src)
        assert report.scanned == 2
        assert report.violations == 1

    def test_violation_results_filtered(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(src, "good.py", FULL_HEADER)
        _write(src, "bad.py", MISSING_ALL)
        report = audit_directory(src)
        bad = report.violation_results
        assert len(bad) == 1
        assert "bad.py" in bad[0].path


# ── AuditReport serialization ─────────────────────────────────────────────────

class TestAuditReportDict:
    def test_to_dict_structure(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(src, "bad.py", MISSING_ROLE)
        report = audit_directory(src)
        d = report.to_dict()
        assert "summary" in d
        assert "violations" in d
        assert d["summary"]["violations"] == 1
        assert len(d["violations"]) == 1
        assert "_EXECUTION_ROLE" in d["violations"][0]["missing"]

    def test_to_dict_all_compliant(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(src, "ok.py", FULL_HEADER)
        report = audit_directory(src)
        d = report.to_dict()
        assert d["summary"]["violations"] == 0
        assert d["violations"] == []


# ── Smoke test: runs against actual src/ ──────────────────────────────────────

class TestActualCodebase:
    def test_audit_runs_without_error(self):
        src_dir = _REPO_ROOT / "src"
        if not src_dir.exists():
            pytest.skip("src/ directory not found")
        report = audit_directory(src_dir)
        # Must complete without exception — violations allowed (not all files upgraded yet)
        assert isinstance(report.scanned, int)
        assert report.scanned > 0

    def test_cgrf_audit_itself_is_compliant(self):
        audit_tool = _REPO_ROOT / "tools" / "cgrf_audit.py"
        result = _audit_file(audit_tool)
        assert result.compliant is True, f"cgrf_audit.py missing: {result.missing}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
