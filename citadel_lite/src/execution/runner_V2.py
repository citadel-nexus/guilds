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
import subprocess
import shlex
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List

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

def _should_execute_verify() -> bool:
    """
    Verification commands can be dangerous (install, rm, network).
    Default: do NOT execute; produce a deterministic simulated result.
    Enable execution explicitly with CITADEL_VERIFY_EXECUTE=1.
    """
    return os.environ.get("CITADEL_VERIFY_EXECUTE", "").strip() in ("1", "true", "True", "yes", "YES")

def _run_verification_steps(
    steps: List[str],
    *,
    cwd: Optional[str] = None,
    timeout_s: int = 30,
    simulated_default: bool = True,
) -> List[Dict[str, Any]]:
    """
    Run (or simulate) verification steps and return structured results.
    Always deterministic in structure; includes simulated flag.
    """
    results: List[Dict[str, Any]] = []
    do_exec = _should_execute_verify()
    for i, cmd in enumerate(steps or [], start=1):
        cmd_str = str(cmd)
        if not cmd_str.strip():
            continue

        if not do_exec and simulated_default:
            results.append({
                "index": i,
                "command": cmd_str,
                "success": True,
                "returncode": 0,
                "stdout": "[SIMULATED] verification not executed (CITADEL_VERIFY_EXECUTE!=1)",
                "stderr": "",
                "duration_ms": 0,
                "simulated": True,
            })
            continue

        # Execute (explicitly enabled)
        started = datetime.now(timezone.utc)
        try:
            # Use shell=False for safety; split command
            args = shlex.split(cmd_str)
            p = subprocess.run(
                args,
                cwd=cwd or None,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            ended = datetime.now(timezone.utc)
            dur_ms = int((ended - started).total_seconds() * 1000)
            results.append({
                "index": i,
                "command": cmd_str,
                "success": (p.returncode == 0),
                "returncode": int(p.returncode),
                "stdout": (p.stdout or "")[:8000],
                "stderr": (p.stderr or "")[:8000],
                "duration_ms": dur_ms,
                "simulated": False,
            })
        except subprocess.TimeoutExpired as e:
            ended = datetime.now(timezone.utc)
            dur_ms = int((ended - started).total_seconds() * 1000)
            results.append({
                "index": i,
                "command": cmd_str,
                "success": False,
                "returncode": None,
                "stdout": (getattr(e, "stdout", "") or "")[:8000],
                "stderr": f"Timeout after {timeout_s}s",
                "duration_ms": dur_ms,
                "simulated": False,
            })
        except Exception as e:
            ended = datetime.now(timezone.utc)
            dur_ms = int((ended - started).total_seconds() * 1000)
            results.append({
                "index": i,
                "command": cmd_str,
                "success": False,
                "returncode": None,
                "stdout": "",
                "stderr": f"{type(e).__name__}: {e}",
                "duration_ms": dur_ms,
                "simulated": False,
            })
    return results

def _write_verify_results(event: EventJsonV1, verify_results: List[Dict[str, Any]]) -> str:
    """
    Persist verify results to out/<event_id>/verify_results.json and return relative path.
    """
    base = Path("out") / event.event_id
    base.mkdir(parents=True, exist_ok=True)
    path = base / "verify_results.json"
    payload = {
        "schema_version": "verify_results_v0",
        "event_id": event.event_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": verify_results,
        "all_success": all(bool(r.get("success")) for r in verify_results) if verify_results else False,
        "simulated": any(bool(r.get("simulated")) for r in verify_results) if verify_results else True,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path.as_posix())

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

        # VERIFY: generate verification results (simulated by default)
        verification_steps = fix_plan.get("verification_steps") or []
        verify_results = _run_verification_steps(
            list(verification_steps) if isinstance(verification_steps, list) else [],
            cwd=None,
            timeout_s=int(os.environ.get("CITADEL_VERIFY_TIMEOUT_S", "30") or "30"),
            simulated_default=True,
        )
        verify_path = _write_verify_results(event, verify_results) if verify_results is not None else ""


        action_data = {
            "planned_action": fix_plan.get("fix_plan", "unknown"),
            "patch": fix_plan.get("patch"),
            "risk_estimate": fix_plan.get("risk_estimate"),
            "decision_action": decision.action,
            "backend": "local",
            "verification_steps": verification_steps,
            "verify_results_path": verify_path,
            "verify_all_success": all(bool(r.get("success")) for r in verify_results) if verify_results else False,

        }
        (base / "execution_action.json").write_text(
            json.dumps(action_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return ExecutionOutcome(
            event_id=event.event_id,
            action_taken="write_action_json",
            success=True,
            details=(
                "Action plan written to out/ (local mode). "
                f"VERIFY results written to {verify_path or 'out/<event_id>/verify_results.json'} "
                f"(simulated={not _should_execute_verify()})."
            ),
        )


# ---------- Dry Run Backend ----------

class DryRunExecutionBackend(ExecutionBackend):
    """Logs what would happen without doing anything."""

    def execute(self, decision: Decision, fix_plan: Dict[str, Any], event: EventJsonV1) -> ExecutionOutcome:
        action = fix_plan.get("fix_plan", "no plan")
        patch = fix_plan.get("patch")
        verification_steps = fix_plan.get("verification_steps") or []
        verify_results = _run_verification_steps(
            list(verification_steps) if isinstance(verification_steps, list) else [],
            cwd=None,
            timeout_s=int(os.environ.get("CITADEL_VERIFY_TIMEOUT_S", "30") or "30"),
            simulated_default=True,
        )
        verify_path = _write_verify_results(event, verify_results) if verify_results is not None else ""

        details_parts = [
            f"[DRY RUN] Would execute: {action}",
            f"  repo: {event.repo}",
            f"  ref: {event.ref}",
            f"  risk: {decision.risk_score}",
        ]
        if patch:
            details_parts.append(f"  patch: {patch[:200]}")

        if verification_steps:
            details_parts.append(f"  verification_steps: {len(verification_steps)} step(s)")
            details_parts.append(f"  verify_results_path: {verify_path}")

        details = "\n".join(details_parts)
        print(details)

        return ExecutionOutcome(
            event_id=event.event_id,
            action_taken="dry_run",
            success=True,
            details=details,
        )


# ---------- GitLab Backend ----------

class GitLabExecutionBackend(ExecutionBackend):
    """
    Creates a Merge Request via the GitLab REST API v4 (src/gitlab/client.py).
    Requires GITLAB_TOKEN and GITLAB_URL in .env or environment.
    Falls back to LocalExecutionBackend if credentials are not configured.
    """

    def __init__(self) -> None:
        from src.gitlab.client import GitLabClient
        self._client = GitLabClient()

    def execute(self, decision: Decision, fix_plan: Dict[str, Any], event: EventJsonV1) -> ExecutionOutcome:
        repo = event.repo
        ref = event.ref or "main"
        patch = fix_plan.get("patch")
        plan_text = fix_plan.get("fix_plan", "automated fix")

        if not repo:
            return ExecutionOutcome(
                event_id=event.event_id,
                action_taken="gitlab_mr",
                success=False,
                details="No repo specified in event",
            )

        # VERIFY: create verify_results.json (simulated by default)
        verification_steps = fix_plan.get("verification_steps") or []
        verify_results = _run_verification_steps(
            list(verification_steps) if isinstance(verification_steps, list) else [],
            cwd=None,
            timeout_s=int(os.environ.get("CITADEL_VERIFY_TIMEOUT_S", "30") or "30"),
            simulated_default=True,
        )
        verify_path = _write_verify_results(event, verify_results) if verify_results is not None else ""

        if not self._client.is_available():
            return LocalExecutionBackend().execute(decision, fix_plan, event)

        try:
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

            body = (
                f"## Automated Fix by Citadel Lite\n\n"
                f"**Event:** `{event.event_id}`\n"
                f"**Type:** {event.event_type}\n"
                f"**Diagnosis:** {plan_text}\n"
                f"**Risk Score:** {decision.risk_score}\n\n"
                f"Applied automatically by the Citadel Lite Agentic DevOps pipeline.\n"
            )

            result = self._client.create_fix_mr(
                namespace_path=repo,
                base_branch=ref,
                title=f"fix: {plan_text[:60]}",
                body=body,
                files={"citadel-fix-notes.md": fix_notes},
            )

            if result.success:
                return ExecutionOutcome(
                    event_id=event.event_id,
                    action_taken="gitlab_mr_created",
                    success=True,
                    details=f"MR created: {result.mr_url} | verify_results_path: {verify_path}",
                    pr_url=result.mr_url,
                )
            else:
                return ExecutionOutcome(
                    event_id=event.event_id,
                    action_taken="gitlab_mr",
                    success=False,
                    details=f"GitLab MR creation failed: {result.error}",
                )

        except Exception as e:
            return ExecutionOutcome(
                event_id=event.event_id,
                action_taken="gitlab_mr",
                success=False,
                details=f"GitLab execution failed: {e}",
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

        # VERIFY: create verify_results.json for audit linkage (simulated by default).
        verification_steps = fix_plan.get("verification_steps") or []
        verify_results = _run_verification_steps(
            list(verification_steps) if isinstance(verification_steps, list) else [],
            cwd=None,
            timeout_s=int(os.environ.get("CITADEL_VERIFY_TIMEOUT_S", "30") or "30"),
            simulated_default=True,
        )
        verify_path = _write_verify_results(event, verify_results) if verify_results is not None else ""


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
                    details=f"PR created: {result.pr_url} | verify_results_path: {verify_path}",
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
    "gitlab": GitLabExecutionBackend,
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
