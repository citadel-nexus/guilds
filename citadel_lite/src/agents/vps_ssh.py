# src/agents/vps_ssh.py
"""
VPS SSH Utility — Remote command execution for MigrateOrchestrator.

Provides SSH access to the VPS (147.93.43.117) for:
- Stopping/starting Docker containers
- Switching nginx upstreams via nginx_route_manager.py
- Health check verification

Uses subprocess with the ssh CLI (no paramiko dependency).

SRS: SRS-MIGRATE-ORCH-20260205-001-V3.0
CGRF v3.0: Tier 1, INFRASTRUCTURE
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
from typing import Tuple

logger = logging.getLogger(__name__)

VPS_HOST = os.environ.get("VPS_HOST", "147.93.43.117")
VPS_USER = os.environ.get("VPS_USER", "root")
VPS_IDENTITY_FILE = os.environ.get("VPS_IDENTITY_FILE", "")
SSH_TIMEOUT = int(os.environ.get("VPS_SSH_TIMEOUT", "30"))

# Paths on VPS
COMPOSE_DIR = "/opt/citadel/runtime"
COMPOSE_FILE = "docker-compose.runtime.yaml"
ROUTE_MANAGER = "/srv/projects/citadel/monitoring/nginx_route_manager.py"
VPS_CITADEL_LITE_DIR = os.environ.get(
    "VPS_CITADEL_LITE_DIR",
    "/opt/citadel/cnwb/citadel_lite",
)

# Input validation patterns (alphanumeric, hyphens, underscores only)
_VALID_SERVICE_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_VALID_TARGET_RE = re.compile(r"^(vps|ecs)$")
_VALID_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,253}$")


def _validate_service(service: str) -> str:
    """Validate service name to prevent shell injection."""
    if not _VALID_SERVICE_RE.match(service):
        raise ValueError(f"Invalid service name: {service!r}")
    return service


def _validate_target(target: str) -> str:
    """Validate target to prevent shell injection."""
    if not _VALID_TARGET_RE.match(target):
        raise ValueError(f"Invalid target (must be 'vps' or 'ecs'): {target!r}")
    return target


def _validate_port(port: int) -> int:
    """Validate port number."""
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ValueError(f"Invalid port (must be 1-65535): {port!r}")
    return port


def _validate_hostname(hostname: str) -> str:
    """Validate ALB DNS hostname to prevent shell injection."""
    if not _VALID_HOSTNAME_RE.match(hostname):
        raise ValueError(f"Invalid hostname: {hostname!r}")
    return hostname


def ssh_exec(command: str, timeout: int | None = None) -> Tuple[int, str, str]:
    """Execute a command on the VPS via SSH.

    Returns (return_code, stdout, stderr).
    """
    timeout = timeout or SSH_TIMEOUT

    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
    ]

    if VPS_IDENTITY_FILE:
        ssh_cmd.extend(["-i", VPS_IDENTITY_FILE])

    ssh_cmd.append(f"{VPS_USER}@{VPS_HOST}")
    ssh_cmd.append(command)

    logger.debug("SSH exec: %s@%s: %s", VPS_USER, VPS_HOST, command[:100])

    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning(
                "SSH command failed (rc=%d): %s",
                result.returncode, result.stderr.strip()[:200],
            )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error("SSH command timed out after %ds: %s", timeout, command[:100])
        return -1, "", "timeout"
    except FileNotFoundError:
        logger.error("ssh binary not found")
        return -1, "", "ssh not found"
    except Exception as e:
        logger.error("SSH exec error: %s", e)
        return -1, "", str(e)


def docker_compose_stop(service: str) -> bool:
    """Stop a Docker Compose service on the VPS."""
    service = _validate_service(service)
    rc, out, err = ssh_exec(
        f"cd {shlex.quote(COMPOSE_DIR)} && "
        f"docker compose -f {shlex.quote(COMPOSE_FILE)} stop {shlex.quote(service)}",
        timeout=60,
    )
    return rc == 0


def docker_compose_start(service: str) -> bool:
    """Start a Docker Compose service on the VPS."""
    service = _validate_service(service)
    rc, out, err = ssh_exec(
        f"cd {shlex.quote(COMPOSE_DIR)} && "
        f"docker compose -f {shlex.quote(COMPOSE_FILE)} start {shlex.quote(service)}",
        timeout=60,
    )
    return rc == 0


def switch_upstream(service: str, target: str, alb_dns: str = "") -> bool:
    """Switch nginx upstream for a service via the route manager."""
    service = _validate_service(service)
    target = _validate_target(target)
    cmd = (
        f"python3 {shlex.quote(ROUTE_MANAGER)} switch "
        f"{shlex.quote(service)} {shlex.quote(target)}"
    )
    if target == "ecs" and alb_dns:
        alb_dns = _validate_hostname(alb_dns)
        cmd += f" --alb-dns {shlex.quote(alb_dns)}"
    rc, out, err = ssh_exec(cmd, timeout=15)
    return rc == 0


def check_service_health(port: int) -> bool:
    """Check if a service on the VPS is responding to health checks."""
    port = _validate_port(port)
    rc, out, err = ssh_exec(
        f"curl -sf -o /dev/null -w '%{{http_code}}' http://localhost:{port}/health",
        timeout=10,
    )
    return rc == 0 and out.strip() == "200"


def get_route_status(service: str | None = None) -> str:
    """Get current nginx routing state from VPS."""
    cmd = f"python3 {shlex.quote(ROUTE_MANAGER)} status"
    if service:
        service = _validate_service(service)
        cmd += f" {shlex.quote(service)}"
    rc, out, err = ssh_exec(cmd, timeout=10)
    return out.strip() if rc == 0 else ""


# ── FAISS Indexer ─────────────────────────────────────────────────────────────

_VALID_AGENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_VALID_INDEXER_MODE_RE = re.compile(r"^(incremental|full-rebuild)$")


def run_faiss_indexer(
    agent_id: str,
    mode: str = "incremental",
    timeout: int = 300,
) -> Tuple[int, str, str]:
    """Trigger the Sentinel FAISS indexer worker on the VPS.

    Executes ``python3 -m src.workers.faiss_indexer`` inside the
    citadel_lite project directory so the indexer can pick up all domain
    indexes and emit the ``citadel.sentinel.index.complete`` NATS event.

    Args:
        agent_id: ElevenLabs agent ID whose conversations to index.
        mode:     ``"incremental"`` (default) or ``"full-rebuild"``.
        timeout:  SSH command timeout in seconds (default 300 for large corpora).

    Returns:
        ``(return_code, stdout, stderr)`` — rc 0 means success.
    """
    if not _VALID_AGENT_ID_RE.match(agent_id):
        raise ValueError(f"Invalid agent_id: {agent_id!r}")
    if not _VALID_INDEXER_MODE_RE.match(mode):
        raise ValueError(f"Invalid mode (must be 'incremental' or 'full-rebuild'): {mode!r}")

    rebuild_flag = "--full-rebuild" if mode == "full-rebuild" else ""
    cmd = (
        f"cd {shlex.quote(VPS_CITADEL_LITE_DIR)} && "
        f"python3 -m src.workers.faiss_indexer "
        f"--agent-id {shlex.quote(agent_id)}"
    )
    if rebuild_flag:
        cmd += f" {rebuild_flag}"

    logger.info(
        "[FAISS-INDEXER] triggering on VPS | agent=%s mode=%s",
        agent_id[:16], mode,
    )
    return ssh_exec(cmd, timeout=timeout)
