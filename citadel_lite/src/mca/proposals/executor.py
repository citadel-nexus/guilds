"""MCA Proposal Executor — applies approved Evolution Proposals.

Dispatches approved proposals by type (EP-CODE, EP-RAG, EP-SALES,
EP-STALE, EP-GAP) to the appropriate execution handler.  Supports
``--dry-run`` mode for preview without side-effects.

Execution handlers:
- EP-RAG:   Create a Notion draft page (or dry-run preview)
- EP-STALE: Mark Notion page as "Needs Update" (or dry-run preview)
- EP-CODE:  Generate local code patch / PR draft (or dry-run preview)
- EP-SALES: Create sales document template (or dry-run preview)
- EP-GAP:   Generate coverage gap report (or dry-run preview)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.mca.proposals.models import (
    EvolutionProposal,
    ProposalStatus,
    ProposalType,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "proposals_executor"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of executing a single proposal."""

    proposal_id: str
    proposal_type: str
    status: str  # "executed" | "failed" | "skipped" | "dry_run"
    message: str = ""
    output: Dict[str, Any] = field(default_factory=dict)
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionSummary:
    """Summary of executing a batch of proposals."""

    total: int = 0
    executed: int = 0
    failed: int = 0
    skipped: int = 0
    dry_run: bool = False
    results: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProposalExecutor:
    """Executes approved MCA Evolution Proposals.

    Usage::

        executor = ProposalExecutor(dry_run=True)
        summary = executor.execute_batch(proposals)
    """

    def __init__(
        self,
        dry_run: bool = True,
        output_dir: Optional[Path] = None,
    ) -> None:
        self._dry_run = dry_run
        self._output_dir = output_dir or Path("out/execution")

        # Handler dispatch map
        self._handlers = {
            ProposalType.EP_CODE: self._execute_code,
            ProposalType.EP_RAG: self._execute_rag,
            ProposalType.EP_SALES: self._execute_sales,
            ProposalType.EP_STALE: self._execute_stale,
            ProposalType.EP_GAP: self._execute_gap,
        }

    @property
    def is_dry_run(self) -> bool:
        return self._dry_run

    def execute_batch(
        self,
        proposals: List[EvolutionProposal],
    ) -> ExecutionSummary:
        """Execute a batch of approved proposals.

        Only proposals with ``status == APPROVED`` are executed.
        Others are skipped with reason.
        """
        summary = ExecutionSummary(
            total=len(proposals),
            dry_run=self._dry_run,
        )

        for proposal in proposals:
            result = self.execute_one(proposal)
            summary.results.append(result.to_dict())

            if result.status == "executed" or result.status == "dry_run":
                summary.executed += 1
            elif result.status == "failed":
                summary.failed += 1
            else:
                summary.skipped += 1

        logger.info(
            "[Executor] Batch complete: %d total, %d executed, %d failed, %d skipped (dry_run=%s)",
            summary.total, summary.executed, summary.failed, summary.skipped,
            self._dry_run,
        )
        return summary

    def execute_one(self, proposal: EvolutionProposal) -> ExecutionResult:
        """Execute a single proposal."""
        # Only execute approved proposals
        if proposal.status != ProposalStatus.APPROVED:
            return ExecutionResult(
                proposal_id=proposal.proposal_id,
                proposal_type=proposal.proposal_type.value,
                status="skipped",
                message=f"Proposal status is '{proposal.status.value}', not 'approved'",
            )

        handler = self._handlers.get(proposal.proposal_type)
        if handler is None:
            return ExecutionResult(
                proposal_id=proposal.proposal_id,
                proposal_type=proposal.proposal_type.value,
                status="failed",
                message=f"No handler for proposal type: {proposal.proposal_type.value}",
            )

        try:
            result = handler(proposal)
            # Update proposal status
            if result.status in ("executed", "dry_run"):
                proposal.status = ProposalStatus.EXECUTED
            elif result.status == "failed":
                proposal.status = ProposalStatus.FAILED
            return result
        except Exception as exc:
            logger.error(
                "[Executor] Failed to execute %s: %s",
                proposal.proposal_id, exc,
            )
            proposal.status = ProposalStatus.FAILED
            return ExecutionResult(
                proposal_id=proposal.proposal_id,
                proposal_type=proposal.proposal_type.value,
                status="failed",
                message=str(exc),
            )

    # -- Type-specific handlers ---------------------------------------------

    def _execute_code(self, proposal: EvolutionProposal) -> ExecutionResult:
        """EP-CODE: Generate code patch or local modification."""
        action = {
            "action": "code_patch",
            "target": proposal.target,
            "description": proposal.description,
            "evidence": proposal.evidence,
        }

        if self._dry_run:
            return ExecutionResult(
                proposal_id=proposal.proposal_id,
                proposal_type=ProposalType.EP_CODE.value,
                status="dry_run",
                message=f"[DRY RUN] Would apply code patch to: {proposal.target}",
                output={"planned_action": action},
            )

        # Real execution: save patch plan to output dir
        output_path = self._save_action(proposal.proposal_id, action)
        return ExecutionResult(
            proposal_id=proposal.proposal_id,
            proposal_type=ProposalType.EP_CODE.value,
            status="executed",
            message=f"Code patch plan saved to: {output_path}",
            output={"action_file": str(output_path), **action},
        )

    def _execute_rag(self, proposal: EvolutionProposal) -> ExecutionResult:
        """EP-RAG: Create RAG draft page (Notion or local)."""
        action = {
            "action": "create_rag_draft",
            "target": proposal.target,
            "title": proposal.title,
            "description": proposal.description,
            "tags": proposal.tags,
        }

        if self._dry_run:
            return ExecutionResult(
                proposal_id=proposal.proposal_id,
                proposal_type=ProposalType.EP_RAG.value,
                status="dry_run",
                message=f"[DRY RUN] Would create RAG draft: {proposal.title}",
                output={"planned_action": action},
            )

        output_path = self._save_action(proposal.proposal_id, action)
        return ExecutionResult(
            proposal_id=proposal.proposal_id,
            proposal_type=ProposalType.EP_RAG.value,
            status="executed",
            message=f"RAG draft action saved to: {output_path}",
            output={"action_file": str(output_path), **action},
        )

    def _execute_sales(self, proposal: EvolutionProposal) -> ExecutionResult:
        """EP-SALES: Create sales document template."""
        action = {
            "action": "create_sales_template",
            "target": proposal.target,
            "title": proposal.title,
            "description": proposal.description,
        }

        if self._dry_run:
            return ExecutionResult(
                proposal_id=proposal.proposal_id,
                proposal_type=ProposalType.EP_SALES.value,
                status="dry_run",
                message=f"[DRY RUN] Would create sales template: {proposal.title}",
                output={"planned_action": action},
            )

        output_path = self._save_action(proposal.proposal_id, action)
        return ExecutionResult(
            proposal_id=proposal.proposal_id,
            proposal_type=ProposalType.EP_SALES.value,
            status="executed",
            message=f"Sales template action saved to: {output_path}",
            output={"action_file": str(output_path), **action},
        )

    def _execute_stale(self, proposal: EvolutionProposal) -> ExecutionResult:
        """EP-STALE: Mark content as needing update."""
        action = {
            "action": "mark_stale",
            "target": proposal.target,
            "reason": proposal.description,
        }

        if self._dry_run:
            return ExecutionResult(
                proposal_id=proposal.proposal_id,
                proposal_type=ProposalType.EP_STALE.value,
                status="dry_run",
                message=f"[DRY RUN] Would mark as stale: {proposal.target}",
                output={"planned_action": action},
            )

        output_path = self._save_action(proposal.proposal_id, action)
        return ExecutionResult(
            proposal_id=proposal.proposal_id,
            proposal_type=ProposalType.EP_STALE.value,
            status="executed",
            message=f"Stale marker action saved to: {output_path}",
            output={"action_file": str(output_path), **action},
        )

    def _execute_gap(self, proposal: EvolutionProposal) -> ExecutionResult:
        """EP-GAP: Generate coverage gap report."""
        action = {
            "action": "generate_gap_report",
            "target": proposal.target,
            "title": proposal.title,
            "description": proposal.description,
            "evidence": proposal.evidence,
        }

        if self._dry_run:
            return ExecutionResult(
                proposal_id=proposal.proposal_id,
                proposal_type=ProposalType.EP_GAP.value,
                status="dry_run",
                message=f"[DRY RUN] Would generate gap report for: {proposal.target}",
                output={"planned_action": action},
            )

        output_path = self._save_action(proposal.proposal_id, action)
        return ExecutionResult(
            proposal_id=proposal.proposal_id,
            proposal_type=ProposalType.EP_GAP.value,
            status="executed",
            message=f"Gap report action saved to: {output_path}",
            output={"action_file": str(output_path), **action},
        )

    # -- Helpers ------------------------------------------------------------

    def _save_action(self, proposal_id: str, action: Dict[str, Any]) -> Path:
        """Save an action plan to the output directory."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{proposal_id}.json"
        filepath = self._output_dir / filename
        with filepath.open("w", encoding="utf-8") as f:
            json.dump(action, f, indent=2, ensure_ascii=False)
        return filepath
