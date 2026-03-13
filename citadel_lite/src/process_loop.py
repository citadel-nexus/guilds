# src/process_loop.py
"""
Outbox process loop for Citadel Lite.

Polls the outbox (file-based or Service Bus) for pending events
and processes each through the orchestrator pipeline.

Usage:
    python -m src.process_loop                    # File outbox
    python -m src.process_loop --azure            # Azure Service Bus
    python -m src.process_loop --orch v3          # Use orchestrator_v3 module
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from src.a2a.agent_wrapper import build_protocol_v2
from src.audit.logger import AuditLogger
from src.memory.store_v2 import LocalMemoryStore
from src.execution.runner_V2 import ExecutionRunner
from src.execution.outcome_store import OutcomeStore
from src.reflex.dispatcher import ReflexDispatcher
from src.ingest.outbox import FileOutbox, OutboxAdapter

def _build_orchestrator(version: str):
    """
    Build orchestrator instance from selected module.
    NOTE: v3 is the default stable entrypoint (src/orchestrator_v3.py).
    """
    v = (version or "v3").lower()
    if v == "v3":
        from src.orchestrator_v3 import OrchestratorV3 as OrchestratorImpl
    else:
        # For hackathon stability: treat anything else as v3 for now.
        from src.orchestrator_v3 import OrchestratorV3 as OrchestratorImpl

    return OrchestratorImpl(
        protocol=build_protocol_v2(),
        memory=LocalMemoryStore(),
        audit=AuditLogger(),
        executor=ExecutionRunner(),
        outcome_store=OutcomeStore(),
        reflex=ReflexDispatcher(),
    )


def run_process_loop(
    outbox: OutboxAdapter,
    poll_interval: float = 2.0,
    max_iterations: int = 0,
    max_runtime_seconds: float = 0,
    orchestrator_version: str = "v3",
) -> None:
    """
    Poll the outbox for pending events and process each.

    Args:
        outbox: The outbox adapter to poll
        poll_interval: Seconds between polls
        max_iterations: Max events to process (0 = unlimited)
        max_runtime_seconds: Max wall-clock runtime in seconds (0 = unlimited)
        orchestrator_version: "v3"
    """
    orchestrator = _build_orchestrator(orchestrator_version)

    processed = 0          # total handled (success + failed)
    succeeded = 0          # success only
    seen_event_ids = set()
    start_time = time.monotonic()
    print(
        f"[process_loop] Starting outbox processor "
        f"(poll_interval={poll_interval}s, max_runtime={max_runtime_seconds}s, orch={orchestrator_version})"
    )

    while True:
        if max_runtime_seconds > 0:
            elapsed = time.monotonic() - start_time
            if elapsed >= max_runtime_seconds:
                print(f"[process_loop] Wall-clock timeout after {elapsed:.1f}s")
                break
        claimed = outbox.claim()

        if claimed is None:
            if max_iterations > 0 and processed >= max_iterations:
                break
            time.sleep(poll_interval)
            continue
            
        event, claim_info = claimed

        print(f"[process_loop] Processing event: {event.event_id} ({event.event_type})")

        # Basic validation: skip malformed events
        if not event.event_id or not event.event_type:
            msg = f"invalid_event(event_id={event.event_id}, event_type={event.event_type})"
            print(f"[process_loop] Skipping: {msg}")
            try:
                outbox.finalize(claim_info, ok=False, reason=msg)
            except Exception as e:
                print(f"[process_loop] finalize(invalid) failed: {e}")
            processed += 1
            continue

        # De-dup within the same loop run
        if event.event_id in seen_event_ids:
            msg = f"duplicate_event(event_id={event.event_id})"
            print(f"[process_loop] Skipping: {msg}")
            try:
                outbox.finalize(claim_info, ok=False, reason=msg)
            except Exception as e:
                print(f"[process_loop] finalize(duplicate) failed: {e}")
            processed += 1
            continue


        try:
            orchestrator.run_from_event(event)
            succeeded += 1
            processed += 1
            seen_event_ids.add(event.event_id)

            try:
                outbox.finalize(claim_info, ok=True, reason="orchestrator_completed")
            except Exception as e:
                print(f"[process_loop] finalize(success) failed for {event.event_id}: {e}")
            print(f"[process_loop] Completed: {event.event_id} (ok: {succeeded}, total: {processed})")
        except Exception as e:
            print(f"[process_loop] Error processing {event.event_id}: {e}")
            processed += 1
            # finalize (file-outbox): processing -> processed/failed
            try:
                outbox.finalize(claim_info, ok=False, reason=str(e))
            except Exception as e2:
                print(f"[process_loop] finalize(failed) failed for {event.event_id}: {e2}")

        if max_iterations > 0 and processed >= max_iterations:
            break

    print(f"[process_loop] Stopped (ok: {succeeded}, total: {processed})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Citadel Lite outbox processing loop")
    parser.add_argument("--azure", action="store_true", help="Use Azure Service Bus outbox")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval seconds")
    parser.add_argument("--max-iterations", type=int, default=0, help="Max events to process (0=unlimited)")
    parser.add_argument("--max-runtime", type=float, default=0, help="Max wall-clock runtime seconds (0=unlimited)")
    parser.add_argument(
        "--orch",
        choices=["v3"],
        default=os.environ.get("ORCHESTRATOR_VERSION", "v3"),
        help='Orchestrator module to use ("v3"). Env: ORCHESTRATOR_VERSION',
    )
    args = parser.parse_args()

    if args.azure:
        try:
            from src.azure.config import load_azure_config
            from src.azure.servicebus_adapter import ServiceBusOutbox
            config = load_azure_config()
            outbox: OutboxAdapter = ServiceBusOutbox(config)
            print("[process_loop] Using Azure Service Bus outbox")
        except Exception as e:
            print(f"[process_loop] Azure Service Bus unavailable ({e}), falling back to file outbox")
            outbox = FileOutbox()
    else:
        outbox = FileOutbox()
        print("[process_loop] Using file-based outbox")

    run_process_loop(
        outbox,
        poll_interval=args.poll_interval,
        max_iterations=args.max_iterations,
        max_runtime_seconds=args.max_runtime,
        orchestrator_version=args.orch,
    )
