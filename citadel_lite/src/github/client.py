# src/github/client.py
"""
GitHub REST API client for the Citadel Lite execution layer.

Provides:
- Branch creation
- File commits (create/update)
- Pull request creation
- Workflow log fetching
- Workflow reruns
- Webhook signature verification

Uses httpx for async-ready HTTP. Auth via GITHUB_TOKEN env var.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy httpx import
# ---------------------------------------------------------------------------

def _get_httpx():
    try:
        import httpx  # type: ignore
        return httpx
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PRResult:
    success: bool = False
    pr_url: str = ""
    pr_number: int = 0
    branch: str = ""
    error: str = ""


@dataclass
class WorkflowLog:
    run_id: int = 0
    status: str = ""
    conclusion: str = ""
    log_text: str = ""
    html_url: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class GitHubClient:
    """
    GitHub REST API client.

    Usage:
        gh = GitHubClient()
        result = gh.create_fix_pr(
            repo="owner/repo",
            base_branch="main",
            title="Fix missing dependency",
            body="Adds requests to requirements.txt",
            files={"requirements.txt": "requests\\nflask\\n"},
        )
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self._httpx = _get_httpx()

    def is_available(self) -> bool:
        return bool(self.token and self._httpx)

    # ------------------------------------------------------------------
    # Headers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Make an API request. Returns parsed JSON or error dict."""
        if not self._httpx:
            return {"error": "httpx not installed"}
        if not self.token:
            return {"error": "GITHUB_TOKEN not set"}

        url = f"{self.BASE_URL}{path}"
        try:
            resp = self._httpx.request(
                method, url, headers=self._headers(), timeout=30.0, **kwargs
            )
            if resp.status_code >= 400:
                return {
                    "error": f"HTTP {resp.status_code}",
                    "detail": resp.text[:500],
                }
            if resp.status_code == 204:
                return {"success": True}
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Branch operations
    # ------------------------------------------------------------------

    def get_default_branch_sha(self, repo: str) -> str:
        """Get the SHA of the default branch HEAD."""
        data = self._request("GET", f"/repos/{repo}/git/ref/heads/main")
        if "error" in data:
            # Try 'master' fallback
            data = self._request("GET", f"/repos/{repo}/git/ref/heads/master")
        return data.get("object", {}).get("sha", "")

    def create_branch(self, repo: str, branch_name: str, from_sha: str) -> bool:
        """Create a new branch from a given SHA."""
        data = self._request(
            "POST",
            f"/repos/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": from_sha},
        )
        return "error" not in data

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def create_or_update_file(
        self,
        repo: str,
        branch: str,
        path: str,
        content: str,
        message: str,
    ) -> bool:
        """Create or update a file on a branch."""
        import base64

        # Check if file exists (to get SHA for update)
        existing = self._request(
            "GET", f"/repos/{repo}/contents/{path}", params={"ref": branch}
        )
        file_sha = existing.get("sha") if "error" not in existing else None

        payload: Dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if file_sha:
            payload["sha"] = file_sha

        data = self._request("PUT", f"/repos/{repo}/contents/{path}", json=payload)
        return "error" not in data

    # ------------------------------------------------------------------
    # Pull Request
    # ------------------------------------------------------------------

    def create_pull_request(
        self,
        repo: str,
        branch: str,
        base: str,
        title: str,
        body: str,
    ) -> PRResult:
        """Create a pull request."""
        data = self._request(
            "POST",
            f"/repos/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": branch,
                "base": base,
            },
        )
        if "error" in data:
            return PRResult(success=False, error=data.get("error", ""))
        return PRResult(
            success=True,
            pr_url=data.get("html_url", ""),
            pr_number=data.get("number", 0),
            branch=branch,
        )

    def create_fix_pr(
        self,
        repo: str,
        base_branch: str,
        title: str,
        body: str,
        files: Dict[str, str],
        branch_prefix: str = "citadel-fix",
    ) -> PRResult:
        """
        End-to-end: create branch, commit files, open PR.

        Args:
            repo: "owner/repo"
            base_branch: branch to target (e.g., "main")
            title: PR title
            body: PR body (markdown)
            files: {file_path: file_content} to commit
            branch_prefix: prefix for the fix branch
        """
        # 1. Get base SHA
        base_sha = self.get_default_branch_sha(repo)
        if not base_sha:
            return PRResult(success=False, error="Could not get base branch SHA")

        # 2. Create fix branch
        branch_name = f"{branch_prefix}/{int(time.time())}"
        if not self.create_branch(repo, branch_name, base_sha):
            return PRResult(success=False, error="Could not create branch")

        # 3. Commit files
        for path, content in files.items():
            if not self.create_or_update_file(
                repo, branch_name, path,
                content, f"citadel-fix: {title}"
            ):
                return PRResult(
                    success=False,
                    error=f"Could not commit {path}",
                    branch=branch_name,
                )

        # 4. Create PR
        return self.create_pull_request(
            repo, branch_name, base_branch, title, body
        )

    # ------------------------------------------------------------------
    # Workflow / CI operations
    # ------------------------------------------------------------------

    def get_latest_workflow_run(self, repo: str) -> WorkflowLog:
        """Get the most recent workflow run."""
        data = self._request(
            "GET",
            f"/repos/{repo}/actions/runs",
            params={"per_page": 1},
        )
        runs = data.get("workflow_runs", [])
        if not runs:
            return WorkflowLog()
        run = runs[0]
        return WorkflowLog(
            run_id=run.get("id", 0),
            status=run.get("status", ""),
            conclusion=run.get("conclusion", ""),
            html_url=run.get("html_url", ""),
        )

    def get_workflow_logs(self, repo: str, run_id: int) -> str:
        """Fetch workflow run logs (text). Returns truncated log content."""
        if not self._httpx:
            return ""
        try:
            url = f"{self.BASE_URL}/repos/{repo}/actions/runs/{run_id}/logs"
            resp = self._httpx.get(
                url, headers=self._headers(), timeout=30.0, follow_redirects=True
            )
            if resp.status_code == 200:
                # Logs come as a zip — return first 4KB of raw content as fallback
                return resp.text[:4096] if resp.headers.get("content-type", "").startswith("text") else f"[binary log archive, {len(resp.content)} bytes]"
            return f"[HTTP {resp.status_code}]"
        except Exception as e:
            return f"[error: {e}]"

    def rerun_workflow(self, repo: str, run_id: int) -> bool:
        """Re-run a failed workflow."""
        data = self._request("POST", f"/repos/{repo}/actions/runs/{run_id}/rerun")
        return "error" not in data

    # ------------------------------------------------------------------
    # PR status checks and merging
    # ------------------------------------------------------------------

    def get_pr_checks(self, repo: str, pr_number: int) -> Dict[str, Any]:
        """
        Get combined CI status for a PR.

        Returns:
            {
                "state": "success" | "pending" | "failure" | "error",
                "statuses": [...],
                "check_runs": [...]
            }
        """
        # Get PR details to get the head SHA
        pr_data = self._request("GET", f"/repos/{repo}/pulls/{pr_number}")
        if "error" in pr_data:
            return {"state": "error", "error": pr_data.get("error")}

        head_sha = pr_data.get("head", {}).get("sha")
        if not head_sha:
            return {"state": "error", "error": "No head SHA"}

        # Get combined status (legacy status checks)
        status_data = self._request(
            "GET", f"/repos/{repo}/commits/{head_sha}/status"
        )

        # Get check runs (GitHub Actions checks)
        checks_data = self._request(
            "GET", f"/repos/{repo}/commits/{head_sha}/check-runs"
        )

        # Combine results
        combined_state = status_data.get("state", "pending")
        check_runs = checks_data.get("check_runs", [])

        # If any check run is still in progress, state is pending
        for run in check_runs:
            if run.get("status") != "completed":
                combined_state = "pending"
                break
            if run.get("conclusion") in ("failure", "cancelled", "timed_out"):
                combined_state = "failure"

        return {
            "state": combined_state,
            "statuses": status_data.get("statuses", []),
            "check_runs": check_runs,
            "total_count": status_data.get("total_count", 0) + len(check_runs),
        }

    def wait_for_ci(
        self,
        repo: str,
        pr_number: int,
        timeout: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """
        Wait for CI checks to complete on a PR.

        Args:
            repo: "owner/repo"
            pr_number: PR number
            timeout: Maximum wait time in seconds (default: 300 = 5 min)
            poll_interval: Check interval in seconds (default: 10)

        Returns:
            {
                "success": bool,
                "state": "success" | "failure" | "timeout" | "error",
                "elapsed_seconds": int,
                "checks": {...}
            }
        """
        start_time = time.time()
        elapsed = 0

        logger.info(f"Waiting for CI on {repo}#{pr_number} (timeout={timeout}s)")

        while elapsed < timeout:
            checks = self.get_pr_checks(repo, pr_number)

            if checks.get("state") == "success":
                logger.info(f"CI passed on {repo}#{pr_number} after {elapsed}s")
                return {
                    "success": True,
                    "state": "success",
                    "elapsed_seconds": elapsed,
                    "checks": checks,
                }

            if checks.get("state") in ("failure", "error"):
                logger.warning(f"CI failed on {repo}#{pr_number} after {elapsed}s")
                return {
                    "success": False,
                    "state": checks.get("state"),
                    "elapsed_seconds": elapsed,
                    "checks": checks,
                }

            # Still pending, wait and retry
            time.sleep(poll_interval)
            elapsed = int(time.time() - start_time)

        logger.warning(f"CI timeout on {repo}#{pr_number} after {elapsed}s")
        return {
            "success": False,
            "state": "timeout",
            "elapsed_seconds": elapsed,
            "checks": self.get_pr_checks(repo, pr_number),
        }

    def merge_pr(
        self,
        repo: str,
        pr_number: int,
        merge_method: str = "squash",
        commit_title: str = "",
        commit_message: str = "",
    ) -> Dict[str, Any]:
        """
        Merge a pull request.

        Args:
            repo: "owner/repo"
            pr_number: PR number
            merge_method: "merge", "squash", or "rebase"
            commit_title: Optional custom commit title
            commit_message: Optional custom commit message

        Returns:
            {
                "success": bool,
                "sha": str,  # merge commit SHA
                "merged": bool,
                "message": str,
            }
        """
        payload: Dict[str, Any] = {"merge_method": merge_method}

        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message

        data = self._request(
            "PUT",
            f"/repos/{repo}/pulls/{pr_number}/merge",
            json=payload,
        )

        if "error" in data:
            logger.error(f"Failed to merge PR {repo}#{pr_number}: {data.get('error')}")
            return {
                "success": False,
                "merged": False,
                "message": data.get("error", "Unknown error"),
            }

        logger.info(f"Successfully merged PR {repo}#{pr_number}")
        return {
            "success": True,
            "sha": data.get("sha", ""),
            "merged": data.get("merged", False),
            "message": data.get("message", ""),
        }

    # ------------------------------------------------------------------
    # Webhook verification
    # ------------------------------------------------------------------

    @staticmethod
    def verify_webhook_signature(
        payload: bytes, signature: str, secret: str
    ) -> bool:
        """Verify GitHub webhook X-Hub-Signature-256."""
        if not signature.startswith("sha256="):
            return False
        expected = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
