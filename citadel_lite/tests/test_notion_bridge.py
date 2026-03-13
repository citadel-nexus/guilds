"""
Tests for src/mca/notion_bridge.py — MS-7 Phase 2

Mocks both notion_mca_client and supabase_mca_mirror so no external calls occur.
"""
from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from src.mca.notion_bridge import (
    NotionRAGDocument,
    ZESPlanContext,
    SalesEvolutionMetrics,
    fetch_rag_documents,
    build_zes_plan_context,
    detect_coverage_gaps,
    publish_evo_result,
    create_coverage_gap_rag_pages,
    ALL_DOMAINS,
    ALL_EP_TYPES,
)


# ============================================================
# Dataclasses
# ============================================================

class TestDataclasses:
    def test_notion_rag_document_is_published(self):
        doc = NotionRAGDocument(id="d1", title="T", domain="sales", status="published")
        assert doc.is_published() is True

    def test_notion_rag_document_not_published(self):
        doc = NotionRAGDocument(id="d2", title="T", domain="sales", status="draft")
        assert doc.is_published() is False

    def test_sales_evolution_metrics_defaults(self):
        m = SalesEvolutionMetrics(
            cycle_id="evo-001",
            event_type="market_expansion",
            domain="sales",
            health_score=80.0,
            proposal_count=5,
        )
        assert m.approved_count == 0
        assert m.duration_seconds == 0.0
        assert m.notion_page_id is None
        assert m.supabase_row_id is None

    def test_zes_plan_context_default_empty(self):
        ctx = ZESPlanContext()
        assert ctx.documents == []
        assert ctx.coverage_gaps == []
        assert ctx.context_text == ""


# ============================================================
# detect_coverage_gaps
# ============================================================

class TestDetectCoverageGaps:
    def test_all_covered_returns_empty(self):
        domain_counts = {d: 5 for d in ALL_DOMAINS}
        ep_counts = {e: 5 for e in ALL_EP_TYPES}
        gaps = detect_coverage_gaps(domain_counts, ep_counts, min_coverage=3)
        assert gaps == []

    def test_missing_domain_flagged(self):
        domain_counts = {d: 5 for d in ALL_DOMAINS}
        domain_counts["sales"] = 1  # below threshold
        ep_counts = {e: 5 for e in ALL_EP_TYPES}
        gaps = detect_coverage_gaps(domain_counts, ep_counts, min_coverage=3)
        assert any("domain:sales" in g for g in gaps)

    def test_missing_ep_type_flagged(self):
        domain_counts = {d: 5 for d in ALL_DOMAINS}
        ep_counts = {e: 5 for e in ALL_EP_TYPES}
        ep_counts["new_feature"] = 0
        gaps = detect_coverage_gaps(domain_counts, ep_counts, min_coverage=3)
        assert any("ep_type:new_feature" in g for g in gaps)

    def test_zero_counts_all_flagged(self):
        gaps = detect_coverage_gaps({}, {}, min_coverage=1)
        assert len(gaps) == len(ALL_DOMAINS) + len(ALL_EP_TYPES)

    def test_gap_label_includes_count(self):
        domain_counts = {"sales": 2}
        ep_counts = {}
        gaps = detect_coverage_gaps(domain_counts, ep_counts, min_coverage=3)
        sales_gap = next(g for g in gaps if "domain:sales" in g)
        assert "2 docs" in sales_gap


# ============================================================
# fetch_rag_documents
# ============================================================

class TestFetchRagDocuments:
    def test_returns_typed_documents(self):
        mock_raw = [
            {
                "id": "page-001",
                "title": "Sales RAG Doc",
                "domain": "sales",
                "status": "published",
                "tags": ["new_feature"],
                "last_edited": "2026-02-25T10:00:00Z",
            }
        ]
        with patch("src.mca.notion_bridge.query_rag_database", return_value=mock_raw):
            docs = fetch_rag_documents(domain_filter="sales")

        assert len(docs) == 1
        assert isinstance(docs[0], NotionRAGDocument)
        assert docs[0].title == "Sales RAG Doc"
        assert docs[0].is_published() is True

    def test_empty_db_returns_empty(self):
        with patch("src.mca.notion_bridge.query_rag_database", return_value=[]):
            docs = fetch_rag_documents()
        assert docs == []


# ============================================================
# build_zes_plan_context
# ============================================================

class TestBuildZesPlanContext:
    def _mock_docs(self):
        return [
            {
                "id": f"d{i}", "title": f"Doc {i}",
                "domain": domain, "status": "published",
                "tags": [ep], "last_edited": "",
            }
            for i, (domain, ep) in enumerate(
                [("sales", "new_feature"), ("sales", "market_expansion"),
                 ("marketing", "new_feature"), ("ops", "cost_reduction"),
                 ("sales", "new_feature")]
            )
        ]

    def test_context_has_documents(self):
        with patch("src.mca.notion_bridge.query_rag_database", return_value=self._mock_docs()):
            ctx = build_zes_plan_context()
        assert len(ctx.documents) == 5
        assert isinstance(ctx, ZESPlanContext)

    def test_domain_counts_computed(self):
        with patch("src.mca.notion_bridge.query_rag_database", return_value=self._mock_docs()):
            ctx = build_zes_plan_context()
        assert ctx.domain_doc_counts.get("sales", 0) == 3
        assert ctx.domain_doc_counts.get("marketing", 0) == 1

    def test_coverage_gaps_detected(self):
        with patch("src.mca.notion_bridge.query_rag_database", return_value=self._mock_docs()):
            # With min_coverage=3, only sales has enough docs
            ctx = build_zes_plan_context(min_coverage=3)
        assert any("domain:marketing" in g for g in ctx.coverage_gaps)

    def test_context_text_non_empty(self):
        with patch("src.mca.notion_bridge.query_rag_database", return_value=self._mock_docs()):
            ctx = build_zes_plan_context()
        assert "ZES RAG Context" in ctx.context_text
        assert "sales" in ctx.context_text

    def test_built_at_populated(self):
        with patch("src.mca.notion_bridge.query_rag_database", return_value=[]):
            ctx = build_zes_plan_context()
        assert ctx.built_at != ""


# ============================================================
# publish_evo_result
# ============================================================

class TestPublishEvoResult:
    def _make_metrics(self) -> SalesEvolutionMetrics:
        return SalesEvolutionMetrics(
            cycle_id="evo-pub-001",
            event_type="market_expansion",
            domain="sales",
            health_score=88.0,
            proposal_count=5,
            approved_count=3,
            duration_seconds=12.0,
            top_proposals=[
                {"title": "P1", "priority": "P1", "ep_type": "new_feature"},
            ],
        )

    def test_dry_run_populates_ids(self):
        metrics = self._make_metrics()
        result = publish_evo_result(metrics, dry_run=True)
        assert result.notion_page_id == "dry-run-page-id"
        assert result.supabase_row_id == "dry-run-row-id"

    def test_no_credentials_ids_none(self):
        with patch("src.mca.notion_bridge.create_evo_cycle_page", return_value=None), \
             patch("src.mca.notion_bridge.mirror_evo_cycle", return_value=None), \
             patch("src.mca.notion_bridge.mirror_proposals", return_value=0):
            metrics = self._make_metrics()
            result = publish_evo_result(metrics)
        assert result.notion_page_id is None
        assert result.supabase_row_id is None

    def test_proposals_mirrored_separately(self):
        extra_proposals = [
            {"title": "EP1", "priority": "P1", "ep_type": "new_feature", "domain": "sales", "status": "pending"},
            {"title": "EP2", "priority": "P2", "ep_type": "market_expansion", "domain": "marketing", "status": "pending"},
        ]
        mirror_mock = MagicMock(return_value=2)
        with patch("src.mca.notion_bridge.create_evo_cycle_page", return_value="page-x"), \
             patch("src.mca.notion_bridge.mirror_evo_cycle", return_value="row-y"), \
             patch("src.mca.notion_bridge.mirror_proposals", mirror_mock):
            metrics = self._make_metrics()
            publish_evo_result(metrics, proposals=extra_proposals)

        mirror_mock.assert_called_once()
        call_args = mirror_mock.call_args
        assert call_args[1]["cycle_id"] == "evo-pub-001"
        assert len(call_args[1]["proposals"]) == 2


# ============================================================
# create_coverage_gap_rag_pages
# ============================================================

class TestCreateCoverageGapRagPages:
    def test_dry_run_creates_pages_for_gaps(self):
        ctx = ZESPlanContext()
        ctx.coverage_gaps = ["domain:sales (1 doc)", "ep_type:new_feature (0 docs)"]
        ctx.built_at = "2026-02-25T00:00:00"

        result = create_coverage_gap_rag_pages(ctx, dry_run=True)
        # dry_run returns "dry-run-rag-id" for each gap
        assert len(result) == 2
        assert all(r == "dry-run-rag-id" for r in result)

    def test_no_gaps_creates_no_pages(self):
        ctx = ZESPlanContext()
        ctx.coverage_gaps = []
        ctx.built_at = "2026-02-25T00:00:00"

        result = create_coverage_gap_rag_pages(ctx, dry_run=True)
        assert result == []
