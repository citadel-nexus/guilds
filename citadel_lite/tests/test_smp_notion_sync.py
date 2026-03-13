# tests/test_smp_notion_sync.py
"""
Tests for smp_notion_sync.

CGRF v3.0: MS-C2 / Tier 1
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.infra.smp_notion_sync import (
    _build_properties,
    _extract_cgrf_fields,
    collect_module_metadata,
    sync_smp_registry,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

COMPLIANT_MODULE = """\
\"\"\"Module docstring.\"\"\"
from __future__ import annotations

_MODULE_NAME    = "my_module"
_MODULE_VERSION = "1.2.3"
_CGRF_TIER      = 2
_EXECUTION_ROLE = "AGENT"
"""

PARTIAL_MODULE = """\
_MODULE_NAME    = "partial"
_CGRF_TIER      = 1
"""

EMPTY_MODULE = """\
def foo(): pass
"""


def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.write_text(content, encoding="utf-8")
    return p


# ── TestExtractCgrfFields ─────────────────────────────────────────────────────

class TestExtractCgrfFields:
    def test_compliant_file_extracts_all_fields(self, tmp_path):
        f = _write(tmp_path, "my_module.py", COMPLIANT_MODULE)
        meta = _extract_cgrf_fields(f)
        assert meta["module_name"] == "my_module"
        assert meta["version"] == "1.2.3"
        assert meta["cgrf_tier"] == 2
        assert meta["execution_role"] == "AGENT"
        assert meta["compliance_pass"] is True

    def test_partial_file_compliance_pass_false(self, tmp_path):
        f = _write(tmp_path, "partial.py", PARTIAL_MODULE)
        meta = _extract_cgrf_fields(f)
        assert meta["compliance_pass"] is False

    def test_empty_file_returns_stem_as_module_name(self, tmp_path):
        f = _write(tmp_path, "empty_mod.py", EMPTY_MODULE)
        meta = _extract_cgrf_fields(f)
        assert meta["module_name"] == "empty_mod"
        assert meta["version"] == ""
        assert meta["cgrf_tier"] == -1

    def test_missing_file_returns_defaults(self, tmp_path):
        ghost = tmp_path / "ghost.py"
        meta = _extract_cgrf_fields(ghost)
        assert meta["module_name"] == "ghost"
        assert meta["compliance_pass"] is False

    def test_tier_invalid_returns_minus_one(self, tmp_path):
        content = '_MODULE_NAME="x"\n_MODULE_VERSION="1"\n_CGRF_TIER="bad"\n_EXECUTION_ROLE="AGENT"\n'
        f = _write(tmp_path, "bad_tier.py", content)
        meta = _extract_cgrf_fields(f)
        assert meta["cgrf_tier"] == -1


# ── TestCollectModuleMetadata ─────────────────────────────────────────────────

class TestCollectModuleMetadata:
    def test_collects_py_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(src, "mod_a.py", COMPLIANT_MODULE)
        _write(src, "mod_b.py", PARTIAL_MODULE)
        modules = collect_module_metadata(src)
        names = [m["module_name"] for m in modules]
        assert "my_module" in names
        assert "partial" in names

    def test_skips_init_and_conftest(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(src, "__init__.py", EMPTY_MODULE)
        _write(src, "conftest.py", EMPTY_MODULE)
        _write(src, "real.py", COMPLIANT_MODULE)
        modules = collect_module_metadata(src)
        assert len(modules) == 1

    def test_includes_rel_path(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write(src, "my_module.py", COMPLIANT_MODULE)
        modules = collect_module_metadata(src)
        assert "rel_path" in modules[0]

    def test_scans_nested_dirs(self, tmp_path):
        src = tmp_path / "src"
        sub = src / "sub"
        sub.mkdir(parents=True)
        _write(src, "top.py", COMPLIANT_MODULE)
        _write(sub, "nested.py", PARTIAL_MODULE)
        modules = collect_module_metadata(src)
        assert len(modules) == 2


# ── TestBuildProperties ───────────────────────────────────────────────────────

class TestBuildProperties:
    def test_module_name_is_title_property(self):
        module = {"module_name": "my_mod", "version": "1.0.0",
                  "cgrf_tier": 1, "execution_role": "AGENT", "compliance_pass": True}
        props = _build_properties(module)
        assert props["module_name"]["title"][0]["text"]["content"] == "my_mod"

    def test_compliance_pass_is_checkbox(self):
        module = {"module_name": "m", "version": "", "cgrf_tier": -1,
                  "execution_role": "", "compliance_pass": False}
        props = _build_properties(module)
        assert props["compliance_pass"]["checkbox"] is False

    def test_tier_minus_one_maps_to_unknown(self):
        module = {"module_name": "m", "version": "", "cgrf_tier": -1,
                  "execution_role": "AGENT", "compliance_pass": False}
        props = _build_properties(module)
        assert props["cgrf_tier"]["select"]["name"] == "UNKNOWN"

    def test_tier_1_maps_to_t1(self):
        module = {"module_name": "m", "version": "", "cgrf_tier": 1,
                  "execution_role": "AGENT", "compliance_pass": True}
        props = _build_properties(module)
        assert props["cgrf_tier"]["select"]["name"] == "T1"

    def test_srs_codes_multi_select(self):
        module = {"module_name": "m", "version": "", "cgrf_tier": 1,
                  "execution_role": "AGENT", "compliance_pass": True,
                  "srs_codes": ["SRS-FIN-001", "SRS-FIN-002"]}
        props = _build_properties(module)
        assert "srs_codes" in props
        names = [s["name"] for s in props["srs_codes"]["multi_select"]]
        assert "SRS-FIN-001" in names
        assert "SRS-FIN-002" in names

    def test_no_srs_codes_omits_field(self):
        module = {"module_name": "m", "version": "", "cgrf_tier": 1,
                  "execution_role": "AGENT", "compliance_pass": True}
        props = _build_properties(module)
        assert "srs_codes" not in props


# ── TestSyncSmpRegistry ───────────────────────────────────────────────────────

class TestSyncSmpRegistry:
    def test_no_credentials_returns_empty(self, monkeypatch):
        monkeypatch.delenv("NOTION_TOKEN", raising=False)
        monkeypatch.delenv("NOTION_SMP_REGISTRY_DB_ID", raising=False)
        result = sync_smp_registry(modules=[], dry_run=False)
        assert result == []

    def test_dry_run_returns_dry_run_actions(self, monkeypatch):
        monkeypatch.setenv("NOTION_TOKEN", "fake-token")
        monkeypatch.setenv("NOTION_SMP_REGISTRY_DB_ID", "fake-db-id")
        modules = [
            {"module_name": "mod_a", "version": "1.0.0", "cgrf_tier": 1,
             "execution_role": "AGENT", "compliance_pass": True},
        ]
        result = sync_smp_registry(modules=modules, dry_run=True)
        assert len(result) == 1
        assert result[0]["action"] == "dry_run"
        assert result[0]["status"] == "dry_run"

    def test_dry_run_multiple_modules(self, monkeypatch):
        monkeypatch.setenv("NOTION_TOKEN", "t")
        monkeypatch.setenv("NOTION_SMP_REGISTRY_DB_ID", "d")
        modules = [
            {"module_name": "a", "version": "1.0.0", "cgrf_tier": 1,
             "execution_role": "AGENT", "compliance_pass": True},
            {"module_name": "b", "version": "1.0.0", "cgrf_tier": 1,
             "execution_role": "INTEGRATION", "compliance_pass": True},
        ]
        result = sync_smp_registry(modules=modules, dry_run=True)
        assert len(result) == 2
        assert all(r["status"] == "dry_run" for r in result)

    def test_missing_only_token_returns_empty(self, monkeypatch):
        monkeypatch.delenv("NOTION_TOKEN", raising=False)
        monkeypatch.setenv("NOTION_SMP_REGISTRY_DB_ID", "fake-db")
        result = sync_smp_registry(modules=[], dry_run=False)
        assert result == []

    def test_missing_only_db_id_returns_empty(self, monkeypatch):
        monkeypatch.setenv("NOTION_TOKEN", "fake-token")
        monkeypatch.delenv("NOTION_SMP_REGISTRY_DB_ID", raising=False)
        result = sync_smp_registry(modules=[], dry_run=False)
        assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
