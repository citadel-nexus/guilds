"""
Reward calculation for task completion and quality.

XP earning (from AIS spec):
  - task_completion: 10-200 XP (base) x tier multiplier
  - quality bonus: +50% XP when verification passes
  - failed fix penalty: -20 XP

TP earning:
  - critical events: deploy_failed=100, security_alert=200
  - low-risk bonus: +20 TP when risk < 0.25
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class RewardEvent:
    """Input for event-based reward calculation."""

    event_type: str        # ci_failed, deploy_failed, security_alert, …
    outcome: str           # approve, need_approval, block
    tier: int              # CGRF tier 0-3
    risk_score: float      # Guardian risk score 0-1
    fix_verified: bool     # did verification pass?
    is_critical: bool      # revenue / security critical event?


class RewardCalculator:
    """Calculate XP / TP rewards based on task completion."""

    # Tier multipliers for XP rewards
    _TIER_MULTIPLIERS: Dict[int, float] = {
        0: 1.0,
        1: 1.5,
        2: 2.5,
        3: 5.0,
    }

    # Base XP by outcome
    _BASE_XP: Dict[str, int] = {
        "approve": 50,
        "need_approval": 30,
        "block": 10,
    }

    # TP awarded for critical event types
    _CRITICAL_TP: Dict[str, int] = {
        "deploy_failed": 100,
        "security_alert": 200,
        "payment_timeout": 150,
        "api_error_spike": 100,
    }

    def calculate_reward(self, event: RewardEvent) -> Dict[str, object]:
        """
        Return ``{"xp": int, "tp": int, "reason": str}`` for *event*.
        """
        xp = 0
        tp = 0
        reasons: list[str] = []

        # 1. Base XP × tier multiplier
        base = self._BASE_XP.get(event.outcome, 20)
        mult = self._TIER_MULTIPLIERS.get(event.tier, 1.0)
        task_xp = int(base * mult)
        xp += task_xp
        reasons.append(f"task_completion: {task_xp} XP (base={base}, tier={event.tier}, mult={mult})")

        # 2. Quality bonus (+50 %) for verified approve
        if event.fix_verified and event.outcome == "approve":
            bonus = int(task_xp * 0.5)
            xp += bonus
            reasons.append(f"quality_bonus: +{bonus} XP")

        # 3. Penalty for failed verification on approve
        if not event.fix_verified and event.outcome == "approve":
            xp -= 20
            reasons.append("failed_fix: -20 XP")

        # 4. TP for critical events
        if event.is_critical or event.event_type in self._CRITICAL_TP:
            crit_tp = self._CRITICAL_TP.get(event.event_type, 50)
            tp += crit_tp
            reasons.append(f"critical_event: +{crit_tp} TP ({event.event_type})")

        # 5. Low-risk bonus
        if event.outcome == "approve" and event.risk_score < 0.25:
            tp += 20
            reasons.append(f"low_risk_bonus: +20 TP (risk={event.risk_score:.2f})")

        return {
            "xp": max(0, xp),
            "tp": max(0, tp),
            "reason": " | ".join(reasons),
        }

    def calculate_penalty(self, violation_type: str) -> Dict[str, object]:
        """Return XP penalty dict for *violation_type*."""
        penalties: Dict[str, int] = {
            "policy_violation": -50,
            "failed_fix": -20,
            "customer_impact": -200,
        }
        xp_pen = penalties.get(violation_type, -10)
        return {"xp": xp_pen, "tp": 0, "reason": f"{violation_type}: {xp_pen} XP"}
