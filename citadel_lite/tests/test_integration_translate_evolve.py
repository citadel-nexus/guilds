"""E2E Integration Test: Roadmap IR → Ingest → Evolve (MS-5).

Tests the full flow: translate IR file → ingest structured metrics →
run Evolution Engine → verify proposals and conflict arbitration.
Uses mock Bedrock to avoid real LLM calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

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
from src.mca.evolution_engine import EvolutionEngine, EvolutionResult
from src.mca.metrics_aggregator import MetricsAggregator

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_integration_translate_evolve"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_NOW = datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc)
_FINGERPRINT = "sha256:" + "a" * 64

# Mock LLM responses for professors
_MIRROR_RESPONSE = """### Code Patterns
- Factory: ShapeFactory creates objects by type

### Anti-Patterns
- God class: AppController has too many methods

### Plan Coverage
- Authentication: COVERED — Implemented in auth module
- Billing: MISSING — No billing code found

### Key Findings
- Test coverage is low

### Recommendations
- Add billing module
"""

_ORACLE_RESPONSE = """### Health Status
- deployment_readiness: 3/10

### Product Documentation Strength
- API docs: 8/10
- User guide: 3/10

### Top 3 Improvements
1. Improve test coverage
2. Add billing module
3. Enhance documentation
"""

_GOVERNMENT_RESPONSE = """### Approved
- EP-CODE-001: Meets quality standards

### Rejected
- EP-GAP-002: Insufficient evidence

### Risk Assessment
- EP-CODE-001: LOW — Standard code fix

### Conflict Arbitration
- phase-01: Resolved using first_wins strategy

### Policy Notes
- All proposals reviewed under CAPS protocol

### ENUM Tags
- CAPS_COMPLIANCE_CHECK
"""


def _make_source() -> Source:
    return Source(
        source_id="src-01",
        type=SourceTypeEnum.markdown,
        label="Test",
        fingerprint=_FINGERPRINT,
        collected_at=_NOW,
    )


def _make_item(
    item_id: str,
    status: StatusEnum = StatusEnum.done,
    revenue_gate: RevenueGateEnum = RevenueGateEnum.unknown,
    phase: int | None = None,
    confidence: float | None = 0.9,
) -> Item:
    return Item(
        item_id=item_id,
        kind=ItemKindEnum.phase,
        title=f"Item {item_id}",
        status=status,
        revenue_gate=revenue_gate,
        phase=phase,
        confidence=confidence,
        evidence=[EvidenceText(source_id="src-01", text="evidence", weight=0.9)],
    )


def _write_ir(items: List[Item], tmp_dir: Path, conflicts=None) -> Path:
    ir = RoadmapIR(
        schema="citadel.roadmap_ir",
        schema_version="1.0.0",
        generated_at=_NOW,
        sources=[_make_source()],
        items=items,
        conflicts=conflicts or [],
    )
    path = tmp_dir / "roadmap_ir.json"
    path.write_text(ir.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    return path


def _mock_bedrock(responses: dict[str, str]) -> MagicMock:
    """Create a mock Bedrock client that returns different responses."""
    mock = MagicMock()
    mock.is_available.return_value = True

    call_count = {"n": 0}
    ordered_responses = list(responses.values())

    def _invoke(**kwargs):
        resp = MagicMock()
        resp.success = True
        idx = min(call_count["n"], len(ordered_responses) - 1)
        resp.content = ordered_responses[idx]
        resp.input_tokens = 100
        resp.output_tokens = 50
        resp.latency_ms = 200
        resp.parsed = None
        call_count["n"] += 1
        return resp

    mock.invoke.side_effect = _invoke
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestE2ETranslateEvolve:
    """End-to-end: IR → Ingest → Evolve → Verify."""

    def test_full_cycle_with_ir(self, tmp_path: Path) -> None:
        """Full Evolution Cycle with Roadmap IR file."""
        items = [
            _make_item("phase-01", StatusEnum.done, phase=1),
            _make_item("phase-02", StatusEnum.in_progress, phase=1),
            _make_item("feat-01", StatusEnum.blocked, RevenueGateEnum.tradebuilder, phase=2),
            _make_item("task-01", StatusEnum.planned, phase=3),
        ]
        ir_path = _write_ir(items, tmp_path)

        bedrock = _mock_bedrock({
            "mirror": _MIRROR_RESPONSE,
            "oracle": _ORACLE_RESPONSE,
            "government": _GOVERNMENT_RESPONSE,
        })

        engine = EvolutionEngine(bedrock_client=bedrock)
        aggregator = MetricsAggregator()
        aggregator.set_code_metrics(total_files=50, test_count=30)

        result = engine.run(
            aggregator,
            roadmap_ir_path=str(ir_path),
            session_id="test-e2e-001",
        )

        assert isinstance(result, EvolutionResult)
        assert "phase_1_collect" in result.phases_completed
        assert "phase_5_propose" in result.phases_completed
        assert len(result.phases_completed) == 7

        # Verify IR metrics were ingested
        assert "roadmap_ir" in result.metrics_snapshot
        assert result.metrics_snapshot["roadmap_ir"]["items_total"] == 4

        # Verify phase details from IR
        assert len(result.metrics_snapshot["phase_details"]) > 0

    def test_cycle_with_conflicts(self, tmp_path: Path) -> None:
        """Evolution Cycle with IR conflicts passed to Government."""
        items = [_make_item("phase-01", StatusEnum.done)]
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
        ir_path = _write_ir(items, tmp_path, conflicts=conflicts)

        bedrock = _mock_bedrock({
            "mirror": _MIRROR_RESPONSE,
            "oracle": _ORACLE_RESPONSE,
            "government": _GOVERNMENT_RESPONSE,
        })

        engine = EvolutionEngine(bedrock_client=bedrock)
        aggregator = MetricsAggregator()

        result = engine.run(
            aggregator,
            roadmap_ir_path=str(ir_path),
            session_id="test-e2e-002",
        )

        # Verify conflicts were ingested
        assert result.metrics_snapshot["roadmap_ir"]["conflicts_count"] == 1

    def test_cycle_without_ir(self) -> None:
        """Evolution Cycle without Roadmap IR (should still work)."""
        bedrock = _mock_bedrock({
            "mirror": _MIRROR_RESPONSE,
            "oracle": _ORACLE_RESPONSE,
            "government": _GOVERNMENT_RESPONSE,
        })

        engine = EvolutionEngine(bedrock_client=bedrock)
        aggregator = MetricsAggregator()
        aggregator.set_code_metrics(total_files=50, test_count=30)

        result = engine.run(aggregator, session_id="test-e2e-003")

        assert isinstance(result, EvolutionResult)
        assert "phase_1_collect" in result.phases_completed
        assert "roadmap_ir" not in result.metrics_snapshot

    def test_cycle_missing_ir_file(self, tmp_path: Path) -> None:
        """Evolution Cycle with non-existent IR file produces error."""
        fake_path = str(tmp_path / "nonexistent.json")

        bedrock = _mock_bedrock({
            "mirror": _MIRROR_RESPONSE,
            "oracle": _ORACLE_RESPONSE,
            "government": _GOVERNMENT_RESPONSE,
        })

        engine = EvolutionEngine(bedrock_client=bedrock)
        aggregator = MetricsAggregator()

        result = engine.run(
            aggregator,
            roadmap_ir_path=fake_path,
            session_id="test-e2e-004",
        )

        # Should complete but with error
        assert "phase_1_collect" in result.phases_completed
        assert any("not found" in e for e in result.errors)

    def test_result_serialization(self, tmp_path: Path) -> None:
        """EvolutionResult.to_dict() includes conflict_arbitration."""
        items = [_make_item("phase-01")]
        ir_path = _write_ir(items, tmp_path)

        bedrock = _mock_bedrock({
            "mirror": _MIRROR_RESPONSE,
            "oracle": _ORACLE_RESPONSE,
            "government": _GOVERNMENT_RESPONSE,
        })

        engine = EvolutionEngine(bedrock_client=bedrock)
        aggregator = MetricsAggregator()

        result = engine.run(
            aggregator,
            roadmap_ir_path=str(ir_path),
            session_id="test-e2e-005",
        )

        d = result.to_dict()
        assert "conflict_arbitration" in d
        assert "session_id" in d
        assert d["session_id"] == "test-e2e-005"
