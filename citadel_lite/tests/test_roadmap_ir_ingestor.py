"""Tests for Roadmap IR Ingestor, Conflict Router, and MCA Mapper (MS-5).

Covers:
  - ingest_roadmap_ir() — structured metric extraction
  - get_roadmap_ir() — full model loading
  - route_conflicts() — conflict conversion and sorting
  - map_revenue_gate_to_zes_tier() — gate-to-tier mapping
  - compute_revenue_gate_coverage() — per-gate completion
  - MetricsAggregator.add_roadmap_ir_metrics() — enhanced integration
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

from src.roadmap_ir.types import (
    Conflict,
    ConflictValue,
    EvidenceText,
    Item,
    ItemKindEnum,
    RevenueGateEnum,
    RoadmapIR,
    Source,
    SourceTypeEnum,
    StatusEnum,
)
from src.integrations.roadmap_ir_ingestor import (
    get_roadmap_ir,
    ingest_roadmap_ir,
)
from src.integrations.roadmap_conflict_router import route_conflicts
from src.integrations.roadmap_to_mca_mapper import (
    compute_revenue_gate_coverage,
    map_revenue_gate_to_zes_tier,
)
from src.mca.metrics_aggregator import MetricsAggregator

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_roadmap_ir_ingestor"
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
    phase: int | None = None,
    confidence: float | None = None,
    **kw,
) -> Item:
    defaults = dict(
        item_id=item_id,
        kind=kind,
        title=f"Item {item_id}",
        status=status,
        revenue_gate=revenue_gate,
        phase=phase,
        confidence=confidence,
        evidence=[_make_evidence()],
    )
    defaults.update(kw)
    return Item(**defaults)


def _build_ir(
    items: List[Item],
    conflicts: list | None = None,
) -> RoadmapIR:
    return RoadmapIR(
        schema="citadel.roadmap_ir",
        schema_version="1.0.0",
        generated_at=_NOW,
        sources=[_make_source()],
        items=items,
        conflicts=conflicts or [],
    )


def _write_ir(ir: RoadmapIR, tmp_dir: Path) -> Path:
    path = tmp_dir / "roadmap_ir.json"
    path.write_text(
        ir.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
    )
    return path


# ---------------------------------------------------------------------------
# Ingestor tests
# ---------------------------------------------------------------------------
class TestIngestor:
    """Tests for ingest_roadmap_ir()."""

    def test_basic_ingestion(self, tmp_path: Path) -> None:
        items = [
            _make_item("phase-01", StatusEnum.done, phase=1, confidence=0.9),
            _make_item("phase-02", StatusEnum.in_progress, phase=1, confidence=0.7),
            _make_item("feat-01", StatusEnum.blocked, ItemKindEnum.feature, phase=2),
            _make_item("task-01", StatusEnum.planned, ItemKindEnum.task),
        ]
        ir = _build_ir(items)
        p = _write_ir(ir, tmp_path)

        result = ingest_roadmap_ir(p)

        assert result["items_total"] == 4
        assert result["items_done"] == 1
        assert result["items_blocked"] == 1
        assert result["items_in_progress"] == 1
        assert result["items_planned"] == 1
        assert result["conflicts_count"] == 0
        assert result["schema_version"] == "1.0.0"
        assert 0 <= result["health_score"] <= 1.0

    def test_avg_confidence(self, tmp_path: Path) -> None:
        items = [
            _make_item("phase-01", confidence=0.8),
            _make_item("phase-02", confidence=0.6),
        ]
        ir = _build_ir(items)
        p = _write_ir(ir, tmp_path)

        result = ingest_roadmap_ir(p)
        assert result["avg_confidence"] == 0.7

    def test_no_confidence(self, tmp_path: Path) -> None:
        items = [_make_item("phase-01")]
        ir = _build_ir(items)
        p = _write_ir(ir, tmp_path)

        result = ingest_roadmap_ir(p)
        assert result["avg_confidence"] == 0.0

    def test_items_by_phase(self, tmp_path: Path) -> None:
        items = [
            _make_item("phase-01", StatusEnum.done, phase=1),
            _make_item("phase-02", StatusEnum.in_progress, phase=1),
            _make_item("feat-01", StatusEnum.blocked, phase=2),
            _make_item("task-01", StatusEnum.planned),  # no phase
        ]
        ir = _build_ir(items)
        p = _write_ir(ir, tmp_path)

        result = ingest_roadmap_ir(p)
        by_phase = result["items_by_phase"]

        assert "1" in by_phase
        assert by_phase["1"]["total"] == 2
        assert by_phase["1"]["done"] == 1
        assert "2" in by_phase
        assert by_phase["2"]["blocked"] == 1
        assert "unassigned" in by_phase

    def test_revenue_gate_coverage(self, tmp_path: Path) -> None:
        items = [
            _make_item("tb-01", StatusEnum.done, revenue_gate=RevenueGateEnum.tradebuilder),
            _make_item("tb-02", StatusEnum.blocked, revenue_gate=RevenueGateEnum.tradebuilder),
        ]
        ir = _build_ir(items)
        p = _write_ir(ir, tmp_path)

        result = ingest_roadmap_ir(p)
        coverage = result["revenue_gate_coverage"]

        assert "tradebuilder" in coverage
        assert coverage["tradebuilder"]["total"] == 2
        assert coverage["tradebuilder"]["done"] == 1
        assert coverage["tradebuilder"]["completion_pct"] == 0.5

    def test_empty_ir(self, tmp_path: Path) -> None:
        ir = _build_ir([])
        p = _write_ir(ir, tmp_path)

        result = ingest_roadmap_ir(p)
        assert result["items_total"] == 0
        assert result["avg_confidence"] == 0.0
        assert result["health_score"] == 1.0

    def test_file_not_found(self, tmp_path: Path) -> None:
        fake = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            ingest_roadmap_ir(fake)

    def test_get_roadmap_ir_model(self, tmp_path: Path) -> None:
        items = [_make_item("phase-01")]
        ir = _build_ir(items)
        p = _write_ir(ir, tmp_path)

        model = get_roadmap_ir(p)
        assert isinstance(model, RoadmapIR)
        assert len(model.items) == 1

    def test_conflicts_count(self, tmp_path: Path) -> None:
        items = [_make_item("phase-01")]
        conflicts = [
            Conflict(
                item_id="phase-01",
                field="status",
                values=[
                    ConflictValue(source_id="src-01", value="done"),
                    ConflictValue(source_id="src-01", value="in_progress"),
                ],
                resolution="first_wins",
                action_hint="Verify manually",
            ),
        ]
        ir = _build_ir(items, conflicts=conflicts)
        p = _write_ir(ir, tmp_path)

        result = ingest_roadmap_ir(p)
        assert result["conflicts_count"] == 1


# ---------------------------------------------------------------------------
# Conflict Router tests
# ---------------------------------------------------------------------------
class TestConflictRouter:
    """Tests for route_conflicts()."""

    def test_empty_conflicts(self) -> None:
        ir = _build_ir([_make_item("phase-01")])
        assert route_conflicts(ir) == []

    def test_basic_routing(self) -> None:
        items = [_make_item("phase-01")]
        conflicts = [
            Conflict(
                item_id="phase-01",
                field="status",
                values=[
                    ConflictValue(source_id="src-01", value="done"),
                    ConflictValue(source_id="src-01", value="in_progress"),
                ],
                resolution="first_wins",
                action_hint="Check manually",
            ),
        ]
        ir = _build_ir(items, conflicts=conflicts)

        result = route_conflicts(ir)
        assert len(result) == 1
        assert result[0]["item_id"] == "phase-01"
        assert result[0]["field"] == "status"
        assert result[0]["severity"] == "HIGH"
        assert len(result[0]["values"]) == 2

    def test_severity_sorting(self) -> None:
        items = [_make_item("phase-01")]
        conflicts = [
            Conflict(
                item_id="phase-01",
                field="title",  # LOW severity
                values=[
                    ConflictValue(source_id="src-01", value="A"),
                    ConflictValue(source_id="src-01", value="B"),
                ],
                resolution="first_wins",
                action_hint="Pick one",
            ),
            Conflict(
                item_id="phase-01",
                field="status",  # HIGH severity
                values=[
                    ConflictValue(source_id="src-01", value="done"),
                    ConflictValue(source_id="src-01", value="blocked"),
                ],
                resolution="first_wins",
                action_hint="Verify",
            ),
            Conflict(
                item_id="phase-01",
                field="readiness",  # MEDIUM severity
                values=[
                    ConflictValue(source_id="src-01", value=0.5),
                    ConflictValue(source_id="src-01", value=0.9),
                ],
                resolution="avg",
                action_hint="Average",
            ),
        ]
        ir = _build_ir(items, conflicts=conflicts)

        result = route_conflicts(ir)
        assert len(result) == 3
        assert result[0]["severity"] == "HIGH"
        assert result[1]["severity"] == "MEDIUM"
        assert result[2]["severity"] == "LOW"


# ---------------------------------------------------------------------------
# MCA Mapper tests
# ---------------------------------------------------------------------------
class TestMCAMapper:
    """Tests for revenue gate mapping."""

    def test_gate_to_zes_tier(self) -> None:
        assert map_revenue_gate_to_zes_tier(RevenueGateEnum.tradebuilder) == "premium"
        assert map_revenue_gate_to_zes_tier(RevenueGateEnum.zes_agent) == "zes_agent"
        assert map_revenue_gate_to_zes_tier(RevenueGateEnum.platform_saas) == "platform"
        assert map_revenue_gate_to_zes_tier(RevenueGateEnum.data_products) == "data"
        assert map_revenue_gate_to_zes_tier(RevenueGateEnum.upsell) == "upsell"
        assert map_revenue_gate_to_zes_tier(RevenueGateEnum.unknown) == "core"

    def test_revenue_gate_coverage(self) -> None:
        items = [
            _make_item("tb-01", StatusEnum.done, revenue_gate=RevenueGateEnum.tradebuilder),
            _make_item("tb-02", StatusEnum.in_progress, revenue_gate=RevenueGateEnum.tradebuilder),
            _make_item("za-01", StatusEnum.done, revenue_gate=RevenueGateEnum.zes_agent),
        ]
        coverage = compute_revenue_gate_coverage(items)

        assert "tradebuilder" in coverage
        assert coverage["tradebuilder"]["total"] == 2
        assert coverage["tradebuilder"]["done"] == 1
        assert coverage["tradebuilder"]["zes_tier"] == "premium"
        assert coverage["tradebuilder"]["completion_pct"] == 0.5

        assert "zes_agent" in coverage
        assert coverage["zes_agent"]["total"] == 1
        assert coverage["zes_agent"]["completion_pct"] == 1.0

    def test_empty_items(self) -> None:
        assert compute_revenue_gate_coverage([]) == {}


# ---------------------------------------------------------------------------
# MetricsAggregator integration tests
# ---------------------------------------------------------------------------
class TestMetricsAggregatorIR:
    """Tests for enhanced add_roadmap_ir_metrics()."""

    def test_ir_metrics_populate_phases(self) -> None:
        agg = MetricsAggregator()
        ir_metrics = {
            "items_total": 10,
            "items_done": 5,
            "items_blocked": 2,
            "items_in_progress": 3,
            "items_planned": 0,
            "conflicts_count": 1,
            "avg_confidence": 0.85,
            "health_score": 0.65,
            "items_by_phase": {
                "1": {"total": 5, "done": 3, "in_progress": 1, "blocked": 1, "planned": 0},
                "2": {"total": 5, "done": 2, "in_progress": 2, "blocked": 1, "planned": 0},
            },
            "revenue_gate_coverage": {},
            "schema_version": "1.0.0",
            "phase_completion": {},
            "warnings": [],
        }
        agg.add_roadmap_ir_metrics(ir_metrics)
        snapshot = agg.aggregate()

        assert "roadmap_ir" in snapshot
        assert snapshot["roadmap_ir"]["items_total"] == 10
        # Phase metrics should be populated
        assert len(snapshot["phase_details"]) == 2
        # Custom metrics should include conflicts
        assert snapshot["custom"]["conflicts_count"] == 1
        assert snapshot["custom"]["avg_confidence"] == 0.85
        assert snapshot["custom"]["health_score"] == 0.65

    def test_code_structure_metrics(self) -> None:
        agg = MetricsAggregator()
        compiler_output = {
            "enums": [{"name": "Status", "members": ["done", "blocked"]}],
            "functions": [{"name": "process", "params": "data: dict"}],
        }
        agg.add_code_structure_metrics(compiler_output)
        snapshot = agg.aggregate()
        assert snapshot["custom"]["code_structure"] == compiler_output
