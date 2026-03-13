"""Evolution Proposal data models — EP-CODE / EP-RAG / EP-SALES / EP-STALE / EP-GAP.

Each proposal type represents a specific category of evolution action
recommended by the MCA professors and approved/rejected by Government.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "proposals_models"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


class ProposalType(str, Enum):
    """Evolution proposal categories."""

    EP_CODE = "EP-CODE"
    EP_RAG = "EP-RAG"
    EP_SALES = "EP-SALES"
    EP_STALE = "EP-STALE"
    EP_GAP = "EP-GAP"


class ProposalStatus(str, Enum):
    """Proposal lifecycle states."""

    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class RiskLevel(str, Enum):
    """Risk classification from Government CAPS review."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class EvolutionProposal:
    """Base data model for all evolution proposals.

    Fields
    ------
    proposal_id:
        Auto-generated unique identifier (``EP-{type}-{uuid4[:8]}``).
    proposal_type:
        One of the ``ProposalType`` enum values.
    title:
        Short human-readable summary.
    description:
        Detailed description of the proposed change.
    source_professor:
        Name of the professor that generated this proposal.
    target:
        What the proposal acts on (file path, Notion page, plan item, etc.).
    priority:
        Numeric priority (1 = highest).
    status:
        Current lifecycle state.
    risk_level:
        Risk classification from Government review.
    evidence:
        Supporting data — metrics, references, or analysis excerpts.
    tags:
        Free-form tags for categorisation.
    created_at:
        UTC timestamp of creation.
    reviewed_at:
        UTC timestamp of Government review (if any).
    review_reason:
        Justification from Government for approval/rejection.
    """

    proposal_type: ProposalType
    title: str
    description: str
    source_professor: str
    target: str = ""
    priority: int = 5
    status: ProposalStatus = ProposalStatus.DRAFT
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    evidence: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reviewed_at: Optional[str] = None
    review_reason: str = ""
    proposal_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.proposal_id:
            short_uuid = uuid.uuid4().hex[:8]
            self.proposal_id = f"{self.proposal_type.value}-{short_uuid}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to plain dict for JSON output."""
        return {
            "proposal_id": self.proposal_id,
            "proposal_type": self.proposal_type.value,
            "title": self.title,
            "description": self.description,
            "source_professor": self.source_professor,
            "target": self.target,
            "priority": self.priority,
            "status": self.status.value,
            "risk_level": self.risk_level.value,
            "evidence": self.evidence,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "review_reason": self.review_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvolutionProposal:
        """Deserialize from plain dict."""
        return cls(
            proposal_id=data.get("proposal_id", ""),
            proposal_type=ProposalType(data["proposal_type"]),
            title=data["title"],
            description=data.get("description", ""),
            source_professor=data.get("source_professor", "unknown"),
            target=data.get("target", ""),
            priority=data.get("priority", 5),
            status=ProposalStatus(data.get("status", "draft")),
            risk_level=RiskLevel(data.get("risk_level", "UNKNOWN")),
            evidence=data.get("evidence", {}),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            reviewed_at=data.get("reviewed_at"),
            review_reason=data.get("review_reason", ""),
        )

    def approve(self, reason: str = "") -> None:
        """Mark proposal as approved."""
        self.status = ProposalStatus.APPROVED
        self.reviewed_at = datetime.now(timezone.utc).isoformat()
        self.review_reason = reason

    def reject(self, reason: str = "") -> None:
        """Mark proposal as rejected."""
        self.status = ProposalStatus.REJECTED
        self.reviewed_at = datetime.now(timezone.utc).isoformat()
        self.review_reason = reason


def create_code_proposal(
    title: str,
    description: str,
    target: str,
    evidence: Optional[Dict[str, Any]] = None,
    priority: int = 3,
) -> EvolutionProposal:
    """Factory for EP-CODE proposals (codebase pattern improvements)."""
    return EvolutionProposal(
        proposal_type=ProposalType.EP_CODE,
        title=title,
        description=description,
        source_professor="mirror_mca",
        target=target,
        priority=priority,
        evidence=evidence or {},
        tags=["code", "pattern"],
    )


def create_rag_proposal(
    title: str,
    description: str,
    target: str,
    evidence: Optional[Dict[str, Any]] = None,
    priority: int = 4,
) -> EvolutionProposal:
    """Factory for EP-RAG proposals (new RAG content)."""
    return EvolutionProposal(
        proposal_type=ProposalType.EP_RAG,
        title=title,
        description=description,
        source_professor="oracle_mca",
        target=target,
        priority=priority,
        evidence=evidence or {},
        tags=["rag", "documentation"],
    )


def create_sales_proposal(
    title: str,
    description: str,
    target: str,
    evidence: Optional[Dict[str, Any]] = None,
    priority: int = 4,
) -> EvolutionProposal:
    """Factory for EP-SALES proposals (sales document updates)."""
    return EvolutionProposal(
        proposal_type=ProposalType.EP_SALES,
        title=title,
        description=description,
        source_professor="oracle_mca",
        target=target,
        priority=priority,
        evidence=evidence or {},
        tags=["sales", "revenue"],
    )


def create_stale_proposal(
    title: str,
    description: str,
    target: str,
    evidence: Optional[Dict[str, Any]] = None,
    priority: int = 2,
) -> EvolutionProposal:
    """Factory for EP-STALE proposals (stale content flags)."""
    return EvolutionProposal(
        proposal_type=ProposalType.EP_STALE,
        title=title,
        description=description,
        source_professor="mirror_mca",
        target=target,
        priority=priority,
        evidence=evidence or {},
        tags=["stale", "outdated"],
    )


def create_gap_proposal(
    title: str,
    description: str,
    target: str,
    evidence: Optional[Dict[str, Any]] = None,
    priority: int = 3,
) -> EvolutionProposal:
    """Factory for EP-GAP proposals (coverage gap detection)."""
    return EvolutionProposal(
        proposal_type=ProposalType.EP_GAP,
        title=title,
        description=description,
        source_professor="oracle_mca",
        target=target,
        priority=priority,
        evidence=evidence or {},
        tags=["gap", "coverage"],
    )
