"""SANCTUM Canonical Publisher — hash-chained evolution decision recording.

Records every MCA Evolution Cycle decision as a tamper-evident JSON entry
using the same SHA-256 hash-chain pattern as ``src/audit/logger.py``.

Each evolution run produces an ``EVO-{timestamp}.json`` file under
``.nexus/sanctum/evolution-decisions/`` containing professor analyses,
CAPS review, proposals, execution outcomes, and ethics assessment.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "sanctum_publisher"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

logger = logging.getLogger(__name__)

_DEFAULT_SANCTUM_DIR = Path(".nexus/sanctum/evolution-decisions")


def _compute_hash(previous_hash: str, stage: str, timestamp: str, payload: Dict[str, Any]) -> str:
    """SHA-256 hash of (previous_hash + stage + timestamp + payload_json)."""
    content = previous_hash + stage + timestamp + json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class SanctumEntry:
    """Single entry in a SANCTUM hash chain."""

    entry_id: str = ""
    stage: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    hash: str = ""
    previous_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SanctumRecord:
    """Complete SANCTUM record for one Evolution Cycle run."""

    record_id: str = ""
    session_id: str = ""
    created_at: str = ""
    entries: List[Dict[str, Any]] = field(default_factory=list)
    genesis_hash: str = ""
    latest_hash: str = ""
    chain_length: int = 0
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SanctumPublisher:
    """Hash-chained publisher for MCA evolution decisions.

    Usage::

        publisher = SanctumPublisher()
        publisher.start(session_id="evo_20260223T120000")
        publisher.record_phase("professor_analysis", {"mirror": {...}})
        publisher.record_phase("government_review", {"approved": [...]})
        publisher.record_phase("execution_outcome", {"results": [...]})
        record = publisher.finalize()
        # record is saved to .nexus/sanctum/evolution-decisions/EVO-{ts}.json
    """

    def __init__(
        self,
        sanctum_dir: Optional[Path] = None,
        dry_run: bool = False,
    ) -> None:
        self._sanctum_dir = sanctum_dir or _DEFAULT_SANCTUM_DIR
        self._dry_run = dry_run
        self._entries: List[SanctumEntry] = []
        self._previous_hash: str = "genesis"
        self._session_id: str = ""
        self._record_id: str = ""
        self._started: bool = False

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def chain_length(self) -> int:
        return len(self._entries)

    def start(self, session_id: str) -> str:
        """Begin a new SANCTUM recording session.

        Returns the record_id.
        """
        self._session_id = session_id
        self._record_id = f"EVO-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self._entries = []
        self._previous_hash = "genesis"
        self._started = True

        self._append_entry("sanctum.start", {
            "session_id": session_id,
            "record_id": self._record_id,
        })

        logger.info("[SANCTUM] Recording started: %s", self._record_id)
        return self._record_id

    def record_phase(self, stage: str, payload: Dict[str, Any]) -> None:
        """Record a phase in the evolution cycle."""
        if not self._started:
            raise RuntimeError("SANCTUM publisher not started -- call start() first")
        self._append_entry(stage, payload)

    def finalize(
        self,
        outcome: Optional[Dict[str, Any]] = None,
    ) -> SanctumRecord:
        """Finalize the recording and save to disk.

        Returns the complete SanctumRecord.
        """
        if not self._started:
            raise RuntimeError("SANCTUM publisher not started -- call start() first")

        self._append_entry("sanctum.finalize", outcome or {})

        record = SanctumRecord(
            record_id=self._record_id,
            session_id=self._session_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            entries=[e.to_dict() for e in self._entries],
            genesis_hash=self._entries[0].hash if self._entries else "",
            latest_hash=self._entries[-1].hash if self._entries else "",
            chain_length=len(self._entries),
            verified=self.verify_chain(),
        )

        if not self._dry_run:
            self._save_record(record)

        logger.info(
            "[SANCTUM] Record finalized: %s (%d entries, verified=%s)",
            self._record_id, len(self._entries), record.verified,
        )

        self._started = False
        return record

    def verify_chain(self) -> bool:
        """Verify the hash chain integrity."""
        prev = "genesis"
        for entry in self._entries:
            expected = _compute_hash(prev, entry.stage, entry.timestamp, entry.payload)
            if entry.hash != expected:
                return False
            prev = entry.hash
        return True

    def get_chain_summary(self) -> Dict[str, Any]:
        """Return summary suitable for inclusion in evolution results."""
        if not self._entries:
            return {"record_id": self._record_id, "chain_length": 0, "entries": []}
        return {
            "record_id": self._record_id,
            "session_id": self._session_id,
            "chain_length": len(self._entries),
            "genesis_hash": self._entries[0].hash,
            "latest_hash": self._entries[-1].hash,
            "stages": [
                {
                    "stage": e.stage,
                    "timestamp": e.timestamp,
                    "hash": e.hash[:16] + "...",
                }
                for e in self._entries
            ],
        }

    # -- Internal -----------------------------------------------------------
    def _append_entry(self, stage: str, payload: Dict[str, Any]) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        h = _compute_hash(self._previous_hash, stage, ts, payload)
        entry = SanctumEntry(
            entry_id=uuid.uuid4().hex[:12],
            stage=stage,
            payload=payload,
            timestamp=ts,
            hash=h,
            previous_hash=self._previous_hash,
        )
        self._entries.append(entry)
        self._previous_hash = h

    def _save_record(self, record: SanctumRecord) -> Path:
        """Save record to JSON file."""
        self._sanctum_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self._record_id}.json"
        filepath = self._sanctum_dir / filename

        with filepath.open("w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info("[SANCTUM] Saved: %s", filepath)
        return filepath
