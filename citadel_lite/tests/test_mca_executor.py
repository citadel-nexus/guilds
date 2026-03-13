"""Tests for MCA Proposal Executor (MS-6).

Covers:
  - Batch execution of approved proposals
  - Dry-run mode
  - Skipping non-approved proposals
  - All 5 proposal types
  - Real file write mode
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.mca.proposals.executor import ExecutionResult, ExecutionSummary, ProposalExecutor
from src.mca.proposals.models import (
    EvolutionProposal,
    ProposalStatus,
    ProposalType,
    create_code_proposal,
    create_gap_proposal,
    create_rag_proposal,
    create_sales_proposal,
    create_stale_proposal,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "test_mca_executor"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


def _make_approved_proposals() -> list[EvolutionProposal]:
    """Create a set of approved proposals for testing."""
    proposals = [
        create_code_proposal("Fix anti-pattern", "Refactor God class", "app.py"),
        create_rag_proposal("Add RAG doc", "New documentation", "docs/"),
        create_sales_proposal("Sales template", "New sales deck", "sales/"),
        create_stale_proposal("Mark stale", "Outdated content", "old_page"),
        create_gap_proposal("Coverage gap", "Missing tests", "tests/"),
    ]
    for p in proposals:
        p.approve("Approved by Government")
    return proposals


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_to_dict(self) -> None:
        r = ExecutionResult(
            proposal_id="EP-CODE-abc12345",
            proposal_type="EP-CODE",
            status="executed",
            message="Done",
        )
        d = r.to_dict()
        assert d["proposal_id"] == "EP-CODE-abc12345"
        assert d["status"] == "executed"


class TestProposalExecutorDryRun:
    """Tests for executor in dry_run mode."""

    def test_dry_run_batch(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        proposals = _make_approved_proposals()

        summary = executor.execute_batch(proposals)

        assert summary.total == 5
        assert summary.executed == 5
        assert summary.failed == 0
        assert summary.skipped == 0
        assert summary.dry_run is True

        for r in summary.results:
            assert r["status"] == "dry_run"
            assert "[DRY RUN]" in r["message"]

    def test_dry_run_single_code(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        p = create_code_proposal("Fix bug", "desc", "target.py")
        p.approve("ok")

        result = executor.execute_one(p)
        assert result.status == "dry_run"
        assert "code patch" in result.message.lower()

    def test_dry_run_single_rag(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        p = create_rag_proposal("New doc", "desc", "docs/")
        p.approve("ok")

        result = executor.execute_one(p)
        assert result.status == "dry_run"
        assert "RAG draft" in result.message

    def test_dry_run_single_sales(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        p = create_sales_proposal("Deck", "desc", "sales/")
        p.approve("ok")

        result = executor.execute_one(p)
        assert result.status == "dry_run"
        assert "sales template" in result.message.lower()

    def test_dry_run_single_stale(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        p = create_stale_proposal("Old", "desc", "page")
        p.approve("ok")

        result = executor.execute_one(p)
        assert result.status == "dry_run"
        assert "stale" in result.message.lower()

    def test_dry_run_single_gap(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        p = create_gap_proposal("Gap", "desc", "tests/")
        p.approve("ok")

        result = executor.execute_one(p)
        assert result.status == "dry_run"
        assert "gap report" in result.message.lower()


class TestProposalExecutorSkipping:
    """Tests for skipping non-approved proposals."""

    def test_skip_draft(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        p = create_code_proposal("Draft", "desc", "t")
        # p is DRAFT by default

        result = executor.execute_one(p)
        assert result.status == "skipped"

    def test_skip_rejected(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        p = create_code_proposal("Rejected", "desc", "t")
        p.reject("Not needed")

        result = executor.execute_one(p)
        assert result.status == "skipped"

    def test_skip_pending(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        p = create_code_proposal("Pending", "desc", "t")
        p.status = ProposalStatus.PENDING

        result = executor.execute_one(p)
        assert result.status == "skipped"

    def test_batch_mixed_statuses(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        approved = create_code_proposal("Approved", "desc", "t")
        approved.approve("ok")
        draft = create_code_proposal("Draft", "desc", "t")
        rejected = create_code_proposal("Rejected", "desc", "t")
        rejected.reject("no")

        summary = executor.execute_batch([approved, draft, rejected])
        assert summary.executed == 1
        assert summary.skipped == 2


class TestProposalExecutorRealWrite:
    """Tests for executor in real (non-dry-run) mode."""

    def test_real_write_creates_file(self, tmp_path: Path) -> None:
        executor = ProposalExecutor(dry_run=False, output_dir=tmp_path)
        p = create_code_proposal("Fix", "desc", "target.py")
        p.approve("ok")

        result = executor.execute_one(p)
        assert result.status == "executed"

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".json"

        content = json.loads(files[0].read_text(encoding="utf-8"))
        assert content["action"] == "code_patch"
        assert content["target"] == "target.py"

    def test_real_batch_creates_files(self, tmp_path: Path) -> None:
        executor = ProposalExecutor(dry_run=False, output_dir=tmp_path)
        proposals = _make_approved_proposals()

        summary = executor.execute_batch(proposals)
        assert summary.executed == 5

        files = list(tmp_path.iterdir())
        assert len(files) == 5

    def test_proposal_status_updated(self) -> None:
        executor = ProposalExecutor(dry_run=True)
        p = create_code_proposal("Fix", "desc", "t")
        p.approve("ok")

        executor.execute_one(p)
        assert p.status == ProposalStatus.EXECUTED


class TestExecutorCGRF:
    """CGRF metadata tests."""

    def test_cgrf_metadata(self) -> None:
        from src.mca.proposals import executor as mod

        assert mod._MODULE_NAME == "proposals_executor"
        assert mod._CGRF_TIER == 1
