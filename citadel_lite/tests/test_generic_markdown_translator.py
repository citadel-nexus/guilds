"""Tests for src/roadmap_translator/translators/generic_markdown.py — MS-8."""

from __future__ import annotations

import pytest

from src.roadmap_ir.types import ItemKindEnum, StatusEnum, VerifyEnum
from src.roadmap_translator.translators.generic_markdown import (
    GenericMarkdownTranslator,
    _detect_status,
    _clean_title,
)


# ---------------------------------------------------------------------------
# Sample documents
# ---------------------------------------------------------------------------

SAMPLE_HEADINGS = """\
# Top Level Title

## Feature A ✅
Some description.

### Sub-feature TODO
Details here.

## Feature B blocked
Another section.

## Feature C WIP
In progress.

## Feature D
No status marker.
""".splitlines(keepends=False)

SAMPLE_LISTS = """\
## Tasks

1. ✅ Completed task
2. TODO Pending task
3. blocked Blocked task
4. Regular task
""".splitlines(keepends=False)

SAMPLE_BULLETS = """\
## Requirements

- ✅ Done requirement
- TODO Planned requirement
- blocked Dependency missing
""".splitlines(keepends=False)

SAMPLE_EMPTY = "".splitlines(keepends=False)

SAMPLE_HIERARCHY = """\
## Parent Section

### Child Heading ✅
""".splitlines(keepends=False)

SAMPLE_PHASE = """\
## Phase 5: Monitoring ✅
""".splitlines(keepends=False)

SAMPLE_VERIFY = """\
## Auth tests passing ✅
""".splitlines(keepends=False)


# ---------------------------------------------------------------------------
# Unit: _detect_status
# ---------------------------------------------------------------------------

class TestDetectStatus:
    def test_checkmark_is_done(self):
        status, reason = _detect_status("✅ Completed")
        assert status == StatusEnum.done
        assert reason is None

    def test_todo_is_planned(self):
        status, _ = _detect_status("TODO implement this")
        assert status == StatusEnum.planned

    def test_blocked_keyword(self):
        status, _ = _detect_status("blocked by upstream")
        assert status == StatusEnum.blocked

    def test_wip_is_in_progress(self):
        status, _ = _detect_status("WIP: working on it")
        assert status == StatusEnum.in_progress

    def test_no_marker_is_unknown(self):
        status, reason = _detect_status("just a normal heading")
        assert status == StatusEnum.unknown
        assert reason is not None


# ---------------------------------------------------------------------------
# Unit: _clean_title
# ---------------------------------------------------------------------------

class TestCleanTitle:
    def test_strips_leading_checkmark(self):
        assert _clean_title("✅ My Feature") == "My Feature"

    def test_strips_trailing_checkmark(self):
        assert _clean_title("My Feature ✅") == "My Feature"

    def test_strips_blocked_emoji(self):
        assert _clean_title("🚫 Blocked Feature") == "Blocked Feature"

    def test_passthrough_clean_text(self):
        assert _clean_title("Clean Title") == "Clean Title"


# ---------------------------------------------------------------------------
# Translator: headings
# ---------------------------------------------------------------------------

class TestGenericMarkdownTranslatorHeadings:
    def setup_method(self):
        self.t = GenericMarkdownTranslator()

    def test_extracts_items_from_headings(self):
        patch = self.t.translate(SAMPLE_HEADINGS, "test-src")
        assert len(patch.items) >= 4

    def test_checkmark_heading_is_done(self):
        patch = self.t.translate(SAMPLE_HEADINGS, "test-src")
        feature_a = next(i for i in patch.items if "Feature A" in i.title)
        assert feature_a.status == StatusEnum.done

    def test_todo_heading_is_planned(self):
        patch = self.t.translate(SAMPLE_HEADINGS, "test-src")
        sub = next(i for i in patch.items if "Sub-feature" in i.title)
        assert sub.status == StatusEnum.planned

    def test_blocked_heading(self):
        patch = self.t.translate(SAMPLE_HEADINGS, "test-src")
        b = next(i for i in patch.items if "Feature B" in i.title)
        assert b.status == StatusEnum.blocked

    def test_unknown_heading(self):
        patch = self.t.translate(SAMPLE_HEADINGS, "test-src")
        d = next(i for i in patch.items if "Feature D" in i.title)
        assert d.status == StatusEnum.unknown

    def test_item_id_has_generic_prefix(self):
        patch = self.t.translate(SAMPLE_HEADINGS, "test-src")
        for item in patch.items:
            assert item.item_id.startswith("generic-"), item.item_id

    def test_evidence_present(self):
        patch = self.t.translate(SAMPLE_HEADINGS, "test-src")
        for item in patch.items:
            assert len(item.evidence) >= 1


# ---------------------------------------------------------------------------
# Translator: hierarchy_path
# ---------------------------------------------------------------------------

class TestHierarchyPath:
    def test_child_has_parent_in_hierarchy(self):
        t = GenericMarkdownTranslator()
        patch = t.translate(SAMPLE_HIERARCHY, "hier-src")
        child = next(i for i in patch.items if "Child Heading" in i.title)
        assert child.raw is not None
        assert "Parent Section" in child.raw.get("hierarchy_path", [])

    def test_top_level_has_empty_hierarchy(self):
        t = GenericMarkdownTranslator()
        patch = t.translate(SAMPLE_HIERARCHY, "hier-src")
        parent = next(i for i in patch.items if "Parent Section" in i.title)
        assert parent.raw["hierarchy_path"] == []


# ---------------------------------------------------------------------------
# Translator: empty doc
# ---------------------------------------------------------------------------

class TestEmptyDocument:
    def test_empty_returns_empty_patch(self):
        t = GenericMarkdownTranslator()
        patch = t.translate(SAMPLE_EMPTY, "empty-src")
        assert patch.items == []


# ---------------------------------------------------------------------------
# Translator: phase extraction
# ---------------------------------------------------------------------------

class TestPhaseExtraction:
    def test_phase_extracted_from_heading(self):
        t = GenericMarkdownTranslator()
        patch = t.translate(SAMPLE_PHASE, "phase-src")
        assert len(patch.items) == 1
        assert patch.items[0].phase == 5

    def test_heading_kind_is_feature(self):
        t = GenericMarkdownTranslator()
        patch = t.translate(SAMPLE_HEADINGS, "kind-src")
        heading_items = [i for i in patch.items if i.kind == ItemKindEnum.feature]
        assert len(heading_items) >= 4


# ---------------------------------------------------------------------------
# Translator: verify detection
# ---------------------------------------------------------------------------

class TestVerifyDetection:
    def test_passing_keyword_sets_tested(self):
        t = GenericMarkdownTranslator()
        patch = t.translate(SAMPLE_VERIFY, "verify-src")
        item = patch.items[0]
        assert item.verify_status == VerifyEnum.tested


# ---------------------------------------------------------------------------
# Translator: list items
# ---------------------------------------------------------------------------

class TestListItems:
    def test_numbered_list_items_extracted(self):
        t = GenericMarkdownTranslator()
        patch = t.translate(SAMPLE_LISTS, "list-src")
        list_items = [i for i in patch.items if i.kind == ItemKindEnum.task]
        assert len(list_items) >= 3

    def test_bullet_list_items_extracted(self):
        t = GenericMarkdownTranslator()
        patch = t.translate(SAMPLE_BULLETS, "bullet-src")
        bullet_items = [i for i in patch.items if i.kind == ItemKindEnum.task]
        assert len(bullet_items) >= 2

    def test_list_item_status_done(self):
        t = GenericMarkdownTranslator()
        patch = t.translate(SAMPLE_LISTS, "list-src")
        done_items = [i for i in patch.items if i.status == StatusEnum.done]
        assert len(done_items) >= 1
