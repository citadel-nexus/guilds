# src/orchestrator_v3.py
"""
Citadel Lite Orchestrator V3 — A2A-aware, memory-enriched, execution-enabled.

Coexists with Kousaki's original orchestrator.py (which remains untouched).
Uses the same types, approval, and audit report modules.

Capabilities:
- A2A handoff protocol (agents registered as message handlers)
- Enhanced agents (v3) with memory-aware diagnosis and variable risk
- Memory recall (injects past incidents before Sherlock)
- Hash-chained audit trail (tamper-evident)
- Execution layer (closes the demo loop: PR creation, CI rerun)
- Reflex dispatch (policy-driven automated responses)
- Telemetry (Application Insights when Azure is configured)

Usage:
    python -m src.orchestrator_v3 demo/events/ci_failed.sample.json
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from src.types import EventJsonV1, EventArtifact, HandoffPacket, Decision

logger = logging.getLogger(__name__)

# Kousaki's modules (unchanged)
from src.audit.report import build_audit_report
from src.approval.request import build_approval_request
from src.approval.response import load_approval_response, build_approval_response_template

# Dmitry's modules
from src.a2a.protocol import A2AProtocol
from src.a2a.agent_wrapper import build_protocol_v2, get_decision_from_packet
from src.audit.logger import AuditLogger
from src.memory.store_v2 import MemoryStore, LocalMemoryStore
from src.execution.runner_V2 import ExecutionRunner
from src.execution.outcome_store import OutcomeStore
from src.reflex.dispatcher import ReflexDispatcher
from src.mike.engine.runner_recursive_soul import run_mike_review_and_remember
from src.github.client import GitHubClient

# AIS (Agent Intelligence System) — Phase 25
try:
    from src.ais.engine import AISEngine
    from src.ais.rewards import RewardEvent
    _AIS_AVAILABLE = True
except ImportError:
    _AIS_AVAILABLE = False

# Monitoring (Phase 26)
try:
    from src.monitoring import metrics as _mon
    _MON_AVAILABLE = True
except ImportError:
    _MON_AVAILABLE = False


# ---- helpers (same as original) ----

def _load_event_json(path: Path) -> EventJsonV1:
    raw = json.loads(path.read_text(encoding="utf-8"))
    artifacts = raw.get("artifacts", {}) or {}
    return EventJsonV1(
        schema_version=raw.get("schema_version", "event_json_v1"),
        event_id=raw.get("event_id") or EventJsonV1().event_id,
        event_type=raw.get("event_type", ""),
        source=raw.get("source", ""),
        occurred_at=raw.get("occurred_at") or EventJsonV1().occurred_at,
        repo=raw.get("repo"),
        ref=raw.get("ref"),
        summary=raw.get("summary"),
        artifacts=EventArtifact(
            log_excerpt=artifacts.get("log_excerpt"),
            links=artifacts.get("links", []),
            extra=artifacts.get("extra", {}),
        ),
    )


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def _load_settings() -> Dict[str, Any]:
    """
    Load settings from config/settings.yaml.
    Returns empty dict if file doesn't exist or YAML not installed.
    """
    settings_path = Path("config/settings.yaml")
    if not settings_path.exists():
        logger.warning(f"Settings file not found: {settings_path}")
        return {}

    if yaml is None:
        logger.warning("PyYAML not installed, using default settings")
        return {}

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        return {}

def _read_verify_payload(base: Path) -> Optional[Dict[str, Any]]:
    """
    Read out/<event_id>/verify_results.json written by execution layer.
    Returns the parsed payload dict or None.
    """
    p = base / "verify_results.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _summarize_verify_payload(payload: Dict[str, Any], max_lines: int = 6) -> str:
    """
    Create a short, deterministic summary string for loop feedback.
    """
    if not payload:
        return ""
    all_success = bool(payload.get("all_success"))
    simulated = bool(payload.get("simulated"))
    results = payload.get("results") or []
    lines: List[str] = []
    lines.append(f"VERIFY all_success={all_success} simulated={simulated} steps={len(results)}")
    # include a few failing steps with stderr hints
    fail_count = 0
    for r in results:
        if not isinstance(r, dict):
            continue
        if bool(r.get("success")):
            continue
        fail_count += 1
        cmd = str(r.get("command", ""))[:140]
        err = str(r.get("stderr", ""))[:180]
        lines.append(f"- FAIL cmd={cmd} err={err}")
        if len(lines) >= max_lines:
            break
    if fail_count == 0 and not all_success:
        lines.append("- FAIL (unknown)")
    return "\n".join(lines)

 
# ---- Orchestrator V3 ----

class OrchestratorV3:
    """
    A2A-aware orchestrator with dependency injection for all subsystems.
    Falls back to sensible defaults for any missing dependency.
    """

    def __init__(
        self,
        protocol: Optional[A2AProtocol] = None,
        memory: Optional[MemoryStore] = None,
        audit: Optional[AuditLogger] = None,
        executor: Optional[ExecutionRunner] = None,
        outcome_store: Optional[OutcomeStore] = None,
        reflex: Optional[ReflexDispatcher] = None,
        github_client: Optional[GitHubClient] = None,
        settings: Optional[Dict[str, Any]] = None,
        ags_pipeline: Optional[Any] = None,
        diagnostics_loop: Optional[Any] = None,
    ) -> None:
        self.protocol = protocol or build_protocol_v2()
        self.memory = memory or LocalMemoryStore()
        self.audit = audit or AuditLogger()
        self.executor = executor or ExecutionRunner()
        self.outcome_store = outcome_store or OutcomeStore()
        self.reflex = reflex or ReflexDispatcher()
        self.github_client = github_client or GitHubClient()
        self.settings = settings if settings is not None else _load_settings()

        # Diagnostics Loop (Blueprint MS-A6)
        diag_enabled = self.settings.get("diagnostics_loop", {}).get("enabled", False)
        self.diagnostics_loop = diagnostics_loop
        if diag_enabled and diagnostics_loop is None:
            try:
                from src.modules.diagnostics_loop import DiagnosticsLoop
                self.diagnostics_loop = DiagnosticsLoop()
            except Exception as e:
                logger.debug("DiagnosticsLoop not available: %s", e)

        # AGS (Agent Governance System) pipeline - Phase 24
        ags_enabled = self.settings.get("ags", {}).get("enabled", True)
        if ags_pipeline is not None:
            self.ags = ags_pipeline
        elif ags_enabled:
            try:
                from src.ags.pipeline import AGSPipeline
                self.ags = AGSPipeline(audit=self.audit)
            except Exception as e:
                logger.debug("AGS pipeline not available: %s", e)
                self.ags = None
        else:
            self.ags = None

        # AIS (Agent Intelligence System) engine - Phase 25
        ais_enabled = self.settings.get("ais", {}).get("enabled", True)
        if ais_enabled and _AIS_AVAILABLE:
            try:
                self.ais_engine: Optional[AISEngine] = AISEngine()
            except Exception as e:
                logger.debug("AIS engine not available: %s", e)
                self.ais_engine = None
        else:
            self.ais_engine = None

    def run(self, event_path: Path) -> None:
        """Run the full pipeline from an event JSON file."""
        event = _load_event_json(event_path)
        self.run_from_event(event)

    def run_from_event(self, event: EventJsonV1) -> None:
        """Run the full pipeline from an EventJsonV1 object."""
        pipeline_start = time.perf_counter()
        if _MON_AVAILABLE:
            _mon.inc_pipelines_in_flight()

        try:
            self._run_from_event_inner(event, pipeline_start)
        finally:
            if _MON_AVAILABLE:
                _mon.dec_pipelines_in_flight()

    def _run_from_event_inner(self, event: EventJsonV1, pipeline_start: float) -> None:
        """Inner pipeline logic (extracted for try/finally gauge safety)."""
        # Reset A2A trace per run (avoid trace accumulation across events)
        if hasattr(self.protocol, "clear_trace"):
            self.protocol.clear_trace()

        # 1. Init packet + audit
        packet = HandoffPacket(event=event)
        span_id = self.audit.start(event.event_id)
        packet.audit_span_id = span_id
        self.audit.log("handoff.start", {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "source": event.source,
        })

        # 2. Memory recall (inject before agents see the packet)
        self._inject_memory(packet)

        # 3. A2A pipeline with short closed-loop on VERIFY failure (max 2 attempts)
        # Attempt 1 includes Sentinel; retries skip Sentinel by default.
        base = Path("out") / event.event_id
        attempts: List[Dict[str, Any]] = []
        max_attempts = int((event.artifacts.extra or {}).get("max_attempts", 2) or 2)
        attempt_no = 1

        decision: Optional[Decision] = None
        reflex_results: list = []
        audit_report: Dict[str, Any] = {}

        while True:
            stages = ["sentinel", "sherlock", "fixer", "guardian"] if attempt_no == 1 else ["sherlock", "fixer", "guardian"]

            packet = self.protocol.pipeline(
                packet,
                stages=stages,
                trace_id=span_id,
            )

            # Log each agent output for this attempt
            for name in stages:
                out = packet.agent_outputs.get(name)
                if out:
                    self.audit.log(f"{name}.attempt_{attempt_no}", out.payload)
                    if _MON_AVAILABLE:
                        _mon.record_agent_run(name)

            # Extract decision
            decision = get_decision_from_packet(packet)

            # Record risk score (Phase 26 monitoring)
            if _MON_AVAILABLE:
                _mon.record_risk_score(decision.risk_score)

            # AGS constitutional judiciary check (can escalate but never downgrade)
            ags_verdict = self._run_ags(decision, packet)
            if _MON_AVAILABLE and ags_verdict is not None:
                _mon.record_ags_verdict(
                    ags_verdict.verdict.lower() if hasattr(ags_verdict, "verdict") else "allow"
                )
            if ags_verdict is not None and ags_verdict.escalated:
                logger.warning("AGS escalation: %s -> %s", decision.action, ags_verdict.action)
                decision = Decision(
                    action=ags_verdict.action,
                    risk_score=ags_verdict.risk_score,
                    rationale=f"AGS ESCALATION: {ags_verdict.rationale} | Guardian: {decision.rationale}",
                    policy_refs=decision.policy_refs + ["AGS-ESCALATION"],
                )

            # Reflex dispatch (policy-driven rules may augment behavior)
            reflex_results = self._run_reflex(event, decision, packet)

            # Persist core outputs for this attempt
            # NOTE: keep main handoff_packet.json for final state, and store per-attempt snapshot too.
            _write_json(base / f"handoff_packet.attempt_{attempt_no}.json", {
                "event": asdict(event),
                "agent_outputs": {k: v.payload for k, v in packet.agent_outputs.items()},
                "memory_hits": [h for h in (packet.memory_hits or [])],
                "risk": {"risk_score": decision.risk_score},
                "audit_span_id": packet.audit_span_id,
                "attempt": attempt_no,
                "stages": stages,
            })

            # Audit report (Kousaki's module)
            audit_report = build_audit_report(packet=packet, decision=decision)

            # Enrich audit with hash chain + reflex + timing (per attempt)
            pipeline_ms = round((time.perf_counter() - pipeline_start) * 1000, 1)
            audit_report["hash_chain"] = self.audit.get_chain_summary()
            audit_report["reflex_rules_triggered"] = [r.rule_id for r in reflex_results if r.success]
            audit_report["pipeline_duration_ms"] = pipeline_ms
            audit_report["agents_version"] = "v3"
            audit_report["attempt"] = attempt_no

            _write_json(base / f"audit_report.attempt_{attempt_no}.json", audit_report)
            _write_json(base / f"decision.attempt_{attempt_no}.json", asdict(decision))

            # Branch on decision for this attempt
            if decision.action == "approve":
                self._execute_auto_approval(decision, packet, event, base)

                # VERIFY results written by execution layer -> inject into packet.artifacts
                verify_payload = _read_verify_payload(base)
                if verify_payload is not None:
                    if getattr(packet, "artifacts", None) is None:
                        packet.artifacts = {}
                    # Guardian expects a list[dict] under packet.artifacts["verification_results"]
                    packet.artifacts["verification_results"] = verify_payload.get("results") or []
                    packet.artifacts["verification_results_meta"] = {
                        "all_success": bool(verify_payload.get("all_success")),
                        "simulated": bool(verify_payload.get("simulated")),
                        "schema_version": verify_payload.get("schema_version"),
                    }

                # Record attempt snapshot
                attempts.append({
                    "attempt": attempt_no,
                    "decision": asdict(decision),
                    "risk_score": decision.risk_score,
                    "verify": verify_payload,
                })

                # If verify failed and we still have budget, run a short re-plan loop.
                verify_all_success = bool(verify_payload.get("all_success")) if verify_payload else True
                if (not verify_all_success) and (attempt_no < max_attempts):
                    # Inject verify feedback into event artifacts for next attempt context
                    fb = _summarize_verify_payload(verify_payload or {})
                    extra = event.artifacts.extra or {}
                    extra["verify_feedback"] = fb
                    extra["attempt_no"] = attempt_no
                    extra["retrying_due_to_verify_failure"] = True
                    event.artifacts.extra = extra
                    self.audit.log("verify.failed", {"attempt": attempt_no, "summary": fb})
                    if _MON_AVAILABLE:
                        _mon.record_verify_retry()
                    attempt_no += 1
                    continue

                # Finalize
                break

            elif decision.action == "block":
                attempts.append({
                    "attempt": attempt_no,
                    "decision": asdict(decision),
                    "risk_score": decision.risk_score,
                    "verify": None,
                })
                _write_json(base / "stop_report.json", {
                    "reason": "blocked_by_guardian",
                    "decision": asdict(decision),
                    "reflex_actions": [r.rule_id for r in reflex_results],
                    "attempt": attempt_no,
                })
                break

            elif decision.action == "need_approval":
                attempts.append({
                    "attempt": attempt_no,
                    "decision": asdict(decision),
                    "risk_score": decision.risk_score,
                    "verify": None,
                })
                self._handle_approval(decision, packet, event, base, audit_report)
                break

            else:
                # Unexpected action -> stop
                attempts.append({
                    "attempt": attempt_no,
                    "decision": asdict(decision),
                    "risk_score": decision.risk_score,
                    "verify": None,
                })
                _write_json(base / "stop_report.json", {
                    "reason": "unknown_decision_action",
                    "decision": asdict(decision),
                    "attempt": attempt_no,
                })
                break

        # Persist final core outputs (single canonical files)
        if decision is None:
            decision = Decision(action="block", risk_score=1.0, rationale="No decision produced", policy_refs=[])

        # Attach attempts into packet.artifacts for audit/report and for future debugging
        if getattr(packet, "artifacts", None) is None:
            packet.artifacts = {}
        packet.artifacts["attempts"] = attempts

        _write_json(base / "handoff_packet.json", {
            "event": asdict(event),
            "agent_outputs": {k: v.payload for k, v in packet.agent_outputs.items()},
            "memory_hits": [h for h in (packet.memory_hits or [])],
            "risk": {"risk_score": decision.risk_score},
            "audit_span_id": packet.audit_span_id,
            "a2a_trace": [
                {
                    "from": m.from_agent,
                    "to": m.to_agent,
                    "stage": m.stage,
                    "timestamp": m.timestamp,
                }
                for m in self.protocol.get_trace()
            ],
            "reflex_results": [
                {"rule_id": r.rule_id, "action": r.action, "success": r.success, "details": r.details}
                for r in reflex_results
            ],
            # New: packet artifacts (guardian_risk_model, verification_results, attempts)
            "packet_artifacts": getattr(packet, "artifacts", None) or {},
        })
        _write_json(base / "decision.json", asdict(decision))

        # Mike review (post-verify, post-canonical writes)
        # Env toggle: MIKE_REVIEW_ON_NEED_APPROVAL=1 enables review even when approval is required.
        run_on_need_approval = os.getenv("MIKE_REVIEW_ON_NEED_APPROVAL", "").strip() in ("1", "true", "yes", "on")
        if decision.action == "approve" or (decision.action == "need_approval" and run_on_need_approval):
            verify_path = base / "verify_results.json"
            try:
                run_mike_review_and_remember(
                    handoff_path=base / "handoff_packet.json",
                    decision_path=base / "decision.json",
                    verify_path=verify_path,
                    output_path=base / "mike_review.json",
                )
                self.audit.log("mike.review", {"status": "ok"})
            except Exception as e:
                self.audit.log("mike.review", {"status": "error", "error": str(e)})

        # Write canonical audit_report.json based on final packet state
        audit_report_final = build_audit_report(packet=packet, decision=decision)
        pipeline_ms = round((time.perf_counter() - pipeline_start) * 1000, 1)
        audit_report_final["hash_chain"] = self.audit.get_chain_summary()
        audit_report_final["reflex_rules_triggered"] = [r.rule_id for r in reflex_results if r.success]
        audit_report_final["pipeline_duration_ms"] = pipeline_ms
        audit_report_final["agents_version"] = "v3"
        _write_json(base / "audit_report.json", audit_report_final)

        # Record monitoring metrics (Phase 26)
        if _MON_AVAILABLE:
            _mon.record_pipeline_duration(pipeline_ms)
            _mon.record_pipeline_run(event.event_type, decision.action)

        # Finish audit span according to final decision
        if decision.action == "approve":
            self.audit.finish({"status": "success", "action": "approve", "duration_ms": pipeline_ms, "attempts": len(attempts)})
        elif decision.action == "block":
            self.audit.finish({"status": "blocked", "action": "block", "duration_ms": pipeline_ms, "attempts": len(attempts)})
        elif decision.action == "need_approval":
            # _handle_approval may finish audit early when waiting human; keep this as a best-effort
            self.audit.finish({"status": "need_approval", "action": "need_approval", "duration_ms": pipeline_ms, "attempts": len(attempts)})

        # 8. Remember this incident for future recall (richer LEARN payload)
        self._remember_incident(event, decision, packet)

        # 9. Record AIS rewards (Phase 25)
        self._record_ais_rewards(event, decision, packet)

        # 10. Sync AIS gauges to Prometheus (Phase 26)
        self._sync_ais_gauges()

        # 11. Diagnostics Loop — READ/THINK/WRITE/ASSESS (Blueprint MS-A6)
        self._run_diagnostics_loop(event, decision)

    # ---- internal methods ----

    def _inject_memory(self, packet: HandoffPacket) -> None:
        """Query memory for similar past incidents and inject into packet."""
        query = packet.event.summary or packet.event.event_type
        if not query:
            return

        hits = self.memory.recall(query, k=3)
        if hits:
            packet.memory_hits = [h.to_dict() for h in hits]
            self.audit.log("memory.recall", {
                "query": query,
                "hits": len(hits),
                "top_hit": hits[0].title if hits else None,
            })

    def _run_ags(self, decision: Decision, packet: HandoffPacket) -> Optional[Any]:
        """Run AGS pipeline if enabled. Returns AGSVerdict or None."""
        if self.ags is None:
            return None
        try:
            pkt_artifacts = getattr(packet, "artifacts", None) or {}
            cgrf_meta = pkt_artifacts.get("guardian_cgrf_metadata", {})
            cgrf_tier = cgrf_meta.get("tier", 0) if isinstance(cgrf_meta, dict) else 0

            verdict = self.ags.run(packet, decision, cgrf_tier=cgrf_tier)
            self.audit.log("ags.pipeline", verdict.to_dict())
            return verdict
        except Exception as e:
            logger.error("AGS pipeline error (non-fatal): %s", e)
            self.audit.log("ags.error", {"error": str(e)})
            return None  # Fail-open: Guardian's decision stands

    def _run_reflex(
        self,
        event: EventJsonV1,
        decision: Decision,
        packet: HandoffPacket,
    ) -> list:
        """Run reflex dispatcher and log results."""
        sentinel_out = packet.agent_outputs.get("sentinel")
        severity = sentinel_out.payload.get("severity", "medium") if sentinel_out else "medium"

        context = {
            "risk_score": decision.risk_score,
            "severity": severity,
            "action": decision.action,
            "event_id": event.event_id,
        }

        results = self.reflex.dispatch(event.event_type, context)

        if results:
            self.audit.log("reflex.dispatch", {
                "rules_matched": len(results),
                "results": [
                    {"rule_id": r.rule_id, "action": r.action, "success": r.success}
                    for r in results
                ],
            })

        return results

    def _execute_and_record(
        self,
        decision: Decision,
        packet: HandoffPacket,
        event: EventJsonV1,
        base: Path,
    ) -> None:
        """Execute the fix and record the outcome."""
        fixer_out = packet.agent_outputs.get("fixer")
        fix_plan = fixer_out.payload if fixer_out else {}

        outcome = self.executor.execute(decision, fix_plan, event)
        self.outcome_store.record(outcome)

        _write_json(base / "execution_outcome.json", outcome.to_dict())
        self.audit.log("execution", outcome.to_dict())

    def _execute_auto_approval(
        self,
        decision: Decision,
        packet: HandoffPacket,
        event: EventJsonV1,
        base: Path,
    ) -> None:
        """
        Execute auto-approval flow with PR creation and auto-merge.

        Flow:
        1. Execute fix (create PR)
        2. Wait for CI to pass
        3. Auto-merge if CI succeeds and settings allow
        4. Notify on success/failure
        """
        # Check if auto-execution is enabled
        auto_exec_enabled = self.settings.get("auto_execution", {}).get("enabled", False)
        if not auto_exec_enabled:
            logger.info("Auto-execution disabled, falling back to manual approval")
            self._execute_and_record(decision, packet, event, base)
            return

        # Execute the fix (creates PR)
        self._execute_and_record(decision, packet, event, base)

        # Check if auto-merge is enabled
        auto_merge_config = self.settings.get("auto_execution", {}).get("auto_merge", {})
        auto_merge_enabled = auto_merge_config.get("enabled", False)

        if not auto_merge_enabled:
            logger.info("Auto-merge disabled, PR created but not merged")
            self.audit.log("auto_merge.skipped", {"reason": "disabled"})
            if _MON_AVAILABLE:
                _mon.record_auto_merge("skipped")
            return

        # Check if event meets auto-merge criteria
        if not self._should_auto_merge(decision, event, auto_merge_config):
            logger.info("Event does not meet auto-merge criteria")
            self.audit.log("auto_merge.skipped", {
                "reason": "criteria_not_met",
                "risk_score": decision.risk_score,
                "event_type": event.event_type,
            })
            if _MON_AVAILABLE:
                _mon.record_auto_merge("skipped")
            return

        # Extract PR info from execution outcome
        outcome_path = base / "execution_outcome.json"
        if not outcome_path.exists():
            logger.warning("No execution outcome found, cannot auto-merge")
            return

        outcome_data = json.loads(outcome_path.read_text(encoding="utf-8"))
        pr_number = outcome_data.get("pr_number", 0)
        repo = event.repo

        if not pr_number or not repo:
            logger.warning("PR number or repo not found, cannot auto-merge")
            return

        # Wait for CI to complete
        ci_timeout = auto_merge_config.get("ci_wait_timeout", 300)
        logger.info(f"Waiting for CI on {repo}#{pr_number} (timeout={ci_timeout}s)")

        ci_result = self.github_client.wait_for_ci(repo, pr_number, timeout=ci_timeout)

        self.audit.log("auto_merge.ci_wait", {
            "pr_number": pr_number,
            "repo": repo,
            "state": ci_result.get("state"),
            "elapsed_seconds": ci_result.get("elapsed_seconds"),
        })

        if not ci_result.get("success"):
            logger.warning(f"CI did not pass for {repo}#{pr_number}: {ci_result.get('state')}")
            _write_json(base / "auto_merge_result.json", {
                "success": False,
                "reason": "ci_failed",
                "ci_state": ci_result.get("state"),
                "pr_number": pr_number,
            })
            if _MON_AVAILABLE:
                _mon.record_auto_merge("failure")
            return

        # CI passed, proceed with merge
        merge_method = auto_merge_config.get("merge_method", "squash")
        logger.info(f"Merging PR {repo}#{pr_number} with method={merge_method}")

        merge_result = self.github_client.merge_pr(
            repo=repo,
            pr_number=pr_number,
            merge_method=merge_method,
            commit_title=f"[AUTO] {event.summary}",
            commit_message=f"Auto-merged by Citadel Lite\nEvent ID: {event.event_id}\nRisk Score: {decision.risk_score}",
        )

        self.audit.log("auto_merge.merge", {
            "pr_number": pr_number,
            "repo": repo,
            "success": merge_result.get("success"),
            "sha": merge_result.get("sha"),
        })

        _write_json(base / "auto_merge_result.json", {
            "success": merge_result.get("success"),
            "pr_number": pr_number,
            "merge_sha": merge_result.get("sha"),
            "ci_elapsed_seconds": ci_result.get("elapsed_seconds"),
        })

        if merge_result.get("success"):
            logger.info(f"Successfully auto-merged PR {repo}#{pr_number}")
            if _MON_AVAILABLE:
                _mon.record_auto_merge("success")
        else:
            logger.error(f"Failed to auto-merge PR {repo}#{pr_number}: {merge_result.get('message')}")
            if _MON_AVAILABLE:
                _mon.record_auto_merge("failure")

    def _should_auto_merge(
        self,
        decision: Decision,
        event: EventJsonV1,
        auto_merge_config: Dict[str, Any],
    ) -> bool:
        """
        Check if event meets auto-merge criteria.

        Returns False if:
        - Risk score exceeds threshold
        - Event type is excluded
        - Branch is excluded
        """
        # Check risk threshold
        try:
            max_risk = float(auto_merge_config.get("max_risk_threshold", 0.25))
        except (TypeError, ValueError):
            max_risk = 0.25
        if decision.risk_score >= max_risk:
            logger.info(f"Risk score {decision.risk_score} >= {max_risk}, blocking auto-merge")
            return False

        # Check excluded event types
        excluded_types = auto_merge_config.get("exclude_event_types", [])
        if event.event_type in excluded_types:
            logger.info(f"Event type {event.event_type} is excluded from auto-merge")
            return False

        # Check excluded branches
        excluded_branches = auto_merge_config.get("exclude_branches", [])
        event_branch = event.ref or ""
        if event_branch in excluded_branches:
            logger.info(f"Branch {event_branch} is excluded from auto-merge")
            return False

        return True

    def _handle_approval(
        self,
        decision: Decision,
        packet: HandoffPacket,
        event: EventJsonV1,
        base: Path,
        audit_report: Dict[str, Any],
    ) -> None:
        """Handle the need_approval branch."""
        approval_request = build_approval_request(audit_report=audit_report)
        _write_json(base / "approval_request.json", approval_request)

        template = build_approval_response_template(event_id=event.event_id)
        _write_json(base / "approval_response.template.json", template)

        # Check if response already exists (for re-runs)
        response_path = base / "approval_response.json"
        if not response_path.exists():
            self.audit.finish({"status": "waiting_human", "action": "need_approval"})
            return

        approval_response = load_approval_response(response_path)
        self.audit.log("approval_response", approval_response)

        decision_id = approval_response.get("decision_id")

        if decision_id == "approve":
            self._execute_and_record(decision, packet, event, base)
            self.audit.finish({"status": "success", "action": "approved_by_human"})

        elif decision_id == "reject":
            _write_json(base / "stop_report.json", {
                "reason": "rejected_by_human",
                "comment": approval_response.get("comment"),
                "by": approval_response.get("by"),
            })
            self.audit.finish({"status": "rejected", "action": "rejected_by_human"})

        elif decision_id == "request_changes":
            _write_json(base / "stop_report.json", {
                "reason": "changes_requested_by_human",
                "comment": approval_response.get("comment"),
                "by": approval_response.get("by"),
            })
            self.audit.finish({"status": "changes_requested", "action": "request_changes"})

        else:
            _write_json(base / "stop_report.json", {
                "reason": "invalid_approval_response",
                "response": approval_response,
            })
            self.audit.finish({"status": "invalid_response", "action": "need_approval"})

    def _remember_incident(self, event: EventJsonV1, decision: Decision, packet: HandoffPacket) -> None:
        """Store this incident in memory for future recall."""
        tags = [event.event_type]
        if event.source:
            tags.append(event.source)

        # Extract richer LEARN features
        sherlock_out = packet.agent_outputs.get("sherlock")
        fixer_out = packet.agent_outputs.get("fixer")
        sherlock_label = ""
        if sherlock_out and isinstance(sherlock_out.payload, dict):
            sherlock_label = str(sherlock_out.payload.get("label", "") or "")
        fix_plan_text = ""
        verification_steps = None
        if fixer_out and isinstance(fixer_out.payload, dict):
            fix_plan_text = str(fixer_out.payload.get("fix_plan", "") or "")
            vs = fixer_out.payload.get("verification_steps")
            if isinstance(vs, list):
                verification_steps = vs

        verify_meta = (getattr(packet, "artifacts", None) or {}).get("verification_results_meta") or {}
        verify_success = verify_meta.get("all_success", None)

        self.memory.remember(
            event_id=event.event_id,
            summary=event.summary or event.event_type,
            tags=tags,
            outcome=decision.action,
            sherlock_label=sherlock_label,
            fix_summary=fix_plan_text[:280],
            verification_steps=verification_steps,
            verify_success=verify_success,
            risk_score=decision.risk_score,
        )

    def _record_ais_rewards(
        self,
        event: EventJsonV1,
        decision: Decision,
        packet: HandoffPacket,
    ) -> None:
        """Record AIS XP/TP rewards for agents after task completion."""
        if self.ais_engine is None:
            return

        try:
            # Extract verification outcome
            verify_meta = (getattr(packet, "artifacts", None) or {}).get(
                "verification_results_meta", {}
            ) or {}
            fix_verified = bool(verify_meta.get("all_success", False))

            # Extract CGRF tier
            pkt_artifacts = getattr(packet, "artifacts", None) or {}
            cgrf_meta = pkt_artifacts.get("guardian_cgrf_metadata", {})
            cgrf_tier = cgrf_meta.get("tier", 0) if isinstance(cgrf_meta, dict) else 0

            # Determine if critical event
            critical_types = {"security_alert", "deploy_failed", "payment_timeout", "api_error_spike"}
            is_critical = event.event_type in critical_types

            reward_event = RewardEvent(
                event_type=event.event_type,
                outcome=decision.action,
                tier=cgrf_tier,
                risk_score=decision.risk_score,
                fix_verified=fix_verified,
                is_critical=is_critical,
            )

            # Reward each agent that contributed
            for agent_name in ("sentinel", "sherlock", "fixer", "guardian"):
                if agent_name in packet.agent_outputs:
                    self.ais_engine.record_reward(agent_name, event=reward_event)

            # Reward composite pipeline_agent
            self.ais_engine.record_reward("pipeline_agent", event=reward_event)

            self.audit.log("ais.rewards", {
                "event_type": event.event_type,
                "outcome": decision.action,
                "tier": cgrf_tier,
                "fix_verified": fix_verified,
                "is_critical": is_critical,
            })

        except Exception as e:
            logger.error("AIS reward recording error (non-fatal): %s", e)
            self.audit.log("ais.error", {"error": str(e)})

    def _run_diagnostics_loop(self, event: EventJsonV1, decision: Decision) -> None:
        """Run DiagnosticsLoop (Blueprint MS-A6: READ/THINK/WRITE/ASSESS)."""
        if self.diagnostics_loop is None:
            return
        try:
            dry_run = self.settings.get("diagnostics_loop", {}).get("dry_run", True)
            report = self.diagnostics_loop.run(
                order_id=event.event_id,
                dry_run=dry_run,
            )
            self.audit.log("diagnostics_loop", {
                "verdict": report.verdict,
                "risk": report.risk,
                "blockers": report.blockers,
            })
        except Exception as e:
            logger.error("DiagnosticsLoop error (non-fatal): %s", e)

    def _sync_ais_gauges(self) -> None:
        """Push current AIS XP/TP/grade to Prometheus gauges (Phase 26)."""
        if not _MON_AVAILABLE or self.ais_engine is None:
            return
        try:
            for agent_id in ("sentinel", "sherlock", "fixer", "guardian", "pipeline_agent"):
                p = self.ais_engine.get_profile(agent_id)
                _mon.set_agent_xp(agent_id, p.xp)
                _mon.set_agent_tp(agent_id, p.tp)
                _mon.set_agent_grade(agent_id, p.grade.value)
        except Exception:
            pass  # fail-open


# ---- CLI entry point ----

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.orchestrator_v3 demo/events/ci_failed.sample.json")
        sys.exit(1)

    orchestrator = OrchestratorV3()
    orchestrator.run(Path(sys.argv[1]))
    print("[orchestrator_v3] Pipeline complete.")
