# src/ingest/outbox.py
"""
Outbox adapter for queuing normalized events.

Provides:
- FileOutbox: writes to outbox/pending/, claims into outbox/processing/,
  then finalizes into outbox/processed/success or outbox/processed/failed
- ServiceBusOutbox: (in src/azure/) sends to Azure Service Bus queue

Pattern: simple push/pull interface for decoupling ingestion from processing.
"""
from __future__ import annotations

import json
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from src.types import EventJsonV1, EventArtifact


class OutboxAdapter(ABC):
    """Abstract interface for event queueing."""

    @abstractmethod
    def push(self, event: EventJsonV1) -> None:
        """Queue an event for processing."""
        ...

    @abstractmethod
    def pull(self) -> Optional[EventJsonV1]:
        """Retrieve the next event to process. Returns None if empty."""
        ...


    # --- v3 style (recommended) ---
    def claim(self) -> Optional[Tuple[EventJsonV1, Dict[str, Any]]]:
        """Atomically claim the next event. Returns (event, claim_info) or None."""
        # Default fallback for adapters that only support pull()
        ev = self.pull()
        if ev is None:
            return None
        return ev, {"mode": "pull_only"}

    def finalize(self, claim_info: Dict[str, Any], *, ok: bool, reason: str = "") -> None:
        """Finalize a claimed event (move to success/failed, write metadata)."""
        # Default no-op for pull-only adapters
        return

class FileOutbox(OutboxAdapter):
    """
    File-based outbox: events are JSON files in outbox/pending/.
    Claiming (pull) moves them to outbox/processing/ to prevent double-processing.
    Finalization moves them to:
      - outbox/processed/success/
      - outbox/processed/failed/
    """

    def __init__(self, base: Optional[Path] = None) -> None:
        self.base = base or Path("outbox")
        self.pending = self.base / "pending"
        self.processing = self.base / "processing"
        self.processed = self.base / "processed"
        self.success = self.processed / "success"
        self.failed = self.processed / "failed"

        self.pending.mkdir(parents=True, exist_ok=True)
        self.processing.mkdir(parents=True, exist_ok=True)
        self.processed.mkdir(parents=True, exist_ok=True)
        self.success.mkdir(parents=True, exist_ok=True)
        self.failed.mkdir(parents=True, exist_ok=True)

        # --- recovery: requeue any in-flight items on startup ---
        # If the process crashed after claiming (pending->processing),
        # we requeue them so the next run can process them again.
        for p in sorted(self.processing.glob("*.json")):
            try:
                dest = self.pending / p.name
                # avoid overwrite (in case the same file also exists in pending)
                if dest.exists():
                    dest = self.pending / f"{p.stem}.requeued.{int(time.time())}{p.suffix}"
                p.replace(dest)  # atomic on same drive
            except Exception:
                # If requeue fails, leave it in processing for manual inspection.
                pass

    def push(self, event: EventJsonV1) -> None:
        path = self.pending / f"{event.event_id}.json"
        tmp = self.pending / f".{event.event_id}.json.tmp"
        tmp.write_text(
            json.dumps(asdict(event), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)  # atomic on same drive

    def pull(self) -> Optional[EventJsonV1]:
        # Deprecated path: keep for backward compatibility
        claimed = self.claim()
        if claimed is None:
            return None
        event, claim_info = claimed
        # For pull() callers, finalize immediately as "ok"
        self.finalize(claim_info, ok=True, reason="pulled_via_legacy_api")
        return event

    def claim(self) -> Optional[Tuple[EventJsonV1, Dict[str, Any]]]:
        files = sorted(self.pending.glob("*.json"))
        if not files:
            return None

        src = files[0]
        dst = self.processing / src.name
        # claim = atomic move pending -> processing
        src.replace(dst)

        raw = json.loads(dst.read_text(encoding="utf-8"))

        artifacts_raw = raw.get("artifacts", {}) or {}
        extra = artifacts_raw.get("extra", {}) or {}
        # Embed receipt path so the process loop can finalize without additional state.
        extra["_outbox_claimed_path"] = str(dst)
        extra["_outbox_base"] = str(self.base)

        event = EventJsonV1(
            schema_version=raw.get("schema_version", "event_json_v1"),
            event_id=raw.get("event_id", ""),
            event_type=raw.get("event_type", ""),
            source=raw.get("source", ""),
            occurred_at=raw.get("occurred_at", ""),
            repo=raw.get("repo"),
            ref=raw.get("ref"),
            summary=raw.get("summary"),
            artifacts=EventArtifact(
                log_excerpt=artifacts_raw.get("log_excerpt"),
                links=artifacts_raw.get("links", []),
                extra=extra,
            ),
        )

        return event, {"mode": "file", "processing_path": str(dst)}

    def finalize(self, claim_info: Dict[str, Any], *, ok: bool, reason: str = "") -> None:
        if claim_info.get("mode") != "file":
            return
        p = Path(claim_info["processing_path"])
        if not p.exists():
            return

        dest_dir = self.success if ok else self.failed
        dest = dest_dir / p.name
        # avoid overwrite
        if dest.exists():
            stem = dest.stem
            dest = dest_dir / f"{stem}.{int(time.time())}{dest.suffix}"
        p.replace(dest)
