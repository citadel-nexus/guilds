"""Tests for the roadmap_ir module — schema, types, and validators.

Covers:
  - Normal-case construction of all models
  - Enum validation
  - Evidence union discrimination
  - JSON Schema round-trip via jsonschema
  - Semantic validators (uniqueness, cycles, dangling refs, etc.)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.roadmap_ir import (
    Blocker,
    Catalog,
    Conflict,
    ConflictValue,
    CommitByDay,
    CommitVelocity,
    EvidenceFileLoc,
    EvidenceGit,
    EvidenceText,
    Item,
    ItemKindEnum,
    Loc,
    Metrics,
    Note,
    NoteLevelEnum,
    Output,
    OutputTypeEnum,
    PhaseCompletion,
    RevenueGateEnum,
    RoadmapIR,
    Source,
    SourceTypeEnum,
    StatusEnum,
    VerifyEnum,
    validate_ir,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_roadmap_ir_schema"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_NOW = datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc)
_FINGERPRINT = "sha256:" + "a" * 64


def _make_source(sid: str = "src-01") -> Source:
    return Source(
        source_id=sid,
        type=SourceTypeEnum.markdown,
        label="Test source",
        fingerprint=_FINGERPRINT,
        collected_at=_NOW,
    )


def _make_evidence_text(sid: str = "src-01") -> EvidenceText:
    return EvidenceText(source_id=sid, text="Some evidence", weight=0.9)


def _make_item(item_id: str = "phase-01", **overrides) -> Item:
    defaults = dict(
        item_id=item_id,
        kind=ItemKindEnum.phase,
        title="Test phase",
        status=StatusEnum.done,
        evidence=[_make_evidence_text()],
    )
    defaults.update(overrides)
    return Item(**defaults)


def _make_ir(**overrides) -> RoadmapIR:
    defaults = dict(
        schema="citadel.roadmap_ir",
        schema_version="1.0.0",
        generated_at=_NOW,
        sources=[_make_source()],
        items=[_make_item()],
    )
    defaults.update(overrides)
    return RoadmapIR(**defaults)


# ===================================================================
# 1. Normal-case model construction
# ===================================================================
class TestModelConstruction:
    def test_minimal_ir(self):
        ir = _make_ir()
        assert ir.schema_ == "citadel.roadmap_ir"
        assert ir.schema_version == "1.0.0"
        assert len(ir.sources) == 1
        assert len(ir.items) == 1

    def test_item_defaults(self):
        item = _make_item()
        assert item.verify_status == VerifyEnum.unknown
        assert item.revenue_gate == RevenueGateEnum.unknown
        assert item.readiness is None
        assert item.tags is None

    def test_catalog_defaults(self):
        cat = Catalog()
        assert len(cat.status_enum) == 5
        assert len(cat.verify_enum) == 4
        assert len(cat.revenue_gates) == 6

    def test_metrics_defaults(self):
        m = Metrics()
        assert m.commit_velocity is None
        assert m.phase_completion is None

    def test_commit_velocity(self):
        cv = CommitVelocity(
            window_days=30,
            commits_total=42,
            commits_by_day=[CommitByDay(date=date(2026, 2, 1), count=5)],
        )
        assert cv.commits_total == 42

    def test_phase_completion(self):
        pc = PhaseCompletion(done=3, in_progress=1, blocked=0, planned=2, unknown=0)
        assert pc.done + pc.in_progress + pc.planned == 6

    def test_blocker(self):
        b = Blocker(text="Needs review", confidence=0.8, evidence_refs=[0])
        assert b.confidence == 0.8

    def test_output(self):
        o = Output(type=OutputTypeEnum.endpoint, value="/api/v1/health")
        assert o.extra is None

    def test_conflict(self):
        c = Conflict(
            item_id="phase-01",
            field="status",
            values=[
                ConflictValue(source_id="src-01", value="done"),
                ConflictValue(source_id="src-02", value="in_progress"),
            ],
            resolution="Chose src-01 (newer)",
            action_hint="Verify with team",
        )
        assert len(c.values) == 2

    def test_note(self):
        n = Note(level=NoteLevelEnum.info, message="All good")
        assert n.source_id is None


# ===================================================================
# 2. Evidence union
# ===================================================================
class TestEvidence:
    def test_file_loc(self):
        ev = EvidenceFileLoc(
            source_id="src-01",
            loc=Loc(path="foo.py", line_start=1, line_end=10),
            weight=0.7,
        )
        assert ev.loc.path == "foo.py"

    def test_git(self):
        ev = EvidenceGit(
            source_id="src-01",
            commit="abcdef1",
            weight=0.6,
        )
        assert ev.commit == "abcdef1"

    def test_text(self):
        ev = _make_evidence_text()
        assert ev.weight == 0.9


# ===================================================================
# 3. Enum validation
# ===================================================================
class TestEnums:
    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            _make_item(status="invalid_status")

    def test_invalid_kind(self):
        with pytest.raises(ValidationError):
            _make_item(kind="unknown_kind")

    def test_all_status_values(self):
        for s in StatusEnum:
            item = _make_item(status=s)
            assert item.status == s


# ===================================================================
# 4. Constraint validation
# ===================================================================
class TestConstraints:
    def test_schema_const(self):
        with pytest.raises(ValidationError, match="schema must be"):
            _make_ir(schema="wrong.schema")

    def test_empty_sources(self):
        with pytest.raises(ValidationError):
            _make_ir(sources=[])

    def test_empty_evidence(self):
        with pytest.raises(ValidationError):
            _make_item(evidence=[])

    def test_readiness_out_of_range(self):
        with pytest.raises(ValidationError):
            _make_item(readiness=1.5)

    def test_item_id_too_short(self):
        with pytest.raises(ValidationError):
            _make_item(item_id="ab")

    def test_bad_fingerprint(self):
        with pytest.raises(ValidationError):
            Source(
                source_id="src-01",
                type=SourceTypeEnum.markdown,
                label="Bad",
                fingerprint="md5:abc",
                collected_at=_NOW,
            )


# ===================================================================
# 5. JSON round-trip
# ===================================================================
class TestJsonRoundTrip:
    def test_serialize_deserialize(self):
        ir = _make_ir()
        data = json.loads(ir.model_dump_json(by_alias=True))
        assert data["schema"] == "citadel.roadmap_ir"
        ir2 = RoadmapIR(**data)
        assert ir2.schema_version == ir.schema_version

    def test_schema_json_loadable(self):
        schema_path = Path(__file__).resolve().parent.parent / "src" / "roadmap_ir" / "schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "Item" in schema["$defs"]


# ===================================================================
# 6. Semantic validators
# ===================================================================
class TestValidators:
    def test_no_issues(self):
        ir = _make_ir()
        notes = validate_ir(ir)
        assert len(notes) == 0

    def test_duplicate_item_id(self):
        ir = _make_ir(items=[_make_item("phase-01"), _make_item("phase-01")])
        notes = validate_ir(ir)
        errors = [n for n in notes if n.level == NoteLevelEnum.error]
        assert any("Duplicate" in n.message for n in errors)

    def test_evidence_with_unknown_status(self):
        item = _make_item(status=StatusEnum.unknown)
        ir = _make_ir(items=[item])
        notes = validate_ir(ir)
        warnings = [n for n in notes if n.level == NoteLevelEnum.warning]
        assert any("unknown" in n.message for n in warnings)

    def test_phase_id_mismatch(self):
        item = _make_item(item_id="feat-auth", phase=1)
        ir = _make_ir(items=[item])
        notes = validate_ir(ir)
        warnings = [n for n in notes if n.level == NoteLevelEnum.warning]
        assert any("phase-" in n.message for n in warnings)

    def test_dangling_source_ref(self):
        bad_ev = EvidenceText(source_id="nonexistent", text="test", weight=0.5)
        item = _make_item(evidence=[bad_ev])
        ir = _make_ir(items=[item])
        notes = validate_ir(ir)
        errors = [n for n in notes if n.level == NoteLevelEnum.error]
        assert any("unknown source_id" in n.message for n in errors)

    def test_dangling_dependency(self):
        item = _make_item(dependencies=["does-not-exist"])
        ir = _make_ir(items=[item])
        notes = validate_ir(ir)
        errors = [n for n in notes if n.level == NoteLevelEnum.error]
        assert any("does not exist" in n.message for n in errors)

    def test_dependency_cycle(self):
        a = _make_item(item_id="item-aaa", dependencies=["item-bbb"])
        b = _make_item(item_id="item-bbb", dependencies=["item-aaa"])
        ir = _make_ir(items=[a, b])
        notes = validate_ir(ir)
        warnings = [n for n in notes if n.level == NoteLevelEnum.warning]
        assert any("cycle" in n.message.lower() for n in warnings)
