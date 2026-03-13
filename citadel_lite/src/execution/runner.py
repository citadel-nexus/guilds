# src/execution/runner.py
"""
Execution layer that closes the demo loop.

Supports three backends:
- local:    writes action JSON to out/ (no real execution)
- dry_run:  logs what would happen without doing it
- github:   creates PR via GitHub API, retriggers CI

Selected via EXECUTION_MODE env var (default: local).
"""
from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.types import EventJsonV1, Decision


@dataclass
class ExecutionOutcome:
    """Result of executing a fix action."""
    event_id: str = ""
    action_taken: str = ""
    success: bool = False
    details: str = ""
    pr_url: Optional[str] = None
    ci_run_id: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------- Backend ABC ----------

class ExecutionBackend(ABC):
    @abstractmethod
    def execute(
        self,
        decision: Decision,
        fix_plan: Dict[str, Any],
        event: EventJsonV1,
    ) -> ExecutionOutcome:
        ...


# ---------- Local Backend ----------

class LocalExecutionBackend(ExecutionBackend):
    """Writes action JSON to out/ directory. No real execution."""

    def execute(self, decision: Decision, fix_plan: Dict[str, Any], event: EventJsonV1) -> ExecutionOutcome:
        base = Path("out") / event.event_id
        base.mkdir(parents=True, exist_ok=True)

        action_data = {
            "planned_action": fix_plan.get("fix_plan", "unknown"),
            "patch": fix_plan.get("patch"),
            "risk_estimate": fix_plan.get("risk_estimate"),
            "decision_action": decision.action,
            "backend": "local",
        }
        (base / "execution_action.json").write_text(
            json.dumps(action_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return ExecutionOutcome(
            event_id=event.event_id,
            action_taken="write_action_json",
            success=True,
            details="Action plan written to out/ (local mode, no real execution)",
        )


# ---------- Dry Run Backend ----------

class DryRunExecutionBackend(ExecutionBackend):
    """Logs what would happen without doing anything."""

    def execute(self, decision: Decision, fix_plan: Dict[str, Any], event: EventJsonV1) -> ExecutionOutcome:
        action = fix_plan.get("fix_plan", "no plan")
        patch = fix_plan.get("patch")
        details_parts = [
            f"[DRY RUN] Would execute: {action}",
            f"  repo: {event.repo}",
            f"  ref: {event.ref}",
            f"  risk: {decision.risk_score}",
        ]
        if patch:
            details_parts.append(f"  patch: {patch[:200]}")

        details = "\n".join(details_parts)
        print(details)

        return ExecutionOutcome(
            event_id=event.event_id,
            action_taken="dry_run",
            success=True,
            details=details,
        )


# ---------- GitHub Backend ----------

class GitHubExecutionBackend(ExecutionBackend):
    """
    Creates a PR via the GitHub REST API client (src/github/client.py).
    Requires GITHUB_TOKEN in citadel.config.yaml or environment.
    Falls back to LocalExecutionBackend if token is not configured.
    """

    def __init__(self) -> None:
        from src.github.client import GitHubClient
        self._client = GitHubClient()

    def execute(self, decision: Decision, fix_plan: Dict[str, Any], event: EventJsonV1) -> ExecutionOutcome:
        repo = event.repo
        ref = event.ref or "main"
        patch = fix_plan.get("patch")
        plan_text = fix_plan.get("fix_plan", "automated fix")

        if not repo:
            return ExecutionOutcome(
                event_id=event.event_id,
                action_taken="github_pr",
                success=False,
                details="No repo specified in event",
            )

        if not self._client.is_available():
            return LocalExecutionBackend().execute(decision, fix_plan, event)

        try:
            # Build files to commit
            fix_notes = (
                f"# Citadel Lite Automated Fix\n\n"
                f"**Event:** `{event.event_id}`\n"
                f"**Type:** {event.event_type}\n"
                f"**Diagnosis:** {plan_text}\n"
                f"**Risk Score:** {decision.risk_score}\n\n"
            )
            if patch:
                fix_notes += f"## Proposed Patch\n\n```\n{patch}\n```\n"
            else:
                fix_notes += "Manual review required — no automated patch generated.\n"

            files = {"citadel-fix-notes.md": fix_notes}

            body = (
                f"## Automated Fix by Citadel Lite\n\n"
                f"**Event:** `{event.event_id}`\n"
                f"**Type:** {event.event_type}\n"
                f"**Diagnosis:** {plan_text}\n"
                f"**Risk Score:** {decision.risk_score}\n\n"
                f"Applied automatically by the Citadel Lite Agentic DevOps pipeline.\n"
            )

            result = self._client.create_fix_pr(
                repo=repo,
                base_branch=ref,
                title=f"fix: {plan_text[:60]}",
                body=body,
                files=files,
            )

            if result.success:
                ci_run_id = None
                try:
                    latest = self._client.get_latest_workflow_run(repo)
                    if latest.run_id and latest.conclusion == "failure":
                        self._client.rerun_workflow(repo, latest.run_id)
                        ci_run_id = str(latest.run_id)
                except Exception:
                    pass

                return ExecutionOutcome(
                    event_id=event.event_id,
                    action_taken="github_pr_created",
                    success=True,
                    details=f"PR created: {result.pr_url}",
                    pr_url=result.pr_url,
                    ci_run_id=ci_run_id,
                )
            else:
                return ExecutionOutcome(
                    event_id=event.event_id,
                    action_taken="github_pr",
                    success=False,
                    details=f"GitHub PR creation failed: {result.error}",
                )

        except Exception as e:
            return ExecutionOutcome(
                event_id=event.event_id,
                action_taken="github_pr",
                success=False,
                details=f"GitHub execution failed: {e}",
            )


# ---------- Runner (facade) ----------

_BACKENDS = {
    "local": LocalExecutionBackend,
    "dry_run": DryRunExecutionBackend,
    "github": GitHubExecutionBackend,
}


class ExecutionRunner:
    """
    Facade that selects the execution backend from EXECUTION_MODE env var.
    """

    def __init__(self, mode: Optional[str] = None) -> None:
        self.mode = mode or os.environ.get("EXECUTION_MODE", "local")
        backend_cls = _BACKENDS.get(self.mode, LocalExecutionBackend)
        self._backend = backend_cls()

    def execute(
        self,
        decision: Decision,
        fix_plan: Dict[str, Any],
        event: EventJsonV1,
    ) -> ExecutionOutcome:
        return self._backend.execute(decision, fix_plan, event)
