"""
Action cost definitions for TP budget checks.

Each action the orchestrator may take has an associated TP cost that the
agent must be able to afford before proceeding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ActionCost:
    """Immutable cost specification for a single action type."""

    action_type: str
    xp_cost: int = 0           # reserved for future capability-unlock spending
    tp_required: int = 0       # TP the agent must hold to execute
    description: str = ""


class CostTable:
    """Central registry of action costs."""

    _COSTS: Dict[str, ActionCost] = {
        "approve_fix": ActionCost(
            action_type="approve_fix",
            xp_cost=10,
            tp_required=50,
            description="Approve a fix for execution",
        ),
        "create_pr": ActionCost(
            action_type="create_pr",
            xp_cost=20,
            tp_required=70,
            description="Create a pull request",
        ),
        "deploy": ActionCost(
            action_type="deploy",
            xp_cost=50,
            tp_required=90,
            description="Deploy to production",
        ),
        "need_approval": ActionCost(
            action_type="need_approval",
            xp_cost=5,
            tp_required=20,
            description="Escalate to human approval",
        ),
        "block": ActionCost(
            action_type="block",
            xp_cost=0,
            tp_required=0,
            description="Block action (no cost)",
        ),
    }

    @classmethod
    def get_cost(cls, action_type: str) -> Optional[ActionCost]:
        """Look up the cost for *action_type*, or ``None`` if unknown."""
        return cls._COSTS.get(action_type)

    @classmethod
    def get_all_costs(cls) -> Dict[str, ActionCost]:
        """Return a shallow copy of the full cost table."""
        return dict(cls._COSTS)
