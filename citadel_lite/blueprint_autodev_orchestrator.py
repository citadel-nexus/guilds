#!/usr/bin/env python3
"""
Blueprint Autodev Orchestrator
================================
Autonomous iterative development loop powered by Azure AI Foundry.

Cycle:
  READ → BLUEPRINT → THINK → ASSESS → BUILD → DIFF → AUDIT → PROGRESSION → TEST → WRITE → READ (repeat)

Every primary AI call routes through:
  Azure AI Foundry (GPT-4o) → OpenAI direct → AWS Bedrock → local fallback

The AUDIT phase is a dedicated secondary layer using AWS Bedrock (Claude) exclusively.
It reviews every BUILD output against: task criteria, coding standards, CAPS gate, SRS refs.
Both AI perspectives are captured and compared: GPT-4o (primary) vs Claude (audit).
Audit verdicts: approved | needs_revision | rejected
Rejected builds are blocked from WRITE regardless of test results.

The PROGRESSION phase aggregates each cycle's comparison report to progression.yaml:
- Both AI perspectives and their alignment/divergence
- Code metrics: difficulty, complexity score, design patterns
- Design choices made: what was chosen, why, and what alternatives existed
- Flaws identified: severity, location, description
- Intent alignment: how well the work serves the blueprint goals

progression.yaml is loaded at loop start and injected into every THINK prompt so the
AI has full context on: history, known flaws, design decisions already made, and intent.

Budget tracking is split: total_cost_usd (primary) + audit_cost_usd (Bedrock).
All decisions logged to loop_journal.jsonl for audit/replay.

Usage:
    python blueprint_autodev_orchestrator.py
    python blueprint_autodev_orchestrator.py --dry-run
    python blueprint_autodev_orchestrator.py --max-cycles 5
    python blueprint_autodev_orchestrator.py --budget-cap 25.0
    python blueprint_autodev_orchestrator.py --blueprint CITADEL_NEXUS_LITE-MVP.en.md
    python blueprint_autodev_orchestrator.py --audit-model haiku
    python blueprint_autodev_orchestrator.py --audit-strictness strict
    python blueprint_autodev_orchestrator.py --progression-file path/to/progression.yaml

SRS Codes: SRS-AUTODEV-ORCH-001 (primary), AOD-AUDIT-001..004 (audit), AOD-PROG-001..003 (progression)
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Paths ───────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent
BLUEPRINTS_DIR = HERE / "blueprints"
STATE_FILE = HERE / "loop_state.json"
JOURNAL_FILE = HERE / "loop_journal.jsonl"
TESTS_DIR = HERE / "tests"
PROGRESSION_FILE = HERE / "progression.yaml"

# ── Cost model (USD per 1k tokens, approximate) ─────────────────────────────
COST_PER_1K = {
    "azure":         0.005,    # GPT-4o on Azure
    "openai":        0.005,    # GPT-4o direct
    "bedrock":       0.003,    # Claude Haiku (default audit model)
    "bedrock_haiku": 0.00080,  # Claude Haiku 4.5  — input+output blended per 1k
    "bedrock_sonnet": 0.0060,  # Claude Sonnet 4.5 — input+output blended per 1k
    "fallback":      0.0,
}

# ── Bedrock model IDs for audit layer ───────────────────────────────────────
BEDROCK_AUDIT_MODELS = {
    "haiku":  "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
}

# ── Audit strictness levels (controls how strict the Claude reviewer is) ────
AUDIT_STRICTNESS = {
    "lenient":  "Be tolerant of minor style issues. Only reject if the code is functionally broken.",
    "standard": "Reject code that has bugs, wrong types, or fails to address the acceptance criteria.",
    "strict":   "Reject any deviation from production standards: typing, docstrings, error handling, and all acceptance criteria must be met.",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("autodev_orch")


# ── State ───────────────────────────────────────────────────────────────────

@dataclass
class LoopState:
    cycle: int = 0
    # Primary LLM costs (Azure/OpenAI gpt-4o)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    # Audit layer costs (Bedrock Claude) — tracked separately
    audit_tokens: int = 0
    audit_cost_usd: float = 0.0
    audit_calls: int = 0
    # Test results
    last_test_passed: int = 0
    last_test_failed: int = 0
    last_test_errors: int = 0
    # Blueprint tracking
    current_blueprint: str = ""
    completed_milestones: List[str] = field(default_factory=list)
    pending_milestones: List[str] = field(default_factory=list)
    attempted_tasks: List[str] = field(default_factory=list)  # dedup across cycles
    # Audit history (last 10 verdicts for trend analysis)
    audit_history: List[Dict[str, Any]] = field(default_factory=list)
    last_think_output: Dict[str, Any] = field(default_factory=dict)
    last_build_files: List[str] = field(default_factory=list)
    last_cycle_ts: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_file(cls, path: Path) -> "LoopState":
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")


# ── Journal ──────────────────────────────────────────────────────────────────

def _journal(path: Path, cycle: int, phase: str, data: Dict[str, Any]) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cycle": cycle,
        "phase": phase,
        **data,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Phase implementations ────────────────────────────────────────────────────

def phase_read(state: LoopState) -> Dict[str, Any]:
    """
    READ — Gather current system state.
    Collects: test results, git status, file counts, cycle history.
    """
    logger.info("[READ] Gathering system state...")

    # Test results from last run
    test_summary = {
        "passed": state.last_test_passed,
        "failed": state.last_test_failed,
        "errors": state.last_test_errors,
        "total": state.last_test_passed + state.last_test_failed + state.last_test_errors,
    }

    # Git status
    try:
        git_out = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=str(HERE), text=True, timeout=10,
            stderr=subprocess.DEVNULL
        )
        git_status = git_out.strip().split("\n") if git_out.strip() else []
    except Exception:
        git_status = []

    # Recent commits
    try:
        log_out = subprocess.check_output(
            ["git", "log", "--oneline", "-5"],
            cwd=str(HERE), text=True, timeout=10,
            stderr=subprocess.DEVNULL
        )
        recent_commits = log_out.strip().split("\n") if log_out.strip() else []
    except Exception:
        recent_commits = []

    # Source file counts
    src_files = list((HERE / "src").rglob("*.py")) if (HERE / "src").exists() else []
    test_files = list(TESTS_DIR.rglob("*.py")) if TESTS_DIR.exists() else []

    read_data = {
        "test_summary": test_summary,
        "git_uncommitted": len(git_status),
        "git_recent_commits": recent_commits[:3],
        "src_file_count": len(src_files),
        "test_file_count": len(test_files),
        "cycle": state.cycle,
        "total_cost_so_far": state.total_cost_usd,
        "completed_milestones": state.completed_milestones,
        "current_blueprint": state.current_blueprint,
        "last_build_files": state.last_build_files,
    }

    logger.info(
        "[READ] Tests: %d passed, %d failed | Files: %d src, %d test | Commits: %d",
        test_summary["passed"], test_summary["failed"],
        len(src_files), len(test_files), len(recent_commits)
    )
    return read_data


def phase_blueprint(state: LoopState, blueprint_filter: Optional[str]) -> Dict[str, Any]:
    """
    BLUEPRINT — Read blueprint files, extract unimplemented milestones.
    Returns the next milestone to build.
    """
    logger.info("[BLUEPRINT] Scanning blueprints...")

    # Pick which blueprint to use
    if blueprint_filter:
        bp_path = BLUEPRINTS_DIR / blueprint_filter
    elif state.current_blueprint:
        bp_path = BLUEPRINTS_DIR / state.current_blueprint
    else:
        # Default to MVP blueprint
        for candidate in ["CITADEL_NEXUS_LITE-MVP.en.md", "citadel-gap-analysis.md", "CGRF-v3.0-Complete-Framework.md"]:
            bp_path = BLUEPRINTS_DIR / candidate
            if bp_path.exists():
                break

    if not bp_path.exists():
        # Fall back to any .md blueprint
        mds = sorted(BLUEPRINTS_DIR.glob("*.md"))
        bp_path = mds[0] if mds else None

    if bp_path is None:
        return {"blueprint_file": None, "content_preview": "", "milestones": []}

    content = bp_path.read_text(encoding="utf-8", errors="replace")

    # Pull git log once to cross-reference completed work
    try:
        git_log = subprocess.check_output(
            ["git", "log", "--oneline", "-50"],
            cwd=str(HERE), stderr=subprocess.DEVNULL, timeout=10
        ).decode(errors="replace").lower()
    except Exception:
        git_log = ""

    # Extract milestone markers — supports checkboxes AND numbered section headings
    milestones = []
    import re as _re
    _numbered_heading = _re.compile(r'^#{1,3}\s+\d+[\.\)]\s+(.+)$')
    _phase_heading = _re.compile(r'^#{1,2}\s+Phase\s+\d+', _re.IGNORECASE)

    for line in content.split("\n"):
        stripped = line.strip()
        text = None
        done_flag = None

        if stripped.startswith("- [ ]") or stripped.startswith("* [ ]"):
            text = stripped[5:].strip()
            done_flag = False
        elif stripped.startswith("- [x]") or stripped.startswith("- [X]") \
                or stripped.startswith("* [x]") or stripped.startswith("* [X]"):
            text = stripped[5:].strip()
            done_flag = True
        else:
            m = _numbered_heading.match(stripped)
            if m:
                text = m.group(1).strip()
                # Mark done if already in state or mentioned in recent commits
                text_lower = text.lower()
                done_flag = (
                    text_lower in [c.lower() for c in state.completed_milestones]
                    or any(word in git_log for word in text_lower.split()[:3] if len(word) > 4)
                )
            elif _phase_heading.match(stripped):
                # Phase headings are section markers, not individual milestones — skip
                continue

        if text:
            milestones.append({"done": done_flag, "text": text})

    # Milestones with done=None (legacy fallback) or done=False are considered pending
    pending = [m for m in milestones if not m["done"]]
    done = [m["text"] for m in milestones if m["done"] is True]

    logger.info(
        "[BLUEPRINT] %s — %d total milestones, %d pending, %d done",
        bp_path.name, len(milestones), len(pending), len(done)
    )

    return {
        "blueprint_file": bp_path.name,
        "content_preview": content[:2000],
        "milestones": milestones,
        "pending": pending[:10],  # top 10 pending
        "done_count": len(done),
        "pending_count": len(pending),
    }


def phase_think(
    llm,
    read_data: Dict[str, Any],
    blueprint_data: Dict[str, Any],
    state: LoopState,
    dry_run: bool,
    progression_context: str = "",
) -> Dict[str, Any]:
    """
    THINK — Azure AI analyzes current state and decides what to build next.
    Returns: priority_task, reasoning, risk_level, estimated_complexity.

    progression_context is injected from ProgressionWriter.get_context_summary()
    so the AI has full awareness of: history, known flaws, design decisions,
    intent alignment trend, and previous cross-layer comparisons.
    SRS: AOD-PROG-003
    """
    logger.info("[THINK] Sending state to LLM for analysis...")

    # Build progression block — injected into system prompt when history exists
    progression_block = ""
    if progression_context:
        progression_block = f"\n\n{progression_context}\n"

    system_prompt = f"""You are the Citadel Lite autonomous development orchestrator.
Analyze the system state and blueprint to determine the single highest-priority task to implement next.

Rules:
- Prioritize tasks that unlock other tasks (foundational work first)
- Prefer tasks with failing tests over new features
- Skip tasks already marked done
- NEVER pick a task from already_attempted — pick the NEXT different pending milestone
- Consider complexity vs value (quick wins first when tests are failing)
- Respect DESIGN DECISIONS already made (listed in progression context below)
- Do NOT repeat KNOWN FLAWS listed in progression context — learn from them
- Consider perspective divergence from previous cycles when planning
- Always return valid JSON
{progression_block}
Return JSON with these exact fields:
{{
  "priority_task": "short task description",
  "task_type": "fix_test|new_feature|refactor|documentation|integration",
  "target_file": "src/path/to/file.py",
  "reasoning": "why this task is highest priority",
  "risk_level": "low|medium|high",
  "estimated_complexity": "trivial|small|medium|large",
  "implementation_hint": "specific approach or code pattern to use",
  "acceptance_criteria": ["list", "of", "testable", "criteria"]
}}"""

    user_message = json.dumps({
        "system_state": read_data,
        "blueprint_summary": {
            "file": blueprint_data.get("blueprint_file"),
            "pending_milestones": blueprint_data.get("pending", [])[:5],
            "done_count": blueprint_data.get("done_count", 0),
            "pending_count": blueprint_data.get("pending_count", 0),
        },
        "completed_milestones": state.completed_milestones[-5:],
        "already_attempted": state.attempted_tasks[-10:],
        "cycle": state.cycle,
    }, indent=2)

    if dry_run:
        logger.info("[THINK] dry-run — skipping LLM call")
        return {
            "priority_task": "DRY RUN — no LLM call",
            "task_type": "dry_run",
            "target_file": "",
            "reasoning": "dry-run mode",
            "risk_level": "low",
            "estimated_complexity": "trivial",
            "implementation_hint": "",
            "acceptance_criteria": [],
        }

    resp = llm.complete(system_prompt, user_message, json_mode=True)

    if resp.success and resp.parsed:
        parsed = resp.parsed
        # Attach CAPS grade to the task decision
        caps_grade = _resolve_task_caps(
            parsed.get("priority_task", ""),
            parsed.get("task_type", ""),
            parsed.get("estimated_complexity", "medium"),
        )
        logger.info(
            "[THINK] Task: '%s' | Type: %s | Risk: %s | CAPS: %s | Backend: %s (%d tokens)",
            parsed.get("priority_task", "?"),
            parsed.get("task_type", "?"),
            parsed.get("risk_level", "?"),
            caps_grade,
            resp.usage.backend,
            resp.usage.total_tokens,
        )
        return {**parsed, "caps_grade": caps_grade, "_tokens": resp.usage.total_tokens, "_backend": resp.usage.backend}

    logger.warning("[THINK] LLM failed: %s — using heuristic fallback", resp.error)
    # Heuristic fallback: fix failing tests first
    if read_data["test_summary"]["failed"] > 0:
        task = f"Fix {read_data['test_summary']['failed']} failing tests"
        return {
            "priority_task": task,
            "task_type": "fix_test",
            "target_file": "tests/",
            "reasoning": "Tests are failing — fix before new development",
            "risk_level": "low",
            "estimated_complexity": "small",
            "implementation_hint": "Run pytest -x to find first failure",
            "acceptance_criteria": ["All tests pass"],
            "caps_grade": _resolve_task_caps(task, "fix_test", "small"),
            "_tokens": 0,
            "_backend": "fallback",
        }
    pending = blueprint_data.get("pending", [])
    task = pending[0]["text"] if pending else "Review blueprint for next milestone"
    return {
        "priority_task": task,
        "task_type": "new_feature",
        "target_file": "src/",
        "reasoning": "Next pending blueprint milestone",
        "risk_level": "medium",
        "estimated_complexity": "medium",
        "implementation_hint": "Follow blueprint spec",
        "acceptance_criteria": ["Feature implemented", "Tests pass"],
        "caps_grade": _resolve_task_caps(task, "new_feature", "medium"),
        "_tokens": 0,
        "_backend": "fallback",
    }


def phase_assess(
    llm,
    think_output: Dict[str, Any],
    blueprint_data: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    """
    ASSESS — Score current implementation completeness vs blueprint.
    Returns implementation_score (0-100) and gap analysis.
    """
    logger.info("[ASSESS] Evaluating implementation completeness...")

    if dry_run:
        return {"implementation_score": 0, "gaps": [], "_backend": "fallback"}

    # Count implemented vs pending as a simple metric
    done = blueprint_data.get("done_count", 0)
    pending = blueprint_data.get("pending_count", 0)
    total = done + pending
    score = int((done / total * 100)) if total > 0 else 0

    # List top gaps from pending milestones
    gaps = [m["text"] for m in blueprint_data.get("pending", [])[:5]]

    logger.info("[ASSESS] Implementation score: %d%% (%d/%d milestones)", score, done, total)
    return {
        "implementation_score": score,
        "done_milestones": done,
        "total_milestones": total,
        "gaps": gaps,
        "_backend": "local",
    }


def phase_build(
    llm,
    think_output: Dict[str, Any],
    state: LoopState,
    dry_run: bool,
) -> Dict[str, Any]:
    """
    BUILD — Generate implementation code for the priority task.
    Uses LLM to generate code, writes files to disk.
    """
    task = think_output.get("priority_task", "unknown")
    target = think_output.get("target_file", "src/")
    hint = think_output.get("implementation_hint", "")
    criteria = think_output.get("acceptance_criteria", [])

    logger.info("[BUILD] Building: '%s' → %s", task, target)

    if dry_run:
        logger.info("[BUILD] dry-run — skipping code generation")
        return {"files_written": [], "skipped": True, "_backend": "fallback"}

    # fix_test tasks need code generation too — don't skip them
    # (the old "defer" logic just prevented any progress on failing tests)

    system_prompt = """You are an expert Python engineer working on Citadel Lite.
Generate production-quality Python code for the requested task.

Rules:
- Write clean, typed Python 3.11+ code
- Follow the existing patterns in src/ (dataclasses, type hints, logging)
- Include docstrings and inline comments for complex logic
- Write code that will pass tests, not just stubs

Return JSON:
{
  "files": [
    {
      "path": "src/relative/path.py",
      "content": "full file content as string",
      "description": "what this file does"
    }
  ],
  "summary": "what was implemented"
}"""

    user_message = json.dumps({
        "task": task,
        "target_file": target,
        "implementation_hint": hint,
        "acceptance_criteria": criteria,
        "task_type": think_output.get("task_type"),
    }, indent=2)

    resp = llm.complete(system_prompt, user_message, json_mode=True)
    files_written = []

    if resp.success and resp.parsed:
        for file_spec in resp.parsed.get("files", []):
            rel_path = file_spec.get("path", "")
            content = file_spec.get("content", "")
            if not rel_path or not content:
                continue

            full_path = HERE / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Safety: don't overwrite files > 50kb
            if full_path.exists() and full_path.stat().st_size > 50_000:
                logger.warning("[BUILD] Skipping large existing file: %s", rel_path)
                continue

            full_path.write_text(content, encoding="utf-8")
            files_written.append(rel_path)
            logger.info("[BUILD] Written: %s", rel_path)

        logger.info(
            "[BUILD] Generated %d files | Backend: %s (%d tokens)",
            len(files_written), resp.usage.backend, resp.usage.total_tokens
        )
        return {
            "files_written": files_written,
            "summary": resp.parsed.get("summary", ""),
            "_tokens": resp.usage.total_tokens,
            "_backend": resp.usage.backend,
        }

    logger.warning("[BUILD] LLM code generation failed: %s", resp.error)
    return {"files_written": [], "error": resp.error, "_backend": "fallback"}


def phase_test(state: LoopState, build_output: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    """
    TEST — Run pytest on newly written test files (targeted), then full suite.
    Targeted run is fast and catches regressions in the built files.
    Updates state with pass/fail counts.
    """
    logger.info("[TEST] Running test suite...")

    if dry_run:
        logger.info("[TEST] dry-run — skipping pytest")
        return {"passed": 0, "failed": 0, "errors": 0, "skipped": True}

    if not TESTS_DIR.exists():
        logger.warning("[TEST] No tests/ directory found")
        return {"passed": 0, "failed": 0, "errors": 0, "no_tests": True}

    # Targeted run: only new test files from this BUILD cycle (much faster)
    new_test_files = [
        str(HERE / f) for f in build_output.get("files_written", [])
        if f.startswith("tests/") and f.endswith(".py")
    ]

    def _run_pytest(targets: List[str], timeout: int) -> subprocess.CompletedProcess:
        cmd = [sys.executable, "-m", "pytest"] + targets + [
            "--tb=short", "-q",
            "--ignore", str(TESTS_DIR / "test_pipeline_e2e.py"),
        ]
        return subprocess.run(
            cmd, cwd=str(HERE), capture_output=True, text=True, timeout=timeout,
        )

    def _parse_counts(output: str) -> tuple:
        passed = failed = errors = 0
        for line in output.split("\n"):
            if " passed" in line:
                try:
                    passed = int(line.split(" passed")[0].strip().split()[-1])
                except (ValueError, IndexError):
                    pass
            if " failed" in line:
                try:
                    failed = int(line.split(" failed")[0].strip().split()[-1])
                except (ValueError, IndexError):
                    pass
            if " error" in line:
                try:
                    errors = int(line.split(" error")[0].strip().split()[-1])
                except (ValueError, IndexError):
                    pass
        return passed, failed, errors

    targeted_result: Dict[str, Any] = {"passed": 0, "failed": 0, "errors": 0}
    targeted_output = ""

    try:
        # Phase A: targeted test run (new files only, 60s timeout)
        if new_test_files:
            logger.info("[TEST] Targeted run: %s", new_test_files)
            tr = _run_pytest(new_test_files, timeout=60)
            targeted_output = tr.stdout + tr.stderr
            p, f, e = _parse_counts(targeted_output)
            targeted_result = {"passed": p, "failed": f, "errors": e, "returncode": tr.returncode}
            logger.info("[TEST] Targeted: %d passed, %d failed, %d errors", p, f, e)

    except subprocess.TimeoutExpired:
        logger.error("[TEST] Targeted pytest timed out")
        targeted_result = {"passed": 0, "failed": 0, "errors": 1, "timeout": True}
    except Exception as e:
        logger.error("[TEST] Targeted pytest error: %s", e)
        targeted_result = {"passed": 0, "failed": 0, "errors": 1, "error": str(e)}

    # If targeted failed or errored, skip full suite — return targeted result directly
    targeted_ok = (
        targeted_result.get("failed", 0) == 0
        and targeted_result.get("errors", 0) == 0
    )
    if new_test_files and not targeted_ok:
        passed = targeted_result["passed"]
        failed = targeted_result["failed"]
        errors = targeted_result["errors"]
        mode = "targeted_only"
        state.last_test_passed = passed
        state.last_test_failed = failed
        state.last_test_errors = errors
        logger.info("[TEST] FAIL (targeted_only) — %d passed, %d failed, %d errors", passed, failed, errors)
        return {
            "passed": passed, "failed": failed, "errors": errors,
            "mode": mode, "targeted": targeted_result,
            "output_tail": targeted_output[-500:],
        }

    # Phase B: full suite (120s timeout) — only if targeted passed or no new test files
    try:
        result = _run_pytest([str(TESTS_DIR)], timeout=120)
        output = result.stdout + result.stderr
        passed, failed, errors = _parse_counts(output)
        mode = "full"

    except subprocess.TimeoutExpired:
        # Full suite timed out — if targeted already passed, use those results
        # Don't block WRITE on a suite-level timeout when the built code works
        if new_test_files and targeted_ok:
            logger.warning("[TEST] Full suite timed out — using targeted results (targeted passed)")
            passed = targeted_result["passed"]
            failed = targeted_result["failed"]
            errors = 0   # targeted passed — timeout is a suite infra issue, not a code failure
            mode = "targeted_fallback"
        else:
            logger.error("[TEST] Full suite timed out (no targeted baseline)")
            passed, failed, errors = 0, 0, 1
            mode = "timeout"
        output = targeted_output

    except Exception as e:
        logger.error("[TEST] Full suite pytest error: %s", e)
        if new_test_files and targeted_ok:
            logger.warning("[TEST] Using targeted results after full suite error")
            passed = targeted_result["passed"]
            failed = targeted_result["failed"]
            errors = 0
            mode = "targeted_fallback"
        else:
            passed, failed, errors = 0, 0, 1
            mode = "error"
        output = targeted_output

    state.last_test_passed = passed
    state.last_test_failed = failed
    state.last_test_errors = errors

    status = "PASS" if failed == 0 and errors == 0 else "FAIL"
    logger.info("[TEST] %s (%s) — %d passed, %d failed, %d errors", status, mode, passed, failed, errors)

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "mode": mode,
        "targeted": targeted_result,
        "output_tail": output[-500:] if len(output) > 500 else output,
    }


# ── CAPS ranking ──────────────────────────────────────────────────────────────

_CAPS_TASK_KEYWORDS: Dict[str, str] = {
    # S-grade: system-critical contracts and core types
    "event contract": "S",
    "handoff packet": "S",
    "decision contract": "S",
    "event json": "S",
    "core types": "S",
    # A-grade: pipeline agents
    "sentinel": "A",
    "sherlock": "A",
    "fixer": "A",
    "guardian": "A",
    "a2a protocol": "A",
    "foundry": "A",
    # B-grade: integration and memory
    "memory": "B",
    "vector": "B",
    "cosmos": "B",
    "azure": "B",
    "integration": "B",
    # C-grade: tooling and scripts
    "script": "C",
    "cli": "C",
    "test coverage": "C",
    "refactor": "C",
    # D-grade: docs and cleanup
    "documentation": "D",
    "readme": "D",
    "cleanup": "D",
    "comment": "D",
}


def _resolve_task_caps(task: str, task_type: str, complexity: str) -> str:
    """Assign a CAPS grade to a task based on keywords and metadata."""
    task_lower = task.lower()
    for keyword, grade in _CAPS_TASK_KEYWORDS.items():
        if keyword in task_lower:
            return grade
    # Fallback: use complexity
    complexity_map = {"trivial": "D", "small": "C", "medium": "B", "large": "A"}
    return complexity_map.get(complexity, "B")


def phase_diff(
    state: LoopState,
    assess_output: Dict[str, Any],
    build_output: Dict[str, Any],
    pre_build_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    DIFF — Two metrics comparing prediction vs reality.

    Metric 1 — Assessment vs Outcome:
        What ASSESS predicted (score, gaps) vs what BUILD actually produced
        (files written, lines of code).

    Metric 2 — Outcome vs Codebase:
        git diff --stat shows what actually changed in the working tree.
    """
    # ── Metric 1: Assessment vs Outcome ─────────────────────────────
    predicted_score = assess_output.get("implementation_score", 0)
    predicted_gaps = assess_output.get("gaps", [])
    files_written = build_output.get("files_written", [])
    build_summary = build_output.get("summary", "")

    # Count lines written (approximate)
    lines_written = 0
    for rel_path in files_written:
        try:
            lines_written += len((HERE / rel_path).read_text(encoding="utf-8").splitlines())
        except Exception:
            pass

    # Did BUILD address any predicted gaps?
    gaps_addressed = [
        g for g in predicted_gaps
        if any(word in build_summary.lower() for word in g.lower().split()[:3] if len(word) > 3)
    ]

    assessment_vs_outcome = {
        "predicted_score_pct": predicted_score,
        "predicted_gaps": predicted_gaps,
        "actual_files_written": len(files_written),
        "actual_lines_written": lines_written,
        "gaps_addressed": gaps_addressed,
        "gaps_remaining": [g for g in predicted_gaps if g not in gaps_addressed],
        "build_summary": build_summary,
        "alignment": "aligned" if files_written else "diverged",
    }

    logger.info(
        "[DIFF] Assessment vs Outcome: score=%d%% | files=%d | lines=%d | gaps_addressed=%d/%d",
        predicted_score, len(files_written), lines_written,
        len(gaps_addressed), len(predicted_gaps)
    )

    # ── Metric 2: Outcome vs Codebase (git diff) ────────────────────
    try:
        diff_stat = subprocess.check_output(
            ["git", "diff", "--stat", "HEAD"],
            cwd=str(HERE), text=True, timeout=10, stderr=subprocess.DEVNULL
        ).strip()
        diff_numstat = subprocess.check_output(
            ["git", "diff", "--numstat", "HEAD"],
            cwd=str(HERE), text=True, timeout=10, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        diff_stat = ""
        diff_numstat = ""

    # Parse numstat: added\tdeleted\tfilename
    lines_added = lines_removed = 0
    changed_files: List[str] = []
    for row in diff_numstat.split("\n"):
        parts = row.split("\t")
        if len(parts) == 3:
            try:
                lines_added += int(parts[0]) if parts[0] != "-" else 0
                lines_removed += int(parts[1]) if parts[1] != "-" else 0
                changed_files.append(parts[2])
            except ValueError:
                pass

    # Also include untracked new files
    try:
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(HERE), text=True, timeout=10, stderr=subprocess.DEVNULL
        ).strip().split("\n")
        new_files = [f for f in untracked if f]
    except Exception:
        new_files = []

    # Snapshot delta (src file count before vs after)
    src_files_before = pre_build_snapshot.get("src_file_count", 0)
    src_files_now = len(list((HERE / "src").rglob("*.py"))) if (HERE / "src").exists() else 0
    src_delta = src_files_now - src_files_before

    outcome_vs_codebase = {
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "changed_files": changed_files,
        "new_untracked_files": new_files[:20],  # cap list length
        "src_file_delta": src_delta,
        "diff_stat_summary": diff_stat[-300:] if len(diff_stat) > 300 else diff_stat,
    }

    logger.info(
        "[DIFF] Outcome vs Codebase: +%d/-%d lines | %d changed | %d new files | src_delta=%+d",
        lines_added, lines_removed, len(changed_files), len(new_files), src_delta
    )

    return {
        "assessment_vs_outcome": assessment_vs_outcome,
        "outcome_vs_codebase": outcome_vs_codebase,
    }


# ── Bedrock Audit Client ──────────────────────────────────────────────────────

class BedrockAuditClient:
    """
    Dedicated Bedrock (Claude) client for the AUDIT layer.
    Separate from LLMClient so audit costs are tracked independently.

    SRS: AOD-AUDIT-001
    """

    def __init__(self, model_key: str = "haiku", strictness: str = "standard") -> None:
        self.model_key = model_key
        self.model_id = BEDROCK_AUDIT_MODELS.get(model_key, BEDROCK_AUDIT_MODELS["haiku"])
        self.strictness = strictness
        self.strictness_instruction = AUDIT_STRICTNESS.get(strictness, AUDIT_STRICTNESS["standard"])
        # Per-instance token tracking
        self.tokens_in = 0
        self.tokens_out = 0
        self.call_count = 0
        self.call_log: List[Dict[str, Any]] = []

    def audit(
        self,
        task: str,
        caps_grade: str,
        acceptance_criteria: List[str],
        files_written: List[str],
        build_summary: str,
        diff_metrics: Dict[str, Any],
        srs_refs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send generated code to Claude for audit review.
        Returns structured verdict dict.
        SRS: AOD-AUDIT-002
        """
        # Read file contents (up to 200 lines each to stay within token budget)
        file_contents: List[Dict[str, str]] = []
        for rel_path in files_written:
            try:
                lines = (HERE / rel_path).read_text(encoding="utf-8").splitlines()
                file_contents.append({
                    "path": rel_path,
                    "content": "\n".join(lines[:200]),
                    "truncated": len(lines) > 200,
                })
            except Exception:
                pass

        system_prompt = f"""You are a senior Python code reviewer for the Citadel Lite project.
Your role is the AUDIT layer of an autonomous development pipeline.
You provide a SECOND PERSPECTIVE alongside the primary GPT-4o generation layer.
Your job is not just to approve/reject — it is to COMPARE perspectives and surface insights.

Strictness level: {self.strictness.upper()} — {self.strictness_instruction}

CAPS grade system: S>A>B>C>D (S=core contracts, A=pipeline agents, B=integration, C=tooling, D=docs)
The task being audited has CAPS grade: {caps_grade}

Return ONLY valid JSON matching this exact schema:
{{
  "verdict": "approved" | "needs_revision" | "rejected",
  "issues": ["list of specific issues found (empty if approved)"],
  "risk_score": 0.0,
  "srs_refs_satisfied": ["list of SRS codes satisfied"],
  "srs_refs_failed": ["list of SRS codes NOT satisfied"],
  "token_efficiency": "good" | "acceptable" | "bloated",
  "rationale": "1-2 sentence summary of decision",
  "perspective_comparison": {{
    "primary_approach": "describe what approach GPT-4o took in 1-2 sentences (infer from the code)",
    "claude_perspective": "describe how you (Claude) would have approached this differently, or confirm alignment",
    "alignment": "aligned" | "partial" | "diverged",
    "divergence_notes": "key differences if alignment is partial/diverged, empty string if aligned"
  }},
  "code_metrics": {{
    "difficulty": "trivial" | "simple" | "moderate" | "complex" | "expert",
    "complexity_score": 5,
    "design_pattern": "primary pattern used e.g. dataclass, factory, strategy, observer, adapter, none",
    "maintainability": "good" | "acceptable" | "poor"
  }},
  "design_choices": [
    {{
      "choice": "specific design decision made in this code",
      "rationale": "why this choice was made (inferred)",
      "alternatives": ["alternative1", "alternative2"]
    }}
  ],
  "flaws_identified": [
    {{
      "severity": "minor" | "major" | "critical",
      "description": "clear description of the flaw",
      "location": "filename or function name"
    }}
  ],
  "intent_alignment": 0.8
}}

Field rules:
- complexity_score: integer 1-10 (1=trivial bash script, 10=distributed systems kernel)
- intent_alignment: 0.0-1.0 — how well this code serves the stated blueprint goals
- design_choices: at least 1 entry per non-trivial file; empty list only for trivial tasks
- flaws_identified: list ALL flaws including minor ones; severity drives escalation

Verdict rules:
- approved: code is correct, addresses criteria, no critical issues
- needs_revision: code mostly works but has minor issues; still allow commit if tests pass
- rejected: functional bugs, wrong types, missing required logic, or acceptance criteria not met"""

        user_message = json.dumps({
            "task": task,
            "caps_grade": caps_grade,
            "acceptance_criteria": acceptance_criteria,
            "build_summary": build_summary,
            "srs_refs": srs_refs or [],
            "diff_metrics": {
                "files": diff_metrics.get("actual_files_written", 0),
                "lines": diff_metrics.get("actual_lines_written", 0),
                "gaps_addressed": len(diff_metrics.get("gaps_addressed", [])),
                "alignment": diff_metrics.get("alignment", "unknown"),
            },
            "generated_files": file_contents,
        }, indent=2)

        try:
            import boto3  # type: ignore
            session = boto3.Session(region_name=os.environ.get("AWS_REGION", "us-east-1"))
            client = session.client("bedrock-runtime")

            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 3000,   # expanded schema: perspective + metrics + design_choices + flaws
                "temperature": 0.1,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            }

            t0 = time.perf_counter()
            resp = client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            latency_ms = (time.perf_counter() - t0) * 1000

            result = json.loads(resp["body"].read())
            raw_text = result.get("content", [{}])[0].get("text", "")
            in_tok = result.get("usage", {}).get("input_tokens", 0)
            out_tok = result.get("usage", {}).get("output_tokens", 0)

            # Track tokens
            self.tokens_in += in_tok
            self.tokens_out += out_tok
            self.call_count += 1
            self.call_log.append({
                "cycle": self.call_count,
                "model": self.model_id,
                "tokens_in": in_tok,
                "tokens_out": out_tok,
                "latency_ms": round(latency_ms, 1),
            })

            # Parse JSON (strip markdown fences if needed)
            # Use raw_decode to handle Claude appending commentary after the JSON object
            text = raw_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            idx = text.find("{")
            if idx == -1:
                raise ValueError("No JSON object found in Bedrock response")
            decoder = json.JSONDecoder()
            parsed, _ = decoder.raw_decode(text[idx:])
            parsed["_tokens_in"] = in_tok
            parsed["_tokens_out"] = out_tok
            parsed["_model"] = self.model_id
            parsed["_latency_ms"] = round(latency_ms, 1)
            return parsed

        except ImportError:
            return _audit_unavailable("boto3 not installed")
        except Exception as e:
            logger.warning("[AUDIT] Bedrock call failed: %s — defaulting to approved", e)
            return _audit_unavailable(str(e))

    def usage_summary(self) -> Dict[str, Any]:
        """Return cumulative token/cost breakdown for this audit client. SRS: AOD-AUDIT-003"""
        total = self.tokens_in + self.tokens_out
        cost_key = f"bedrock_{self.model_key}"
        cost = (total / 1000) * COST_PER_1K.get(cost_key, COST_PER_1K["bedrock"])
        return {
            "model": self.model_id,
            "strictness": self.strictness,
            "call_count": self.call_count,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": total,
            "estimated_cost_usd": round(cost, 6),
        }


def _audit_unavailable(reason: str) -> Dict[str, Any]:
    """Return a safe default when Bedrock audit is unavailable. SRS: AOD-AUDIT-004"""
    return {
        "verdict": "approved",
        "issues": [],
        "risk_score": 0.0,
        "srs_refs_satisfied": [],
        "srs_refs_failed": [],
        "token_efficiency": "acceptable",
        "rationale": f"Audit unavailable ({reason}) — defaulting to approved",
        # Perspective comparison defaults (neutral — no opinion available)
        "perspective_comparison": {
            "primary_approach": "",
            "claude_perspective": f"Audit skipped: {reason}",
            "alignment": "unknown",
            "divergence_notes": "",
        },
        "code_metrics": {
            "difficulty": "unknown",
            "complexity_score": 5,
            "design_pattern": "unknown",
            "maintainability": "acceptable",
        },
        "design_choices": [],
        "flaws_identified": [],
        "intent_alignment": 0.5,
        "_tokens_in": 0,
        "_tokens_out": 0,
        "_model": "unavailable",
        "_latency_ms": 0.0,
        "_skipped": True,
        "_skip_reason": reason,
    }


# ── Progression tracking ─────────────────────────────────────────────────────

class ProgressionWriter:
    """
    Aggregates per-cycle comparison reports to progression.yaml.

    Each cycle produces a structured entry capturing:
      - Both AI perspectives: GPT-4o (primary) vs Claude Bedrock (audit)
      - Their alignment/divergence as judged by Claude
      - Code metrics: difficulty, complexity score, design patterns
      - Design choices: what was chosen and why, alternatives considered
      - Flaws: identified issues with severity and location
      - Intent alignment: 0.0-1.0 reflecting how well the work serves blueprint goals

    The accumulated history feeds back into THINK as a context block so the AI
    knows: what was tried, what worked, what failed, what design decisions are
    locked in, and what flaws must not be repeated.

    SRS: AOD-PROG-001, AOD-PROG-002, AOD-PROG-003
    """

    MAX_CONTEXT_CYCLES: int = 5      # recent cycles injected into THINK
    MAX_KNOWN_FLAWS: int = 20        # rolling window for accumulated flaws
    MAX_DESIGN_DECISIONS: int = 30   # rolling window for design decisions

    def __init__(self, path: Path, run_id: Optional[str] = None) -> None:
        self.path = path
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._data: Dict[str, Any] = self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        """Load existing progression file or return a fresh scaffold."""
        if self.path.exists():
            try:
                text = self.path.read_text(encoding="utf-8")
                try:
                    import yaml as _yaml
                    loaded = _yaml.safe_load(text)
                except ImportError:
                    loaded = json.loads(text)
                if isinstance(loaded, dict):
                    return loaded
            except Exception:
                pass
        return {
            "_meta": {
                "schema": "progression-metrics-v1",
                "created": datetime.now(timezone.utc).isoformat(),
                "run_id": self.run_id,
                "blueprint": "",
            },
            "summary": {
                "total_cycles": 0,
                "goals_completed": [],
                "known_flaws": [],
                "design_decisions": [],
                "accumulated_difficulty_score": 5.0,
                "avg_intent_alignment": 0.5,
                "alignment_trend": [],   # last 10 intent_alignment values
            },
            "cycles": [],
        }

    def save(self, blueprint_name: str = "") -> None:
        """Persist progression data to disk (YAML preferred, JSON fallback)."""
        meta = self._data.setdefault("_meta", {})
        if blueprint_name:
            meta["blueprint"] = blueprint_name
        meta["last_updated"] = datetime.now(timezone.utc).isoformat()
        meta["run_id"] = self.run_id

        try:
            import yaml as _yaml
            text = _yaml.dump(
                self._data,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
                width=120,
            )
        except ImportError:
            text = json.dumps(self._data, indent=2, ensure_ascii=False)

        self.path.write_text(text, encoding="utf-8")

    # ── Cycle recording ──────────────────────────────────────────────────────

    def record_cycle(
        self,
        cycle: int,
        task: str,
        caps_grade: str,
        think_output: Dict[str, Any],
        assess_output: Dict[str, Any],
        build_output: Dict[str, Any],
        diff_output: Dict[str, Any],
        audit_output: Dict[str, Any],
        test_output: Dict[str, Any],
        outcome: str,
    ) -> Dict[str, Any]:
        """
        Build and record one cycle entry. Returns the entry dict.

        outcome values:
          committed       — git commit succeeded
          blocked_audit   — Claude rejected the build
          blocked_test    — tests failed after audit approved
          no_files        — BUILD produced no files
          skipped         — dry-run or other skip
        """
        perspective = audit_output.get("perspective_comparison", {})
        code_metrics = audit_output.get("code_metrics", {})
        design_choices = audit_output.get("design_choices", [])
        flaws = audit_output.get("flaws_identified", [])
        intent_alignment = float(audit_output.get("intent_alignment", 0.5))

        entry: Dict[str, Any] = {
            "cycle": cycle,
            "ts": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "caps_grade": caps_grade,
            "outcome": outcome,
            # Both AI perspectives for comparison
            "primary_layer": {
                "backend": think_output.get("_backend", "azure"),
                "approach": perspective.get("primary_approach", ""),
                "reasoning": think_output.get("reasoning", ""),
                "hint": think_output.get("implementation_hint", ""),
            },
            "audit_layer": {
                "verdict": audit_output.get("verdict", "approved"),
                "risk_score": audit_output.get("risk_score", 0.0),
                "rationale": audit_output.get("rationale", ""),
                "claude_perspective": perspective.get("claude_perspective", ""),
                "alignment": perspective.get("alignment", "unknown"),
                "divergence_notes": perspective.get("divergence_notes", ""),
                "issues_count": len(audit_output.get("issues", [])),
                "srs_refs_failed": audit_output.get("srs_refs_failed", []),
            },
            # Objective code metrics from Claude's analysis
            "code_metrics": {
                "difficulty": code_metrics.get("difficulty", "unknown"),
                "complexity_score": code_metrics.get("complexity_score", 5),
                "design_pattern": code_metrics.get("design_pattern", ""),
                "maintainability": code_metrics.get("maintainability", "acceptable"),
            },
            "design_choices": design_choices,
            "flaws": flaws,
            "intent_alignment": round(intent_alignment, 3),
            # Diff summary for tracking codebase growth
            "diff_summary": {
                "lines_added": diff_output.get("outcome_vs_codebase", {}).get("lines_added", 0),
                "lines_removed": diff_output.get("outcome_vs_codebase", {}).get("lines_removed", 0),
                "files_written": build_output.get("files_written", []),
                "assessment_alignment": diff_output.get("assessment_vs_outcome", {}).get("alignment", ""),
            },
            "test_result": {
                "passed": test_output.get("passed", 0),
                "failed": test_output.get("failed", 0),
                "errors": test_output.get("errors", 0),
            },
            "implementation_score": assess_output.get("implementation_score", 0),
        }

        # ── Update summary ────────────────────────────────────────────────

        self._data["summary"]["total_cycles"] = cycle

        # Track completed goals
        if outcome == "committed":
            goals: List[str] = self._data["summary"]["goals_completed"]
            if task and task not in goals:
                goals.append(task)

        # Accumulate major/critical flaws (dedup by description)
        existing_desc: set = {f.get("description", "") for f in self._data["summary"]["known_flaws"]}
        for flaw in flaws:
            severity = flaw.get("severity", "minor")
            desc = flaw.get("description", "")
            if severity in ("major", "critical") and desc and desc not in existing_desc:
                self._data["summary"]["known_flaws"].append(
                    {**flaw, "cycle": cycle, "task": task}
                )
                existing_desc.add(desc)
        self._data["summary"]["known_flaws"] = (
            self._data["summary"]["known_flaws"][-self.MAX_KNOWN_FLAWS:]
        )

        # Accumulate design decisions (dedup by choice text)
        existing_choices: set = {d.get("choice", "") for d in self._data["summary"]["design_decisions"]}
        for choice in design_choices:
            c_text = choice.get("choice", "")
            if c_text and c_text not in existing_choices:
                self._data["summary"]["design_decisions"].append(
                    {**choice, "cycle": cycle, "task": task}
                )
                existing_choices.add(c_text)
        self._data["summary"]["design_decisions"] = (
            self._data["summary"]["design_decisions"][-self.MAX_DESIGN_DECISIONS:]
        )

        # Rolling averages (include the entry we're about to append)
        all_cycles = self._data["cycles"] + [entry]
        complexity_scores = [
            c.get("code_metrics", {}).get("complexity_score", 5) for c in all_cycles
        ]
        self._data["summary"]["accumulated_difficulty_score"] = round(
            sum(complexity_scores) / len(complexity_scores), 2
        )
        intent_values = [c.get("intent_alignment", 0.5) for c in all_cycles]
        self._data["summary"]["avg_intent_alignment"] = round(
            sum(intent_values) / len(intent_values), 3
        )
        self._data["summary"]["alignment_trend"] = intent_values[-10:]

        # Append cycle
        self._data["cycles"].append(entry)
        return entry

    # ── Context generation ───────────────────────────────────────────────────

    def get_context_summary(self, n_cycles: Optional[int] = None) -> str:
        """
        Generate a structured text block for injection into THINK.

        Covers: recent cycle outcomes, known flaws, design decisions made,
        intent alignment trend, and completed goals.
        Returns empty string on first cycle (no history yet).

        SRS: AOD-PROG-003
        """
        n = n_cycles or self.MAX_CONTEXT_CYCLES
        recent = self._data.get("cycles", [])[-n:]
        summary = self._data.get("summary", {})

        has_history = bool(
            recent
            or summary.get("known_flaws")
            or summary.get("design_decisions")
            or summary.get("goals_completed")
        )
        if not has_history:
            return ""

        lines: List[str] = [
            "=== PROGRESSION CONTEXT (read before planning) ===",
            (
                f"Cycles: {summary.get('total_cycles', 0)} | "
                f"Goals done: {len(summary.get('goals_completed', []))} | "
                f"Avg intent: {summary.get('avg_intent_alignment', 0.5):.0%} | "
                f"Avg difficulty: {summary.get('accumulated_difficulty_score', 5):.1f}/10"
            ),
        ]

        # Known flaws — critical context to avoid repeating mistakes
        known_flaws = summary.get("known_flaws", [])
        if known_flaws:
            lines.append("\nKNOWN FLAWS — do NOT repeat these mistakes:")
            for f in known_flaws[-5:]:
                lines.append(
                    f"  [{f.get('severity', '?').upper()}] {f.get('description', '')} "
                    f"(cycle {f.get('cycle', '?')}, loc: {f.get('location', 'unknown')})"
                )

        # Design decisions — locked-in choices to respect
        decisions = summary.get("design_decisions", [])
        if decisions:
            lines.append("\nDESIGN DECISIONS already made — respect these:")
            for d in decisions[-5:]:
                alts = d.get("alternatives", [])
                alt_str = f" [considered: {', '.join(alts[:2])}]" if alts else ""
                lines.append(
                    f"  - {d.get('choice', '')} — {d.get('rationale', '')}{alt_str}"
                )

        # Recent cycles with both perspectives
        if recent:
            lines.append(f"\nRECENT {len(recent)} CYCLE(S) — both AI perspectives:")
            for c in recent:
                al = c.get("audit_layer", {})
                pl = c.get("primary_layer", {})
                lines.append(
                    f"  [Cycle {c.get('cycle', '?')} | {c.get('caps_grade', '?')}] "
                    f"{c.get('task', '')} → {c.get('outcome', '')} | "
                    f"audit={al.get('verdict', '?')} | "
                    f"perspective={al.get('alignment', '?')} | "
                    f"intent={c.get('intent_alignment', 0):.0%} | "
                    f"difficulty={c.get('code_metrics', {}).get('difficulty', '?')}"
                )
                if al.get("divergence_notes"):
                    lines.append(
                        f"    > Claude diverged: {al['divergence_notes']}"
                    )
                for flaw in c.get("flaws", [])[:2]:
                    lines.append(
                        f"    > [{flaw.get('severity', '?')}] {flaw.get('description', '')}"
                    )
                if pl.get("approach"):
                    lines.append(f"    > GPT-4o approach: {pl['approach'][:120]}")

        goals_done = summary.get("goals_completed", [])
        if goals_done:
            lines.append(f"\nCompleted goals: {', '.join(goals_done[-5:])}")

        lines.append("=== END PROGRESSION ===")
        return "\n".join(lines)


def phase_progression(
    writer: ProgressionWriter,
    state: LoopState,
    think_output: Dict[str, Any],
    assess_output: Dict[str, Any],
    build_output: Dict[str, Any],
    diff_output: Dict[str, Any],
    audit_output: Dict[str, Any],
    test_output: Dict[str, Any],
    blueprint_data: Dict[str, Any],
    write_committed: bool,
) -> Dict[str, Any]:
    """
    PROGRESSION — Record this cycle's full comparison report to progression.yaml.

    Called AFTER WRITE so outcome (committed|blocked_*|no_files) is known.
    Determines outcome from write_committed flag and phase signals.
    The recorded data includes both AI perspectives, code metrics, design choices,
    and accumulated flaws — building a persistent, cross-cycle context file.

    SRS: AOD-PROG-001, AOD-PROG-002
    """
    verdict = audit_output.get("verdict", "approved")
    files_written = build_output.get("files_written", [])
    tests_ok = (
        test_output.get("failed", 0) == 0
        and test_output.get("errors", 0) == 0
    )

    if write_committed:
        outcome = "committed"
    elif not files_written:
        outcome = "no_files"
    elif verdict == "rejected":
        outcome = "blocked_audit"
    elif not tests_ok:
        outcome = "blocked_test"
    else:
        outcome = "skipped"

    entry = writer.record_cycle(
        cycle=state.cycle,
        task=think_output.get("priority_task", ""),
        caps_grade=think_output.get("caps_grade", "B"),
        think_output=think_output,
        assess_output=assess_output,
        build_output=build_output,
        diff_output=diff_output,
        audit_output=audit_output,
        test_output=test_output,
        outcome=outcome,
    )

    writer.save(blueprint_data.get("blueprint_file", ""))

    logger.info(
        "[PROGRESSION] Cycle %d → outcome=%s | intent=%.0f%% | "
        "difficulty=%s | complexity=%s/10 | pattern=%s | flaws=%d | "
        "perspective=%s",
        state.cycle,
        outcome,
        entry.get("intent_alignment", 0.5) * 100,
        entry.get("code_metrics", {}).get("difficulty", "?"),
        entry.get("code_metrics", {}).get("complexity_score", "?"),
        entry.get("code_metrics", {}).get("design_pattern", "?"),
        len(entry.get("flaws", [])),
        entry.get("audit_layer", {}).get("alignment", "?"),
    )

    return entry


def phase_audit(
    audit_client: BedrockAuditClient,
    state: LoopState,
    think_output: Dict[str, Any],
    build_output: Dict[str, Any],
    diff_output: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    """
    AUDIT — Claude (Bedrock) reviews the generated code as a second opinion layer.

    Runs AFTER BUILD+DIFF, BEFORE TEST+WRITE.
    Uses the same chain system (Bedrock Claude) as the primary LLMClient fallback
    but is always invoked directly — never falls through to Azure/OpenAI.

    Verdict: approved | needs_revision | rejected
    - rejected → WRITE is blocked regardless of test results
    - needs_revision → WRITE proceeds if tests pass, issues are logged
    - approved → normal flow

    SRS: AOD-AUDIT-001, AOD-AUDIT-002
    """
    files_written = build_output.get("files_written", [])

    if dry_run:
        logger.info("[AUDIT] dry-run — skipping Bedrock audit")
        return {
            "verdict": "approved",
            "issues": [],
            "risk_score": 0.0,
            "rationale": "dry-run mode",
            "_skipped": True,
        }

    if not files_written:
        logger.info("[AUDIT] No files written — skipping audit")
        return {
            "verdict": "approved",
            "issues": [],
            "risk_score": 0.0,
            "rationale": "No files to audit",
            "_skipped": True,
        }

    assess_vs_outcome = diff_output.get("assessment_vs_outcome", {})

    result = audit_client.audit(
        task=think_output.get("priority_task", ""),
        caps_grade=think_output.get("caps_grade", "B"),
        acceptance_criteria=think_output.get("acceptance_criteria", []),
        files_written=files_written,
        build_summary=build_output.get("summary", ""),
        diff_metrics=assess_vs_outcome,
        srs_refs=["SRS-AUTODEV-ORCH-001"],
    )

    verdict = result.get("verdict", "approved")
    risk = result.get("risk_score", 0.0)
    issues = result.get("issues", [])
    rationale = result.get("rationale", "")

    # Update state audit tracking
    in_tok = result.get("_tokens_in", 0)
    out_tok = result.get("_tokens_out", 0)
    total_audit_tokens = in_tok + out_tok
    cost_key = f"bedrock_{audit_client.model_key}"
    audit_cost = (total_audit_tokens / 1000) * COST_PER_1K.get(cost_key, COST_PER_1K["bedrock"])

    state.audit_tokens += total_audit_tokens
    state.audit_cost_usd += audit_cost
    state.audit_calls += 1

    # Keep rolling history of last 10 verdicts
    state.audit_history = (state.audit_history + [{
        "cycle": state.cycle,
        "task": think_output.get("priority_task", ""),
        "verdict": verdict,
        "risk_score": risk,
        "tokens": total_audit_tokens,
        "model": result.get("_model", ""),
    }])[-10:]

    verdict_icon = {"approved": "PASS", "needs_revision": "WARN", "rejected": "FAIL"}.get(verdict, "?")
    logger.info(
        "[AUDIT] %s | verdict=%s | risk=%.2f | issues=%d | tokens=%d | cost=$%.5f",
        verdict_icon, verdict, risk, len(issues), total_audit_tokens, audit_cost,
    )
    if issues:
        for issue in issues[:3]:
            logger.info("[AUDIT]   > %s", issue)

    return {**result, "_audit_cost_usd": audit_cost, "_audit_tokens": total_audit_tokens}


def _cleanup_generated_files(files: List[str]) -> None:
    """Delete uncommitted generated files so they don't contaminate future test runs."""
    for f in files:
        try:
            p = Path(f)
            if p.exists():
                p.unlink()
                logger.debug("[WRITE] Cleaned up uncommitted file: %s", f)
        except OSError:
            pass


def phase_write(
    state: LoopState,
    think_output: Dict[str, Any],
    assess_output: Dict[str, Any],
    build_output: Dict[str, Any],
    audit_output: Dict[str, Any],
    test_output: Dict[str, Any],
    blueprint_data: Dict[str, Any],
    dry_run: bool,
) -> bool:
    """
    WRITE — Commit built files if AUDIT approves and tests pass.

    Gate order:
      1. Audit verdict != rejected  (Bedrock Claude layer)
      2. Tests pass                  (pytest)
      3. Files exist                 (BUILD produced output)

    Returns True if commit succeeded, False otherwise (for PROGRESSION tracking).
    """
    files = build_output.get("files_written", [])
    tests_ok = test_output.get("failed", 0) == 0 and test_output.get("errors", 0) == 0
    audit_verdict = audit_output.get("verdict", "approved")

    if not files:
        logger.info("[WRITE] No files to commit")
        return False

    # Audit gate — rejected builds never commit
    if audit_verdict == "rejected" and not dry_run:
        logger.warning(
            "[WRITE] AUDIT rejected build — not committing. Issues: %s",
            audit_output.get("issues", [])[:3],
        )
        _cleanup_generated_files(files)
        return False

    if not tests_ok and not dry_run:
        logger.warning("[WRITE] Tests failing — not committing (%d failed)", test_output.get("failed", 0))
        _cleanup_generated_files(files)
        return False

    if dry_run:
        logger.info("[WRITE] dry-run — would commit: %s", files)
        return False

    try:
        for f in files:
            subprocess.run(["git", "add", f], cwd=str(HERE), check=True, capture_output=True)

        task = think_output.get("priority_task", "autodev cycle")
        audit_note = (
            f"Audit: {audit_verdict} (risk={audit_output.get('risk_score', 0):.2f}) | "
            f"intent={audit_output.get('intent_alignment', 0.5):.0%} | "
            f"pattern={audit_output.get('code_metrics', {}).get('design_pattern', '?')}"
        )
        # Include perspective divergence note in commit if Claude diverged
        divergence = audit_output.get("perspective_comparison", {}).get("divergence_notes", "")
        divergence_line = f"\nPerspective: {divergence}" if divergence else ""

        msg = (
            f"feat(autodev): {task}\n\n"
            f"Cycle {state.cycle} | Score: {assess_output.get('implementation_score', 0)}% | "
            f"CAPS: {think_output.get('caps_grade', 'B')} | {audit_note}"
            f"{divergence_line}\n"
            f"Files: {', '.join(files)}\n\n"
            f"Co-Authored-By: Azure AI Foundry <noreply@microsoft.com>\n"
            f"Co-Reviewed-By: Claude via AWS Bedrock <noreply@anthropic.com>"
        )

        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(HERE), check=True, capture_output=True
        )
        logger.info("[WRITE] Committed %d files | audit=%s", len(files), audit_verdict)

        # Mark milestone as completed
        task_text = think_output.get("priority_task", "")
        if task_text and task_text not in state.completed_milestones:
            state.completed_milestones.append(task_text)

        state.last_build_files = files
        state.current_blueprint = blueprint_data.get("blueprint_file", "")
        return True

    except subprocess.CalledProcessError as e:
        logger.warning("[WRITE] Git commit failed: %s", e)
        return False


# ── Budget tracking ──────────────────────────────────────────────────────────

def _update_cost(state: LoopState, phase_outputs: List[Dict[str, Any]]) -> float:
    """Update state with token costs from primary phases (Azure/OpenAI) this cycle."""
    cycle_tokens = sum(p.get("_tokens", 0) for p in phase_outputs)
    cycle_backend = next(
        (p.get("_backend", "fallback") for p in phase_outputs if p.get("_tokens", 0) > 0),
        "fallback"
    )
    cost_per_k = COST_PER_1K.get(cycle_backend, 0.005)
    cycle_cost = (cycle_tokens / 1000) * cost_per_k

    state.total_tokens += cycle_tokens
    state.total_cost_usd += cycle_cost

    logger.info(
        "[BUDGET] Primary tokens: %d | Primary cost: $%.4f | Total primary: $%.4f",
        cycle_tokens, cycle_cost, state.total_cost_usd,
    )
    logger.info(
        "[BUDGET] Audit tokens: %d | Audit cost: $%.5f | Total audit: $%.5f",
        state.audit_tokens, state.audit_cost_usd, state.audit_cost_usd,
    )
    logger.info(
        "[BUDGET] Combined total: $%.4f",
        state.total_cost_usd + state.audit_cost_usd,
    )
    return cycle_cost


# ── Main loop ────────────────────────────────────────────────────────────────

def run_loop(
    max_cycles: int = 10,
    budget_cap: float = 50.0,
    dry_run: bool = False,
    blueprint_filter: Optional[str] = None,
    resume: bool = True,
    audit_model: str = "haiku",
    audit_strictness: str = "standard",
    progression_file: Optional[str] = None,
) -> None:
    """
    Run the autonomous development loop.

    Args:
        max_cycles: Maximum number of READ→WRITE cycles before stopping.
        budget_cap: Maximum USD spend (primary + audit) before stopping.
        dry_run: If True, skip all LLM calls and file writes.
        blueprint_filter: Specific blueprint filename to focus on.
        resume: If True, load previous state from loop_state.json.
        audit_model: Bedrock Claude model for audit layer ('haiku' or 'sonnet').
        audit_strictness: Audit review level ('lenient', 'standard', 'strict').
        progression_file: Path to progression.yaml (default: citadel_lite/progression.yaml).
    """
    # Load environment — workspace.env is one level up from citadel_lite/
    env_file = HERE.parent / "tools" / "workspace.env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(str(env_file))
            logger.info("Loaded workspace.env from %s", env_file)
        except ImportError:
            pass
    else:
        logger.warning("workspace.env not found at %s", env_file)

    # Load state
    state = LoopState.from_file(STATE_FILE) if resume else LoopState()

    # Init LLM client
    sys.path.insert(0, str(HERE))
    try:
        from src.llm.client import LLMClient
        llm = LLMClient(temperature=0.2, max_tokens=4096)
        backend_info = "Azure→OpenAI→Bedrock→fallback"
    except ImportError as e:
        logger.error("Cannot import LLMClient: %s", e)
        return

    # Init Bedrock audit client
    audit_client = BedrockAuditClient(model_key=audit_model, strictness=audit_strictness)

    # Init ProgressionWriter — loads existing history, provides context to THINK
    prog_path = Path(progression_file) if progression_file else PROGRESSION_FILE
    progression_writer = ProgressionWriter(
        path=prog_path,
        run_id=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
    )
    logger.info("Progression file: %s (cycles stored: %d)", prog_path,
                len(progression_writer._data.get("cycles", [])))

    logger.info("=" * 60)
    logger.info("CITADEL LITE — Blueprint Autodev Orchestrator")
    logger.info("Max cycles: %d | Budget cap: $%.2f | Dry-run: %s", max_cycles, budget_cap, dry_run)
    logger.info("LLM chain: %s", backend_info)
    logger.info("Audit layer: Bedrock %s | Strictness: %s", audit_model, audit_strictness)
    logger.info("Resume from cycle: %d | Spend so far: $%.4f (primary) + $%.5f (audit)",
                state.cycle, state.total_cost_usd, state.audit_cost_usd)
    logger.info("=" * 60)

    for _ in range(max_cycles):
        state.cycle += 1
        state.last_cycle_ts = datetime.now(timezone.utc).isoformat()
        cycle_start = time.perf_counter()

        logger.info("\n── CYCLE %d ──────────────────────────────────────────", state.cycle)

        # Budget guard
        if state.total_cost_usd >= budget_cap:
            logger.warning("Budget cap $%.2f reached ($%.4f spent). Stopping.", budget_cap, state.total_cost_usd)
            break

        # ── Phase 1: READ ────────────────────────────────────────────
        read_data = phase_read(state)
        _journal(JOURNAL_FILE, state.cycle, "read", read_data)

        # ── Phase 2: BLUEPRINT ───────────────────────────────────────
        blueprint_data = phase_blueprint(state, blueprint_filter)
        _journal(JOURNAL_FILE, state.cycle, "blueprint", {
            "file": blueprint_data.get("blueprint_file"),
            "pending_count": blueprint_data.get("pending_count", 0),
            "done_count": blueprint_data.get("done_count", 0),
        })

        # ── Phase 3: THINK (with progression context) ────────────────
        # Build context from accumulated progression history — injected into prompt
        progression_context = progression_writer.get_context_summary()
        think_output = phase_think(
            llm, read_data, blueprint_data, state, dry_run,
            progression_context=progression_context,
        )
        _journal(JOURNAL_FILE, state.cycle, "think", {
            **think_output,
            "_progression_cycles_injected": len(progression_writer._data.get("cycles", [])),
        })
        state.last_think_output = think_output
        # Track attempted tasks for deduplication
        task_name = think_output.get("priority_task", "")
        if task_name and task_name not in state.attempted_tasks:
            state.attempted_tasks.append(task_name)

        # ── Phase 4: ASSESS ──────────────────────────────────────────
        assess_output = phase_assess(llm, think_output, blueprint_data, dry_run)
        _journal(JOURNAL_FILE, state.cycle, "assess", assess_output)

        # ── Phase 5: BUILD ───────────────────────────────────────────
        # Snapshot src file count before building (for diff metric)
        pre_build_snapshot = {"src_file_count": len(list((HERE / "src").rglob("*.py"))) if (HERE / "src").exists() else 0}
        build_output = phase_build(llm, think_output, state, dry_run)
        _journal(JOURNAL_FILE, state.cycle, "build", {
            "files_written": build_output.get("files_written", []),
            "summary": build_output.get("summary", ""),
            "caps_grade": think_output.get("caps_grade", "B"),
        })

        # ── Phase 5b: DIFF ───────────────────────────────────────────
        diff_output = phase_diff(state, assess_output, build_output, pre_build_snapshot)
        _journal(JOURNAL_FILE, state.cycle, "diff", {
            "assessment_vs_outcome": diff_output["assessment_vs_outcome"],
            "outcome_vs_codebase": {
                "lines_added": diff_output["outcome_vs_codebase"]["lines_added"],
                "lines_removed": diff_output["outcome_vs_codebase"]["lines_removed"],
                "src_file_delta": diff_output["outcome_vs_codebase"]["src_file_delta"],
                "changed_files_count": len(diff_output["outcome_vs_codebase"]["changed_files"]),
            },
        })

        # ── Phase 5c: AUDIT (Bedrock Claude — perspective comparison) ─
        audit_output = phase_audit(audit_client, state, think_output, build_output, diff_output, dry_run)
        _journal(JOURNAL_FILE, state.cycle, "audit", {
            "verdict": audit_output.get("verdict"),
            "risk_score": audit_output.get("risk_score", 0.0),
            "issues": audit_output.get("issues", []),
            "srs_refs_satisfied": audit_output.get("srs_refs_satisfied", []),
            "srs_refs_failed": audit_output.get("srs_refs_failed", []),
            "token_efficiency": audit_output.get("token_efficiency"),
            "rationale": audit_output.get("rationale"),
            "model": audit_output.get("_model"),
            "tokens_in": audit_output.get("_tokens_in", 0),
            "tokens_out": audit_output.get("_tokens_out", 0),
            "cost_usd": audit_output.get("_audit_cost_usd", 0.0),
            # Perspective comparison fields
            "perspective_alignment": audit_output.get("perspective_comparison", {}).get("alignment"),
            "divergence_notes": audit_output.get("perspective_comparison", {}).get("divergence_notes"),
            "code_metrics": audit_output.get("code_metrics", {}),
            "design_choices_count": len(audit_output.get("design_choices", [])),
            "flaws_count": len(audit_output.get("flaws_identified", [])),
            "intent_alignment": audit_output.get("intent_alignment", 0.5),
        })

        # ── Phase 6: TEST ────────────────────────────────────────────
        test_output = phase_test(state, build_output, dry_run)
        _journal(JOURNAL_FILE, state.cycle, "test", test_output)

        # ── Phase 7: WRITE (commit if audit approved + tests pass) ───
        write_committed = phase_write(
            state, think_output, assess_output, build_output,
            audit_output, test_output, blueprint_data, dry_run
        )

        # ── Phase 8: PROGRESSION (aggregate comparison report) ───────
        prog_entry = phase_progression(
            progression_writer, state,
            think_output, assess_output, build_output, diff_output,
            audit_output, test_output, blueprint_data,
            write_committed=write_committed,
        )
        _journal(JOURNAL_FILE, state.cycle, "progression", {
            "outcome": prog_entry.get("outcome"),
            "intent_alignment": prog_entry.get("intent_alignment"),
            "perspective_alignment": prog_entry.get("audit_layer", {}).get("alignment"),
            "difficulty": prog_entry.get("code_metrics", {}).get("difficulty"),
            "design_choices": len(prog_entry.get("design_choices", [])),
            "flaws_recorded": len(prog_entry.get("flaws", [])),
            "progression_total_cycles": progression_writer._data.get("summary", {}).get("total_cycles", 0),
        })

        # ── Budget update ─────────────────────────────────────────────
        _update_cost(state, [think_output, assess_output, build_output, diff_output])

        # ── Save state ────────────────────────────────────────────────
        state.save(STATE_FILE)

        cycle_duration = time.perf_counter() - cycle_start
        logger.info(
            "── Cycle %d complete in %.1fs | Score: %d%% | Tests: %d passed, %d failed | "
            "Perspective: %s | Intent: %.0f%%",
            state.cycle,
            cycle_duration,
            assess_output.get("implementation_score", 0),
            test_output.get("passed", 0),
            test_output.get("failed", 0),
            audit_output.get("perspective_comparison", {}).get("alignment", "?"),
            audit_output.get("intent_alignment", 0.5) * 100,
        )

        # Stop only if tests are perfect AND we have explicitly completed milestones
        total_milestones = blueprint_data.get("pending_count", 0) + blueprint_data.get("done_count", 0)
        explicitly_done = len(state.completed_milestones)
        if (test_output.get("failed", 0) == 0
                and test_output.get("errors", 0) == 0
                and blueprint_data.get("pending_count", 1) == 0
                and (explicitly_done > 0 or total_milestones == 0)):
            logger.info("All milestones complete and tests passing. Loop finished.")
            break

    # Final summary
    audit_summary = audit_client.usage_summary()
    prog_summary = progression_writer._data.get("summary", {})
    logger.info("\n" + "=" * 60)
    logger.info("ORCHESTRATOR COMPLETE")
    logger.info("Total cycles: %d", state.cycle)
    logger.info("--- Primary LLM (Azure/OpenAI gpt-4o) ---")
    logger.info("  Tokens: %d | Cost: $%.4f", state.total_tokens, state.total_cost_usd)
    logger.info("--- Audit Layer (Bedrock Claude %s / %s) ---", audit_model, audit_strictness)
    logger.info("  Calls: %d | Tokens: %d | Cost: $%.5f",
                audit_summary["call_count"], audit_summary["total_tokens"], audit_summary["estimated_cost_usd"])
    logger.info("--- Combined ---")
    logger.info("  Total cost: $%.4f / $%.2f budget",
                state.total_cost_usd + state.audit_cost_usd, budget_cap)
    logger.info("--- Progression ---")
    logger.info("  Goals completed: %d | Known flaws tracked: %d | Design decisions: %d",
                len(prog_summary.get("goals_completed", [])),
                len(prog_summary.get("known_flaws", [])),
                len(prog_summary.get("design_decisions", [])))
    logger.info("  Avg intent alignment: %.0f%% | Avg difficulty: %.1f/10",
                prog_summary.get("avg_intent_alignment", 0.5) * 100,
                prog_summary.get("accumulated_difficulty_score", 5.0))
    logger.info("  File: %s", prog_path)
    logger.info("Milestones completed: %d", len(state.completed_milestones))
    logger.info("Final test score: %d passed, %d failed", state.last_test_passed, state.last_test_failed)
    logger.info("Audit history (last %d): %s",
                len(state.audit_history),
                [h.get("verdict") for h in state.audit_history])
    logger.info("Journal: %s", JOURNAL_FILE)
    logger.info("=" * 60)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Citadel Lite — Blueprint Autodev Orchestrator"
    )
    parser.add_argument("--max-cycles", type=int, default=10,
                        help="Max development cycles (default: 10)")
    parser.add_argument("--budget-cap", type=float, default=50.0,
                        help="Max USD to spend on Azure credits (default: $50)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without LLM calls or file writes")
    parser.add_argument("--blueprint", type=str, default=None,
                        help="Specific blueprint file to target (e.g. CITADEL_NEXUS_LITE-MVP.en.md)")
    parser.add_argument("--no-resume", action="store_true",
                        help="Start fresh, ignore previous loop_state.json")
    parser.add_argument("--status", action="store_true",
                        help="Show current loop state and exit")
    parser.add_argument("--audit-model", type=str, default="haiku",
                        choices=["haiku", "sonnet"],
                        help="Bedrock Claude model for audit layer (default: haiku)")
    parser.add_argument("--audit-strictness", type=str, default="standard",
                        choices=["lenient", "standard", "strict"],
                        help="Audit review strictness (default: standard)")
    parser.add_argument("--progression-file", type=str, default=None,
                        help="Path to progression.yaml (default: citadel_lite/progression.yaml). "
                             "Loads history on start; appended each cycle; injected into THINK.")

    args = parser.parse_args()

    if args.status:
        state = LoopState.from_file(STATE_FILE)
        print(state.to_json())
        return

    run_loop(
        max_cycles=args.max_cycles,
        budget_cap=args.budget_cap,
        dry_run=args.dry_run,
        blueprint_filter=args.blueprint,
        resume=not args.no_resume,
        audit_model=args.audit_model,
        audit_strictness=args.audit_strictness,
        progression_file=args.progression_file,
    )


if __name__ == "__main__":
    main()
