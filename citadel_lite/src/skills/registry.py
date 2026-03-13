# src/skills/registry.py
"""
Agent Skills Registry with execution history tracking.

Each agent advertises skills (capabilities + metadata). When a skill is invoked
during a pipeline run, the outcome is recorded in a history log. This enables:
- Skill-based routing (match incident to best-skilled agent)
- Performance tracking (success rate, avg latency per skill)
- Learning (Sherlock can reference past diagnosis accuracy)

Usage:
    from src.skills.registry import SkillRegistry
    reg = SkillRegistry()
    reg.register_skill("sentinel", "classify_ci_failure", ...)
    reg.record_execution("sentinel", "classify_ci_failure", event_id, success=True, ...)
    history = reg.get_history("sentinel", limit=20)
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

_HISTORY_PATH = Path(__file__).resolve().parent.parent.parent / "out" / "skill_history.jsonl"
_SKILLS_PATH = Path(__file__).resolve().parent / "skills.json"
_MAX_HISTORY_SIZE = 10000


@dataclass
class Skill:
    """A single agent skill declaration."""
    skill_id: str = ""
    agent_name: str = ""
    name: str = ""
    description: str = ""
    event_types: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    enabled: bool = True
    # Performance stats (computed from history)
    invocations: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillExecution:
    """Record of a single skill invocation."""
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    skill_id: str = ""
    agent_name: str = ""
    event_id: str = ""
    event_type: str = ""
    success: bool = True
    latency_ms: float = 0.0
    risk_score: float = 0.0
    outcome: str = ""
    error: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SkillRegistry:
    """
    Central registry for agent skills with execution history.
    Skills are defined declaratively; history is appended as JSONL.
    """

    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}  # skill_id -> Skill
        self._history: Deque[SkillExecution] = deque(maxlen=_MAX_HISTORY_SIZE)
        self._load_skills()
        self._load_history()

    # ---- Skills ----

    def _load_skills(self) -> None:
        """Load built-in skills and any custom skills from skills.json."""
        # Built-in skills
        builtins = [
            Skill(
                skill_id="sentinel.detect_classify",
                agent_name="sentinel",
                name="Detect & Classify",
                description="Signal extraction and event classification from CI/CD logs",
                event_types=["ci_failure", "deploy_failure", "infra_alert", "security_alert",
                             "rollback_needed", "performance_degradation", "test_failure"],
                tags=["detection", "classification", "signal_extraction"],
            ),
            Skill(
                skill_id="sentinel.severity_map",
                agent_name="sentinel",
                name="Severity Mapping",
                description="Map event signals to severity tier (low/medium/critical)",
                event_types=["*"],
                tags=["severity", "triage"],
            ),
            Skill(
                skill_id="sherlock.root_cause",
                agent_name="sherlock",
                name="Root Cause Analysis",
                description="Memory-aware diagnosis with confidence scoring",
                event_types=["ci_failure", "deploy_failure", "test_failure"],
                tags=["diagnosis", "root_cause", "memory_aware"],
            ),
            Skill(
                skill_id="sherlock.security_analysis",
                agent_name="sherlock",
                name="Security Analysis",
                description="Analyze security alerts for vulnerability assessment",
                event_types=["security_alert"],
                tags=["security", "vulnerability", "cve"],
            ),
            Skill(
                skill_id="sherlock.performance_profile",
                agent_name="sherlock",
                name="Performance Profiling",
                description="Analyze performance degradation patterns",
                event_types=["performance_degradation", "infra_alert"],
                tags=["performance", "profiling", "latency"],
            ),
            Skill(
                skill_id="fixer.patch_proposal",
                agent_name="fixer",
                name="Patch Proposal",
                description="Generate fix patches with variable risk assessment",
                event_types=["ci_failure", "deploy_failure", "test_failure"],
                tags=["fix", "patch", "code_change"],
            ),
            Skill(
                skill_id="fixer.dependency_fix",
                agent_name="fixer",
                name="Dependency Fix",
                description="Resolve missing or vulnerable dependencies",
                event_types=["ci_failure", "security_alert"],
                tags=["dependency", "requirements", "package"],
            ),
            Skill(
                skill_id="fixer.config_fix",
                agent_name="fixer",
                name="Configuration Fix",
                description="Fix environment variables, secrets, and config issues",
                event_types=["deploy_failure", "infra_alert"],
                tags=["config", "env_var", "secrets"],
            ),
            Skill(
                skill_id="guardian.risk_gate",
                agent_name="guardian",
                name="Risk Gate",
                description="Multi-factor governance with policy engine + responsible AI",
                event_types=["*"],
                tags=["governance", "risk", "compliance"],
            ),
            Skill(
                skill_id="guardian.approval_routing",
                agent_name="guardian",
                name="Approval Routing",
                description="Route decisions to human approval via Slack/Teams/portal",
                event_types=["*"],
                tags=["approval", "human_in_loop"],
            ),
        ]

        for s in builtins:
            self._skills[s.skill_id] = s

        # Load custom skills from JSON
        if _SKILLS_PATH.exists():
            try:
                custom = json.loads(_SKILLS_PATH.read_text(encoding="utf-8"))
                for entry in custom:
                    s = Skill(**entry)
                    self._skills[s.skill_id] = s
            except Exception as e:
                logger.warning("Failed to load custom skills: %s", e)

    # ---- History ----

    def _load_history(self) -> None:
        if not _HISTORY_PATH.exists():
            return
        try:
            lines = _HISTORY_PATH.read_text(encoding="utf-8").strip().split("\n")
            # Only load the most recent entries to bound memory usage
            for line in lines[-_MAX_HISTORY_SIZE:]:
                if line.strip():
                    self._history.append(SkillExecution(**json.loads(line)))
        except Exception as e:
            logger.warning("Failed to load skill history: %s", e)

        # Update skill stats from history
        self._recompute_stats()

    def _recompute_stats(self) -> None:
        """Recompute per-skill performance stats from history."""
        from collections import defaultdict
        counts: Dict[str, List[SkillExecution]] = defaultdict(list)
        for ex in self._history:
            counts[ex.skill_id].append(ex)

        for skill_id, execs in counts.items():
            skill = self._skills.get(skill_id)
            if not skill:
                continue
            skill.invocations = len(execs)
            skill.success_rate = sum(1 for e in execs if e.success) / max(len(execs), 1)
            latencies = [e.latency_ms for e in execs if e.latency_ms > 0]
            skill.avg_latency_ms = sum(latencies) / max(len(latencies), 1) if latencies else 0.0

    # ---- Public API ----

    def register_skill(self, skill: Skill) -> None:
        self._skills[skill.skill_id] = skill

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def list_skills(self, agent_name: Optional[str] = None) -> List[Skill]:
        skills = list(self._skills.values())
        if agent_name:
            skills = [s for s in skills if s.agent_name == agent_name]
        return skills

    def skills_for_event(self, event_type: str) -> List[Skill]:
        """Find all skills that handle a given event type."""
        return [
            s for s in self._skills.values()
            if s.enabled and (event_type in s.event_types or "*" in s.event_types)
        ]

    def record_execution(
        self,
        skill_id: str,
        agent_name: str,
        event_id: str,
        event_type: str = "",
        success: bool = True,
        latency_ms: float = 0.0,
        risk_score: float = 0.0,
        outcome: str = "",
        error: Optional[str] = None,
    ) -> SkillExecution:
        """Record a skill execution and update stats."""
        ex = SkillExecution(
            skill_id=skill_id,
            agent_name=agent_name,
            event_id=event_id,
            event_type=event_type,
            success=success,
            latency_ms=latency_ms,
            risk_score=risk_score,
            outcome=outcome,
            error=error,
        )
        self._history.append(ex)

        # Append to JSONL
        try:
            _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_HISTORY_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(ex.to_dict()) + "\n")
        except Exception as e:
            logger.warning("Failed to write skill history: %s", e)

        # Update stats
        skill = self._skills.get(skill_id)
        if skill:
            skill.invocations += 1
            if success:
                n = skill.invocations
                skill.success_rate = ((skill.success_rate * (n - 1)) + 1.0) / n
            else:
                n = skill.invocations
                skill.success_rate = (skill.success_rate * (n - 1)) / n

        return ex

    def get_history(
        self,
        agent_name: Optional[str] = None,
        skill_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[SkillExecution]:
        """Get execution history, optionally filtered."""
        results = self._history
        if agent_name:
            results = [e for e in results if e.agent_name == agent_name]
        if skill_id:
            results = [e for e in results if e.skill_id == skill_id]
        return results[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Summary statistics for all skills."""
        total = len(self._history)
        successes = sum(1 for e in self._history if e.success)
        return {
            "total_executions": total,
            "success_rate": successes / max(total, 1),
            "skills_registered": len(self._skills),
            "agents_with_skills": len(set(s.agent_name for s in self._skills.values())),
        }
