"""Tests for SANCTUM publisher (MS-6).

Covers:
  - Hash chain creation and verification
  - Phase recording
  - Finalization and record structure
  - Dry-run mode
  - Error handling
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.mca.sanctum.publisher import (
    SanctumEntry,
    SanctumPublisher,
    SanctumRecord,
    _compute_hash,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_sanctum"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


class TestComputeHash:
    """Tests for the hash function."""

    def test_deterministic(self) -> None:
        h1 = _compute_hash("genesis", "start", "2026-01-01T00:00:00", {"a": 1})
        h2 = _compute_hash("genesis", "start", "2026-01-01T00:00:00", {"a": 1})
        assert h1 == h2

    def test_different_inputs_different_hash(self) -> None:
        h1 = _compute_hash("genesis", "start", "2026-01-01T00:00:00", {"a": 1})
        h2 = _compute_hash("genesis", "start", "2026-01-01T00:00:00", {"a": 2})
        assert h1 != h2

    def test_hash_is_sha256(self) -> None:
        h = _compute_hash("genesis", "test", "ts", {})
        assert len(h) == 64  # SHA-256 hex digest


class TestSanctumEntry:
    """Tests for SanctumEntry dataclass."""

    def test_to_dict(self) -> None:
        entry = SanctumEntry(
            entry_id="abc123",
            stage="test_stage",
            payload={"key": "value"},
            timestamp="2026-01-01T00:00:00",
            hash="deadbeef",
            previous_hash="genesis",
        )
        d = entry.to_dict()
        assert d["entry_id"] == "abc123"
        assert d["stage"] == "test_stage"
        assert d["payload"] == {"key": "value"}


class TestSanctumPublisher:
    """Tests for SanctumPublisher."""

    def test_start_and_finalize(self) -> None:
        pub = SanctumPublisher(dry_run=True)
        record_id = pub.start("test-session-001")

        assert record_id.startswith("EVO-")
        assert pub.is_started
        assert pub.chain_length == 1  # sanctum.start entry

        record = pub.finalize()
        assert not pub.is_started
        assert record.session_id == "test-session-001"
        assert record.chain_length == 2  # start + finalize
        assert record.verified is True

    def test_record_phases(self) -> None:
        pub = SanctumPublisher(dry_run=True)
        pub.start("session-002")

        pub.record_phase("metrics", {"total_files": 120})
        pub.record_phase("mirror", {"anti_patterns": ["God class"]})
        pub.record_phase("government", {"approved": ["P1"]})

        assert pub.chain_length == 4  # start + 3 phases

        record = pub.finalize()
        assert record.chain_length == 5  # + finalize
        assert record.verified is True

    def test_hash_chain_integrity(self) -> None:
        pub = SanctumPublisher(dry_run=True)
        pub.start("session-003")
        pub.record_phase("phase_a", {"data": "alpha"})
        pub.record_phase("phase_b", {"data": "beta"})

        assert pub.verify_chain() is True

    def test_chain_summary(self) -> None:
        pub = SanctumPublisher(dry_run=True)
        pub.start("session-004")
        pub.record_phase("test", {"x": 1})

        summary = pub.get_chain_summary()
        assert summary["session_id"] == "session-004"
        assert summary["chain_length"] == 2
        assert len(summary["stages"]) == 2
        assert summary["stages"][0]["stage"] == "sanctum.start"

    def test_record_before_start_raises(self) -> None:
        pub = SanctumPublisher(dry_run=True)
        with pytest.raises(RuntimeError, match="not started"):
            pub.record_phase("test", {})

    def test_finalize_before_start_raises(self) -> None:
        pub = SanctumPublisher(dry_run=True)
        with pytest.raises(RuntimeError, match="not started"):
            pub.finalize()

    def test_dry_run_no_file_write(self, tmp_path: Path) -> None:
        pub = SanctumPublisher(sanctum_dir=tmp_path, dry_run=True)
        pub.start("session-dry")
        pub.record_phase("test", {"x": 1})
        record = pub.finalize()

        # Dry run should not create any files
        assert list(tmp_path.iterdir()) == []
        assert record.verified is True

    def test_real_write(self, tmp_path: Path) -> None:
        pub = SanctumPublisher(sanctum_dir=tmp_path, dry_run=False)
        pub.start("session-write")
        pub.record_phase("analysis", {"result": "ok"})
        record = pub.finalize()

        # Should write a file
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".json"

        # Verify file content
        content = json.loads(files[0].read_text(encoding="utf-8"))
        assert content["session_id"] == "session-write"
        assert content["verified"] is True
        assert len(content["entries"]) == 3  # start + analysis + finalize

    def test_finalize_with_outcome(self) -> None:
        pub = SanctumPublisher(dry_run=True)
        pub.start("session-outcome")
        record = pub.finalize(outcome={"status": "success", "errors": []})

        last_entry = record.entries[-1]
        assert last_entry["stage"] == "sanctum.finalize"
        assert last_entry["payload"]["status"] == "success"

    def test_cgrf_metadata(self) -> None:
        from src.mca.sanctum import publisher as mod

        assert mod._MODULE_NAME == "sanctum_publisher"
        assert mod._CGRF_TIER == 1
