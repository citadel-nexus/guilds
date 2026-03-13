# src/audit/logger.py
"""
Hash-chained audit logger for Citadel Lite.

Every pipeline stage is recorded as an AuditEntry with a SHA-256 hash
that chains to the previous entry, providing tamper-evident audit trails.

Pattern adapted from CNWB src/ais/orchestrator.py Archivist seat (S03).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AuditEntry:
    """Single entry in the hash-chained audit trail."""
    span_id: str = ""
    stage: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    hash: str = ""
    previous_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _compute_hash(previous_hash: str, stage: str, timestamp: str, payload: Dict[str, Any]) -> str:
    """SHA-256 hash of (previous_hash + stage + timestamp + payload_json)."""
    content = previous_hash + stage + timestamp + json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class AuditLogger:
    """
    Hash-chained audit logger with pluggable backends.

    Usage:
        audit = AuditLogger()
        span = audit.start("event-123")
        audit.log("sentinel", {"classification": "ci_failed"})
        audit.log("sherlock", {"hypotheses": [...]})
        audit.finish({"status": "success"})
    """

    def __init__(self, backend: Optional[AuditBackend] = None) -> None:
        self._backend = backend or FileAuditBackend()
        self._entries: List[AuditEntry] = []
        self._span_id: str = ""
        self._previous_hash: str = "genesis"

    def start(self, event_id: str) -> str:
        """Begin a new audit span. Returns span_id."""
        self._span_id = str(uuid.uuid4())
        self._entries = []
        self._previous_hash = "genesis"

        entry = self._make_entry("audit.start", {"event_id": event_id})
        self._entries.append(entry)
        self._backend.write(entry)

        return self._span_id

    def log(self, stage: str, payload: Dict[str, Any]) -> None:
        """Record a pipeline stage."""
        entry = self._make_entry(stage, payload)
        self._entries.append(entry)
        self._backend.write(entry)

    def finish(self, outcome: Dict[str, Any]) -> None:
        """Close the audit span with final outcome."""
        entry = self._make_entry("audit.finish", outcome)
        self._entries.append(entry)
        self._backend.write(entry)

    def get_trail(self) -> List[AuditEntry]:
        """Return all entries in the current span."""
        return list(self._entries)

    def get_chain_summary(self) -> Dict[str, Any]:
        """Return summary suitable for inclusion in audit_report.json."""
        if not self._entries:
            return {"span_id": self._span_id, "chain_length": 0, "entries": []}
        return {
            "span_id": self._span_id,
            "chain_length": len(self._entries),
            "genesis_hash": self._entries[0].hash,
            "latest_hash": self._entries[-1].hash,
            "entries": [
                {
                    "stage": e.stage,
                    "timestamp": e.timestamp,
                    "hash": e.hash[:16] + "...",
                }
                for e in self._entries
            ],
        }

    def verify_chain(self) -> bool:
        """Verify the hash chain integrity. Returns True if all hashes are valid."""
        prev = "genesis"
        for entry in self._entries:
            expected = _compute_hash(prev, entry.stage, entry.timestamp, entry.payload)
            if entry.hash != expected:
                return False
            prev = entry.hash
        return True

    def _make_entry(self, stage: str, payload: Dict[str, Any]) -> AuditEntry:
        ts = datetime.now(timezone.utc).isoformat()
        h = _compute_hash(self._previous_hash, stage, ts, payload)
        entry = AuditEntry(
            span_id=self._span_id,
            stage=stage,
            payload=payload,
            timestamp=ts,
            hash=h,
            previous_hash=self._previous_hash,
        )
        self._previous_hash = h
        return entry


# ---------- Backends ----------

class AuditBackend:
    """Base class for audit storage backends."""
    def write(self, entry: AuditEntry) -> None:
        pass


class FileAuditBackend(AuditBackend):
    """Appends audit entries to a JSONL file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or Path("out/audit/audit_log.jsonl")

    def write(self, entry: AuditEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.to_dict(), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
