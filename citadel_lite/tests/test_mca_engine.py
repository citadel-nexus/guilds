"""Tests for src/mca/evolution_engine.py — EvolutionEngine 7-Phase orchestration."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.mca.evolution_engine import EvolutionEngine, EvolutionResult
from src.mca.metrics_aggregator import (
    MetricsAggregator,
    MetricItem,
    MetricStatus,
    PhaseMetrics,
)


# ── Mock Bedrock helper ────────────────────────────────────────────────────
def _make_mock_bedrock(responses: dict[str, str] | None = None):
    """Create a mock BedrockProfessorClient.

    ``responses`` maps system_prompt substrings to return text.
    """
    mock = MagicMock()
    mock.is_available.return_value = True

    def _invoke(system_prompt="", user_message="", json_mode=False):
        resp = MagicMock()
        resp.success = True
        resp.input_tokens = 50
        resp.output_tokens = 100
        resp.latency_ms = 300.0
        resp.parsed = None

        if responses:
            for key, text in responses.items():
                if key.lower() in system_prompt.lower():
                    resp.content = text
                    return resp
        resp.content = "### Key Findings\n- No findings"
        return resp

    mock.invoke.side_effect = _invoke
    return mock


# Sample professor outputs for mock
MIRROR_MOCK = """\
### Code Patterns
- Repository pattern: Consistent data access

### Anti-Patterns
- Circular import: Between module A and B

### Plan Coverage
- Auth module: MISSING — Not implemented

### Key Findings
- Code duplication in utils

### Recommendations
- Extract shared utilities
"""

ORACLE_MOCK = """\
### Health Status
- overall: YELLOW
- code_quality: 6 — Needs improvement
- test_coverage: 5 — Below target

### Product Doc Strength
- plan_clarity: 7 — Good
- sales_readiness: 3 — Weak documentation

### Top 3 Improvements
1. Test Coverage: Increase to 80%
2. API Docs: Add OpenAPI specs
3. CI Pipeline: Automate builds

### Tier Coverage
- Scout: 50%

### Key Findings
- Revenue blocked by low docs
"""

GOVERNMENT_MOCK = """\
### Approved
- EP-CODE-mock0001: Approved

### Rejected

### Risk Assessment
- EP-CODE-mock0001: LOW — Simple fix

### Conflict Arbitration

### Policy Notes
- All proposals reviewed

### ENUM Tags
- CAPS_APPROVAL_GRANTED
"""


# ── MetricsAggregator tests ───────────────────────────────────────────────
class TestMetricsAggregator:
    def test_cgrf_metadata(self):
        from src.mca import metrics_aggregator
        assert metrics_aggregator._MODULE_NAME == "metrics_aggregator"
        assert metrics_aggregator._CGRF_TIER == 1

    def test_empty_aggregate(self):
        agg = MetricsAggregator()
        snapshot = agg.aggregate()
        assert snapshot["plan_summary"]["total_items"] == 0
        assert snapshot["code_summary"] == {}

    def test_code_metrics(self):
        agg = MetricsAggregator()
        agg.set_code_metrics(total_files=120, total_lines=15000, test_count=68)
        snapshot = agg.aggregate()
        assert snapshot["code_summary"]["total_files"] == 120
        assert snapshot["code_summary"]["test_count"] == 68

    def test_phase_metrics(self):
        agg = MetricsAggregator()
        agg.add_phase(PhaseMetrics(
            phase_id="phase_19",
            name="A2A Protocol",
            items_total=10,
            items_done=10,
            completion_pct=100.0,
        ))
        agg.add_phase(PhaseMetrics(
            phase_id="phase_25",
            name="ZES Agent",
            items_total=5,
            items_done=1,
            completion_pct=20.0,
        ))
        snapshot = agg.aggregate()
        assert snapshot["plan_summary"]["total_phases"] == 2
        assert snapshot["plan_summary"]["phases_done"] == 1
        assert len(snapshot["phase_details"]) == 2

    def test_item_metrics(self):
        agg = MetricsAggregator()
        agg.add_item(MetricItem(item_id="a", name="A", status=MetricStatus.COMPLETE))
        agg.add_item(MetricItem(item_id="b", name="B", status=MetricStatus.IN_PROGRESS))
        agg.add_item(MetricItem(item_id="c", name="C", status=MetricStatus.BLOCKED))
        snapshot = agg.aggregate()
        assert snapshot["plan_summary"]["total_items"] == 3
        assert snapshot["plan_summary"]["items_done"] == 1
        assert snapshot["plan_summary"]["items_blocked"] == 1

    def test_weighted_completion(self):
        agg = MetricsAggregator()
        agg.add_item(MetricItem(item_id="a", name="A", status=MetricStatus.COMPLETE))
        agg.add_item(MetricItem(item_id="b", name="B", status=MetricStatus.NOT_STARTED))
        snapshot = agg.aggregate()
        # (1.0 + 0.0) / 2 * 100 = 50.0
        assert snapshot["plan_summary"]["weighted_completion_pct"] == 50.0

    def test_roadmap_ir_metrics(self):
        agg = MetricsAggregator()
        agg.add_roadmap_ir_metrics({"phase_completion": 75.0})
        snapshot = agg.aggregate()
        assert snapshot["roadmap_ir"]["phase_completion"] == 75.0

    def test_custom_metrics(self):
        agg = MetricsAggregator()
        agg.set_custom("deployment_env", "staging")
        snapshot = agg.aggregate()
        assert snapshot["custom"]["deployment_env"] == "staging"

    def test_metric_status_weights(self):
        assert MetricStatus.NOT_STARTED.weight == 0.0
        assert MetricStatus.IN_PROGRESS.weight == 0.3
        assert MetricStatus.BLOCKED.weight == 0.1
        assert MetricStatus.REVIEW.weight == 0.7
        assert MetricStatus.COMPLETE.weight == 1.0


# ── EvolutionEngine tests ─────────────────────────────────────────────────
class TestEvolutionEngine:
    def test_cgrf_metadata(self):
        from src.mca import evolution_engine
        assert evolution_engine._MODULE_NAME == "evolution_engine"
        assert evolution_engine._CGRF_TIER == 1

    def test_full_cycle_with_mock(self):
        mock = _make_mock_bedrock({
            "mirror": MIRROR_MOCK,
            "oracle": ORACLE_MOCK,
            "government": GOVERNMENT_MOCK,
        })
        engine = EvolutionEngine(bedrock_client=mock)
        agg = MetricsAggregator()
        agg.set_code_metrics(total_files=50, test_count=30)

        result = engine.run(agg, session_id="test-001")

        assert result.session_id == "test-001"
        assert "phase_1_collect" in result.phases_completed
        assert "phase_2_meta" in result.phases_completed
        assert "phase_3_aggregate" in result.phases_completed
        assert "phase_4_analyze" in result.phases_completed
        assert "phase_5_propose" in result.phases_completed
        assert "phase_6_sanctum" in result.phases_completed
        assert "phase_7_execute_publish" in result.phases_completed
        assert len(result.phases_completed) == 7

    def test_proposals_generated_from_mirror(self):
        mock = _make_mock_bedrock({
            "mirror": MIRROR_MOCK,
            "oracle": ORACLE_MOCK,
            "government": GOVERNMENT_MOCK,
        })
        engine = EvolutionEngine(bedrock_client=mock)
        agg = MetricsAggregator()
        result = engine.run(agg)

        # Should have proposals from anti-patterns + coverage gaps + improvements + stale
        assert len(result.proposals) > 0
        types = {p["proposal_type"] for p in result.proposals}
        assert "EP-CODE" in types  # from anti-pattern
        assert "EP-GAP" in types   # from coverage gap

    def test_result_to_dict(self):
        result = EvolutionResult(
            session_id="test",
            timestamp="2026-02-20T00:00:00Z",
        )
        d = result.to_dict()
        assert d["session_id"] == "test"
        assert isinstance(d["proposals"], list)
        assert isinstance(d["errors"], list)

    def test_meta_document_loading(self, tmp_path):
        meta_file = tmp_path / "meta.yaml"
        meta_file.write_text("system:\n  name: test\n", encoding="utf-8")

        mock = _make_mock_bedrock({})
        engine = EvolutionEngine(meta_path=str(meta_file), bedrock_client=mock)
        agg = MetricsAggregator()
        result = engine.run(agg)

        # If pyyaml is available, meta should be parsed
        if result.meta_document:
            assert "system" in result.meta_document or "raw" in result.meta_document

    def test_roadmap_ir_loading(self, tmp_path):
        from datetime import datetime, timezone
        from src.roadmap_ir.types import (
            EvidenceText, RoadmapIR, Source, SourceTypeEnum,
        )

        ir = RoadmapIR(
            schema="citadel.roadmap_ir",
            schema_version="1.0.0",
            generated_at=datetime.now(timezone.utc),
            sources=[Source(
                source_id="src-01",
                type=SourceTypeEnum.markdown,
                label="Test",
                fingerprint="sha256:" + "a" * 64,
                collected_at=datetime.now(timezone.utc),
            )],
            items=[],
        )
        ir_file = tmp_path / "roadmap_ir.json"
        ir_file.write_text(
            ir.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
        )

        mock = _make_mock_bedrock({})
        engine = EvolutionEngine(bedrock_client=mock)
        agg = MetricsAggregator()
        result = engine.run(agg, roadmap_ir_path=str(ir_file))

        assert "roadmap_ir" in result.metrics_snapshot
        assert result.metrics_snapshot["roadmap_ir"]["schema_version"] == "1.0.0"
        assert result.metrics_snapshot["roadmap_ir"]["items_total"] == 0

    def test_missing_roadmap_ir(self):
        mock = _make_mock_bedrock({})
        engine = EvolutionEngine(bedrock_client=mock)
        agg = MetricsAggregator()
        result = engine.run(agg, roadmap_ir_path="/nonexistent/path.json")

        assert any("not found" in e for e in result.errors)
        # Should still complete all phases
        assert len(result.phases_completed) == 7


# ── CLI tests ──────────────────────────────────────────────────────────────
class TestMCACLI:
    def test_cgrf_metadata(self):
        from src.mca import cli
        assert cli._MODULE_NAME == "mca_cli"
        assert cli._CGRF_TIER == 1

    def test_parser_creation(self):
        from src.mca.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["evolve", "--dry-run", "--files", "100"])
        assert args.command == "evolve"
        assert args.dry_run is True
        assert args.files == 100

    def test_parser_defaults(self):
        from src.mca.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["evolve"])
        assert args.meta == "config/mca_meta_001.yaml"
        assert args.roadmap_ir is None
        assert args.dry_run is False
