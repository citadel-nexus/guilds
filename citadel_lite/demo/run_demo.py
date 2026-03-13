# demo/run_demo.py
"""
Full demo script for Citadel Lite.
Runs the complete pipeline on demo events with stage-by-stage output.

Usage:
    python demo/run_demo.py                           # Run all demo events
    python demo/run_demo.py demo/events/ci_failed.sample.json  # Run single event
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator_v3 import OrchestratorV3, _load_event_json, _write_json
from src.a2a.agent_wrapper import build_protocol_v2
from src.audit.logger import AuditLogger
from src.memory.store_v2 import LocalMemoryStore
from src.execution.runner_V2 import ExecutionRunner
from src.execution.outcome_store import OutcomeStore
from src.reflex.dispatcher import ReflexDispatcher


# ---------- Styling ----------

class Style:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"
    LINE = "-" * 60


def _print_header(text: str) -> None:
    print(f"\n{Style.BOLD}{Style.CYAN}{Style.LINE}{Style.RESET}")
    print(f"{Style.BOLD}{Style.CYAN}  {text}{Style.RESET}")
    print(f"{Style.BOLD}{Style.CYAN}{Style.LINE}{Style.RESET}")


def _print_stage(name: str, detail: str = "") -> None:
    print(f"  {Style.GREEN}[+]{Style.RESET} {Style.BOLD}{name}{Style.RESET} {Style.DIM}{detail}{Style.RESET}")


def _print_result(key: str, value: str) -> None:
    # Sanitize unicode characters for Windows console
    safe_value = value.encode('cp932', errors='replace').decode('cp932')
    print(f"      {Style.DIM}{key}:{Style.RESET} {safe_value}")


def _print_cgrf_metadata(agent_name: str, metadata: dict) -> None:
    """Display CGRF v3.0 metadata with color coding by tier."""
    tier = metadata.get("tier", 0)
    tier_colors = {0: Style.DIM, 1: Style.CYAN, 2: Style.YELLOW, 3: Style.RED}
    tier_labels = {0: "Tier 0 (Experimental)", 1: "Tier 1 (Development)", 2: "Tier 2 (Production)", 3: "Tier 3 (Mission-Critical)"}
    color = tier_colors.get(tier, Style.RESET)
    label = tier_labels.get(tier, f"Tier {tier}")

    print(f"      {Style.BOLD}[CGRF]:{Style.RESET} {color}{label}{Style.RESET} | "
          f"{Style.DIM}Module:{Style.RESET} {metadata.get('module_name', 'unknown')} "
          f"{Style.DIM}v{metadata.get('module_version', '0.0.0')}{Style.RESET}")


# ---------- Demo Runner ----------

def run_demo_event(event_path: Path, shared_memory: LocalMemoryStore) -> None:
    """Run the full pipeline on a single demo event."""
    event = _load_event_json(event_path)

    # Defensive: skip malformed/empty demo events
    if not getattr(event, "event_type", None):
        _print_header(f"SKIP DEMO: {event_path.name}")
        _print_stage("Reason", "event_type is missing/empty")
        return

    _print_header(f"CITADEL LITE DEMO: {event.event_type}")
    _print_stage("Event loaded", f"id={event.event_id}")
    _print_result("source", event.source)
    _print_result("repo", str(event.repo))
    _print_result("summary", str(event.summary))

    # Build orchestrator with shared memory and v2 agents
    orchestrator = OrchestratorV3(
        protocol=build_protocol_v2(),
        memory=shared_memory,
        audit=AuditLogger(),
        executor=ExecutionRunner(mode="dry_run"),
        outcome_store=OutcomeStore(),
        reflex=ReflexDispatcher(),
    )

    start_time = time.perf_counter()

    # Run pipeline
    _print_stage("Memory recall", "querying past incidents...")
    _print_stage("A2A Pipeline", "Sentinel -> Sherlock -> Fixer -> Guardian")

    orchestrator.run(event_path)

    elapsed = (time.perf_counter() - start_time) * 1000

    # Read outputs
    base = Path("out") / event.event_id

    # Load CGRF metadata from audit report (if available)
    cgrf_metadata = {}
    if (base / "audit_report.json").exists():
        report = json.loads((base / "audit_report.json").read_text(encoding="utf-8"))
        cgrf_metadata = report.get("cgrf_metadata", {})

    if (base / "handoff_packet.json").exists():
        packet = json.loads((base / "handoff_packet.json").read_text(encoding="utf-8"))
        outputs = packet.get("agent_outputs", {})

        if "sentinel" in outputs:
            s = outputs["sentinel"]
            _print_stage("Sentinel", "detect & classify")
            _print_result("classification", str(s.get("classification")))
            _print_result("severity", str(s.get("severity")))
            # Display CGRF metadata if available
            if cgrf_metadata.get("sentinel"):
                _print_cgrf_metadata("sentinel", cgrf_metadata["sentinel"])

        if "sherlock" in outputs:
            sh = outputs["sherlock"]
            _print_stage("Sherlock", "diagnose")
            _print_result("hypotheses", str(sh.get("hypotheses")))
            _print_result("confidence", str(sh.get("confidence")))
            # Display CGRF metadata if available
            if cgrf_metadata.get("sherlock"):
                _print_cgrf_metadata("sherlock", cgrf_metadata["sherlock"])

        if "fixer" in outputs:
            f = outputs["fixer"]
            _print_stage("Fixer", "propose fix")
            _print_result("fix_plan", str(f.get("fix_plan", ""))[:80])
            _print_result("risk_estimate", str(f.get("risk_estimate")))
            vsteps = f.get("verification_steps") or []
            if vsteps:
                _print_result("verification_steps", str(vsteps))
            # Display CGRF metadata if available
            if cgrf_metadata.get("fixer"):
                _print_cgrf_metadata("fixer", cgrf_metadata["fixer"])

        memory_hits = packet.get("memory_hits", [])
        if memory_hits:
            _print_stage("Memory", f"{len(memory_hits)} past incidents found")
            for hit in memory_hits[:2]:
                mid = hit.get("memory_id") or hit.get("id") or ""
                conf = hit.get("confidence", "")
                title = hit.get("title", "")
                _print_result("recall", f"{mid} conf={conf} title={title}")

    if (base / "decision.json").exists():
        decision = json.loads((base / "decision.json").read_text(encoding="utf-8"))
        action = decision.get("action", "unknown")
        color = Style.GREEN if action == "approve" else (Style.YELLOW if action == "need_approval" else Style.RED)
        _print_stage("Guardian", "governance gate")
        print(f"      {Style.BOLD}{color}DECISION: {action.upper()}{Style.RESET}")
        _print_result("risk_score", str(decision.get("risk_score")))
        _print_result("rationale", str(decision.get("rationale")))
        # Display CGRF metadata if available
        if cgrf_metadata.get("guardian"):
            _print_cgrf_metadata("guardian", cgrf_metadata["guardian"])

    if (base / "execution_outcome.json").exists():
        outcome = json.loads((base / "execution_outcome.json").read_text(encoding="utf-8"))
        _print_stage("Execution", outcome.get("action_taken", ""))
        _print_result("success", str(outcome.get("success")))
        _print_result("details", str(outcome.get("details", ""))[:80])

    if (base / "audit_report.json").exists():
        report = json.loads((base / "audit_report.json").read_text(encoding="utf-8"))
        chain = report.get("hash_chain", {})
        _print_stage("Audit", f"hash chain length={chain.get('chain_length', 0)}")

        grm = report.get("guardian_risk_model") or {}
        if grm:
            mits = grm.get("mitigations") or []
            tops = grm.get("top_factors") or []
            if mits:
                _print_result("mitigations", str(mits))
            if tops:
                _print_result("top_factors", str(tops))

    print(f"\n  {Style.DIM}Pipeline completed in {elapsed:.1f}ms{Style.RESET}")
    print(f"  {Style.DIM}Outputs: {base}/{Style.RESET}")


def main() -> None:
    """Run demo on all or specified event files."""
    print(f"\n{Style.BOLD}{Style.MAGENTA}{'=' * 60}{Style.RESET}")
    print(f"{Style.BOLD}{Style.MAGENTA}  CITADEL LITE - Agentic DevOps Pipeline Demo{Style.RESET}")
    print(f"{Style.BOLD}{Style.MAGENTA}  Microsoft AI Dev Days Hackathon{Style.RESET}")
    print(f"{Style.BOLD}{Style.MAGENTA}{'=' * 60}{Style.RESET}")

    # Shared memory across all demo events (shows learning)
    shared_memory = LocalMemoryStore()

    if len(sys.argv) > 1:
        # Run single event
        run_demo_event(Path(sys.argv[1]), shared_memory)
    else:
        # Run all demo events
        demo_dir = Path(__file__).parent / "events"
        event_files = sorted(demo_dir.glob("*.json"))
        if not event_files:
            print(f"\n  {Style.RED}No event files found in {demo_dir}{Style.RESET}")
            return

        for event_file in event_files:
            run_demo_event(event_file, shared_memory)

    print(f"\n{Style.BOLD}{Style.MAGENTA}{'=' * 60}{Style.RESET}")
    print(f"{Style.BOLD}{Style.MAGENTA}  Demo complete. Audit trails in out/{Style.RESET}")
    print(f"{Style.BOLD}{Style.MAGENTA}{'=' * 60}{Style.RESET}\n")


if __name__ == "__main__":
    main()
