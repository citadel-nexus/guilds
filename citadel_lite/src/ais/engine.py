"""
AIS Engine — main coordinator for the XP/TP economy.

Responsibilities:
  - Load / save agent profiles via :class:`ProfileStore`
  - Check action budgets (TP required)
  - Record rewards (XP/TP earning)
  - Provide AGS-compatible :class:`CAPSProfile` for the pipeline
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from src.ags.caps_stub import CAPSProfile, get_default_profile
from src.ais.costs import ActionCost, CostTable
from src.ais.profile import AgentProfile
from src.ais.rewards import RewardCalculator, RewardEvent
from src.ais.storage import ProfileStore

logger = logging.getLogger(__name__)


class AISEngine:
    """
    Central AIS engine.

    Usage::

        engine = AISEngine()
        profile = engine.get_profile("sentinel")
        can, cost = engine.check_budget(profile, "approve_fix")
        engine.record_reward("sentinel", event=reward_event)
    """

    def __init__(self, storage: Optional[ProfileStore] = None) -> None:
        self.storage = storage or ProfileStore()
        self.rewards = RewardCalculator()
        self.costs = CostTable()

    # ---- profile access ----

    def get_profile(self, agent_id: str) -> AgentProfile:
        """Get agent profile, creating one with defaults if absent."""
        return self.storage.get_or_create_profile(agent_id)

    def get_caps_profile(self, agent_id: str) -> CAPSProfile:
        """Return an AGS-compatible :class:`CAPSProfile` (fail-open)."""
        try:
            return self.get_profile(agent_id).to_caps_profile()
        except Exception as e:
            logger.error("AIS error getting profile for %s: %s", agent_id, e)
            return get_default_profile(agent_id)

    def get_all_profiles(self) -> Dict[str, AgentProfile]:
        """Return every persisted profile."""
        return self.storage.list_all_profiles()

    # ---- budget ----

    def check_budget(
        self, profile: AgentProfile, action_type: str
    ) -> Tuple[bool, Optional[ActionCost]]:
        """
        Check whether *profile* can afford *action_type*.

        Returns ``(can_afford, cost)``; *cost* is ``None`` for unknown actions
        (treated as free).
        """
        cost = self.costs.get_cost(action_type)
        if cost is None:
            return (True, None)
        return (profile.can_afford(cost.tp_required), cost)

    # ---- rewards ----

    def record_reward(
        self,
        agent_id: str,
        *,
        xp: Optional[int] = None,
        tp: Optional[int] = None,
        reason: str = "",
        event: Optional[RewardEvent] = None,
    ) -> Dict[str, int]:
        """
        Record an XP/TP reward.

        Two modes:
          1. **Manual**: ``record_reward("id", xp=50, tp=20, reason="…")``
          2. **Event-based**: ``record_reward("id", event=RewardEvent(…))``

        Returns ``{"xp": int, "tp": int}`` actually applied.
        """
        try:
            profile = self.get_profile(agent_id)

            if event is not None:
                calc = self.rewards.calculate_reward(event)
                xp = calc["xp"]
                tp = calc["tp"]
                reason = calc["reason"]

            if xp and xp != 0:
                profile.add_xp(xp, reason)
            if tp and tp != 0:
                profile.add_tp(tp, reason)

            self.storage.save_profile(profile)
            logger.info("Reward: %s +%s XP, +%s TP (%s)", agent_id, xp, tp, reason)
            return {"xp": xp or 0, "tp": tp or 0}

        except Exception as e:
            logger.error("Failed to record reward for %s: %s", agent_id, e)
            return {"xp": 0, "tp": 0}

    # ---- spending ----

    def spend_tp(self, agent_id: str, amount: int, reason: str) -> bool:
        """
        Deduct *amount* TP from *agent_id*.

        Returns ``True`` on success, ``False`` if insufficient balance.
        """
        try:
            profile = self.get_profile(agent_id)
            if not profile.can_afford(amount):
                logger.warning(
                    "Insufficient TP: %s has %d, needs %d", agent_id, profile.tp, amount,
                )
                return False
            profile.add_tp(-amount, reason)
            self.storage.save_profile(profile)
            logger.info("TP spent: %s -%d TP (%s)", agent_id, amount, reason)
            return True
        except Exception as e:
            logger.error("Failed to spend TP for %s: %s", agent_id, e)
            return False
