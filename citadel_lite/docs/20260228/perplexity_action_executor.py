#!/usr/bin/env python3
"""
perplexity_action_executor.py — Bidirectional GitLab + Linear Action Executor
===============================================================================
Reads diagnostic state from all sources (GitLab, DV health, KB freshness),
builds a prioritised action plan, and executes each action against the
correct downstream system.

Bidirectional GitLab integration:
  READ  → gitlab_diagnostic_source.build_gitlab_diagnostic()
            pipeline status + job traces + MR health + issue label state
  WRITE → CREATE/COMMENT/CLOSE GitLab issues, COMMENT MRs, RETRY pipelines
  CLOSE → Auto-close loop-managed issues when effectiveness scorer resolves them

Usage:
    python tools/perplexity_action_executor.py --dry-run
    python tools/perplexity_action_executor.py --run
    python tools/perplexity_action_executor.py --run --cycle-id EVO-2026-042

SRS: PAE-001
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import requests

# ── Env ──────────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from vault_loader import bootstrap as _vault_bootstrap; _vault_bootstrap()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("action_executor")

# ── Config ────────────────────────────────────────────────────────────────────
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
GITLAB_TOKEN = (
    os.environ.get("GITLAB_ADMIN_TOKEN")
    or os.environ.get("GITLAB_TOKEN_AUTOMATION")
    or os.environ.get("GITLAB_TOKEN", "")
)
PROJECT_ID = os.environ.get("GITLAB_PROJECT_ID", "75")

LINEAR_TOKEN = os.environ.get("LINEAR_API_KEY") or os.environ.get("LINEAR_API_TOKEN", "")
LINEAR_TEAM_ID = os.environ.get("LINEAR_TEAM_ID", "")

# Label convention for loop-managed GitLab issues
LABEL_BLOCKER = "auto-blocker"
LABEL_LOOP    = "perplexity-loop"


# ═══════════════════════════════════════════════════════════════
# ACTION TYPE REGISTRY
# ═══════════════════════════════════════════════════════════════

class ActionType(str, Enum):
    # GitLab write actions
    CREATE_GITLAB_ISSUE      = "CREATE_GITLAB_ISSUE"
    CLOSE_GITLAB_ISSUE       = "CLOSE_GITLAB_ISSUE"
    COMMENT_GITLAB_ISSUE     = "COMMENT_GITLAB_ISSUE"
    CREATE_GITLAB_MR_COMMENT = "CREATE_GITLAB_MR_COMMENT"
    RETRY_GITLAB_PIPELINE    = "RETRY_GITLAB_PIPELINE"
    # Linear write actions
    CREATE_LINEAR_ISSUE      = "CREATE_LINEAR_ISSUE"
    # Internal triggers
    TRIGGER_CONTEXT_REDISTILL = "TRIGGER_CONTEXT_REDISTILL"
    TRIGGER_KB_RESYNC         = "TRIGGER_KB_RESYNC"


# ═══════════════════════════════════════════════════════════════
# GITLAB HELPERS
# ═══════════════════════════════════════════════════════════════

def _gl_headers() -> dict:
    return {"PRIVATE-TOKEN": GITLAB_TOKEN, "Content-Type": "application/json"}


def _gl_post(path: str, payload: dict) -> dict | None:
    try:
        r = requests.post(
            f"{GITLAB_URL}/api/v4{path}",
            headers=_gl_headers(), json=payload, timeout=15,
        )
        if r.status_code in (400, 401, 403, 404):
            log.warning("[GL:write] POST %s → HTTP %s: %s",
                        path, r.status_code, r.text[:200])
            return None
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.warning("[GL:write] POST %s failed: %s", path, exc)
        return None


def _gl_put(path: str, payload: dict) -> dict | None:
    try:
        r = requests.put(
            f"{GITLAB_URL}/api/v4{path}",
            headers=_gl_headers(), json=payload, timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.warning("[GL:write] PUT %s failed: %s", path, exc)
        return None


# ═══════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════

def execute_create_gitlab_issue(action: dict, dry_run: bool = True) -> dict:
    title       = action.get("title", "(no title)")
    description = action.get("description", "")
    labels      = action.get("labels", [LABEL_LOOP, LABEL_BLOCKER])
    priority    = action.get("priority", "")

    if dry_run:
        return {"status": "dry_run", "title": title, "labels": labels}

    issue = _gl_post(f"/projects/{PROJECT_ID}/issues", {
        "title":       title,
        "description": description,
        "labels":      ",".join(labels),
    })
    if issue:
        log.info("[GL:write] Created issue #%s: %s", issue.get("iid"), title[:60])
        return {"status": "created", "iid": issue.get("iid"), "url": issue.get("web_url", "")}
    return {"status": "failed", "title": title}


def execute_close_gitlab_issue(action: dict, dry_run: bool = True) -> dict:
    iid    = action.get("issue_iid")
    reason = action.get("resolution_reason", "Resolved by perplexity loop")

    if dry_run:
        return {"status": "dry_run", "would_close": iid, "reason": reason}

    # Add closing comment first
    _gl_post(f"/projects/{PROJECT_ID}/issues/{iid}/notes",
             {"body": f"**Auto-closed by perplexity loop**\n\n{reason}"})

    result = _gl_put(f"/projects/{PROJECT_ID}/issues/{iid}",
                     {"state_event": "close"})
    if result:
        log.info("[GL:write] Closed issue #%s", iid)
        return {"status": "closed", "iid": iid}
    return {"status": "failed", "iid": iid}


def execute_comment_gitlab_issue(action: dict, dry_run: bool = True) -> dict:
    iid  = action.get("issue_iid")
    body = action.get("comment_body", "")

    if dry_run:
        return {"status": "dry_run", "would_comment": iid, "preview": body[:200]}

    result = _gl_post(f"/projects/{PROJECT_ID}/issues/{iid}/notes", {"body": body})
    if result:
        log.info("[GL:write] Commented on issue #%s (note %s)", iid, result.get("id"))
        return {"status": "commented", "iid": iid, "note_id": result.get("id")}
    return {"status": "failed", "iid": iid}


def execute_create_gitlab_mr_comment(action: dict, dry_run: bool = True) -> dict:
    mr_iid = action.get("mr_iid")
    body   = action.get("comment_body", "")

    if dry_run:
        return {"status": "dry_run", "would_comment_mr": mr_iid}

    result = _gl_post(f"/projects/{PROJECT_ID}/merge_requests/{mr_iid}/notes",
                      {"body": body})
    if result:
        log.info("[GL:write] Commented on MR !%s", mr_iid)
        return {"status": "commented", "mr_iid": mr_iid, "note_id": result.get("id")}
    return {"status": "failed", "mr_iid": mr_iid}


def execute_retry_gitlab_pipeline(action: dict, dry_run: bool = True) -> dict:
    pipeline_id  = action.get("pipeline_id")
    consecutive  = action.get("consecutive_failures", 0)

    if consecutive >= 3:
        log.warning("[GL:write] Skip retry — %d consecutive failures, needs manual fix",
                    consecutive)
        return {"status": "skipped",
                "reason": f"{consecutive} consecutive failures — manual intervention needed"}

    if dry_run:
        return {"status": "dry_run", "would_retry": pipeline_id}

    try:
        r = requests.post(
            f"{GITLAB_URL}/api/v4/projects/{PROJECT_ID}/pipelines/{pipeline_id}/retry",
            headers=_gl_headers(), timeout=15,
        )
        r.raise_for_status()
        new_id = r.json().get("id")
        log.info("[GL:write] Retried pipeline %s → new pipeline %s", pipeline_id, new_id)
        return {"status": "retried", "old_pipeline_id": pipeline_id,
                "new_pipeline_id": new_id}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def execute_create_linear_issue(action: dict, dry_run: bool = True) -> dict:
    if not LINEAR_TOKEN or not LINEAR_TEAM_ID:
        return {"status": "skipped", "reason": "LINEAR_API_KEY or LINEAR_TEAM_ID not set"}

    title       = action.get("title", "(no title)")
    description = action.get("description", "")
    priority    = {"P0": 1, "P1": 1, "P2": 2, "P3": 3}.get(
        action.get("priority", ""), 2)

    if dry_run:
        return {"status": "dry_run", "title": title, "priority": priority}

    query = """
    mutation CreateIssue($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue { id identifier url title }
      }
    }
    """
    variables = {"input": {
        "title":       title,
        "description": description,
        "teamId":      LINEAR_TEAM_ID,
        "priority":    priority,
    }}
    try:
        r = requests.post(
            "https://api.linear.app/graphql",
            headers={"Authorization": LINEAR_TOKEN, "Content-Type": "application/json"},
            json={"query": query, "variables": variables},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        issue = data.get("data", {}).get("issueCreate", {}).get("issue", {})
        if issue:
            log.info("[Linear:write] Created %s: %s", issue.get("identifier"), title[:60])
            return {"status": "created", "id": issue.get("identifier"),
                    "url": issue.get("url", "")}
        return {"status": "failed", "errors": data.get("errors")}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def execute_trigger_context_redistill(action: dict, dry_run: bool = True) -> dict:
    if dry_run:
        return {"status": "dry_run", "action": "trigger_context_redistill"}
    log.info("[executor] Context redistill triggered (implement via citadel_rehydrator)")
    return {"status": "triggered", "note": "wire to citadel_rehydrator --pull"}


def execute_trigger_kb_resync(action: dict, dry_run: bool = True) -> dict:
    if dry_run:
        return {"status": "dry_run", "action": "trigger_kb_resync"}
    log.info("[executor] KB resync triggered")
    return {"status": "triggered"}


EXECUTORS: dict[ActionType, Any] = {
    ActionType.CREATE_GITLAB_ISSUE:       execute_create_gitlab_issue,
    ActionType.CLOSE_GITLAB_ISSUE:        execute_close_gitlab_issue,
    ActionType.COMMENT_GITLAB_ISSUE:      execute_comment_gitlab_issue,
    ActionType.CREATE_GITLAB_MR_COMMENT:  execute_create_gitlab_mr_comment,
    ActionType.RETRY_GITLAB_PIPELINE:     execute_retry_gitlab_pipeline,
    ActionType.CREATE_LINEAR_ISSUE:       execute_create_linear_issue,
    ActionType.TRIGGER_CONTEXT_REDISTILL: execute_trigger_context_redistill,
    ActionType.TRIGGER_KB_RESYNC:         execute_trigger_kb_resync,
}


# ═══════════════════════════════════════════════════════════════
# DIAGNOSTIC ASSEMBLY
# ═══════════════════════════════════════════════════════════════

def build_diagnostic_payload(raw_input: dict | None = None) -> dict:
    """
    Assemble full diagnostic from all sources.
    GitLab is a first-class source alongside any raw telemetry passed in.
    """
    payload: dict = dict(raw_input or {})
    payload.setdefault("blockers", [])
    payload.setdefault("resolved", [])

    # ── GitLab ───────────────────────────────────────────────
    try:
        from gitlab_diagnostic_source import build_gitlab_diagnostic
        gl = build_gitlab_diagnostic()
        payload["gitlab"] = gl
        payload["blockers"].extend(gl.get("blockers", []))
        payload["resolved"].extend(gl.get("resolved", []))
        log.info("[diag] GitLab: score=%d blockers=%d resolved=%d",
                 gl.get("gitlab_health_score", 0),
                 len(gl.get("blockers", [])),
                 len(gl.get("resolved", [])))
    except Exception as exc:
        log.warning("[diag] GitLab read failed: %s", exc)
        payload["gitlab"] = {"error": str(exc), "gitlab_health_score": 0}

    return payload


# ═══════════════════════════════════════════════════════════════
# ACTION PLAN BUILDER
# ═══════════════════════════════════════════════════════════════

def _blocker_to_issue_payload(blocker: dict) -> dict:
    source = blocker.get("source", "unknown")
    sev    = blocker.get("severity", "medium")
    title  = blocker.get("title", "(unknown blocker)")
    detail = blocker.get("detail", "")
    url    = blocker.get("web_url", "")
    trace  = blocker.get("trace_tail", "")

    priority = {"high": "P1", "medium": "P2", "low": "P3"}.get(sev, "P2")
    body_parts = [f"**Source:** `{source}`\n**Severity:** {sev}"]
    if detail:
        body_parts.append(f"**Detail:** {detail}")
    if url:
        body_parts.append(f"**Link:** {url}")
    if trace:
        body_parts.append(f"\n```\n{trace[:1000]}\n```")
    body_parts.append("\n_Auto-generated by perplexity_action_executor_")

    return {
        "title":       f"[Auto-{sev.upper()}] {title[:100]}",
        "description": "\n\n".join(body_parts),
        "labels":      [LABEL_LOOP, LABEL_BLOCKER],
        "priority":    priority,
    }


def build_action_plan(
    diagnostics: dict,
    health_score: int = 100,
    prev_ledger: dict | None = None,
) -> list[dict]:
    """
    Build a prioritised action list from diagnostic state.
    Returns list of {type: ActionType, ...} dicts for execute_plan().
    """
    actions: list[dict] = []
    gl        = diagnostics.get("gitlab", {})
    pipeline  = gl.get("pipeline", {})
    mrs       = gl.get("merge_requests", {})
    issues    = gl.get("issues", {})

    # ── 1. Pipeline failure ──────────────────────────────────
    if pipeline.get("status") == "failed":
        consecutive = pipeline.get("consecutive_failures", 0)

        # Auto-retry if transient (< 3 consecutive)
        if consecutive < 3:
            actions.append({
                "type":                ActionType.RETRY_GITLAB_PIPELINE,
                "pipeline_id":         pipeline.get("pipeline_id"),
                "consecutive_failures": consecutive,
                "reason":              f"Auto-retry: {consecutive} consecutive failure(s)",
            })

        # Create an issue for each failed job
        for job in pipeline.get("failed_jobs", []):
            actions.append({
                "type":        ActionType.CREATE_GITLAB_ISSUE,
                "title":       f"[CI] Pipeline job '{job['name']}' failed (stage: {job['stage']})",
                "description": (
                    f"**Stage:** {job['stage']}\n"
                    f"**Failure reason:** {job.get('failure_reason', 'unknown')}\n"
                    f"**Pipeline:** {pipeline.get('web_url', '')}\n\n"
                    + (f"```\n{pipeline.get('job_traces', {}).get(job['name'], '')[:1200]}\n```"
                       if pipeline.get("job_traces", {}).get(job["name"]) else "")
                ),
                "labels":   [LABEL_LOOP, LABEL_BLOCKER, "pipeline-failure"],
                "priority": "P1" if consecutive >= 2 else "P2",
            })

    # ── 2. Stale MRs → nudge comments ───────────────────────
    for mr in mrs.get("stale_mrs", [])[:3]:
        actions.append({
            "type":         ActionType.CREATE_GITLAB_MR_COMMENT,
            "mr_iid":       mr["iid"],
            "comment_body": (
                f"**Perplexity Loop — Stale MR Alert**\n\n"
                f"This MR has been inactive for **{mr['age_days']} days**.\n"
                f"Please review, rebase, or close if no longer needed.\n\n"
                f"_Auto-generated by perplexity_action_executor_"
            ),
        })

    # ── 3. Conflicting MRs → alert comment ──────────────────
    for mr in mrs.get("conflict_mrs", []):
        actions.append({
            "type":         ActionType.CREATE_GITLAB_MR_COMMENT,
            "mr_iid":       mr["iid"],
            "comment_body": (
                f"**Merge Conflict Detected**\n\n"
                f"This MR has conflicts with the target branch. "
                f"Rebase required before merge.\n\n"
                f"_Auto-detected by perplexity_action_executor_"
            ),
        })

    # ── 4. Resolve closed loop issues (prev ledger comparison) ─
    if prev_ledger:
        prev_blockers = prev_ledger.get("blockers_at_execution", [])
        current_resolved_lower = [r.lower() for r in diagnostics.get("resolved", [])]
        effectiveness = prev_ledger.get("effectiveness", {})

        for blocker in prev_blockers:
            title_lower = blocker.get("title", "").lower()
            if any(title_lower in r or r in title_lower
                   for r in current_resolved_lower):
                for gi in issues.get("perplexity_loop_issues", []):
                    if (gi["title"].lower() in title_lower
                            or title_lower in gi["title"].lower()):
                        actions.append({
                            "type":               ActionType.CLOSE_GITLAB_ISSUE,
                            "issue_iid":          gi["iid"],
                            "resolution_reason": (
                                f"Blocker resolved: {blocker.get('title', '')}\n"
                                f"Health delta: +{diagnostics.get('health_delta', '?')}"
                            ),
                        })

        # Post effectiveness summary on still-open blocker issues
        if effectiveness.get("resolved", 0) > 0 or effectiveness.get("still_open", 0) > 0:
            for gi in issues.get("blocker_issues", [])[:3]:
                actions.append({
                    "type":         ActionType.COMMENT_GITLAB_ISSUE,
                    "issue_iid":    gi["iid"],
                    "comment_body": (
                        f"**Loop Effectiveness Update**\n\n"
                        f"- Resolved this cycle: {effectiveness.get('resolved', 0)}\n"
                        f"- Still open: {effectiveness.get('still_open', 0)}\n"
                        f"- Score delta: {effectiveness.get('score_delta', 0):+d}\n"
                        f"- Health: {diagnostics.get('health_label', '?')} "
                        f"({health_score}/100)\n\n"
                        f"_Cycle: {diagnostics.get('cycle_id', 'unknown')}_"
                    ),
                })

    # ── 5. Non-GitLab blockers → issue on both GL + Linear ──
    for blocker in diagnostics.get("blockers", []):
        if blocker.get("source", "").startswith("gitlab_"):
            continue  # already handled above
        payload = _blocker_to_issue_payload(blocker)
        actions.append({"type": ActionType.CREATE_GITLAB_ISSUE, **payload})
        actions.append({"type": ActionType.CREATE_LINEAR_ISSUE, **payload})

    log.info("[plan] %d actions planned (health=%d)", len(actions), health_score)
    return actions


# ═══════════════════════════════════════════════════════════════
# PLAN EXECUTOR
# ═══════════════════════════════════════════════════════════════

def execute_plan(
    actions: list[dict],
    dry_run: bool = True,
) -> list[dict]:
    """Execute each action in sequence. Returns results list."""
    results = []
    for action in actions:
        action_type_raw = action.get("type")
        try:
            action_type = ActionType(action_type_raw)
        except ValueError:
            log.warning("[executor] Unknown action type: %s", action_type_raw)
            results.append({"type": action_type_raw, "status": "unknown_type"})
            continue

        executor = EXECUTORS.get(action_type)
        if not executor:
            log.warning("[executor] No executor for %s", action_type)
            results.append({"type": action_type, "status": "no_executor"})
            continue

        try:
            result = executor(action, dry_run=dry_run)
            result["type"] = action_type.value
            results.append(result)
            mode = "DRY" if dry_run else "LIVE"
            log.info("[executor:%s] %s → %s", mode, action_type.value,
                     result.get("status", "?"))
        except Exception as exc:
            log.warning("[executor] %s failed: %s", action_type, exc)
            results.append({"type": action_type.value, "status": "error",
                            "error": str(exc)})

    return results


# ═══════════════════════════════════════════════════════════════
# LEDGER (persist action history for effectiveness scoring)
# ═══════════════════════════════════════════════════════════════

_LEDGER_DIR = Path.home() / ".citadel" / "executor_ledger"


def _load_prev_ledger(cycle_id: str) -> dict:
    path = _LEDGER_DIR / f"{cycle_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_ledger(cycle_id: str, entry: dict) -> None:
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    path = _LEDGER_DIR / f"{cycle_id}.json"
    path.write_text(json.dumps(entry, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def run(cycle_id: str, dry_run: bool = True) -> dict:
    t0 = time.time()
    log.info("=== Perplexity Action Executor — cycle=%s dry_run=%s ===",
             cycle_id, dry_run)

    prev_ledger = _load_prev_ledger(cycle_id)

    # 1. Assemble diagnostics
    diagnostics = build_diagnostic_payload({"cycle_id": cycle_id})
    gl_score = diagnostics.get("gitlab", {}).get("gitlab_health_score", 100)
    log.info("[run] GitLab health score: %d", gl_score)

    # 2. Build action plan
    actions = build_action_plan(diagnostics, health_score=gl_score,
                                prev_ledger=prev_ledger)

    # 3. Execute
    results = execute_plan(actions, dry_run=dry_run)

    summary = {
        "cycle_id":       cycle_id,
        "dry_run":        dry_run,
        "gl_health_score": gl_score,
        "actions_planned": len(actions),
        "actions_executed": len(results),
        "results":         results,
        "blockers_at_execution": diagnostics.get("blockers", []),
        "duration_sec":    round(time.time() - t0, 1),
        "ts":              datetime.now(timezone.utc).isoformat(),
    }

    if not dry_run:
        _save_ledger(cycle_id, summary)

    return summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Perplexity Action Executor — bidirectional GitLab + Linear integration")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="Show planned actions without executing")
    mode.add_argument("--run",     action="store_true",
                      help="Execute actions against real systems")
    ap.add_argument("--cycle-id", default=None,
                    help="Cycle ID for ledger (default: timestamp)")
    ap.add_argument("--json-out", default=None, metavar="FILE",
                    help="Write JSON summary to file")
    args = ap.parse_args()

    cycle_id = args.cycle_id or f"EVO-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    dry_run  = args.dry_run

    result = run(cycle_id=cycle_id, dry_run=dry_run)

    print(f"\n{'='*60}")
    print(f"ACTION EXECUTOR COMPLETE — cycle={cycle_id}")
    print(f"  GL health score : {result['gl_health_score']}")
    print(f"  Actions planned : {result['actions_planned']}")
    print(f"  Results         : {len(result['results'])}")
    for r in result["results"]:
        print(f"    [{r.get('status','?'):10}] {r.get('type','?')}")
    print(f"  Duration        : {result['duration_sec']}s")
    print(f"{'='*60}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        print(f"JSON written to {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
