# src/gitlab/client.py
"""
GitLab REST API v4 client for the Citadel Lite execution layer.

Provides:
- Project lookup by namespace path
- Branch creation
- File commits (create/update)
- Merge Request creation

Auth via GITLAB_TOKEN env var (Personal Access Token: glpat-xxx).
Base URL via GITLAB_URL env var (e.g. https://gitlab.citadel-nexus.com).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


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
class MRResult:
    success: bool = False
    mr_url: str = ""
    mr_iid: int = 0
    branch: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class GitLabClient:
    """
    GitLab REST API v4 client.

    Usage:
        gl = GitLabClient()
        result = gl.create_fix_mr(
            namespace_path="guilds/citadel_lite_repo",
            base_branch="main",
            title="Fix missing dependency",
            body="Adds requests to requirements.txt",
            files={"citadel-fix-notes.md": "..."},
        )
    """

    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self.token = token or os.environ.get("GITLAB_TOKEN", "")
        self.base_url = (base_url or os.environ.get("GITLAB_URL", "")).rstrip("/")
        self._httpx = _get_httpx()

    def is_available(self) -> bool:
        return bool(self.token and self.base_url and self._httpx)

    # ------------------------------------------------------------------
    # Headers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Make a GitLab API v4 request. Returns parsed JSON or error dict."""
        if not self._httpx:
            return {"error": "httpx not installed"}
        if not self.token:
            return {"error": "GITLAB_TOKEN not set"}
        if not self.base_url:
            return {"error": "GITLAB_URL not set"}

        url = f"{self.base_url}/api/v4{path}"
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
    # Project operations
    # ------------------------------------------------------------------

    def get_current_user(self) -> Dict[str, Any]:
        """Get the authenticated user info."""
        return self._request("GET", "/user")

    def get_project(self, namespace_path: str) -> Dict[str, Any]:
        """
        Get project by namespace/path (e.g. "guilds/citadel_lite_repo").
        GitLab requires the path to be URL-encoded (/ → %2F).
        """
        encoded = quote(namespace_path, safe="")
        return self._request("GET", f"/projects/{encoded}")

    # ------------------------------------------------------------------
    # Branch operations
    # ------------------------------------------------------------------

    def get_branch(self, project_id: int, branch: str) -> Dict[str, Any]:
        """Get branch info including HEAD commit SHA."""
        encoded = quote(branch, safe="")
        return self._request("GET", f"/projects/{project_id}/repository/branches/{encoded}")

    def create_branch(self, project_id: int, branch_name: str, from_ref: str) -> Dict[str, Any]:
        """Create a new branch from a given ref (branch name or SHA)."""
        return self._request(
            "POST",
            f"/projects/{project_id}/repository/branches",
            json={"branch": branch_name, "ref": from_ref},
        )

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def create_or_update_file(
        self,
        project_id: int,
        branch: str,
        path: str,
        content: str,
        message: str,
    ) -> Dict[str, Any]:
        """Create or update a file on a branch (plain text content)."""
        encoded_path = quote(path, safe="")
        payload = {
            "branch": branch,
            "content": content,
            "commit_message": message,
            "encoding": "text",
        }

        # Check if file exists to decide POST vs PUT
        existing = self._request(
            "GET",
            f"/projects/{project_id}/repository/files/{encoded_path}",
            params={"ref": branch},
        )
        if "error" not in existing:
            # Update existing file
            return self._request(
                "PUT",
                f"/projects/{project_id}/repository/files/{encoded_path}",
                json=payload,
            )
        else:
            # Create new file
            return self._request(
                "POST",
                f"/projects/{project_id}/repository/files/{encoded_path}",
                json=payload,
            )

    # ------------------------------------------------------------------
    # Merge Request
    # ------------------------------------------------------------------

    def create_merge_request(
        self,
        project_id: int,
        source_branch: str,
        target_branch: str,
        title: str,
        body: str,
    ) -> Dict[str, Any]:
        """Create a Merge Request."""
        return self._request(
            "POST",
            f"/projects/{project_id}/merge_requests",
            json={
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
                "description": body,
                "remove_source_branch": True,
            },
        )

    def create_fix_mr(
        self,
        namespace_path: str,
        base_branch: str,
        title: str,
        body: str,
        files: Dict[str, str],
        branch_prefix: str = "citadel-fix",
    ) -> MRResult:
        """
        End-to-end: resolve project, create branch, commit files, open MR.

        Args:
            namespace_path: "group/project" (e.g. "guilds/citadel_lite_repo")
            base_branch: target branch (e.g. "main")
            title: MR title
            body: MR description (markdown)
            files: {file_path: file_content} to commit
            branch_prefix: prefix for the fix branch
        """
        # 1. Resolve project ID
        project = self.get_project(namespace_path)
        if "error" in project:
            return MRResult(
                success=False,
                error=f"Project not found ({namespace_path}): {project.get('error')} {project.get('detail', '')}",
            )
        project_id: int = project["id"]
        logger.info(f"GitLab project_id={project_id} for {namespace_path}")

        # 2. Get base branch HEAD SHA
        branch_info = self.get_branch(project_id, base_branch)
        if "error" in branch_info:
            return MRResult(
                success=False,
                error=f"Could not get branch '{base_branch}': {branch_info.get('error')}",
            )
        from_ref = branch_info["commit"]["id"]

        # 3. Create fix branch
        branch_name = f"{branch_prefix}/{int(time.time())}"
        br = self.create_branch(project_id, branch_name, from_ref)
        if "error" in br:
            return MRResult(
                success=False,
                error=f"Could not create branch '{branch_name}': {br.get('error')}",
            )

        # 4. Commit files
        for path, content in files.items():
            r = self.create_or_update_file(
                project_id, branch_name, path, content, f"citadel-fix: {title}"
            )
            if "error" in r:
                return MRResult(
                    success=False,
                    error=f"Could not commit '{path}': {r.get('error')}",
                    branch=branch_name,
                )

        # 5. Create Merge Request
        mr = self.create_merge_request(
            project_id, branch_name, base_branch, title, body
        )
        if "error" in mr:
            return MRResult(
                success=False,
                error=f"Could not create MR: {mr.get('error')} {mr.get('detail', '')}",
                branch=branch_name,
            )

        return MRResult(
            success=True,
            mr_url=mr.get("web_url", ""),
            mr_iid=mr.get("iid", 0),
            branch=branch_name,
        )
