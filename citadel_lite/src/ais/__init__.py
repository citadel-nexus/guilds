"""
AIS (Agent Intelligence System) — XP/TP Economy Engine for Citadel Lite.

Phase 25 MVP: Dual-token economy, action costs, profile persistence,
autonomy budget, and orchestrator integration.

Public API:
    from src.ais import AISEngine, AgentProfile, RewardCalculator, RewardEvent

    engine = AISEngine()
    profile = engine.get_profile("sentinel")
    can_afford, cost = engine.check_budget(profile, "approve_fix")
    engine.record_reward("sentinel", event=reward_event)
"""
from __future__ import annotations

from src.ais.engine import AISEngine
from src.ais.profile import AgentProfile
from src.ais.storage import ProfileStore
from src.ais.rewards import RewardCalculator, RewardEvent
from src.ais.costs import ActionCost, CostTable

__all__ = [
    "AISEngine",
    "AgentProfile",
    "ProfileStore",
    "RewardCalculator",
    "RewardEvent",
    "ActionCost",
    "CostTable",
]
