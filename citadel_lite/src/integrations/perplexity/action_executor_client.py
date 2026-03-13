"""
PerplexityActionExecutor — executes action lists returned by Perplexity Loop.

Actions are Notion / Linear / GitLab write operations recommended by the
diagnostic WRITE stage.  In dry_run mode (default) writes are logged only.

CGRF compliance
---------------
_MODULE_NAME    = "action_executor_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "action_executor_client"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


class PerplexityActionExecutor:
    """
    Executes action items emitted by Perplexity WRITE stage.

    Each action dict has at minimum: ``type`` (str) and ``payload`` (dict).
    Supported types: ``notion_page``, ``linear_issue``, ``gitlab_mr`` (stubs).
    """

    def __init__(self, dry_run: bool = True):
        self._dry_run = dry_run

    def execute(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute a list of diagnostic actions.

        Returns a list of result dicts: ``{"type": ..., "status": "ok"|"dry_run"|"stub"}``.
        """
        results = []
        for action in actions:
            action_type = action.get("type", "unknown")
            if self._dry_run:
                logger.info("PerplexityActionExecutor: dry_run — skip %s", action_type)
                results.append({"type": action_type, "status": "dry_run"})
                continue
            result = self._dispatch(action_type, action.get("payload", {}))
            results.append({"type": action_type, "status": result})
        return results

    def _dispatch(self, action_type: str, payload: Dict[str, Any]) -> str:
        """Route action to the appropriate handler stub."""
        handlers = {
            "notion_page": self._handle_notion_page,
            "linear_issue": self._handle_linear_issue,
            "gitlab_mr": self._handle_gitlab_mr,
        }
        handler = handlers.get(action_type)
        if handler is None:
            logger.warning("PerplexityActionExecutor: unknown action type '%s'", action_type)
            return "stub"
        return handler(payload)

    def _handle_notion_page(self, payload: Dict[str, Any]) -> str:
        logger.info("PerplexityActionExecutor: notion_page stub (wired in MS-A3)")
        return "stub"

    def _handle_linear_issue(self, payload: Dict[str, Any]) -> str:
        logger.info("PerplexityActionExecutor: linear_issue stub (wired in MS-A3)")
        return "stub"

    def _handle_gitlab_mr(self, payload: Dict[str, Any]) -> str:
        logger.info("PerplexityActionExecutor: gitlab_mr stub (wired in MS-A3)")
        return "stub"
