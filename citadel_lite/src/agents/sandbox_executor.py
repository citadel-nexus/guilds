# src/agents/sandbox_executor.py
"""
Sandbox Executor — Isolated code testing before merge.

Runs generated code + tests in a Docker container or subprocess sandbox
to verify correctness before allowing merge into the codebase.

Pipeline position: F993 → **Sandbox** → Council Merge Gate → Deploy

Two execution modes:
- Docker mode: Full isolation via Docker container (production)
- Subprocess mode: Local subprocess with timeout (development/fallback)

CGRF v3.0 Compliance:
- SRS Code: SRS-SANDBOX-001
- Tier: 1 (DEVELOPMENT)
- Execution Role: VERIFICATION

@module citadel_lite.src.agents.sandbox_executor
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.types import HandoffPacket

logger = logging.getLogger(__name__)

# Sandbox configuration
_SANDBOX_TIMEOUT = 300  # 5 minutes max
_SANDBOX_IMAGE = os.environ.get("CITADEL_SANDBOX_IMAGE", "python:3.11-slim")
_MAX_OUTPUT_SIZE = 50000  # chars


def _run_in_subprocess(
    workspace: str,
    test_command: str = "python -m pytest --tb=short -q",
    timeout: int = _SANDBOX_TIMEOUT,
) -> Dict[str, Any]:
    """
    Run tests in a local subprocess (development mode).
    No Docker required but less isolated.
    """
    start = time.time()
    try:
        result = subprocess.run(
            test_command.split(),
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": workspace,
            },
        )
        duration = time.time() - start

        return {
            "exit_code": result.returncode,
            "passed": result.returncode == 0,
            "stdout": result.stdout[:_MAX_OUTPUT_SIZE],
            "stderr": result.stderr[:_MAX_OUTPUT_SIZE],
            "duration_seconds": round(duration, 2),
            "mode": "subprocess",
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "passed": False,
            "stdout": "",
            "stderr": f"Sandbox timeout after {timeout}s",
            "duration_seconds": timeout,
            "mode": "subprocess",
        }
    except Exception as e:
        return {
            "exit_code": -1,
            "passed": False,
            "stdout": "",
            "stderr": str(e),
            "duration_seconds": time.time() - start,
            "mode": "subprocess",
        }


def _run_in_docker(
    workspace: str,
    test_command: str = "python -m pytest --tb=short -q",
    timeout: int = _SANDBOX_TIMEOUT,
) -> Dict[str, Any]:
    """
    Run tests in a Docker container (production mode).
    Full isolation: no network, limited CPU/memory.
    """
    start = time.time()
    try:
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--network", "none",
            "--memory", "2g",
            "--cpus", "1.0",
            "-v", f"{workspace}:/workspace:ro",
            "-w", "/workspace",
            _SANDBOX_IMAGE,
            "sh", "-c",
            f"pip install -q pytest && {test_command}",
        ]

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start

        return {
            "exit_code": result.returncode,
            "passed": result.returncode == 0,
            "stdout": result.stdout[:_MAX_OUTPUT_SIZE],
            "stderr": result.stderr[:_MAX_OUTPUT_SIZE],
            "duration_seconds": round(duration, 2),
            "mode": "docker",
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "passed": False,
            "stdout": "",
            "stderr": f"Docker sandbox timeout after {timeout}s",
            "duration_seconds": timeout,
            "mode": "docker",
        }
    except FileNotFoundError:
        logger.warning("Docker not available, falling back to subprocess")
        return _run_in_subprocess(workspace, test_command, timeout)
    except Exception as e:
        return {
            "exit_code": -1,
            "passed": False,
            "stdout": "",
            "stderr": str(e),
            "duration_seconds": time.time() - start,
            "mode": "docker",
        }


def _prepare_workspace(
    generated_files: List[Dict[str, Any]],
    test_files: List[Dict[str, Any]] | None = None,
) -> str:
    """
    Create a temporary workspace with generated code and test files.
    Returns the workspace path.
    """
    workspace = tempfile.mkdtemp(prefix="citadel_sandbox_")

    for file_info in generated_files:
        target = Path(workspace) / Path(file_info["path"]).name
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(file_info["content"])

    if test_files:
        for test_info in test_files:
            target = Path(workspace) / Path(test_info["path"]).name
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(test_info["content"])

    return workspace


def run_sandbox_executor(packet: HandoffPacket) -> Dict[str, Any]:
    """
    Execute generated code in a sandboxed environment.

    Reads F993 output from packet, sets up workspace, runs tests.

    Returns:
        Dict with sandbox execution results.
    """
    f993_out = packet.agent_outputs.get("f993_python") or packet.agent_outputs.get("f993")
    if not f993_out:
        return {
            "passed": False,
            "exit_code": -1,
            "error": "No F993 output found in packet",
            "mode": "none",
        }

    f993_data = f993_out.payload if hasattr(f993_out, "payload") else f993_out
    generated_files = f993_data.get("files", [])

    if not generated_files:
        return {
            "passed": False,
            "exit_code": -1,
            "error": "No generated files in F993 output",
            "mode": "none",
        }

    # Check if code was valid before sandbox
    if not f993_data.get("valid", False):
        return {
            "passed": False,
            "exit_code": -1,
            "error": f"F993 code invalid: {f993_data.get('validation_error')}",
            "mode": "none",
        }

    # Get test files if test_generator produced any
    test_gen_out = packet.agent_outputs.get("test_generator")
    test_files = None
    if test_gen_out:
        test_data = test_gen_out.payload if hasattr(test_gen_out, "payload") else test_gen_out
        test_files = test_data.get("test_files", [])

    # Prepare workspace
    workspace = _prepare_workspace(generated_files, test_files)

    try:
        # Try Docker first, fall back to subprocess
        docker_available = shutil.which("docker") is not None
        if docker_available:
            result = _run_in_docker(workspace)
        else:
            result = _run_in_subprocess(workspace)

        # Add metadata
        result["workspace"] = workspace
        result["files_tested"] = len(generated_files)
        result["content_hash"] = generated_files[0].get("content_hash", "unknown")

        return result

    except Exception as e:
        logger.error("Sandbox execution failed: %s", e)
        return {
            "passed": False,
            "exit_code": -1,
            "error": str(e),
            "mode": "error",
        }
    finally:
        # Clean up workspace
        try:
            shutil.rmtree(workspace, ignore_errors=True)
        except Exception:
            pass
