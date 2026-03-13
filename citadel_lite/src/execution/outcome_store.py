# src/execution/outcome_store.py
"""
Records execution outcomes to a JSONL log for audit trail.
Each line is a JSON object with the full ExecutionOutcome plus metadata.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.execution.runner_V2 import ExecutionOutcome


class OutcomeStore:
    """Append-only JSONL store for execution outcomes."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or Path("out/outcomes.jsonl")

    def record(self, outcome: ExecutionOutcome) -> None:
        """Append an outcome record."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(outcome.to_dict(), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def get_outcomes(self, event_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Read all outcomes, optionally filtered by event_id."""
        if not self.path.exists():
            return []
        results = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if event_id is None or record.get("event_id") == event_id:
                results.append(record)
        return results
