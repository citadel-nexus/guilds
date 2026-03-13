# src/nemesis/sanctions.py
"""
Nemesis v2 — Sanctions Engine

Graduated sanctions state machine with escalation, de-escalation,
cooldown periods, and restriction enforcement.

Sanction Ladder (NEM-SAN-001):
  Level 0: OBSERVE     — monitoring only
  Level 1: WARN        — formal warning (cooldown: 72h)
  Level 2: THROTTLE    — capability reduction (cooldown: 168h / 1wk)
  Level 3: RESTRICT    — major suspension (cooldown: 336h / 2wk)
  Level 4: QUARANTINE  — full isolation (no auto-cooldown)
  Level 5: HUMAN_ESCALATION — requires human review (no auto-cooldown)
  Level 6: RETIREMENT  — permanent, irreversible (NEM-SAN-007)

Escalation Rules (NEM-SAN-003):
  OBSERVE → WARN:        2 violations
  WARN → THROTTLE:       2 more violations
  THROTTLE → RESTRICT:   1 more violation
  RESTRICT → QUARANTINE: 1 more violation
  QUARANTINE → HUMAN_ESCALATION: 1 more violation
  RETIREMENT:            human decision only

SRS: NEM-SAN-001 to NEM-SAN-007
CGRF v3.0, Tier 1
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from src.nemesis.models import (
    SanctionLevel,
    SanctionRecord,
    ThreatEvent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Escalation / cooldown config
# ---------------------------------------------------------------------------

# Violations required to move to the NEXT level from current
_ESCALATION_THRESHOLD: Dict[SanctionLevel, int] = {
    SanctionLevel.OBSERVE: 2,            # 2 violations → WARN
    SanctionLevel.WARN: 2,               # 2 more → THROTTLE
    SanctionLevel.THROTTLE: 1,           # 1 more → RESTRICT
    SanctionLevel.RESTRICT: 1,           # 1 more → QUARANTINE
    SanctionLevel.QUARANTINE: 1,         # 1 more → HUMAN_ESCALATION
    SanctionLevel.HUMAN_ESCALATION: 999, # only human can retire
    SanctionLevel.RETIREMENT: 999,       # terminal
}

# Cooldown period before automatic de-escalation (hours)
_COOLDOWN_HOURS: Dict[SanctionLevel, Optional[float]] = {
    SanctionLevel.OBSERVE: None,       # no cooldown needed
    SanctionLevel.WARN: 72.0,          # 3 days
    SanctionLevel.THROTTLE: 168.0,     # 1 week
    SanctionLevel.RESTRICT: 336.0,     # 2 weeks
    SanctionLevel.QUARANTINE: None,    # no auto-de-escalation
    SanctionLevel.HUMAN_ESCALATION: None,
    SanctionLevel.RETIREMENT: None,    # permanent
}

# Restrictions applied at each level
_RESTRICTIONS: Dict[SanctionLevel, List[str]] = {
    SanctionLevel.OBSERVE: [],
    SanctionLevel.WARN: ["audit_frequency_increased"],
    SanctionLevel.THROTTLE: [
        "audit_frequency_increased",
        "rate_limit_50pct",
        "no_governance_voting",
    ],
    SanctionLevel.RESTRICT: [
        "audit_frequency_increased",
        "rate_limit_80pct",
        "no_governance_voting",
        "no_code_merge",
        "supervised_only",
    ],
    SanctionLevel.QUARANTINE: [
        "all_access_suspended",
        "credentials_revoked",
        "network_isolated",
        "state_preserved_for_forensics",
    ],
    SanctionLevel.HUMAN_ESCALATION: [
        "all_access_suspended",
        "credentials_revoked",
        "network_isolated",
        "pending_human_review",
    ],
    SanctionLevel.RETIREMENT: [
        "permanently_decommissioned",
        "all_access_revoked",
        "archived",
        "blacklisted",
    ],
}


# ---------------------------------------------------------------------------
# Agent state tracking
# ---------------------------------------------------------------------------

class _AgentState:
    """Internal mutable state for a single agent's sanction tracking."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.current_level = SanctionLevel.OBSERVE
        self.previous_level = SanctionLevel.OBSERVE
        self.violation_count_at_level = 0
        self.total_violations = 0
        self.last_violation_at: Optional[str] = None
        self.level_entered_at: str = datetime.now(timezone.utc).isoformat()
        self.history: List[SanctionRecord] = []
        self.escalation_count = 0


# ---------------------------------------------------------------------------
# Sanctions Engine
# ---------------------------------------------------------------------------

class SanctionsEngine:
    """
    State machine for graduated agent sanctions.

    Thread-safe for single-process use (in-memory state).
    For multi-process, back with Supabase (Phase 2).
    """

    def __init__(self):
        self._agents: Dict[str, _AgentState] = {}

    # -- State access -------------------------------------------------------

    def _get_state(self, agent_id: str) -> _AgentState:
        if agent_id not in self._agents:
            self._agents[agent_id] = _AgentState(agent_id)
        return self._agents[agent_id]

    def get_current_level(self, agent_id: str) -> SanctionLevel:
        """Get the current sanction level for an agent."""
        return self._get_state(agent_id).current_level

    def get_record(self, agent_id: str) -> Optional[SanctionRecord]:
        """Get the most recent sanction record for an agent."""
        state = self._get_state(agent_id)
        if state.history:
            return state.history[-1]
        return None

    def get_history(self, agent_id: str) -> List[SanctionRecord]:
        """Full sanction history for an agent."""
        return list(self._get_state(agent_id).history)

    def get_active_restrictions(self, agent_id: str) -> List[str]:
        """Get active restrictions for an agent based on current level."""
        level = self.get_current_level(agent_id)
        return list(_RESTRICTIONS.get(level, []))

    # -- Escalation ---------------------------------------------------------

    def escalate(
        self,
        agent_id: str,
        threat_event: ThreatEvent,
    ) -> SanctionRecord:
        """
        Record a violation and escalate if threshold reached.

        Returns the new SanctionRecord (may or may not have changed level).
        """
        state = self._get_state(agent_id)

        # RETIREMENT is terminal — no further escalation
        if state.current_level == SanctionLevel.RETIREMENT:
            logger.warning("Agent %s is retired — cannot escalate further", agent_id)
            return self._make_record(state, "already_retired", threat_event.event_id)

        state.violation_count_at_level += 1
        state.total_violations += 1
        state.last_violation_at = datetime.now(timezone.utc).isoformat()

        threshold = _ESCALATION_THRESHOLD.get(state.current_level, 999)

        if state.violation_count_at_level >= threshold:
            # Move to next level
            old_level = state.current_level
            new_level_val = min(state.current_level.value + 1, SanctionLevel.HUMAN_ESCALATION.value)
            new_level = SanctionLevel(new_level_val)

            state.previous_level = old_level
            state.current_level = new_level
            state.violation_count_at_level = 0
            state.level_entered_at = datetime.now(timezone.utc).isoformat()
            state.escalation_count = state.total_violations

            reason = (
                f"Escalated {old_level.name} → {new_level.name} "
                f"after {threshold} violations (total: {state.total_violations})"
            )
            logger.info("Sanctions: %s — %s", agent_id, reason)
        else:
            reason = (
                f"Violation recorded at {state.current_level.name} "
                f"({state.violation_count_at_level}/{threshold} to escalate)"
            )

        record = self._make_record(state, reason, threat_event.event_id)
        state.history.append(record)
        return record

    # -- De-escalation ------------------------------------------------------

    def de_escalate(
        self,
        agent_id: str,
        reason: str = "clean_period",
        authorized_by: Optional[str] = None,
    ) -> SanctionRecord:
        """
        Manually de-escalate an agent one level.
        Levels QUARANTINE+ require authorized_by.
        """
        state = self._get_state(agent_id)

        if state.current_level == SanctionLevel.OBSERVE:
            return self._make_record(state, "already_at_observe")

        if state.current_level == SanctionLevel.RETIREMENT:
            logger.warning("Cannot de-escalate retired agent %s", agent_id)
            return self._make_record(state, "retirement_is_permanent")

        # Require authorization for serious levels
        if state.current_level.value >= SanctionLevel.QUARANTINE.value and not authorized_by:
            logger.warning("De-escalation from %s requires authorization", state.current_level.name)
            return self._make_record(state, "authorization_required")

        old_level = state.current_level
        new_level = SanctionLevel(state.current_level.value - 1)

        state.previous_level = old_level
        state.current_level = new_level
        state.violation_count_at_level = 0
        state.level_entered_at = datetime.now(timezone.utc).isoformat()

        desc = f"De-escalated {old_level.name} → {new_level.name}: {reason}"
        logger.info("Sanctions: %s — %s", agent_id, desc)

        record = self._make_record(state, desc, authorized_by=authorized_by)
        state.history.append(record)
        return record

    # -- Cooldown -----------------------------------------------------------

    def check_cooldown(self, agent_id: str) -> bool:
        """
        Check if an agent is eligible for automatic de-escalation
        based on clean period at current level.

        Returns True if cooldown elapsed and de-escalation was applied.
        """
        state = self._get_state(agent_id)
        cooldown = _COOLDOWN_HOURS.get(state.current_level)

        if cooldown is None:
            return False  # no auto-de-escalation for this level

        entered = datetime.fromisoformat(state.level_entered_at)
        now = datetime.now(timezone.utc)
        elapsed_hours = (now - entered).total_seconds() / 3600

        if elapsed_hours >= cooldown:
            # Check no violations since entering this level
            if state.violation_count_at_level == 0:
                self.de_escalate(agent_id, reason="cooldown_elapsed", authorized_by="system")
                return True

        return False

    # -- Direct set (for RETIREMENT by human) --------------------------------

    def retire(self, agent_id: str, authorized_by: str, reason: str = "human_decision") -> SanctionRecord:
        """
        Permanently retire an agent. NEM-SAN-007: irreversible.
        Requires explicit human authorization.
        """
        state = self._get_state(agent_id)
        old_level = state.current_level

        state.previous_level = old_level
        state.current_level = SanctionLevel.RETIREMENT
        state.level_entered_at = datetime.now(timezone.utc).isoformat()

        desc = f"RETIRED from {old_level.name}: {reason}"
        logger.warning("Sanctions: %s — %s (authorized by %s)", agent_id, desc, authorized_by)

        record = self._make_record(state, desc, authorized_by=authorized_by)
        state.history.append(record)
        return record

    # -- Restrictions -------------------------------------------------------

    def apply_restrictions(self, agent_id: str) -> Dict[str, Any]:
        """
        Get the restrictions that should be enforced for an agent's current level.
        Returns a dict describing what to apply.
        """
        level = self.get_current_level(agent_id)
        restrictions = _RESTRICTIONS.get(level, [])

        return {
            "agent_id": agent_id,
            "sanction_level": level.name,
            "restrictions": restrictions,
            "restriction_count": len(restrictions),
        }

    # -- Helpers ------------------------------------------------------------

    def _make_record(
        self,
        state: _AgentState,
        reason: str,
        event_id: Optional[str] = None,
        authorized_by: Optional[str] = None,
    ) -> SanctionRecord:
        events = [event_id] if event_id else []
        cooldown = _COOLDOWN_HOURS.get(state.current_level)
        expires_at = None
        if cooldown is not None:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(hours=cooldown)
            ).isoformat()

        return SanctionRecord(
            agent_id=state.agent_id,
            current_level=state.current_level,
            previous_level=state.previous_level,
            reason=reason,
            threat_events=events,
            escalation_count=state.total_violations,
            expires_at=expires_at,
            authorized_by=authorized_by,
        )
