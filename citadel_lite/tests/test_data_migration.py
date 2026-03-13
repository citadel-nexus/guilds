# citadel_lite/tests/test_data_migration.py
"""
Tests for Data Migration Tool (Supabase <-> AWS S3 <-> VPS).

Verifies:
- Migration record creation and serialization
- Direction routing via run_migration()
- CLI argument parsing
- Error handling for missing credentials
- Full backup orchestration

CGRF v3.0: SRS-TEST-MIGRATION-001, Tier 1
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

CNWB_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(CNWB_ROOT / "citadel_lite"))

from src.tools.data_migration import (
    MigrationDirection,
    MigrationRecord,
    MIGRATABLE_TABLES,
    S3_PREFIX_MAP,
    S3_BUCKET,
    run_migration,
    _content_hash,
    _migration_id,
    _now,
    supabase_to_s3,
    s3_to_vps,
    vps_to_s3,
    supabase_to_vps,
    vps_to_supabase,
    s3_to_supabase,
    full_backup,
    migration_status,
)


# ============================================================================
# MigrationRecord tests
# ============================================================================

class TestMigrationRecord:
    """Tests for MigrationRecord dataclass."""

    def test_create_record(self):
        record = MigrationRecord(
            migration_id="test-001",
            direction="supabase_to_s3",
            source="supabase:pipeline_runs",
            target="s3://bucket/data/",
            entity_type="pipeline_runs",
            started_at="2026-02-05T00:00:00Z",
        )
        assert record.status == "pending"
        assert record.records_processed == 0
        assert record.errors == []

    def test_to_dict(self):
        record = MigrationRecord(
            migration_id="test-002",
            direction="vps_to_s3",
            source="/srv/data",
            target="s3://bucket/vps/",
            entity_type="assets",
            started_at="2026-02-05T00:00:00Z",
            status="completed",
            records_processed=42,
        )
        d = record.to_dict()
        assert d["migration_id"] == "test-002"
        assert d["status"] == "completed"
        assert d["records_processed"] == 42
        assert isinstance(d, dict)

    def test_record_with_errors(self):
        record = MigrationRecord(
            migration_id="test-003",
            direction="s3_to_supabase",
            source="s3://bucket/data/file.json",
            target="supabase:pipeline_runs",
            entity_type="pipeline_runs",
            started_at="2026-02-05T00:00:00Z",
            status="failed",
            errors=["Connection timeout", "Retry exhausted"],
        )
        assert len(record.errors) == 2
        assert "Connection timeout" in record.errors


# ============================================================================
# Constants tests
# ============================================================================

class TestConstants:
    """Tests for module constants."""

    def test_migratable_tables_populated(self):
        assert len(MIGRATABLE_TABLES) >= 5
        assert "pipeline_runs" in MIGRATABLE_TABLES
        assert "agent_outputs" in MIGRATABLE_TABLES

    def test_s3_prefix_map_matches_tables(self):
        for table in MIGRATABLE_TABLES:
            assert table in S3_PREFIX_MAP, f"Missing S3 prefix for {table}"

    def test_migration_directions(self):
        assert len(MigrationDirection) == 7
        assert MigrationDirection.FULL_BACKUP.value == "full_backup"


# ============================================================================
# Utility function tests
# ============================================================================

class TestUtilities:
    """Tests for utility functions."""

    def test_content_hash_deterministic(self):
        data = b"test data for hashing"
        h1 = _content_hash(data)
        h2 = _content_hash(data)
        assert h1 == h2
        assert len(h1) == 16

    def test_content_hash_different_data(self):
        assert _content_hash(b"hello") != _content_hash(b"world")

    def test_migration_id_format(self):
        mid = _migration_id("sub2s3", "pipeline_runs")
        assert mid.startswith("mig_sub2s3_pipeline_runs_")
        assert len(mid) > 30

    def test_now_returns_iso(self):
        ts = _now()
        assert "T" in ts
        assert ts.endswith("+00:00") or ts.endswith("Z")


# ============================================================================
# run_migration routing tests
# ============================================================================

class TestRunMigration:
    """Tests for the agent-compatible entry point."""

    def test_unknown_direction(self):
        result = run_migration({"direction": "bogus_direction"})
        assert result["status"] == "error"
        assert "Unknown direction" in result["error"]
        assert "valid_directions" in result

    def test_status_direction(self):
        with patch("src.tools.data_migration._aws") as mock_aws, \
             patch("src.tools.data_migration._get_supabase") as mock_sb:
            mock_aws.side_effect = RuntimeError("no aws")
            mock_sb.side_effect = RuntimeError("no supabase")
            result = run_migration({"direction": "status"})
            assert "stores" in result

    @patch("src.tools.data_migration._get_supabase")
    @patch("src.tools.data_migration._aws")
    def test_supabase_to_s3_routing(self, mock_aws, mock_sb):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": 1, "status": "ok"}]
        )
        mock_sb.return_value = mock_client
        mock_aws.return_value = ""

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.tools.data_migration.os.unlink"):
                result = run_migration({
                    "direction": "supabase_to_s3",
                    "table": "pipeline_runs",
                    "limit": 10,
                })

        assert result["direction"] == "supabase_to_s3"

    def test_missing_required_param(self):
        result = run_migration({"direction": "supabase_to_s3"})
        assert result["status"] == "failed"
        assert "error" in result


# ============================================================================
# S3 <-> VPS tests
# ============================================================================

class TestS3VPSMigration:
    """Tests for S3 <-> VPS sync operations."""

    @patch("src.tools.data_migration._aws")
    def test_vps_to_s3_nonexistent_path(self, mock_aws):
        result = vps_to_s3("/nonexistent/path/xyz")
        assert result.status == "failed"
        assert any("does not exist" in e for e in result.errors)

    @patch("src.tools.data_migration._aws")
    def test_vps_to_s3_success(self, mock_aws):
        mock_aws.return_value = ""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file = Path(tmpdir) / "test.json"
            test_file.write_text('{"key": "value"}')

            result = vps_to_s3(tmpdir, s3_prefix="test-sync/")
            assert result.status == "completed"
            assert result.records_processed == 1

    @patch("src.tools.data_migration._aws")
    def test_s3_to_vps_success(self, mock_aws):
        mock_aws.return_value = ""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = s3_to_vps("test-prefix/", local_dir=tmpdir)
            assert result.status == "completed"
            assert result.direction == "s3_to_vps"


# ============================================================================
# VPS <-> Supabase tests
# ============================================================================

class TestVPSSupabaseMigration:
    """Tests for VPS <-> Supabase operations."""

    @patch("src.tools.data_migration._get_supabase")
    def test_supabase_to_vps_success(self, mock_sb):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": 1, "name": "test"}]
        )
        mock_sb.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            result = supabase_to_vps("pipeline_runs", local_dir=tmpdir, limit=10)
            assert result.status == "completed"
            assert result.records_processed == 1
            # Verify file was written
            files = list(Path(tmpdir).glob("*.json"))
            assert len(files) == 1

    @patch("src.tools.data_migration._get_supabase")
    def test_vps_to_supabase_success(self, mock_sb):
        mock_client = MagicMock()
        mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
        mock_sb.return_value = mock_client

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"id": 1, "data": "test"}], f)
            tmp_path = f.name

        try:
            result = vps_to_supabase(tmp_path, "pipeline_runs")
            assert result.status == "completed"
            assert result.records_processed == 1
        finally:
            os.unlink(tmp_path)

    def test_vps_to_supabase_missing_file(self):
        result = vps_to_supabase("/nonexistent/file.json", "pipeline_runs")
        assert result.status == "failed"


# ============================================================================
# Full backup tests
# ============================================================================

class TestFullBackup:
    """Tests for full backup orchestration."""

    @patch("src.tools.data_migration.supabase_to_vps")
    @patch("src.tools.data_migration.supabase_to_s3")
    def test_full_backup_single_table(self, mock_s3, mock_vps):
        mock_s3.return_value = MigrationRecord(
            migration_id="test", direction="supabase_to_s3",
            source="supabase:pipeline_runs", target="s3://bucket/",
            entity_type="pipeline_runs", started_at=_now(),
            status="completed",
        )
        mock_vps.return_value = MigrationRecord(
            migration_id="test2", direction="supabase_to_vps",
            source="supabase:pipeline_runs", target="/srv/",
            entity_type="pipeline_runs", started_at=_now(),
            status="completed",
        )

        result = full_backup(tables=["pipeline_runs"])
        assert result["status"] == "completed"
        assert result["summary"]["successful"] == 1
        assert "pipeline_runs" in result["tables"]

    @patch("src.tools.data_migration.supabase_to_s3")
    def test_full_backup_no_vps(self, mock_s3):
        mock_s3.return_value = MigrationRecord(
            migration_id="test", direction="supabase_to_s3",
            source="supabase:pipeline_runs", target="s3://bucket/",
            entity_type="pipeline_runs", started_at=_now(),
            status="completed",
        )

        result = full_backup(tables=["pipeline_runs"], include_vps=False)
        assert result["status"] == "completed"
        assert "vps" not in result["tables"].get("pipeline_runs", {})


# ============================================================================
# Migration status tests
# ============================================================================

class TestMigrationStatus:
    """Tests for status reporting."""

    @patch("src.tools.data_migration._get_supabase")
    @patch("src.tools.data_migration._aws")
    def test_status_all_unavailable(self, mock_aws, mock_sb):
        mock_aws.side_effect = RuntimeError("no credentials")
        mock_sb.side_effect = RuntimeError("no supabase")

        result = migration_status()
        assert "stores" in result
        assert result["stores"]["s3"]["available"] is False
        assert result["stores"]["supabase"]["available"] is False

    @patch("src.tools.data_migration._get_supabase")
    @patch("src.tools.data_migration._aws")
    def test_status_s3_available(self, mock_aws, mock_sb):
        mock_aws.return_value = [1073741824, 100]  # 1GB, 100 objects
        mock_sb.side_effect = RuntimeError("no supabase")

        result = migration_status()
        assert result["stores"]["s3"]["available"] is True
        assert result["stores"]["s3"]["object_count"] == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
