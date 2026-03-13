"""
Agent profile with XP/TP economy metrics.

AgentProfile tracks experience points (XP) and treasury points (TP) for each agent.
XP is non-transferable and drives CAPS grade progression.
TP is the autonomy budget consumed by actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.ags.caps_stub import CAPSGrade, CAPSProfile, resolve_caps_grade


@dataclass
class AgentProfile:
    """
    Agent XP/TP profile with transaction history.

    Attributes:
        agent_id: Unique identifier (sentinel, sherlock, fixer, guardian, pipeline_agent).
        xp: Experience points — non-transferable, drives CAPS grade.
        tp: Treasury points — autonomy budget for actions.
        grade: CAPS grade, auto-resolved from XP via ``__post_init__``.
        created_at: Profile creation timestamp (UTC ISO).
        last_updated: Last transaction timestamp (UTC ISO).
        transaction_log: Rolling window of recent transactions (max 100).
        metadata: Additional stats (total_tasks, total_rewards, …).
    """

    agent_id: str
    xp: int = 0
    tp: int = 0
    grade: CAPSGrade = CAPSGrade.D
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    transaction_log: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Resolve grade from current XP."""
        self.grade = resolve_caps_grade(self.xp)

    # ---- XP / TP mutations ----

    def add_xp(self, amount: int, reason: str) -> None:
        """Add *amount* XP (may be negative for penalties) and recompute grade."""
        self.xp = max(0, self.xp + amount)
        self.grade = resolve_caps_grade(self.xp)
        self.last_updated = datetime.now(timezone.utc).isoformat()
        self._log_transaction("xp", amount, reason)

    def add_tp(self, amount: int, reason: str) -> None:
        """Add *amount* TP (negative to spend)."""
        self.tp = max(0, self.tp + amount)
        self.last_updated = datetime.now(timezone.utc).isoformat()
        self._log_transaction("tp", amount, reason)

    def can_afford(self, tp_cost: int) -> bool:
        """Return ``True`` if this agent has at least *tp_cost* TP."""
        return self.tp >= tp_cost

    # ---- AGS compatibility ----

    def to_caps_profile(self) -> CAPSProfile:
        """Convert to legacy :class:`CAPSProfile` for the AGS pipeline."""
        return CAPSProfile(
            agent_id=self.agent_id,
            xp=self.xp,
            tp=self.tp,
            grade=self.grade,
        )

    # ---- Serialisation ----

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dict."""
        d = asdict(self)
        d["grade"] = self.grade.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentProfile:
        """Deserialise from a dict (e.g. loaded from JSON)."""
        data = dict(data)  # shallow copy to avoid mutating caller
        if "grade" in data and isinstance(data["grade"], str):
            data["grade"] = CAPSGrade(data["grade"])
        return cls(**data)

    # ---- internal ----

    def _log_transaction(self, token_type: str, amount: int, reason: str) -> None:
        self.transaction_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": token_type,
            "amount": amount,
            "reason": reason,
            "balance_xp": self.xp,
            "balance_tp": self.tp,
        })
        # Rolling window — keep last 100 entries.
        if len(self.transaction_log) > 100:
            self.transaction_log = self.transaction_log[-100:]
