"""
File-based JSON persistence for agent profiles.

Storage layout::

    data/ais/profiles/sentinel.json
    data/ais/profiles/sherlock.json
    data/ais/profiles/pipeline_agent.json
    ...

Follows the same file-based pattern used by LocalMemoryStore and OutcomeStore.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from src.ais.profile import AgentProfile

logger = logging.getLogger(__name__)


class ProfileStore:
    """File-based storage for :class:`AgentProfile` objects."""

    def __init__(self, base_path: Optional[Path] = None) -> None:
        self.base_path = base_path or Path("data/ais/profiles")
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, AgentProfile] = {}

    # ---- read ----

    def get_profile(self, agent_id: str) -> Optional[AgentProfile]:
        """Load a profile from disk (cached after first read)."""
        if agent_id in self._cache:
            return self._cache[agent_id]

        profile_path = self.base_path / f"{agent_id}.json"
        if not profile_path.exists():
            return None

        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            profile = AgentProfile.from_dict(data)
            self._cache[agent_id] = profile
            return profile
        except Exception as e:
            logger.error("Failed to load profile %s: %s", agent_id, e)
            return None

    def get_or_create_profile(
        self,
        agent_id: str,
        initial_xp: int = 1000,
        initial_tp: int = 50,
    ) -> AgentProfile:
        """Return existing profile or create a new one with *initial_xp* / *initial_tp*."""
        profile = self.get_profile(agent_id)
        if profile is None:
            profile = AgentProfile(agent_id=agent_id, xp=initial_xp, tp=initial_tp)
            self.save_profile(profile)
            logger.info("Created new profile: %s (xp=%d, tp=%d)", agent_id, initial_xp, initial_tp)
        return profile

    def list_all_profiles(self) -> Dict[str, AgentProfile]:
        """Load every ``*.json`` profile under the storage directory."""
        profiles: Dict[str, AgentProfile] = {}
        for path in self.base_path.glob("*.json"):
            agent_id = path.stem
            profile = self.get_profile(agent_id)
            if profile is not None:
                profiles[agent_id] = profile
        return profiles

    # ---- write ----

    def save_profile(self, profile: AgentProfile) -> None:
        """Persist *profile* to disk and update the in-memory cache."""
        profile_path = self.base_path / f"{profile.agent_id}.json"
        try:
            profile_path.write_text(
                json.dumps(profile.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._cache[profile.agent_id] = profile
        except Exception as e:
            logger.error("Failed to save profile %s: %s", profile.agent_id, e)
            raise
