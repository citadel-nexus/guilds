"""Tests for src/mca/proposals/models.py — Evolution Proposal data models."""

import pytest

from src.mca.proposals.models import (
    EvolutionProposal,
    ProposalStatus,
    ProposalType,
    RiskLevel,
    create_code_proposal,
    create_gap_proposal,
    create_rag_proposal,
    create_sales_proposal,
    create_stale_proposal,
)


# ── CGRF Tier 1 check ─────────────────────────────────────────────────────
class TestCGRFMetadata:
    def test_module_metadata(self):
        from src.mca.proposals import models
        assert models._MODULE_NAME == "proposals_models"
        assert models._MODULE_VERSION == "1.0.0"
        assert models._CGRF_TIER == 1


# ── Enum tests ─────────────────────────────────────────────────────────────
class TestEnums:
    def test_proposal_types(self):
        assert ProposalType.EP_CODE.value == "EP-CODE"
        assert ProposalType.EP_RAG.value == "EP-RAG"
        assert ProposalType.EP_SALES.value == "EP-SALES"
        assert ProposalType.EP_STALE.value == "EP-STALE"
        assert ProposalType.EP_GAP.value == "EP-GAP"

    def test_proposal_status(self):
        assert ProposalStatus.DRAFT.value == "draft"
        assert ProposalStatus.APPROVED.value == "approved"
        assert ProposalStatus.REJECTED.value == "rejected"
        assert ProposalStatus.EXECUTED.value == "executed"

    def test_risk_levels(self):
        assert RiskLevel.LOW.value == "LOW"
        assert RiskLevel.CRITICAL.value == "CRITICAL"


# ── EvolutionProposal tests ───────────────────────────────────────────────
class TestEvolutionProposal:
    def test_auto_id_generation(self):
        p = EvolutionProposal(
            proposal_type=ProposalType.EP_CODE,
            title="Test",
            description="A test proposal",
            source_professor="mirror_mca",
        )
        assert p.proposal_id.startswith("EP-CODE-")
        assert len(p.proposal_id) == len("EP-CODE-") + 8

    def test_explicit_id(self):
        p = EvolutionProposal(
            proposal_type=ProposalType.EP_RAG,
            title="Test",
            description="",
            source_professor="oracle_mca",
            proposal_id="EP-RAG-custom01",
        )
        assert p.proposal_id == "EP-RAG-custom01"

    def test_default_status(self):
        p = EvolutionProposal(
            proposal_type=ProposalType.EP_CODE,
            title="Test",
            description="",
            source_professor="mirror_mca",
        )
        assert p.status == ProposalStatus.DRAFT

    def test_to_dict(self):
        p = EvolutionProposal(
            proposal_type=ProposalType.EP_GAP,
            title="Coverage gap",
            description="Missing feature X",
            source_professor="oracle_mca",
            target="feature_x",
            priority=2,
        )
        d = p.to_dict()
        assert d["proposal_type"] == "EP-GAP"
        assert d["title"] == "Coverage gap"
        assert d["target"] == "feature_x"
        assert d["priority"] == 2
        assert d["status"] == "draft"

    def test_from_dict_roundtrip(self):
        original = EvolutionProposal(
            proposal_type=ProposalType.EP_SALES,
            title="Sales doc update",
            description="Update pricing page",
            source_professor="oracle_mca",
            tags=["sales", "pricing"],
        )
        d = original.to_dict()
        restored = EvolutionProposal.from_dict(d)
        assert restored.proposal_id == original.proposal_id
        assert restored.proposal_type == original.proposal_type
        assert restored.tags == original.tags

    def test_approve(self):
        p = create_code_proposal("Fix", "Fix something", "src/foo.py")
        p.approve("Looks good")
        assert p.status == ProposalStatus.APPROVED
        assert p.review_reason == "Looks good"
        assert p.reviewed_at is not None

    def test_reject(self):
        p = create_rag_proposal("New doc", "Add docs", "docs/api.md")
        p.reject("Insufficient evidence")
        assert p.status == ProposalStatus.REJECTED
        assert p.review_reason == "Insufficient evidence"


# ── Factory tests ──────────────────────────────────────────────────────────
class TestFactories:
    def test_create_code_proposal(self):
        p = create_code_proposal("Fix pattern", "Fix duplication", "src/utils.py")
        assert p.proposal_type == ProposalType.EP_CODE
        assert p.source_professor == "mirror_mca"
        assert "code" in p.tags

    def test_create_rag_proposal(self):
        p = create_rag_proposal("New RAG", "Add content", "notion/page")
        assert p.proposal_type == ProposalType.EP_RAG
        assert p.source_professor == "oracle_mca"

    def test_create_sales_proposal(self):
        p = create_sales_proposal("Update pricing", "Refresh pricing", "sales/pricing")
        assert p.proposal_type == ProposalType.EP_SALES

    def test_create_stale_proposal(self):
        p = create_stale_proposal("Stale doc", "Outdated", "docs/old.md")
        assert p.proposal_type == ProposalType.EP_STALE
        assert p.priority == 2  # Higher priority for stale

    def test_create_gap_proposal(self):
        p = create_gap_proposal("Missing auth", "No auth module", "auth")
        assert p.proposal_type == ProposalType.EP_GAP
        assert "gap" in p.tags
