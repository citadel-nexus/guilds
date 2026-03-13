"""MCA EvolutionEngine — 7-Phase orchestration for the Evolution Cycle.

Phase 1: Data Collection
Phase 2: Meta Document Loading (MCA-META-001)
Phase 3: Metrics Aggregation
Phase 4: AI Professor Analysis (Mirror, Oracle, Government)
Phase 5: Proposal Generation
Phase 6: SANCTUM Recording
Phase 7: Proposal Execution + Canonical Publisher
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.integrations.roadmap_ir_ingestor import get_roadmap_ir, ingest_roadmap_ir
from src.integrations.roadmap_conflict_router import route_conflicts
from src.mca.metrics_aggregator import MetricsAggregator
from src.mca.professors.prof_government import ProfGovernment
from src.mca.professors.prof_mirror import ProfMirror
from src.mca.professors.prof_oracle import ProfOracle
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
from src.mca.proposals.executor import ProposalExecutor
from src.mca.sanctum.publisher import SanctumPublisher

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "evolution_engine"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)


@dataclass
class EvolutionResult:
    """Result of a full Evolution Cycle run."""

    session_id: str
    timestamp: str
    phases_completed: List[str] = field(default_factory=list)
    metrics_snapshot: Dict[str, Any] = field(default_factory=dict)
    mirror_analysis: Dict[str, Any] = field(default_factory=dict)
    oracle_analysis: Dict[str, Any] = field(default_factory=dict)
    government_review: Dict[str, Any] = field(default_factory=dict)
    proposals: List[Dict[str, Any]] = field(default_factory=list)
    meta_document: Dict[str, Any] = field(default_factory=dict)
    conflict_arbitration: List[Dict[str, Any]] = field(default_factory=list)
    sanctum_record: Dict[str, Any] = field(default_factory=dict)
    execution_summary: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "phases_completed": self.phases_completed,
            "metrics_snapshot": self.metrics_snapshot,
            "mirror_analysis": self.mirror_analysis,
            "oracle_analysis": self.oracle_analysis,
            "government_review": self.government_review,
            "proposals": self.proposals,
            "meta_document": self.meta_document,
            "conflict_arbitration": self.conflict_arbitration,
            "sanctum_record": self.sanctum_record,
            "execution_summary": self.execution_summary,
            "errors": self.errors,
        }


class EvolutionEngine:
    """7-Phase MCA Evolution Cycle orchestrator.

    Usage::

        engine = EvolutionEngine(meta_path="config/mca_meta_001.yaml")
        aggregator = MetricsAggregator()
        aggregator.set_code_metrics(total_files=120, test_count=68)
        result = engine.run(aggregator)
    """

    def __init__(
        self,
        meta_path: Optional[str] = None,
        bedrock_client=None,
        dry_run: bool = False,
    ) -> None:
        self._meta_path = Path(meta_path) if meta_path else None
        self._bedrock_client = bedrock_client
        self._dry_run = dry_run

        self._mirror = ProfMirror(bedrock_client=bedrock_client)
        self._oracle = ProfOracle(bedrock_client=bedrock_client)
        self._government = ProfGovernment(bedrock_client=bedrock_client)

        # MS-6: SANCTUM publisher and proposal executor
        self._sanctum = SanctumPublisher(dry_run=dry_run)
        self._executor = ProposalExecutor(dry_run=dry_run)

        # Populated by Phase 1 when IR is loaded (MS-5)
        self._ir_conflicts: List[Dict[str, Any]] = []
        # Populated by Phase 5 for use in Phase 7
        self._proposals: List[EvolutionProposal] = []

    # ── Main entry point ───────────────────────────────────────────────────
    def run(
        self,
        aggregator: MetricsAggregator,
        *,
        session_id: Optional[str] = None,
        roadmap_ir_path: Optional[str] = None,
    ) -> EvolutionResult:
        """Execute the full 7-Phase Evolution Cycle.

        Parameters
        ----------
        aggregator:
            Pre-configured ``MetricsAggregator`` with code/plan metrics.
        session_id:
            Optional session identifier for tracing.
        roadmap_ir_path:
            Optional path to Roadmap IR JSON for MS-5 integration.

        Returns
        -------
        ``EvolutionResult`` containing all phase outputs.
        """
        sid = session_id or f"evo_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        result = EvolutionResult(
            session_id=sid,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Phase 1: Data Collection
        self._phase_1_collect(result, roadmap_ir_path, aggregator)

        # Phase 2: Meta Document Loading
        self._phase_2_load_meta(result)

        # Phase 3: Metrics Aggregation
        self._phase_3_aggregate(result, aggregator)

        # Phase 4: AI Professor Analysis
        self._phase_4_analyze(result)

        # Phase 5: Proposal Generation
        self._phase_5_propose(result)

        # Phase 6: SANCTUM Recording
        self._phase_6_sanctum(result)

        # Phase 7: Proposal Execution + Canonical Publisher
        self._phase_7_execute_and_publish(result)

        return result

    # ── Phase implementations ──────────────────────────────────────────────
    def _phase_1_collect(
        self,
        result: EvolutionResult,
        roadmap_ir_path: Optional[str],
        aggregator: MetricsAggregator,
    ) -> None:
        """Phase 1: Data Collection — load Roadmap IR via ingestor (MS-5)."""
        logger.info("[Phase 1] Data Collection")
        if roadmap_ir_path:
            ir_path = Path(roadmap_ir_path)
            try:
                # Use structured ingestor instead of raw JSON loading
                ir_metrics = ingest_roadmap_ir(ir_path)
                aggregator.add_roadmap_ir_metrics(ir_metrics)
                logger.info("[Phase 1] Roadmap IR ingested: %s", roadmap_ir_path)

                # Load full IR model for conflict routing in Phase 5
                ir_model = get_roadmap_ir(ir_path)
                self._ir_conflicts = route_conflicts(ir_model)
                if self._ir_conflicts:
                    logger.info(
                        "[Phase 1] %d conflict(s) routed for Government",
                        len(self._ir_conflicts),
                    )
            except FileNotFoundError:
                msg = f"[Phase 1] Roadmap IR file not found: {roadmap_ir_path}"
                logger.warning(msg)
                result.errors.append(msg)
            except (ValueError, OSError) as exc:
                msg = f"[Phase 1] Failed to load Roadmap IR: {exc}"
                logger.error(msg)
                result.errors.append(msg)
        result.phases_completed.append("phase_1_collect")

    def _phase_2_load_meta(self, result: EvolutionResult) -> None:
        """Phase 2: Meta Document Loading — load MCA-META-001."""
        logger.info("[Phase 2] Meta Document Loading")
        if self._meta_path and self._meta_path.exists():
            try:
                import yaml  # type: ignore[import-untyped]
                content = self._meta_path.read_text(encoding="utf-8")
                result.meta_document = yaml.safe_load(content) or {}
                logger.info("[Phase 2] Meta document loaded: %s", self._meta_path)
            except ImportError:
                # Fallback: just store the raw content
                result.meta_document = {"raw": self._meta_path.read_text(encoding="utf-8")}
                logger.warning("[Phase 2] PyYAML not available — stored raw content")
            except Exception as exc:
                msg = f"[Phase 2] Failed to load meta document: {exc}"
                logger.error(msg)
                result.errors.append(msg)
        else:
            logger.info("[Phase 2] No meta document configured — skipping")
        result.phases_completed.append("phase_2_meta")

    def _phase_3_aggregate(
        self, result: EvolutionResult, aggregator: MetricsAggregator
    ) -> None:
        """Phase 3: Metrics Aggregation."""
        logger.info("[Phase 3] Metrics Aggregation")
        result.metrics_snapshot = aggregator.aggregate()
        result.phases_completed.append("phase_3_aggregate")

    def _phase_4_analyze(self, result: EvolutionResult) -> None:
        """Phase 4: AI Professor Analysis — Mirror, Oracle, Government."""
        logger.info("[Phase 4] AI Professor Analysis")
        snapshot = result.metrics_snapshot

        # Mirror analysis
        try:
            result.mirror_analysis = self._mirror.analyze(
                snapshot, session_id=result.session_id
            )
            logger.info("[Phase 4] Mirror analysis complete")
        except Exception as exc:
            msg = f"[Phase 4] Mirror analysis failed: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            result.mirror_analysis = {}

        # Oracle analysis
        try:
            result.oracle_analysis = self._oracle.analyze(
                snapshot, session_id=result.session_id
            )
            logger.info("[Phase 4] Oracle analysis complete")
        except Exception as exc:
            msg = f"[Phase 4] Oracle analysis failed: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            result.oracle_analysis = {}

        result.phases_completed.append("phase_4_analyze")

    def _phase_5_propose(self, result: EvolutionResult) -> None:
        """Phase 5: Proposal Generation + Government CAPS Review (MS-5: + conflicts)."""
        logger.info("[Phase 5] Proposal Generation")

        # Generate proposals from Mirror + Oracle analyses
        proposals = self._generate_proposals(
            result.mirror_analysis, result.oracle_analysis
        )

        # Government CAPS review — now includes IR conflicts (MS-5)
        if proposals or self._ir_conflicts:
            proposal_dicts = [p.to_dict() for p in proposals]
            try:
                gov_result = self._government.analyze(
                    result.metrics_snapshot,
                    proposals=proposal_dicts,
                    conflicts=self._ir_conflicts or None,
                    session_id=result.session_id,
                )
                result.government_review = gov_result

                # Store conflict arbitration results separately
                result.conflict_arbitration = gov_result.get(
                    "conflict_arbitration", []
                )

                # Apply Government decisions
                self._apply_government_decisions(proposals, gov_result)
                logger.info("[Phase 5] Government review complete")
            except Exception as exc:
                msg = f"[Phase 5] Government review failed: {exc}"
                logger.error(msg)
                result.errors.append(msg)

        self._proposals = proposals
        result.proposals = [p.to_dict() for p in proposals]
        result.phases_completed.append("phase_5_propose")

    def _phase_6_sanctum(self, result: EvolutionResult) -> None:
        """Phase 6: SANCTUM Recording — hash-chained decision audit."""
        logger.info("[Phase 6] SANCTUM Recording")
        try:
            self._sanctum.start(session_id=result.session_id)

            self._sanctum.record_phase("metrics_snapshot", result.metrics_snapshot)
            self._sanctum.record_phase("mirror_analysis", result.mirror_analysis)
            self._sanctum.record_phase("oracle_analysis", result.oracle_analysis)
            self._sanctum.record_phase("government_review", result.government_review)
            self._sanctum.record_phase("proposals", {"proposals": result.proposals})

            if result.conflict_arbitration:
                self._sanctum.record_phase(
                    "conflict_arbitration",
                    {"conflicts": result.conflict_arbitration},
                )

            logger.info("[Phase 6] SANCTUM recording in progress (%d entries)",
                        self._sanctum.chain_length)
        except Exception as exc:
            msg = f"[Phase 6] SANCTUM recording failed: {exc}"
            logger.error(msg)
            result.errors.append(msg)

        result.phases_completed.append("phase_6_sanctum")

    def _phase_7_execute_and_publish(self, result: EvolutionResult) -> None:
        """Phase 7: Execute approved proposals + finalize SANCTUM record."""
        logger.info("[Phase 7] Proposal Execution + Canonical Publisher")

        # 7A: Execute approved proposals
        try:
            exec_summary = self._executor.execute_batch(self._proposals)
            result.execution_summary = exec_summary.to_dict()

            # Record execution in SANCTUM
            if self._sanctum.is_started:
                self._sanctum.record_phase(
                    "execution_outcome", result.execution_summary
                )

            logger.info(
                "[Phase 7] Execution: %d executed, %d failed, %d skipped",
                exec_summary.executed, exec_summary.failed, exec_summary.skipped,
            )
        except Exception as exc:
            msg = f"[Phase 7] Proposal execution failed: {exc}"
            logger.error(msg)
            result.errors.append(msg)

        # 7B: Finalize SANCTUM record
        try:
            if self._sanctum.is_started:
                record = self._sanctum.finalize(
                    outcome={"errors": result.errors}
                )
                result.sanctum_record = record.to_dict()
                logger.info("[Phase 7] SANCTUM finalized: %s", record.record_id)
        except Exception as exc:
            msg = f"[Phase 7] SANCTUM finalization failed: {exc}"
            logger.error(msg)
            result.errors.append(msg)

        result.phases_completed.append("phase_7_execute_publish")

    # ── Proposal generation ────────────────────────────────────────────────
    @staticmethod
    def _generate_proposals(
        mirror: Dict[str, Any],
        oracle: Dict[str, Any],
    ) -> List[EvolutionProposal]:
        """Generate proposals from professor analyses."""
        proposals: List[EvolutionProposal] = []

        # From Mirror: code pattern improvements
        for pattern in mirror.get("anti_patterns", []):
            proposals.append(create_code_proposal(
                title=f"Fix anti-pattern: {pattern[:60]}",
                description=pattern,
                target="codebase",
                evidence={"source": "mirror", "anti_pattern": pattern},
            ))

        # From Mirror: coverage gaps
        coverage = mirror.get("plan_coverage", {})
        for feature, info in coverage.items():
            if isinstance(info, dict) and info.get("status") in ("MISSING", "PARTIAL"):
                proposals.append(create_gap_proposal(
                    title=f"Coverage gap: {feature[:60]}",
                    description=f"{feature}: {info.get('status')} — {info.get('notes', '')}",
                    target=feature,
                    evidence={"source": "mirror", "coverage": info},
                ))

        # From Oracle: top improvements
        for imp in oracle.get("top_3_improvements", []):
            title = imp.get("title", "Improvement") if isinstance(imp, dict) else str(imp)
            desc = imp.get("description", "") if isinstance(imp, dict) else ""
            proposals.append(create_rag_proposal(
                title=f"Strategic: {title[:60]}",
                description=desc or title,
                target="documentation",
                evidence={"source": "oracle", "improvement": imp},
            ))

        # From Oracle: stale detection via low doc scores
        doc_strength = oracle.get("product_doc_strength", {})
        for key, val in doc_strength.items():
            if isinstance(val, dict) and val.get("score", 10) < 5:
                proposals.append(create_stale_proposal(
                    title=f"Weak documentation: {key}",
                    description=f"{key} scored {val.get('score')}/10 — {val.get('notes', '')}",
                    target=key,
                    evidence={"source": "oracle", "doc_metric": val},
                ))

        # From Oracle: sales readiness
        health = oracle.get("health_status", {})
        if isinstance(health, dict):
            deploy = health.get("deployment_readiness", {})
            if isinstance(deploy, dict) and deploy.get("score", 10) < 5:
                proposals.append(create_sales_proposal(
                    title="Improve deployment readiness for sales",
                    description=f"Deployment readiness: {deploy.get('score')}/10",
                    target="deployment",
                    evidence={"source": "oracle", "readiness": deploy},
                ))

        return proposals

    @staticmethod
    def _apply_government_decisions(
        proposals: List[EvolutionProposal],
        gov_result: Dict[str, Any],
    ) -> None:
        """Apply Government approval/rejection to proposals."""
        approved_ids = {
            item["id"] for item in gov_result.get("approved", []) if isinstance(item, dict)
        }
        rejected_map = {
            item["id"]: item.get("reason", "")
            for item in gov_result.get("rejected", [])
            if isinstance(item, dict)
        }

        for proposal in proposals:
            if proposal.proposal_id in approved_ids:
                proposal.approve("Approved by Government CAPS review")
            elif proposal.proposal_id in rejected_map:
                proposal.reject(rejected_map[proposal.proposal_id])
            else:
                # Default: mark as pending if not explicitly reviewed
                proposal.status = ProposalStatus.PENDING
