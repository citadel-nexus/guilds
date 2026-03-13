"""
Tests for src/infra/notion_mca_client.py — MS-7 Phase 1-A

All tests use unittest.mock to avoid real Notion API calls.
ENV vars are never set in tests; all credential-gated paths are covered via dry_run.
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from src.infra.notion_mca_client import (
    _rt,
    _heading,
    _bullet,
    _numbered,
    _code_block,
    _divider,
    _callout,
    _paragraph,
    _score_to_grade,
    _grade_to_callout_color,
    _grade_to_emoji,
    _extract_title,
    _extract_select,
    _extract_multi_select,
    create_evo_cycle_page,
    patch_evo_tracker_callout,
    query_rag_database,
    create_rag_draft_page,
    update_rag_page_status,
)


# ============================================================
# Block builders
# ============================================================

class TestBlockBuilders:
    def test_rt_plain(self):
        rt = _rt("hello")
        assert rt["type"] == "text"
        assert rt["text"]["content"] == "hello"
        assert rt["annotations"]["bold"] is False

    def test_rt_bold(self):
        rt = _rt("world", bold=True)
        assert rt["annotations"]["bold"] is True

    def test_heading_level(self):
        h2 = _heading(2, "Section")
        assert h2["type"] == "heading_2"
        assert h2["heading_2"]["rich_text"][0]["text"]["content"] == "Section"

    def test_heading_clamps_level(self):
        # Level 5 → heading_3
        h = _heading(5, "X")
        assert h["type"] == "heading_3"

    def test_bullet_block(self):
        b = _bullet("item")
        assert b["type"] == "bulleted_list_item"
        assert b["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "item"

    def test_numbered_block(self):
        n = _numbered("first")
        assert n["type"] == "numbered_list_item"

    def test_code_block_default_language(self):
        cb = _code_block('{"key": "val"}')
        assert cb["type"] == "code"
        assert cb["code"]["language"] == "json"

    def test_divider(self):
        d = _divider()
        assert d["type"] == "divider"

    def test_callout_has_emoji(self):
        c = _callout("test", emoji="📊")
        assert c["type"] == "callout"
        assert c["callout"]["icon"]["emoji"] == "📊"

    def test_paragraph(self):
        p = _paragraph("text")
        assert p["type"] == "paragraph"


# ============================================================
# Grade / score helpers
# ============================================================

class TestGradeHelpers:
    @pytest.mark.parametrize("score,expected", [
        (95, "S"), (80, "A"), (65, "B"), (50, "C"), (30, "D"),
        (90, "S"), (75, "A"), (60, "B"), (45, "C"), (0, "D"),
    ])
    def test_score_to_grade(self, score, expected):
        assert _score_to_grade(score) == expected

    def test_grade_to_callout_color_s(self):
        assert _grade_to_callout_color("S") == "green_background"

    def test_grade_to_callout_color_d(self):
        assert _grade_to_callout_color("D") == "red_background"

    def test_grade_to_emoji_a(self):
        assert _grade_to_emoji("A") == "✅"


# ============================================================
# Property extractors
# ============================================================

class TestPropertyExtractors:
    def test_extract_title(self):
        props = {"title": {"title": [{"plain_text": "My Title"}]}}
        assert _extract_title(props) == "My Title"

    def test_extract_title_missing(self):
        assert _extract_title({}) == ""

    def test_extract_select(self):
        props = {"domain": {"select": {"name": "sales"}}}
        assert _extract_select(props, "domain") == "sales"

    def test_extract_select_missing(self):
        assert _extract_select({}, "domain") == ""

    def test_extract_multi_select(self):
        props = {"tags": {"multi_select": [{"name": "abc"}, {"name": "def"}]}}
        tags = _extract_multi_select(props, "tags")
        assert tags == ["abc", "def"]


# ============================================================
# create_evo_cycle_page — dry_run
# ============================================================

class TestCreateEvoCyclePage:
    def test_dry_run_returns_placeholder_id(self):
        page_id = create_evo_cycle_page(
            cycle_id="evo-test-001",
            event_type="market_expansion",
            domain="sales",
            proposal_count=5,
            top_proposals=[
                {"title": "Proposal A", "priority": "P1", "ep_type": "new_feature"}
            ],
            health_score=82.5,
            duration_seconds=12.3,
            dry_run=True,
        )
        assert page_id == "dry-run-page-id"

    def test_no_token_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove NOTION_TOKEN and NOTION_EVO_TRACKER_PAGE_ID
            os.environ.pop("NOTION_TOKEN", None)
            page_id = create_evo_cycle_page(
                cycle_id="evo-test-002",
                event_type="market_expansion",
                domain="sales",
                proposal_count=0,
                top_proposals=[],
                health_score=50.0,
                duration_seconds=5.0,
                dry_run=False,
            )
        assert page_id is None

    def test_api_call_made_when_configured(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "abc-page-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("src.infra.notion_mca_client._token", return_value="tok"), \
             patch("src.infra.notion_mca_client._evo_tracker_id", return_value="parent-123"), \
             patch("requests.post", return_value=mock_response) as mock_post:
            page_id = create_evo_cycle_page(
                cycle_id="evo-test-003",
                event_type="test",
                domain="ops",
                proposal_count=2,
                top_proposals=[],
                health_score=70.0,
                duration_seconds=8.0,
            )

        assert page_id == "abc-page-123"
        assert mock_post.called


# ============================================================
# patch_evo_tracker_callout
# ============================================================

class TestPatchEvoTrackerCallout:
    def test_no_token_returns_false(self):
        with patch("src.infra.notion_mca_client._token", return_value=None):
            result = patch_evo_tracker_callout(
                page_id="some-id",
                cycle_id="evo-001",
                health_score=70.0,
                status="approved",
            )
        assert result is False

    def test_api_patch_called(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"object": "list"}
        mock_response.raise_for_status = MagicMock()

        with patch("src.infra.notion_mca_client._token", return_value="tok"), \
             patch("requests.patch", return_value=mock_response) as mock_patch:
            result = patch_evo_tracker_callout(
                page_id="page-xyz",
                cycle_id="evo-001",
                health_score=88.0,
                status="approved",
                note="test note",
            )
        assert result is True
        assert mock_patch.called


# ============================================================
# query_rag_database
# ============================================================

class TestQueryRagDatabase:
    def test_no_token_returns_empty(self):
        with patch("src.infra.notion_mca_client._token", return_value=None):
            result = query_rag_database()
        assert result == []

    def test_no_db_id_returns_empty(self):
        with patch("src.infra.notion_mca_client._token", return_value="tok"), \
             patch("src.infra.notion_mca_client._rag_db_id", return_value=None):
            result = query_rag_database()
        assert result == []

    def test_returns_parsed_docs(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "doc-001",
                    "last_edited_time": "2026-02-25T00:00:00.000Z",
                    "properties": {
                        "title": {"title": [{"plain_text": "RAG Doc 1"}]},
                        "domain": {"select": {"name": "sales"}},
                        "status": {"select": {"name": "published"}},
                        "tags": {"multi_select": [{"name": "new_feature"}]},
                    },
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("src.infra.notion_mca_client._token", return_value="tok"), \
             patch("src.infra.notion_mca_client._rag_db_id", return_value="db-123"), \
             patch("requests.post", return_value=mock_response):
            result = query_rag_database(domain_filter="sales")

        assert len(result) == 1
        assert result[0]["title"] == "RAG Doc 1"
        assert result[0]["domain"] == "sales"
        assert "new_feature" in result[0]["tags"]


# ============================================================
# create_rag_draft_page
# ============================================================

class TestCreateRagDraftPage:
    def test_dry_run_returns_placeholder(self):
        page_id = create_rag_draft_page(
            title="Test Draft",
            domain="sales",
            content_blocks=[_paragraph("Hello")],
            tags=["new_feature"],
            dry_run=True,
        )
        assert page_id == "dry-run-rag-id"

    def test_no_token_returns_none(self):
        with patch("src.infra.notion_mca_client._token", return_value=None):
            result = create_rag_draft_page("t", "d", [], dry_run=False)
        assert result is None


# ============================================================
# update_rag_page_status
# ============================================================

class TestUpdateRagPageStatus:
    def test_no_token_returns_false(self):
        with patch("src.infra.notion_mca_client._token", return_value=None):
            result = update_rag_page_status("page-id", "published")
        assert result is False

    def test_patch_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "page-id"}
        mock_response.raise_for_status = MagicMock()

        with patch("src.infra.notion_mca_client._token", return_value="tok"), \
             patch("requests.patch", return_value=mock_response):
            result = update_rag_page_status("page-id", "published")

        assert result is True
