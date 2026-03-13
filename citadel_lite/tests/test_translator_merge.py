"""Tests for merge logic."""

from __future__ import annotations

import pytest

from src.roadmap_ir.types import (
    EvidenceText,
    Item,
    ItemKindEnum,
    StatusEnum,
    VerifyEnum,
)
from src.roadmap_translator.merge import merge_items

_MODULE_NAME = "test_translator_merge"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


def _ev(sid: str = "s1") -> EvidenceText:
    return EvidenceText(source_id=sid, text="test", weight=0.5)


def _item(item_id: str = "phase-01", status=StatusEnum.done, **kw) -> Item:
    defaults = dict(
        item_id=item_id,
        kind=ItemKindEnum.phase,
        title="Test",
        status=status,
        evidence=[_ev()],
    )
    defaults.update(kw)
    return Item(**defaults)


class TestMerge:
    def test_single_source_passthrough(self):
        items = [_item("phase-01"), _item("phase-02")]
        merged, conflicts = merge_items([("s1", items)])
        assert len(merged) == 2
        assert len(conflicts) == 0

    def test_duplicate_merge(self):
        a = _item("phase-01", status=StatusEnum.done)
        b = _item("phase-01", status=StatusEnum.in_progress)
        merged, conflicts = merge_items([("s1", [a]), ("s2", [b])])
        assert len(merged) == 1
        assert merged[0].status == StatusEnum.done  # done > in_progress

    def test_conflict_generated(self):
        a = _item("phase-01", status=StatusEnum.done)
        b = _item("phase-01", status=StatusEnum.blocked)
        merged, conflicts = merge_items([("s1", [a]), ("s2", [b])])
        assert len(conflicts) == 1
        assert conflicts[0].field == "status"

    def test_evidence_union(self):
        a = _item("phase-01", evidence=[_ev("s1")])
        b = _item("phase-01", evidence=[_ev("s2")])
        merged, _ = merge_items([("s1", [a]), ("s2", [b])])
        assert len(merged[0].evidence) == 2

    def test_title_longest_wins(self):
        a = _item("phase-01", title="Short")
        b = _item("phase-01", title="A much longer descriptive title")
        merged, _ = merge_items([("s1", [a]), ("s2", [b])])
        assert merged[0].title == "A much longer descriptive title"

    def test_verify_highest_wins(self):
        a = _item("phase-01", verify_status=VerifyEnum.unknown)
        b = _item("phase-01", verify_status=VerifyEnum.tested)
        merged, _ = merge_items([("s1", [a]), ("s2", [b])])
        assert merged[0].verify_status == VerifyEnum.tested

    def test_no_conflict_when_same_status(self):
        a = _item("phase-01", status=StatusEnum.done)
        b = _item("phase-01", status=StatusEnum.done)
        merged, conflicts = merge_items([("s1", [a]), ("s2", [b])])
        assert len(conflicts) == 0

    def test_tags_union(self):
        a = _item("phase-01", tags=["a", "b"])
        b = _item("phase-01", tags=["b", "c"])
        merged, _ = merge_items([("s1", [a]), ("s2", [b])])
        assert set(merged[0].tags) == {"a", "b", "c"}
