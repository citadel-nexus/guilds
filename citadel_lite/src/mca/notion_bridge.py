"""
Bridge layer between the MCA pipeline and Notion/Supabase persistence.

Provides:
  - Typed dataclasses for RAG documents, ZES plan context, and sales metrics
  - ``fetch_rag_documents()``  — pull live context from the ZES RAG Notion DB
  - ``build_zes_plan_context()`` — assemble an LLM-ready context snapshot
  - ``detect_coverage_gaps()`` — identify domains/EP-types with thin coverage
  - ``publish_evo_result()``  — write one EVO cycle to both Notion and Supabase

All functions degrade gracefully when Notion/Supabase credentials are absent.

CGRF compliance
---------------
_MODULE_NAME    = "notion_bridge"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.infra.notion_mca_client import (
    create_evo_cycle_page,
    create_rag_draft_page,
    patch_evo_tracker_callout,
    query_rag_database,
    _heading,
    _bullet,
    _paragraph,
    _divider,
)
from src.infra.supabase_mca_mirror import (
    mirror_evo_cycle,
    mirror_proposals,
)

# --------------------------------------------------------------------------- #
# CGRF metadata
# --------------------------------------------------------------------------- #
_MODULE_NAME = "notion_bridge"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Domain / EP-type constants
# --------------------------------------------------------------------------- #

ALL_DOMAINS: Set[str] = {"sales", "marketing", "cs", "product", "ops"}

ALL_EP_TYPES: Set[str] = {
    "new_feature",
    "market_expansion",
    "process_improvement",
    "cost_reduction",
    "risk_mitigation",
}

# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass
class NotionRAGDocument:
    """
    A single document retrieved from the ZES RAG Notion database.

    Attributes
    ----------
    id          : Notion page ID
    title       : Page title
    domain      : e.g. ``"sales"``, ``"marketing"``
    status      : e.g. ``"published"``, ``"draft"``
    tags        : List of tag strings
    last_edited : ISO-8601 timestamp string from Notion
    """

    id: str
    title: str
    domain: str
    status: str
    tags: List[str] = field(default_factory=list)
    last_edited: str = ""

    def is_published(self) -> bool:
        return self.status == "published"


@dataclass
class ZESPlanContext:
    """
    An LLM-ready context snapshot assembled from the ZES RAG database.

    Attributes
    ----------
    documents           : All retrieved RAG documents
    domains_covered     : Unique set of domains present in the DB
    ep_types_covered    : Unique set of EP-types (from document tags)
    domain_doc_counts   : Dict mapping domain → document count
    ep_type_doc_counts  : Dict mapping ep_type → document count
    coverage_gaps       : Domains or EP-types with < ``min_coverage`` docs
    context_text        : Human-readable summary string for LLM injection
    built_at            : UTC timestamp when this context was built
    """

    documents: List[NotionRAGDocument] = field(default_factory=list)
    domains_covered: Set[str] = field(default_factory=set)
    ep_types_covered: Set[str] = field(default_factory=set)
    domain_doc_counts: Dict[str, int] = field(default_factory=dict)
    ep_type_doc_counts: Dict[str, int] = field(default_factory=dict)
    coverage_gaps: List[str] = field(default_factory=list)
    context_text: str = ""
    built_at: str = ""


@dataclass
class SalesEvolutionMetrics:
    """
    Aggregated metrics for one MCA evolution cycle.

    Attributes
    ----------
    cycle_id            : Unique cycle identifier
    event_type          : Triggering event type
    domain              : Primary domain
    health_score        : Float 0–100 domain health score
    proposal_count      : Total proposals generated
    approved_count      : Proposals auto-approved
    rejected_count      : Proposals rejected / deferred
    duration_seconds    : End-to-end pipeline duration
    top_proposals       : Up to 5 highest-priority proposal dicts
    notion_page_id      : Notion page ID if persisted (may be None)
    supabase_row_id     : Supabase row ID if persisted (may be None)
    """

    cycle_id: str
    event_type: str
    domain: str
    health_score: float
    proposal_count: int
    approved_count: int = 0
    rejected_count: int = 0
    duration_seconds: float = 0.0
    top_proposals: List[Dict[str, Any]] = field(default_factory=list)
    notion_page_id: Optional[str] = None
    supabase_row_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# Public API — RAG document fetching
# --------------------------------------------------------------------------- #


def fetch_rag_documents(
    domain_filter: Optional[str] = None,
    status_filter: str = "published",
    page_size: int = 50,
) -> List[NotionRAGDocument]:
    """
    Fetch documents from the ZES RAG Notion database.

    Returns typed ``NotionRAGDocument`` objects.

    Parameters
    ----------
    domain_filter   : Optional domain filter (e.g. ``"sales"``)
    status_filter   : Default ``"published"``; pass ``None`` to fetch all statuses
    page_size       : Max results
    """
    raw = query_rag_database(
        domain_filter=domain_filter,
        status_filter=status_filter,
        page_size=page_size,
    )
    docs: List[NotionRAGDocument] = []
    for item in raw:
        docs.append(
            NotionRAGDocument(
                id=item.get("id", ""),
                title=item.get("title", ""),
                domain=item.get("domain", ""),
                status=item.get("status", ""),
                tags=item.get("tags", []),
                last_edited=item.get("last_edited", ""),
            )
        )
    logger.info("[notion_bridge] Fetched %d RAG documents (domain=%s)", len(docs), domain_filter or "all")
    return docs


# --------------------------------------------------------------------------- #
# Public API — context assembly
# --------------------------------------------------------------------------- #


def build_zes_plan_context(
    domain_filter: Optional[str] = None,
    min_coverage: int = 3,
) -> ZESPlanContext:
    """
    Build an LLM-ready ``ZESPlanContext`` from the ZES RAG Notion database.

    Parameters
    ----------
    domain_filter   : If provided, only fetch docs for this domain
    min_coverage    : Minimum docs per domain/EP-type before flagging as a gap

    The returned ``context_text`` can be injected directly into an LLM system prompt.
    """
    docs = fetch_rag_documents(domain_filter=domain_filter)

    ctx = ZESPlanContext()
    ctx.built_at = datetime.now(timezone.utc).isoformat()
    ctx.documents = docs

    domain_counts: Dict[str, int] = {}
    ep_counts: Dict[str, int] = {}

    for doc in docs:
        d = doc.domain
        if d:
            ctx.domains_covered.add(d)
            domain_counts[d] = domain_counts.get(d, 0) + 1
        for tag in doc.tags:
            if tag in ALL_EP_TYPES:
                ctx.ep_types_covered.add(tag)
                ep_counts[tag] = ep_counts.get(tag, 0) + 1

    ctx.domain_doc_counts = domain_counts
    ctx.ep_type_doc_counts = ep_counts
    ctx.coverage_gaps = detect_coverage_gaps(domain_counts, ep_counts, min_coverage)

    # Build human-readable context text
    lines = [
        f"ZES RAG Context (as of {ctx.built_at[:10]})",
        f"Total documents: {len(docs)}",
        "",
        "Domain coverage:",
    ]
    for dom in sorted(ALL_DOMAINS):
        cnt = domain_counts.get(dom, 0)
        gap_marker = " ⚠ LOW" if cnt < min_coverage else ""
        lines.append(f"  {dom}: {cnt} docs{gap_marker}")

    lines += ["", "EP-type coverage:"]
    for ep in sorted(ALL_EP_TYPES):
        cnt = ep_counts.get(ep, 0)
        gap_marker = " ⚠ LOW" if cnt < min_coverage else ""
        lines.append(f"  {ep}: {cnt} docs{gap_marker}")

    if ctx.coverage_gaps:
        lines += ["", f"Coverage gaps detected ({len(ctx.coverage_gaps)}):"]
        for gap in ctx.coverage_gaps:
            lines.append(f"  - {gap}")

    ctx.context_text = "\n".join(lines)
    return ctx


def detect_coverage_gaps(
    domain_counts: Dict[str, int],
    ep_type_counts: Dict[str, int],
    min_coverage: int = 3,
) -> List[str]:
    """
    Return a list of gap labels where coverage is below ``min_coverage``.

    Format: ``"domain:sales (1 doc)"`` or ``"ep_type:new_feature (0 docs)"``.

    Parameters
    ----------
    domain_counts   : Mapping of domain → document count
    ep_type_counts  : Mapping of EP-type → document count
    min_coverage    : Threshold below which a category is flagged
    """
    gaps: List[str] = []

    for dom in ALL_DOMAINS:
        cnt = domain_counts.get(dom, 0)
        if cnt < min_coverage:
            gaps.append(f"domain:{dom} ({cnt} doc{'s' if cnt != 1 else ''})")

    for ep in ALL_EP_TYPES:
        cnt = ep_type_counts.get(ep, 0)
        if cnt < min_coverage:
            gaps.append(f"ep_type:{ep} ({cnt} doc{'s' if cnt != 1 else ''})")

    return gaps


# --------------------------------------------------------------------------- #
# Public API — publishing results
# --------------------------------------------------------------------------- #


def publish_evo_result(
    metrics: SalesEvolutionMetrics,
    proposals: Optional[List[Dict[str, Any]]] = None,
    raw_payload: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> SalesEvolutionMetrics:
    """
    Write one EVO cycle result to both Notion and Supabase, returning
    the updated ``SalesEvolutionMetrics`` with ``notion_page_id`` and
    ``supabase_row_id`` populated.

    Parameters
    ----------
    metrics     : Populated ``SalesEvolutionMetrics`` dataclass
    proposals   : Full proposal list (for Supabase ``mca_proposals`` table)
    raw_payload : Optional full pipeline output dict (serialised into Notion)
    dry_run     : When True, skip all external API calls

    Execution order:
      1. Create Notion EVO cycle page
      2. Mirror cycle to Supabase ``automation_events``
      3. Bulk-insert proposals into Supabase ``mca_proposals``
    """
    top5 = metrics.top_proposals[:5]

    # 1. Notion page
    notion_page_id = create_evo_cycle_page(
        cycle_id=metrics.cycle_id,
        event_type=metrics.event_type,
        domain=metrics.domain,
        proposal_count=metrics.proposal_count,
        top_proposals=top5,
        health_score=metrics.health_score,
        duration_seconds=metrics.duration_seconds,
        raw_payload=raw_payload,
        dry_run=dry_run,
    )
    metrics.notion_page_id = notion_page_id

    # 2. Supabase cycle row
    supabase_row_id = mirror_evo_cycle(
        cycle_id=metrics.cycle_id,
        event_type=metrics.event_type,
        domain=metrics.domain,
        health_score=metrics.health_score,
        proposal_count=metrics.proposal_count,
        approved_count=metrics.approved_count,
        duration_seconds=metrics.duration_seconds,
        notion_page_id=notion_page_id,
        dry_run=dry_run,
    )
    metrics.supabase_row_id = supabase_row_id

    # 3. Supabase proposals
    all_proposals = proposals or metrics.top_proposals
    if all_proposals:
        inserted = mirror_proposals(
            cycle_id=metrics.cycle_id,
            proposals=all_proposals,
            dry_run=dry_run,
        )
        logger.info("[notion_bridge] Published %d proposals for %s", inserted, metrics.cycle_id)

    logger.info(
        "[notion_bridge] publish_evo_result complete: cycle=%s notion=%s supabase=%s",
        metrics.cycle_id,
        notion_page_id,
        supabase_row_id,
    )
    return metrics


def create_coverage_gap_rag_pages(
    context: ZESPlanContext,
    dry_run: bool = False,
) -> List[str]:
    """
    Auto-create draft RAG pages in Notion for each detected coverage gap.

    One page is created per gap with placeholder content blocks.

    Parameters
    ----------
    context : A ``ZESPlanContext`` (from ``build_zes_plan_context()``)
    dry_run : When True, skip API calls

    Returns list of created Notion page IDs.
    """
    created_ids: List[str] = []

    for gap in context.coverage_gaps:
        # Parse gap label  "domain:sales (1 docs)" → domain=sales, label=sales
        if gap.startswith("domain:"):
            raw = gap[len("domain:"):]
            label = raw.split(" ")[0]
            domain = label
            ep_tag: Optional[str] = None
            title = f"[AUTO] {label} — Domain Coverage Placeholder"
            tags = [domain]
        elif gap.startswith("ep_type:"):
            raw = gap[len("ep_type:"):]
            label = raw.split(" ")[0]
            domain = "general"
            ep_tag = label
            title = f"[AUTO] {label} — EP-Type Coverage Placeholder"
            tags = [ep_tag]
        else:
            continue

        content_blocks = [
            _heading(2, f"Coverage Gap: {gap}"),
            _paragraph(
                f"This placeholder page was auto-generated by notion_bridge on "
                f"{context.built_at[:10]} to flag a coverage gap in the ZES RAG database."
            ),
            _divider(),
            _bullet(f"Gap: {gap}"),
            _bullet("Status: Needs human review and content"),
            _bullet("Action: Fill in domain-specific RAG content and set status → published"),
        ]

        page_id = create_rag_draft_page(
            title=title,
            domain=domain,
            content_blocks=content_blocks,
            tags=tags,
            dry_run=dry_run,
        )
        if page_id:
            created_ids.append(page_id)

    logger.info("[notion_bridge] Created %d gap placeholder pages", len(created_ids))
    return created_ids
