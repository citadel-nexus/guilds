# src/agents/intent_generator.py
"""
Intent Generator — Autonomous task creation from system state.

Reads:
- Open GitHub/GitLab issues (prioritized by labels)
- Watcher/Scaler/Curator infrastructure findings
- Failed test patterns
- College professor knowledge gaps (if available)

Outputs:
- SAKE-compatible task specifications for the development pipeline

This is the "brain" that decides WHAT to build next without human input.
It closes the loop: system state → intent → SAKE → code → test → merge.

CGRF v3.0 Compliance:
- SRS Code: SRS-INTENT-GEN-001
- Tier: 2 (STAGING)
- Execution Role: ORCHESTRATION

@module citadel_lite.src.agents.intent_generator
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket

logger = logging.getLogger(__name__)

# Priority weights for different intent sources
_PRIORITY_WEIGHTS = {
    "watcher_critical": 1.0,
    "watcher_warning": 0.7,
    "rollback_remediation": 0.9,
    "github_bug": 0.8,
    "github_enhancement": 0.5,
    "test_failure": 0.85,
    "college_gap": 0.3,
}

# Labels that make issues eligible for auto-processing
_AUTO_ELIGIBLE_LABELS = {"auto-eligible", "auto-fix", "bot-ok", "automated"}
_BUG_LABELS = {"bug", "defect", "regression", "broken"}
_ENHANCEMENT_LABELS = {"enhancement", "feature", "improvement"}


def _issue_to_sake_spec(issue: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a GitHub/GitLab issue to a SAKE-compatible task specification."""
    title = issue.get("title", "Unknown task")
    body = issue.get("body", "") or issue.get("description", "")
    labels = [l.get("name", l) if isinstance(l, dict) else l for l in issue.get("labels", [])]

    # Determine language from labels or default
    language = "Python"
    if any("typescript" in l.lower() or "frontend" in l.lower() for l in labels):
        language = "TypeScript"

    return {
        "filetype": "SAKE",
        "version": "1.0",
        "taskir_blocks": {
            "task_name": title.replace(" ", ""),
            "purpose": title,
            "inputs": ["issue_context"],
            "outputs": ["code_change"],
            "preconditions": "Codebase is in a stable state",
            "postconditions": body[:200] if body else "Issue requirements met",
            "algorithm_summary": f"Implement: {title}",
            "pseudocode": body[:500] if body else f"# TODO: {title}",
            "design_notes": f"Auto-generated from issue #{issue.get('number', 'unknown')}",
            "complexity": "O(n)",
            "edge_cases": "See issue description",
            "test_spec": f"Verify {title} works as described",
            "extensibility_hooks": "post_implement",
        },
        "sake_layers": {
            "backend_layer": {
                "language": language,
                "framework": "Standalone",
                "entrypoint": f"{title.replace(' ', '')}.execute",
            },
            "caps_profile": {
                "confidence": 0.7,
                "cost": 0.2,
                "latency_ms": 5000.0,
                "risk": 0.3,
                "precision": 0.8,
                "trust_score": 0.75,
                "grade": "T2",
            },
        },
        "metadata": {
            "srs_code": "F993",
            "generator": "intent_generator",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reflex_group": "AUTO_DEV",
            "code_gen_hooks": ["post_generate", "post_test"],
        },
        "_source": {
            "type": "issue",
            "id": issue.get("number", issue.get("iid")),
            "url": issue.get("url", issue.get("web_url")),
        },
    }


def _finding_to_sake_spec(finding: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Watcher/infra finding to a SAKE task specification."""
    event_type = finding.get("event_type", "unknown")
    action = finding.get("recommended_action", "investigate")
    signals = finding.get("signals", [])

    return {
        "filetype": "SAKE",
        "version": "1.0",
        "taskir_blocks": {
            "task_name": f"AutoFix{event_type.replace('_', '')}",
            "purpose": f"Auto-fix infrastructure issue: {event_type}",
            "inputs": ["infrastructure_state", "signals"],
            "outputs": ["remediation_action"],
            "preconditions": f"Detected: {', '.join(signals[:3])}",
            "postconditions": f"Infrastructure issue {event_type} resolved",
            "algorithm_summary": f"Apply remediation for {event_type}: {action}",
            "pseudocode": f"# Detect {event_type}\n# Apply {action}\n# Verify resolution",
            "design_notes": f"Auto-generated from Watcher finding",
            "complexity": "O(1)",
            "edge_cases": "Service may be unreachable",
            "test_spec": f"Verify {event_type} is resolved after action",
            "extensibility_hooks": "post_remediation",
        },
        "sake_layers": {
            "backend_layer": {
                "language": "Python",
                "framework": "Standalone",
                "entrypoint": f"AutoFix{event_type.replace('_', '')}.execute",
            },
            "caps_profile": {
                "confidence": 0.8,
                "cost": 0.1,
                "latency_ms": 1000.0,
                "risk": 0.2,
                "precision": 0.9,
                "trust_score": 0.8,
                "grade": "T1",
            },
        },
        "metadata": {
            "srs_code": "F993",
            "generator": "intent_generator",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reflex_group": "INFRA_FIX",
            "code_gen_hooks": ["post_generate"],
        },
    }


def _get_github_issues() -> List[Dict[str, Any]]:
    """Fetch open auto-eligible issues from GitHub/GitLab."""
    try:
        from src.github.client import GitHubClient
        client = GitHubClient()
        issues = client.list_issues(state="open")
        # Filter for auto-eligible
        eligible = []
        for issue in issues:
            labels = {
                (l.get("name", l) if isinstance(l, dict) else l).lower()
                for l in issue.get("labels", [])
            }
            if labels & _AUTO_ELIGIBLE_LABELS:
                eligible.append(issue)
        return eligible
    except Exception as e:
        logger.debug("GitHub issues unavailable: %s", e)
        return []


def _calculate_priority(issue: Dict[str, Any]) -> float:
    """Calculate priority score for an issue based on labels and metadata."""
    labels = {
        (l.get("name", l) if isinstance(l, dict) else l).lower()
        for l in issue.get("labels", [])
    }

    if labels & _BUG_LABELS:
        return _PRIORITY_WEIGHTS["github_bug"]
    if labels & _ENHANCEMENT_LABELS:
        return _PRIORITY_WEIGHTS["github_enhancement"]
    return 0.4


def run_intent_generator(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Generate autonomous development intents from system state.

    Reads infrastructure findings, open issues, and failed tests
    to produce prioritized SAKE task specifications.

    Returns:
        Dict with selected_intent, intent_queue, and queue_depth.
    """
    intents: List[Dict[str, Any]] = []

    # 1. Check infrastructure findings (highest priority)
    watcher = packet.agent_outputs.get("watcher")
    if watcher:
        w_data = watcher.payload if hasattr(watcher, "payload") else watcher
        severity = w_data.get("severity", "info")
        if severity in ("critical", "warning"):
            priority = (
                _PRIORITY_WEIGHTS["watcher_critical"]
                if severity == "critical"
                else _PRIORITY_WEIGHTS["watcher_warning"]
            )
            intents.append({
                "source": "watcher_finding",
                "id": w_data.get("event_type", "unknown"),
                "title": f"Auto-fix: {w_data.get('recommended_action', 'investigate')}",
                "priority": priority,
                "sake_spec": _finding_to_sake_spec(w_data),
            })

    # 2. Check for rollback remediation tasks
    rollback = packet.agent_outputs.get("rollback")
    if rollback:
        r_data = rollback.payload if hasattr(rollback, "payload") else rollback
        if r_data.get("remediation_task_created"):
            intents.append({
                "source": "rollback_remediation",
                "id": r_data.get("failing_commit", "unknown"),
                "title": f"Fix regression from {r_data.get('failing_commit', 'unknown')[:8]}",
                "priority": _PRIORITY_WEIGHTS["rollback_remediation"],
                "sake_spec": r_data.get("remediation_sake_spec", {}),
            })

    # 3. Scan GitHub/GitLab issues
    try:
        issues = _get_github_issues()
        for issue in issues[:5]:
            intents.append({
                "source": "github_issue",
                "id": issue.get("number", issue.get("iid")),
                "title": issue.get("title", "Unknown"),
                "priority": _calculate_priority(issue),
                "sake_spec": _issue_to_sake_spec(issue),
            })
    except Exception as e:
        logger.debug("Issue scanning failed: %s", e)

    # 4. Sort by priority
    intents.sort(key=lambda x: x["priority"], reverse=True)

    return {
        "selected_intent": intents[0] if intents else None,
        "intent_queue": intents,
        "queue_depth": len(intents),
        "timestamp": time.time(),
    }
