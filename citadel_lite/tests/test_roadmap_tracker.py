"""Tests for the roadmap Tracker & API (MS-3).

Covers:
  - RoadmapTracker.build_snapshot()
  - RoadmapTracker.get_finance_guild_report()
  - API endpoints: /roadmap/snapshot, /roadmap/finance-guild, /roadmap/health
  - Edge cases: empty items, missing file, oversized file
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

from src.roadmap_ir.types import (
    EvidenceText,
    Item,
    ItemKindEnum,
    PhaseCompletion,
    RevenueGateEnum,
    RoadmapIR,
    Source,
    SourceTypeEnum,
    StatusEnum,
)
from src.roadmap.models import FinancePhase, RoadmapSnapshot
from src.roadmap.tracker import RoadmapTracker

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_roadmap_tracker"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_NOW = datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc)
_FINGERPRINT = "sha256:" + "a" * 64


def _make_source(sid: str = "src-01") -> Source:
    return Source(
        source_id=sid,
        type=SourceTypeEnum.markdown,
        label="Test source",
        fingerprint=_FINGERPRINT,
        collected_at=_NOW,
    )


def _make_evidence(sid: str = "src-01") -> EvidenceText:
    return EvidenceText(source_id=sid, text="evidence", weight=0.9)


def _make_item(
    item_id: str = "phase-01",
    status: StatusEnum = StatusEnum.done,
    kind: ItemKindEnum = ItemKindEnum.phase,
    revenue_gate: RevenueGateEnum = RevenueGateEnum.unknown,
    **kw,
) -> Item:
    defaults = dict(
        item_id=item_id,
        kind=kind,
        title=f"Item {item_id}",
        status=status,
        revenue_gate=revenue_gate,
        evidence=[_make_evidence()],
    )
    defaults.update(kw)
    return Item(**defaults)


def _build_ir(items: List[Item]) -> RoadmapIR:
    return RoadmapIR(
        schema="citadel.roadmap_ir",
        schema_version="1.0.0",
        generated_at=_NOW,
        sources=[_make_source()],
        items=items,
    )


def _write_ir_file(ir: RoadmapIR, tmp_dir: str) -> Path:
    path = Path(tmp_dir) / "roadmap_ir.json"
    path.write_text(
        ir.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
    )
    return path


# ---------------------------------------------------------------------------
# Tracker unit tests
# ---------------------------------------------------------------------------
class TestRoadmapTracker:
    """Unit tests for RoadmapTracker."""

    def test_build_snapshot_basic(self, tmp_path: Path) -> None:
        items = [
            _make_item("phase-01", StatusEnum.done),
            _make_item("phase-02", StatusEnum.done),
            _make_item("feat-01", StatusEnum.in_progress, ItemKindEnum.feature),
            _make_item("feat-02", StatusEnum.blocked, ItemKindEnum.feature),
            _make_item("task-01", StatusEnum.planned, ItemKindEnum.task),
        ]
        ir = _build_ir(items)
        p = _write_ir_file(ir, str(tmp_path))

        tracker = RoadmapTracker(p)
        snap = tracker.build_snapshot()

        assert isinstance(snap, RoadmapSnapshot)
        assert snap.total_items == 5
        assert snap.schema_version == "1.0.0"
        assert snap.phase_completion.done == 2
        assert snap.phase_completion.in_progress == 1
        assert snap.phase_completion.blocked == 1
        assert snap.phase_completion.planned == 1
        assert snap.items_by_status["done"] == 2
        assert snap.items_by_kind["phase"] == 2
        assert snap.items_by_kind["feature"] == 2
        assert snap.items_by_kind["task"] == 1

    def test_health_score_all_done(self, tmp_path: Path) -> None:
        items = [
            _make_item("p-01", StatusEnum.done),
            _make_item("p-02", StatusEnum.done),
        ]
        ir = _build_ir(items)
        p = _write_ir_file(ir, str(tmp_path))

        snap = RoadmapTracker(p).build_snapshot()
        assert snap.health_score == 1.0

    def test_health_score_mixed(self, tmp_path: Path) -> None:
        items = [
            _make_item("p-01", StatusEnum.done),
            _make_item("p-02", StatusEnum.in_progress),
            _make_item("p-03", StatusEnum.blocked),
            _make_item("p-04", StatusEnum.planned),
        ]
        ir = _build_ir(items)
        p = _write_ir_file(ir, str(tmp_path))

        snap = RoadmapTracker(p).build_snapshot()
        # (1*1.0 + 1*0.3) / 4 = 0.325
        assert snap.health_score == 0.325

    def test_health_score_empty(self, tmp_path: Path) -> None:
        ir = _build_ir([])
        p = _write_ir_file(ir, str(tmp_path))

        snap = RoadmapTracker(p).build_snapshot()
        assert snap.health_score == 1.0
        assert snap.total_items == 0

    def test_finance_guild_report(self, tmp_path: Path) -> None:
        items = [
            _make_item("tb-01", StatusEnum.done, revenue_gate=RevenueGateEnum.tradebuilder),
            _make_item("tb-02", StatusEnum.in_progress, revenue_gate=RevenueGateEnum.tradebuilder),
            _make_item("za-01", StatusEnum.done, revenue_gate=RevenueGateEnum.zes_agent),
            _make_item("za-02", StatusEnum.done, revenue_gate=RevenueGateEnum.zes_agent),
            _make_item("za-03", StatusEnum.blocked, revenue_gate=RevenueGateEnum.zes_agent),
        ]
        ir = _build_ir(items)
        p = _write_ir_file(ir, str(tmp_path))

        report = RoadmapTracker(p).get_finance_guild_report()

        assert isinstance(report, list)
        # Two gates with items
        gates = {fp.revenue_gate: fp for fp in report}
        assert RevenueGateEnum.tradebuilder in gates
        assert RevenueGateEnum.zes_agent in gates

        tb = gates[RevenueGateEnum.tradebuilder]
        assert tb.total == 2
        assert tb.done == 1
        assert tb.in_progress == 1
        assert tb.completion_pct == 0.5

        za = gates[RevenueGateEnum.zes_agent]
        assert za.total == 3
        assert za.done == 2
        assert za.blocked == 1
        assert round(za.completion_pct, 4) == round(2 / 3, 4)

    def test_finance_guild_empty(self, tmp_path: Path) -> None:
        ir = _build_ir([])
        p = _write_ir_file(ir, str(tmp_path))

        report = RoadmapTracker(p).get_finance_guild_report()
        assert report == []

    def test_file_not_found(self, tmp_path: Path) -> None:
        fake = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            RoadmapTracker(fake)

    def test_file_too_large(self, tmp_path: Path) -> None:
        # Create a file that exceeds the size limit
        big_file = tmp_path / "big.json"
        # Write just over the limit header to trigger the check
        from src.roadmap.tracker import _MAX_IR_FILE_BYTES

        big_file.write_bytes(b"x" * (_MAX_IR_FILE_BYTES + 1))
        with pytest.raises(ValueError, match="too large"):
            RoadmapTracker(big_file)

    def test_snapshot_warnings_from_validation(self, tmp_path: Path) -> None:
        """Items with dangling dependencies should produce validation warnings."""
        items = [
            _make_item("feat-01", StatusEnum.done, dependencies=["nonexistent-item"]),
        ]
        ir = _build_ir(items)
        p = _write_ir_file(ir, str(tmp_path))

        snap = RoadmapTracker(p).build_snapshot()
        # Validator should catch dangling dependency
        assert any("nonexistent" in w.lower() or "dependency" in w.lower() for w in snap.warnings)


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------
class TestModels:
    """Unit tests for FinancePhase and RoadmapSnapshot models."""

    def test_finance_phase_creation(self) -> None:
        fp = FinancePhase(
            revenue_gate=RevenueGateEnum.tradebuilder,
            total=10,
            done=7,
            in_progress=2,
            blocked=1,
            completion_pct=0.7,
        )
        assert fp.revenue_gate == RevenueGateEnum.tradebuilder
        assert fp.completion_pct == 0.7

    def test_snapshot_serialization(self) -> None:
        snap = RoadmapSnapshot(
            generated_at=_NOW,
            schema_version="1.0.0",
            total_items=5,
            phase_completion=PhaseCompletion(done=3, in_progress=1, blocked=1),
            items_by_status={"done": 3, "in_progress": 1, "blocked": 1},
            items_by_kind={"phase": 2, "feature": 3},
            finance_phases=[],
            health_score=0.76,
        )
        data = json.loads(snap.model_dump_json())
        assert data["total_items"] == 5
        assert data["health_score"] == 0.76
        assert data["phase_completion"]["done"] == 3


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------
class TestRoadmapAPI:
    """Tests for the roadmap FastAPI endpoints."""

    @pytest.fixture()
    def client(self, tmp_path: Path):
        """Create a test client with a valid IR file."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.roadmap.api import create_roadmap_router

        items = [
            _make_item("p-01", StatusEnum.done),
            _make_item("p-02", StatusEnum.in_progress),
            _make_item("f-01", StatusEnum.blocked, ItemKindEnum.feature,
                       revenue_gate=RevenueGateEnum.tradebuilder),
        ]
        ir = _build_ir(items)
        ir_path = _write_ir_file(ir, str(tmp_path))

        test_app = FastAPI()
        test_app.include_router(create_roadmap_router(ir_path))
        return TestClient(test_app)

    @pytest.fixture()
    def client_no_ir(self, tmp_path: Path):
        """Create a test client without an IR file."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.roadmap.api import create_roadmap_router

        missing = tmp_path / "nonexistent.json"
        test_app = FastAPI()
        test_app.include_router(create_roadmap_router(missing))
        return TestClient(test_app)

    def test_snapshot_endpoint(self, client) -> None:
        resp = client.get("/roadmap/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_items"] == 3
        assert data["phase_completion"]["done"] == 1
        assert data["phase_completion"]["in_progress"] == 1
        assert data["phase_completion"]["blocked"] == 1
        assert 0 <= data["health_score"] <= 1.0

    def test_finance_guild_endpoint(self, client) -> None:
        resp = client.get("/roadmap/finance-guild")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should have at least tradebuilder and unknown gates
        gates = {item["revenue_gate"]: item for item in data}
        assert "tradebuilder" in gates
        assert gates["tradebuilder"]["total"] == 1
        assert gates["tradebuilder"]["blocked"] == 1

    def test_health_endpoint(self, client) -> None:
        resp = client.get("/roadmap/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "health_score" in data
        assert data["total_items"] == 3

    def test_health_endpoint_no_ir(self, client_no_ir) -> None:
        resp = client_no_ir.get("/roadmap/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_snapshot_no_ir_returns_503(self, client_no_ir) -> None:
        resp = client_no_ir.get("/roadmap/snapshot")
        assert resp.status_code == 503

    def test_finance_guild_no_ir_returns_503(self, client_no_ir) -> None:
        resp = client_no_ir.get("/roadmap/finance-guild")
        assert resp.status_code == 503
