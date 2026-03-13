"""
AWS Agent — ECS / ECR / Bedrock / S3 / ALB control plane for Citadel Nexus.

Registers with the A2A protocol and provides:
  - ECS service management (status, scale, deploy, create, register-task)
  - ECR image management (list, describe)
  - ALB target health inspection
  - Bedrock Claude model invocation
  - IAM policy management for Bedrock access
  - S3 asset storage operations
  - CloudWatch log tailing & metrics
  - Datadog/PostHog telemetry queries
  - Runtime health monitor integration

Usage (standalone):
    python -m citadel_lite.src.agents.aws_agent status
    python -m citadel_lite.src.agents.aws_agent ecr-images --repo citadel-runtime
    python -m citadel_lite.src.agents.aws_agent target-health --service health-monitor
    python -m citadel_lite.src.agents.aws_agent register-task --service event-listener --image latest
    python -m citadel_lite.src.agents.aws_agent runtime-health
    python -m citadel_lite.src.agents.aws_agent deploy --service workshop
    python -m citadel_lite.src.agents.aws_agent bedrock-check-access
    python -m citadel_lite.src.agents.aws_agent bedrock-fix-access
    python -m citadel_lite.src.agents.aws_agent iam-policies --user citadel-admin

Usage (A2A):
    from citadel_lite.src.agents.aws_agent import register_aws_agent
    register_aws_agent(protocol)

SRS: AWS-AGENT-001
CGRF v2.0 COMPLIANT
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AWS_REGION = "us-east-1"
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-west-2")
ECS_CLUSTER = "citadel-cluster"
ACCOUNT_ID = "568721121468"
ECR_BASE = f"{ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com"
IAM_USER = "citadel-admin"
BEDROCK_POLICY_NAME = "CitadelBedrockInvokeAccess"

SERVICES = {
    # Infrastructure (always-on)
    "nats": "nats-service",
    "n8n": "n8n-service",
    "zayara": "zayara-service",
    # Workshop + Worker
    "workshop": "workshop-service",
    "worker": "worker-service",
    # Runtime Tier 1 (SRS-MIGRATE-ORCH-20260205-001)
    "event-listener": "event-listener-service",
    "sake-builder": "sake-builder-service",
    "governance-gateway": "governance-gateway-service",
    "health-monitor": "health-monitor-service",
    # Runtime Tier 2 (burst)
    "smartbank": "smartbank-service",
    "guardian-runtime": "guardian-runtime-service",
    "council": "council-service",
    "reflex-runtime": "reflex-runtime-service",
}

ECR_REPOS = {
    "runtime": "citadel-runtime",
    "zayara": "citadel-zayara",
    "worker": "citadel-worker",
    "workshop": "citadel-workshop",
    "artcraft": "citadel-artcraft",
}

# Service → port mapping (for ALB target groups and health checks)
SERVICE_PORTS = {
    "event-listener": 8100,
    "sake-builder": 8150,
    "reflex-runtime": 8170,
    "council": 8200,
    "smartbank": 8400,
    "guardian-runtime": 8500,
    "governance-gateway": 8787,
    "health-monitor": 8090,
}

# Datadog configuration
DD_API_KEY_VAR = "DD_API_KEY"
DD_SITE = "us5.datadoghq.com"

CLAUDE_MODELS = {
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "opus": "us.anthropic.claude-opus-4-5-20251101-v1:0",
    "sonnet4": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "opus4": "us.anthropic.claude-opus-4-20250514-v1:0",
}

DEFAULT_MODEL = "haiku"


# ---------------------------------------------------------------------------
# AWS CLI wrapper
# ---------------------------------------------------------------------------


def _aws(*args: str, parse_json: bool = True, region: str | None = None) -> Any:
    """Run an AWS CLI command and return parsed JSON or raw output.

    Args:
        *args: AWS CLI arguments (service, command, flags, etc.)
        parse_json: Whether to parse output as JSON (default True)
        region: Override the default AWS_REGION for this call
    """
    import shutil
    aws_bin = shutil.which("aws") or "aws"
    cmd = [aws_bin, "--region", region or AWS_REGION, "--output", "json", *args]
    # shell=True needed on Windows for .cmd wrappers
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                            shell=(os.name == "nt"))
    if result.returncode != 0:
        raise RuntimeError(f"aws {' '.join(args[:3])}... failed: {result.stderr.strip()}")
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout) if parse_json else result.stdout


# ---------------------------------------------------------------------------
# ECS operations
# ---------------------------------------------------------------------------


def ecs_status() -> Dict[str, Any]:
    """Get status of all ECS services in the cluster."""
    data = _aws("ecs", "describe-services",
                 "--cluster", ECS_CLUSTER,
                 "--services", *SERVICES.values())
    services = []
    for svc in data.get("services", []):
        services.append({
            "name": svc["serviceName"],
            "status": svc["status"],
            "desired": svc["desiredCount"],
            "running": svc["runningCount"],
            "pending": svc["pendingCount"],
            "task_def": svc["taskDefinition"].rsplit("/", 1)[-1],
            "launch_type": svc.get("launchType", "FARGATE"),
        })
    return {"cluster": ECS_CLUSTER, "services": services}


def ecs_scale(service_key: str, count: int) -> Dict[str, Any]:
    """Scale an ECS service to desired count."""
    svc_name = SERVICES.get(service_key)
    if not svc_name:
        return {"error": f"Unknown service: {service_key}. Known: {list(SERVICES.keys())}"}
    _aws("ecs", "update-service",
         "--cluster", ECS_CLUSTER,
         "--service", svc_name,
         "--desired-count", str(count))
    return {"service": svc_name, "desired_count": count, "status": "scaling"}


def ecs_deploy(service_key: str, image_tag: str = "latest") -> Dict[str, Any]:
    """Force new deployment of an ECS service (pulls latest image)."""
    svc_name = SERVICES.get(service_key)
    if not svc_name:
        return {"error": f"Unknown service: {service_key}"}
    _aws("ecs", "update-service",
         "--cluster", ECS_CLUSTER,
         "--service", svc_name,
         "--force-new-deployment")
    return {"service": svc_name, "action": "force-new-deployment", "tag": image_tag}


def ecs_tasks(service_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """List running tasks, optionally filtered by service."""
    args = ["ecs", "list-tasks", "--cluster", ECS_CLUSTER]
    if service_key and service_key in SERVICES:
        args += ["--service-name", SERVICES[service_key]]
    data = _aws(*args)
    task_arns = data.get("taskArns", [])
    if not task_arns:
        return []
    details = _aws("ecs", "describe-tasks", "--cluster", ECS_CLUSTER, "--tasks", *task_arns)
    tasks = []
    for t in details.get("tasks", []):
        tasks.append({
            "task_id": t["taskArn"].rsplit("/", 1)[-1],
            "status": t["lastStatus"],
            "cpu": t.get("cpu"),
            "memory": t.get("memory"),
            "started_at": t.get("startedAt", ""),
            "group": t.get("group", ""),
        })
    return tasks


# ---------------------------------------------------------------------------
# ECR operations
# ---------------------------------------------------------------------------


def ecr_images(repo_key: str = "runtime") -> Dict[str, Any]:
    """List images in an ECR repository."""
    repo_name = ECR_REPOS.get(repo_key, repo_key)
    try:
        data = _aws("ecr", "describe-images",
                     "--repository-name", repo_name,
                     "--query", "imageDetails[*].{pushed:imagePushedAt,tags:imageTags,size:imageSizeInBytes,digest:imageDigest}")
        images = data if isinstance(data, list) else []
        return {
            "repository": repo_name,
            "image_count": len(images),
            "images": sorted(images, key=lambda x: x.get("pushed", ""), reverse=True)[:10],
        }
    except Exception as exc:
        return {"repository": repo_name, "error": str(exc)}


def ecr_list_repos() -> List[Dict[str, Any]]:
    """List all ECR repositories."""
    data = _aws("ecr", "describe-repositories",
                 "--query", "repositories[*].{name:repositoryName,uri:repositoryUri,created:createdAt}")
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# ECS task definition operations
# ---------------------------------------------------------------------------


def ecs_register_task(
    service_key: str,
    image_tag: str = "latest",
    cpu: str = "256",
    memory: str = "512",
    with_datadog: bool = True,
) -> Dict[str, Any]:
    """Register a new task definition revision for a runtime service.

    SRS: AWS-AGENT-TASK-001
    """
    import os

    svc_name = SERVICES.get(service_key)
    if not svc_name:
        return {"error": f"Unknown service: {service_key}. Known: {list(SERVICES.keys())}"}

    port = SERVICE_PORTS.get(service_key)
    if not port:
        return {"error": f"No port mapping for {service_key}. Cannot build task definition."}

    family = f"citadel-{service_key}"
    image = f"{ECR_BASE}/citadel-runtime:{image_tag}"

    env = [
        {"name": "NATS_URL", "value": "nats://147.93.43.117:4222"},
        {"name": "REDIS_URL", "value": "redis://147.93.43.117:6379"},
        {"name": "SUPABASE_URL", "value": os.getenv("SUPABASE_URL", "")},
        {"name": "SERVICE_NAME", "value": service_key},
        {"name": "DD_AGENT_HOST", "value": "localhost"},
        {"name": "DD_TRACE_AGENT_PORT", "value": "8126"},
        {"name": "DD_DOGSTATSD_PORT", "value": "8125"},
    ]

    main_container = {
        "name": service_key,
        "image": image,
        "essential": True,
        "portMappings": [{"containerPort": port, "protocol": "tcp"}],
        "environment": env,
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": "/ecs/citadel",
                "awslogs-region": AWS_REGION,
                "awslogs-stream-prefix": service_key,
                "awslogs-create-group": "true",
            },
        },
        "healthCheck": {
            "command": ["CMD-SHELL", f"curl -f http://localhost:{port}/health || exit 1"],
            "interval": 30,
            "timeout": 5,
            "retries": 3,
            "startPeriod": 60,
        },
    }

    containers = [main_container]

    if with_datadog:
        dd_key = os.getenv(DD_API_KEY_VAR, "")
        if dd_key:
            containers.append({
                "name": "datadog-agent",
                "image": "public.ecr.aws/datadog/agent:latest",
                "essential": False,
                "cpu": 128,
                "memory": 256,
                "portMappings": [
                    {"containerPort": 8126, "protocol": "tcp"},
                    {"containerPort": 8125, "protocol": "udp"},
                ],
                "environment": [
                    {"name": "DD_API_KEY", "value": dd_key},
                    {"name": "DD_SITE", "value": DD_SITE},
                    {"name": "DD_ECS_COLLECT", "value": "true"},
                    {"name": "DD_APM_ENABLED", "value": "true"},
                    {"name": "DD_APM_NON_LOCAL_TRAFFIC", "value": "true"},
                    {"name": "DD_DOGSTATSD_NON_LOCAL_TRAFFIC", "value": "true"},
                    {"name": "DD_PROCESS_AGENT_ENABLED", "value": "true"},
                    {"name": "DD_LOGS_ENABLED", "value": "true"},
                    {"name": "DD_LOGS_CONFIG_CONTAINER_COLLECT_ALL", "value": "true"},
                    {"name": "DD_TAGS", "value": f"project:citadel-nexus env:production service:{service_key}"},
                    {"name": "ECS_FARGATE", "value": "true"},
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": "/ecs/citadel",
                        "awslogs-region": AWS_REGION,
                        "awslogs-stream-prefix": "datadog",
                        "awslogs-create-group": "true",
                    },
                },
            })

    # Write JSON to temp file and call aws cli
    import tempfile
    taskdef = {
        "family": family,
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "cpu": cpu,
        "memory": memory,
        "executionRoleArn": f"arn:aws:iam::{ACCOUNT_ID}:role/citadel-ecs-task-execution",
        "taskRoleArn": f"arn:aws:iam::{ACCOUNT_ID}:role/citadel-ecs-task",
        "containerDefinitions": containers,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(taskdef, f)
        tmp_path = f.name

    try:
        data = _aws("ecs", "register-task-definition",
                     "--cli-input-json", f"file://{tmp_path}")
        td = data.get("taskDefinition", {})
        return {
            "family": td.get("family"),
            "revision": td.get("revision"),
            "status": td.get("status"),
            "containers": len(td.get("containerDefinitions", [])),
            "datadog": with_datadog,
        }
    finally:
        import os as _os
        _os.unlink(tmp_path)


def ecs_create_service(
    service_key: str,
    desired_count: int = 0,
    subnets: Optional[List[str]] = None,
    security_groups: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a new ECS service for a runtime component.

    SRS: AWS-AGENT-SVC-001
    """
    svc_name = SERVICES.get(service_key)
    if not svc_name:
        return {"error": f"Unknown service: {service_key}"}

    family = f"citadel-{service_key}"

    # Default network config from existing services
    if subnets is None:
        subnets = ["subnet-0b60b46054003b8e4", "subnet-0a766525c1976719b"]
    if security_groups is None:
        security_groups = ["sg-007b5068d4f6541af"]

    try:
        _aws("ecs", "create-service",
             "--cluster", ECS_CLUSTER,
             "--service-name", svc_name,
             "--task-definition", family,
             "--desired-count", str(desired_count),
             "--launch-type", "FARGATE",
             "--network-configuration",
             json.dumps({
                 "awsvpcConfiguration": {
                     "subnets": subnets,
                     "securityGroups": security_groups,
                     "assignPublicIp": "ENABLED",
                 }
             }))
        return {"service": svc_name, "desired_count": desired_count, "action": "created"}
    except RuntimeError as exc:
        if "already exists" in str(exc):
            return {"service": svc_name, "action": "already_exists"}
        raise


# ---------------------------------------------------------------------------
# ALB target health
# ---------------------------------------------------------------------------


def alb_target_health(service_key: Optional[str] = None) -> Dict[str, Any]:
    """Check ALB target group health for runtime services.

    SRS: AWS-AGENT-ALB-001
    """
    try:
        data = _aws("elbv2", "describe-target-groups",
                     "--query", "TargetGroups[*].{name:TargetGroupName,arn:TargetGroupArn,port:Port,healthPath:HealthCheckPath}")
        tgs = data if isinstance(data, list) else []

        results = {}
        for tg in tgs:
            name = tg.get("name", "")
            if service_key and service_key not in name:
                continue
            try:
                health_data = _aws("elbv2", "describe-target-health",
                                    "--target-group-arn", tg["arn"])
                targets = health_data.get("TargetHealthDescriptions", [])
                results[name] = {
                    "port": tg.get("port"),
                    "health_path": tg.get("healthPath"),
                    "targets": [
                        {
                            "id": t["Target"]["Id"],
                            "port": t["Target"].get("Port"),
                            "health": t["TargetHealth"]["State"],
                            "reason": t["TargetHealth"].get("Reason", ""),
                        }
                        for t in targets
                    ],
                }
            except Exception as exc:
                results[name] = {"error": str(exc)}

        return {"target_groups": results}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Runtime health monitor query
# ---------------------------------------------------------------------------


def runtime_health(alb_dns: str = "citadel-alb-1203272115.us-east-1.elb.amazonaws.com") -> Dict[str, Any]:
    """Query the health-monitor service for full cluster health.

    Curls the health-monitor /status endpoint via ALB or direct.
    SRS: SYH-PROBE-003
    """
    import urllib.request
    url = f"http://{alb_dns}/status"
    headers = {"Host": "health-monitor.citadel-nexus.com"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        # Try direct via ECS task IP (fallback)
        try:
            tasks = ecs_tasks("health-monitor")
            if tasks:
                task = tasks[0]
                # Get task network interface
                details = _aws("ecs", "describe-tasks",
                               "--cluster", ECS_CLUSTER,
                               "--tasks", task["task_id"])
                for t in details.get("tasks", []):
                    for att in t.get("attachments", []):
                        for det in att.get("details", []):
                            if det.get("name") == "privateIPv4Address":
                                ip = det["value"]
                                req = urllib.request.Request(f"http://{ip}:8090/status")
                                with urllib.request.urlopen(req, timeout=10) as resp:
                                    return json.loads(resp.read().decode())
        except Exception as inner_exc:
            return {"error": f"Could not reach health-monitor: {inner_exc}"}
    return {"error": "health-monitor unreachable"}


# ---------------------------------------------------------------------------
# Datadog telemetry queries
# ---------------------------------------------------------------------------


def datadog_query_metrics(metric: str = "citadel.vps.cpu", minutes: int = 10) -> Dict[str, Any]:
    """Query Datadog metrics API for telemetry data.

    SRS: AWS-AGENT-DD-001
    """
    import os
    import urllib.request

    api_key = os.getenv(DD_API_KEY_VAR, "")
    if not api_key:
        return {"error": "DD_API_KEY not set"}

    from datetime import timedelta
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    url = (
        f"https://api.{DD_SITE}/api/v1/query"
        f"?from={int(start.timestamp())}"
        f"&to={int(end.timestamp())}"
        f"&query=avg:{metric}{{*}}"
    )
    req = urllib.request.Request(url, headers={
        "DD-API-KEY": api_key,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            series = data.get("series", [])
            if series:
                points = series[0].get("pointlist", [])
                return {
                    "metric": metric,
                    "points": len(points),
                    "latest_value": points[-1][1] if points else None,
                    "min": min(p[1] for p in points) if points else None,
                    "max": max(p[1] for p in points) if points else None,
                }
            return {"metric": metric, "points": 0, "latest_value": None}
    except Exception as exc:
        return {"metric": metric, "error": str(exc)}


# ---------------------------------------------------------------------------
# Bedrock operations (Claude only)
# ---------------------------------------------------------------------------


def bedrock_invoke(
    prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """Invoke a Claude model via Bedrock."""
    model_id = CLAUDE_MODELS.get(model, model)

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    })

    result = _aws(
        "bedrock-runtime", "invoke-model",
        "--model-id", model_id,
        "--content-type", "application/json",
        "--accept", "application/json",
        "--body", body,
        region=BEDROCK_REGION,
    )
    return {
        "model": model_id,
        "response": result,
    }


def bedrock_list_models() -> List[str]:
    """List available Claude models."""
    return list(CLAUDE_MODELS.items())


# ---------------------------------------------------------------------------
# IAM / Bedrock access management  (boto3 — no AWS CLI dependency)
# ---------------------------------------------------------------------------

def _iam_client():
    """Return a boto3 IAM client (global region)."""
    import boto3
    return boto3.client("iam", region_name=AWS_REGION)


def _bedrock_client():
    """Return a boto3 Bedrock client in the Bedrock region."""
    import boto3
    return boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)


def iam_get_user_policies(user: str = IAM_USER) -> Dict[str, Any]:
    """List all IAM policies (inline + attached) for a user.

    SRS: AWS-AGENT-IAM-001
    """
    iam = _iam_client()
    result: Dict[str, Any] = {"user": user, "inline": [], "attached": []}

    try:
        resp = iam.list_user_policies(UserName=user)
        result["inline"] = resp.get("PolicyNames", [])
    except Exception as exc:
        result["inline_error"] = str(exc)

    try:
        resp = iam.list_attached_user_policies(UserName=user)
        result["attached"] = [
            {"name": p["PolicyName"], "arn": p["PolicyArn"]}
            for p in resp.get("AttachedPolicies", [])
        ]
    except Exception as exc:
        result["attached_error"] = str(exc)

    return result


def iam_get_inline_policy(user: str, policy_name: str) -> Dict[str, Any]:
    """Get the JSON document of an inline IAM policy."""
    iam = _iam_client()
    try:
        resp = iam.get_user_policy(UserName=user, PolicyName=policy_name)
        return {
            "user": user,
            "policy_name": policy_name,
            "document": resp.get("PolicyDocument", {}),
        }
    except Exception as exc:
        return {"error": str(exc)}


def iam_check_bedrock_access(
    user: str = IAM_USER,
    model_id: str | None = None,
) -> Dict[str, Any]:
    """Check whether an IAM user can invoke Bedrock models.

    Tests by simulating bedrock:InvokeModel on the target model ARN.
    Also scans inline + attached policies for explicit deny statements
    that block Bedrock access.

    SRS: AWS-AGENT-IAM-002
    """
    iam = _iam_client()
    model_id = model_id or CLAUDE_MODELS.get("opus", "")
    model_arn = f"arn:aws:bedrock:{BEDROCK_REGION}::foundation-model/{model_id}"
    user_arn = f"arn:aws:iam::{ACCOUNT_ID}:user/{user}"
    result: Dict[str, Any] = {
        "user": user,
        "model_id": model_id,
        "model_arn": model_arn,
        "region": BEDROCK_REGION,
    }

    # 1. Simulate principal policy
    try:
        sim = iam.simulate_principal_policy(
            PolicySourceArn=user_arn,
            ActionNames=["bedrock:InvokeModel"],
            ResourceArns=[model_arn],
        )
        evals = sim.get("EvaluationResults", [])
        if evals:
            decision = evals[0].get("EvalDecision", "unknown")
            result["simulation"] = {
                "decision": decision,
                "allowed": decision == "allowed",
                "matched_statements": evals[0].get("MatchedStatements", []),
            }
        else:
            result["simulation"] = {"decision": "no_results", "allowed": False}
    except Exception as exc:
        result["simulation"] = {"error": str(exc)}

    # 2. Scan inline policies for explicit Deny on bedrock
    deny_found: List[Dict[str, Any]] = []
    try:
        pol_names = iam.list_user_policies(UserName=user).get("PolicyNames", [])
        for pol_name in pol_names:
            pol_resp = iam.get_user_policy(UserName=user, PolicyName=pol_name)
            doc = pol_resp.get("PolicyDocument", {})
            for stmt in doc.get("Statement", []):
                effect = stmt.get("Effect", "")
                actions = stmt.get("Action", [])
                if isinstance(actions, str):
                    actions = [actions]
                if effect == "Deny" and any(
                    "bedrock" in a.lower() for a in actions
                ):
                    deny_found.append({
                        "policy": pol_name,
                        "statement_id": stmt.get("Sid", ""),
                        "actions": actions,
                        "resources": stmt.get("Resource", "*"),
                    })
    except Exception as exc:
        result["policy_scan_error"] = str(exc)

    result["explicit_denies"] = deny_found
    result["access_blocked"] = (
        bool(deny_found)
        or not result.get("simulation", {}).get("allowed", False)
    )
    return result


def iam_remove_bedrock_deny(
    user: str = IAM_USER,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Remove explicit Deny statements for bedrock:InvokeModel from inline policies.

    SRS: AWS-AGENT-IAM-003
    """
    import copy
    iam = _iam_client()

    check = iam_check_bedrock_access(user)
    denies = check.get("explicit_denies", [])
    if not denies:
        return {"user": user, "status": "no_deny_found", "action": "none"}

    changes: List[Dict[str, Any]] = []

    for deny_info in denies:
        pol_name = deny_info["policy"]
        pol_resp = iam.get_user_policy(UserName=user, PolicyName=pol_name)
        doc = copy.deepcopy(pol_resp.get("PolicyDocument", {}))
        original_stmts = doc.get("Statement", [])
        new_stmts = []

        for stmt in original_stmts:
            effect = stmt.get("Effect", "")
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]

            if effect == "Deny" and any("bedrock" in a.lower() for a in actions):
                remaining = [a for a in actions if "bedrock" not in a.lower()]
                if remaining:
                    stmt["Action"] = remaining
                    new_stmts.append(stmt)
                    changes.append({
                        "policy": pol_name,
                        "action": "removed_bedrock_actions",
                        "removed": [a for a in actions if "bedrock" in a.lower()],
                        "kept": remaining,
                    })
                else:
                    changes.append({
                        "policy": pol_name,
                        "action": "removed_entire_statement",
                        "statement_id": stmt.get("Sid", ""),
                    })
            else:
                new_stmts.append(stmt)

        if not dry_run and new_stmts != original_stmts:
            doc["Statement"] = new_stmts
            if new_stmts:
                iam.put_user_policy(
                    UserName=user,
                    PolicyName=pol_name,
                    PolicyDocument=json.dumps(doc),
                )
            else:
                iam.delete_user_policy(UserName=user, PolicyName=pol_name)
                changes.append({"policy": pol_name, "action": "deleted_empty_policy"})

    return {
        "user": user,
        "dry_run": dry_run,
        "changes": changes,
        "status": "would_apply" if dry_run else "applied",
    }


def iam_create_bedrock_policy() -> Dict[str, Any]:
    """Create a managed IAM policy allowing bedrock:InvokeModel for all Claude models.

    SRS: AWS-AGENT-IAM-004
    """
    iam = _iam_client()
    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowBedrockInvoke",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                "Resource": [
                    f"arn:aws:bedrock:{BEDROCK_REGION}::foundation-model/anthropic.*",
                    f"arn:aws:bedrock:{AWS_REGION}::foundation-model/anthropic.*",
                ],
            },
            {
                "Sid": "AllowBedrockList",
                "Effect": "Allow",
                "Action": [
                    "bedrock:ListFoundationModels",
                    "bedrock:GetFoundationModel",
                ],
                "Resource": "*",
            },
        ],
    }

    policy_arn = f"arn:aws:iam::{ACCOUNT_ID}:policy/{BEDROCK_POLICY_NAME}"

    # Check if policy already exists
    try:
        existing = iam.get_policy(PolicyArn=policy_arn)
        return {
            "policy_arn": policy_arn,
            "status": "already_exists",
            "versions": existing.get("Policy", {}).get("DefaultVersionId"),
        }
    except iam.exceptions.NoSuchEntityException:
        pass  # Create it

    try:
        resp = iam.create_policy(
            PolicyName=BEDROCK_POLICY_NAME,
            Description="Allow citadel-admin to invoke Anthropic Claude models via Bedrock",
            PolicyDocument=json.dumps(policy_doc),
        )
        return {"policy_arn": resp["Policy"]["Arn"], "status": "created"}
    except Exception as exc:
        return {"error": str(exc)}


def iam_attach_bedrock_policy(user: str = IAM_USER) -> Dict[str, Any]:
    """Attach the Bedrock invoke policy to a user.

    SRS: AWS-AGENT-IAM-005
    """
    iam = _iam_client()
    policy_arn = f"arn:aws:iam::{ACCOUNT_ID}:policy/{BEDROCK_POLICY_NAME}"

    try:
        resp = iam.list_attached_user_policies(UserName=user)
        attached = [p["PolicyArn"] for p in resp.get("AttachedPolicies", [])]
        if policy_arn in attached:
            return {"user": user, "policy_arn": policy_arn, "status": "already_attached"}
    except Exception:
        pass

    try:
        iam.attach_user_policy(UserName=user, PolicyArn=policy_arn)
        return {"user": user, "policy_arn": policy_arn, "status": "attached"}
    except Exception as exc:
        return {"error": str(exc)}


def bedrock_fix_access(
    user: str = IAM_USER,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """End-to-end fix for Bedrock IAM access issues.

    Steps:
      1. Check current access (iam_check_bedrock_access)
      2. Remove any explicit Deny statements blocking Bedrock
      3. Create the Bedrock allow policy if missing
      4. Attach the policy to the user
      5. Verify access is restored

    SRS: AWS-AGENT-IAM-006
    """
    steps: List[Dict[str, Any]] = []

    # Step 1: Check current state
    check = iam_check_bedrock_access(user)
    steps.append({"step": "check_access", "result": check})

    if not check.get("access_blocked"):
        return {
            "user": user,
            "status": "already_allowed",
            "steps": steps,
            "message": "Bedrock access is already working — no changes needed.",
        }

    # Step 2: Remove explicit denies
    if check.get("explicit_denies"):
        deny_result = iam_remove_bedrock_deny(user, dry_run=dry_run)
        steps.append({"step": "remove_denies", "result": deny_result})
    else:
        steps.append({"step": "remove_denies", "result": {"status": "no_denies_found"}})

    if dry_run:
        return {
            "user": user,
            "status": "dry_run_complete",
            "steps": steps,
            "message": "Dry run — no changes applied. Run without --dry-run to apply.",
        }

    # Step 3: Create policy
    create_result = iam_create_bedrock_policy()
    steps.append({"step": "create_policy", "result": create_result})

    # Step 4: Attach policy
    attach_result = iam_attach_bedrock_policy(user)
    steps.append({"step": "attach_policy", "result": attach_result})

    # Step 5: Verify (IAM propagation delay)
    import time as _time
    _time.sleep(3)
    verify = iam_check_bedrock_access(user)
    steps.append({"step": "verify", "result": verify})

    fixed = not verify.get("access_blocked")
    return {
        "user": user,
        "status": "fixed" if fixed else "still_blocked",
        "steps": steps,
        "message": (
            "Bedrock access restored successfully."
            if fixed else
            "Policy applied but access still blocked. Check for SCPs or permission boundaries."
        ),
    }


# ---------------------------------------------------------------------------
# S3 operations
# ---------------------------------------------------------------------------

S3_BUCKET = "citadel-nexus-assets"


def s3_upload(local_path: str, s3_key: str) -> Dict[str, Any]:
    """Upload a file to S3."""
    _aws("s3", "cp", local_path, f"s3://{S3_BUCKET}/{s3_key}", parse_json=False)
    return {"bucket": S3_BUCKET, "key": s3_key, "action": "uploaded"}


def s3_download(s3_key: str, local_path: str) -> Dict[str, Any]:
    """Download a file from S3."""
    _aws("s3", "cp", f"s3://{S3_BUCKET}/{s3_key}", local_path, parse_json=False)
    return {"bucket": S3_BUCKET, "key": s3_key, "local_path": local_path}


def s3_list(prefix: str = "") -> List[Dict[str, Any]]:
    """List objects in S3 bucket."""
    data = _aws("s3api", "list-objects-v2",
                 "--bucket", S3_BUCKET,
                 "--prefix", prefix,
                 "--max-items", "50")
    return [
        {"key": obj["Key"], "size": obj["Size"], "modified": obj["LastModified"]}
        for obj in data.get("Contents", [])
    ]


# ---------------------------------------------------------------------------
# CloudWatch logs
# ---------------------------------------------------------------------------


def cloudwatch_tail(service: str = "nats", lines: int = 50) -> List[str]:
    """Tail recent CloudWatch logs for an ECS service."""
    data = _aws(
        "logs", "filter-log-events",
        "--log-group-name", "/ecs/citadel",
        "--log-stream-name-prefix", service,
        "--limit", str(lines),
        "--interleaved",
    )
    return [
        f"[{evt.get('timestamp', '')}] {evt.get('message', '').strip()}"
        for evt in data.get("events", [])
    ]


# ---------------------------------------------------------------------------
# CloudWatch metrics & auto-scaling
# ---------------------------------------------------------------------------


CW_VPS_NAMESPACE = "Citadel/VPS"
CW_VPS_INSTANCE = "vps-147-93-43-117"


def cloudwatch_get_vps_metrics(minutes: int = 10) -> Dict[str, Any]:
    """Get VPS CPU/memory metrics from the Citadel/VPS CloudWatch namespace."""
    from datetime import timedelta

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    results: Dict[str, Any] = {"instance": CW_VPS_INSTANCE, "period_minutes": minutes}

    for metric in ("cpu_usage_user", "mem_used_percent"):
        try:
            data = _aws(
                "cloudwatch", "get-metric-statistics",
                "--namespace", CW_VPS_NAMESPACE,
                "--metric-name", metric,
                "--start-time", start.isoformat(),
                "--end-time", end.isoformat(),
                "--period", "60",
                "--statistics", "Average", "Maximum",
                "--dimensions", f"Name=InstanceId,Value={CW_VPS_INSTANCE}",
            )
            points = data.get("Datapoints", [])
            if points:
                latest = max(points, key=lambda p: p.get("Timestamp", ""))
                results[metric] = {
                    "average": latest.get("Average"),
                    "maximum": latest.get("Maximum"),
                    "timestamp": latest.get("Timestamp"),
                    "datapoints": len(points),
                }
            else:
                results[metric] = {"average": None, "datapoints": 0}
        except Exception as exc:
            results[metric] = {"error": str(exc)}

    return results


def cloudwatch_get_container_metrics(minutes: int = 10) -> Dict[str, Any]:
    """Get per-Docker-container CPU/memory metrics from CloudWatch.

    SRS: SRS-MIGRATE-MONITOR-001
    Returns dict keyed by container name with cpu_percent and mem_percent.
    """
    from datetime import timedelta

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    results: Dict[str, Any] = {"instance": CW_VPS_INSTANCE, "period_minutes": minutes, "containers": {}}

    for metric_name, result_key in [("container_cpu_percent", "cpu_percent"),
                                     ("container_mem_percent", "mem_percent")]:
        try:
            # List all container dimensions for this metric
            data = _aws(
                "cloudwatch", "get-metric-statistics",
                "--namespace", CW_VPS_NAMESPACE,
                "--metric-name", metric_name,
                "--start-time", start.isoformat(),
                "--end-time", end.isoformat(),
                "--period", "60",
                "--statistics", "Average", "Maximum",
                "--dimensions",
                f"Name=InstanceId,Value={CW_VPS_INSTANCE}",
            )
            # Single dimension query returns aggregated data; need per-container
            # Use list-metrics to discover container names first
        except Exception:
            pass

    # Use list-metrics to find container names, then query each
    try:
        list_data = _aws(
            "cloudwatch", "list-metrics",
            "--namespace", CW_VPS_NAMESPACE,
            "--metric-name", "container_cpu_percent",
        )
        metrics_list = list_data.get("Metrics", [])
        container_names = set()
        for m in metrics_list:
            for dim in m.get("Dimensions", []):
                if dim.get("Name") == "ContainerName":
                    container_names.add(dim["Value"])

        for container_name in container_names:
            results["containers"][container_name] = {}
            for metric_name, result_key in [("container_cpu_percent", "cpu_percent"),
                                             ("container_mem_percent", "mem_percent")]:
                try:
                    data = _aws(
                        "cloudwatch", "get-metric-statistics",
                        "--namespace", CW_VPS_NAMESPACE,
                        "--metric-name", metric_name,
                        "--start-time", start.isoformat(),
                        "--end-time", end.isoformat(),
                        "--period", "60",
                        "--statistics", "Average", "Maximum",
                        "--dimensions",
                        f"Name=InstanceId,Value={CW_VPS_INSTANCE}",
                        f"Name=ContainerName,Value={container_name}",
                    )
                    points = data.get("Datapoints", [])
                    if points:
                        latest = max(points, key=lambda p: p.get("Timestamp", ""))
                        results["containers"][container_name][result_key] = {
                            "average": latest.get("Average"),
                            "maximum": latest.get("Maximum"),
                            "timestamp": latest.get("Timestamp"),
                        }
                    else:
                        results["containers"][container_name][result_key] = {"average": None}
                except Exception as exc:
                    results["containers"][container_name][result_key] = {"error": str(exc)}
    except Exception as exc:
        results["error"] = str(exc)

    return results


def ecs_describe_scaling(service_key: str) -> Dict[str, Any]:
    """Describe auto-scaling policies for an ECS service."""
    svc_name = SERVICES.get(service_key)
    if not svc_name:
        return {"error": f"Unknown service: {service_key}"}
    resource_id = f"service/{ECS_CLUSTER}/{svc_name}"
    try:
        data = _aws(
            "application-autoscaling", "describe-scaling-policies",
            "--service-namespace", "ecs",
            "--resource-id", resource_id,
        )
        policies = data.get("ScalingPolicies", [])
        return {
            "service": svc_name,
            "resource_id": resource_id,
            "policies": [
                {
                    "name": p.get("PolicyName"),
                    "type": p.get("PolicyType"),
                    "creation_time": p.get("CreationTime"),
                }
                for p in policies
            ],
        }
    except Exception as exc:
        return {"service": svc_name, "error": str(exc)}


def cloudwatch_get_alarms() -> Dict[str, Any]:
    """Get all CloudWatch alarms for VPS/Citadel namespace."""
    try:
        data = _aws(
            "cloudwatch", "describe-alarms",
            "--alarm-name-prefix", "vps-",
        )
        alarms = data.get("MetricAlarms", [])
        return {
            "count": len(alarms),
            "alarms": [
                {
                    "name": a.get("AlarmName"),
                    "state": a.get("StateValue"),
                    "metric": a.get("MetricName"),
                    "threshold": a.get("Threshold"),
                    "comparison": a.get("ComparisonOperator"),
                }
                for a in alarms
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


def s3_bucket_stats(prefix: str = "") -> Dict[str, Any]:
    """Get size and object count for the S3 bucket (or a prefix)."""
    try:
        data = _aws(
            "s3api", "list-objects-v2",
            "--bucket", S3_BUCKET,
            "--prefix", prefix,
            "--query", "length(Contents)",
        )
        # Use CloudWatch bucket-level metrics for total size
        from datetime import timedelta
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=1)
        size_data = _aws(
            "cloudwatch", "get-metric-statistics",
            "--namespace", "AWS/S3",
            "--metric-name", "BucketSizeBytes",
            "--start-time", start.isoformat(),
            "--end-time", end.isoformat(),
            "--period", "86400",
            "--statistics", "Average",
            "--dimensions",
            f"Name=BucketName,Value={S3_BUCKET}",
            "Name=StorageType,Value=StandardStorage",
        )
        count_data = _aws(
            "cloudwatch", "get-metric-statistics",
            "--namespace", "AWS/S3",
            "--metric-name", "NumberOfObjects",
            "--start-time", start.isoformat(),
            "--end-time", end.isoformat(),
            "--period", "86400",
            "--statistics", "Average",
            "--dimensions",
            f"Name=BucketName,Value={S3_BUCKET}",
            "Name=StorageType,Value=AllStorageTypes",
        )
        size_points = size_data.get("Datapoints", [])
        count_points = count_data.get("Datapoints", [])
        total_bytes = size_points[-1]["Average"] if size_points else 0
        total_objects = int(count_points[-1]["Average"]) if count_points else 0
        return {
            "bucket": S3_BUCKET,
            "total_size_gb": round(total_bytes / (1024 ** 3), 2),
            "total_size_bytes": total_bytes,
            "object_count": total_objects,
            "monthly_cost_estimate": round((total_bytes / (1024 ** 3)) * 0.023, 2),
        }
    except Exception as exc:
        return {"bucket": S3_BUCKET, "error": str(exc)}


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


def aws_health_check() -> Dict[str, Any]:
    """Comprehensive AWS infrastructure health check.

    Checks:
    - ECS services: desired vs running counts
    - CloudWatch alarms: any in ALARM state
    - CloudWatch metrics: freshness of VPS metrics
    - S3 bucket: accessibility and size
    - Auto-scaling: policies configured
    - ECR: repository accessibility

    Returns a structured report with overall status (healthy/degraded/critical).
    """
    checks: List[Dict[str, Any]] = []
    overall = "healthy"

    def _add(name: str, status: str, detail: Any = None) -> None:
        nonlocal overall
        entry: Dict[str, Any] = {"name": name, "status": status}
        if detail is not None:
            entry["detail"] = detail
        checks.append(entry)
        if status == "critical":
            overall = "critical"
        elif status == "degraded" and overall != "critical":
            overall = "degraded"

    # 1. ECS Services
    try:
        ecs = ecs_status()
        unhealthy = []
        for svc in ecs.get("services", []):
            if svc.get("desired", 0) > 0 and svc.get("running", 0) < svc.get("desired", 0):
                unhealthy.append(svc["name"])
        if unhealthy:
            _add("ecs_services", "degraded", {
                "unhealthy": unhealthy,
                "total": len(ecs.get("services", [])),
            })
        else:
            _add("ecs_services", "healthy", {
                "count": len(ecs.get("services", [])),
                "all_running": True,
            })
    except Exception as exc:
        _add("ecs_services", "critical", {"error": str(exc)})

    # 2. CloudWatch Alarms
    try:
        alarm_data = cloudwatch_get_alarms()
        active_alarms = [
            a for a in alarm_data.get("alarms", [])
            if a.get("state") == "ALARM"
        ]
        if active_alarms:
            _add("cloudwatch_alarms", "degraded", {
                "active": [a["name"] for a in active_alarms],
                "total": alarm_data.get("count", 0),
            })
        else:
            _add("cloudwatch_alarms", "healthy", {
                "total": alarm_data.get("count", 0),
                "active": 0,
            })
    except Exception as exc:
        _add("cloudwatch_alarms", "degraded", {"error": str(exc)})

    # 3. CloudWatch VPS Metrics (freshness)
    try:
        metrics = cloudwatch_get_vps_metrics(minutes=15)
        cpu = metrics.get("cpu_usage_user", {})
        mem = metrics.get("mem_used_percent", {})
        has_data = (cpu.get("datapoints", 0) > 0) or (mem.get("datapoints", 0) > 0)
        if has_data:
            _add("cloudwatch_vps_metrics", "healthy", {
                "cpu_avg": cpu.get("average"),
                "mem_avg": mem.get("average"),
                "datapoints": cpu.get("datapoints", 0),
            })
        else:
            _add("cloudwatch_vps_metrics", "degraded", {
                "reason": "no_recent_datapoints",
            })
    except Exception as exc:
        _add("cloudwatch_vps_metrics", "degraded", {"error": str(exc)})

    # 4. S3 Bucket
    try:
        stats = s3_bucket_stats()
        if "error" in stats:
            _add("s3_bucket", "degraded", stats)
        else:
            _add("s3_bucket", "healthy", {
                "size_gb": stats.get("total_size_gb"),
                "objects": stats.get("object_count"),
                "cost_estimate": stats.get("monthly_cost_estimate"),
            })
    except Exception as exc:
        _add("s3_bucket", "degraded", {"error": str(exc)})

    # 5. Auto-scaling Policies
    try:
        scaling_ok = True
        scaling_detail = {}
        for svc_key in ("workshop", "worker"):
            desc = ecs_describe_scaling(svc_key)
            policies = desc.get("policies", [])
            scaling_detail[svc_key] = len(policies)
            if not policies and "error" not in desc:
                scaling_ok = False
        _add("auto_scaling", "healthy" if scaling_ok else "degraded", scaling_detail)
    except Exception as exc:
        _add("auto_scaling", "degraded", {"error": str(exc)})

    # 6. ECR Repositories
    try:
        all_repos = list(ECR_REPOS.values())
        _aws("ecr", "describe-repositories",
             "--repository-names", *all_repos)
        _add("ecr_repos", "healthy", {"repos": all_repos})
    except Exception as exc:
        _add("ecr_repos", "degraded", {"error": str(exc)})

    # 7. Budget Status
    try:
        budget_data = _aws(
            "budgets", "describe-budgets",
            "--account-id", ACCOUNT_ID,
        )
        budgets = budget_data.get("Budgets", [])
        budget_info = []
        for b in budgets:
            calc = b.get("CalculatedSpend", {})
            actual = float(calc.get("ActualSpend", {}).get("Amount", 0))
            limit_amt = float(b.get("BudgetLimit", {}).get("Amount", 0))
            utilization = (actual / limit_amt * 100) if limit_amt else 0
            budget_info.append({
                "name": b.get("BudgetName"),
                "actual": actual,
                "limit": limit_amt,
                "utilization_pct": round(utilization, 1),
            })
        over_budget = any(bi["utilization_pct"] >= 100 for bi in budget_info)
        warning = any(bi["utilization_pct"] >= 80 for bi in budget_info)
        status = "critical" if over_budget else ("degraded" if warning else "healthy")
        _add("budget", status, {"budgets": budget_info})
    except Exception as exc:
        _add("budget", "degraded", {"error": str(exc)})

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "healthy_count": sum(1 for c in checks if c["status"] == "healthy"),
        "degraded_count": sum(1 for c in checks if c["status"] == "degraded"),
        "critical_count": sum(1 for c in checks if c["status"] == "critical"),
        "total_checks": len(checks),
    }


# ---------------------------------------------------------------------------
# A2A Protocol registration
# ---------------------------------------------------------------------------


def register_aws_agent(protocol) -> None:
    """Register the AWS agent with the A2A protocol."""
    try:
        from citadel_lite.src.a2a.protocol import AgentCard
    except ImportError:
        return

    card = AgentCard(
        name="aws-agent",
        capabilities=[
            "ecs-control", "ecs-register-task", "ecs-create-service",
            "ecr-images", "ecr-repos",
            "alb-target-health", "runtime-health",
            "bedrock-invoke", "bedrock-check-access", "bedrock-fix-access",
            "iam-policies", "iam-check-bedrock", "iam-remove-deny",
            "s3-storage",
            "cloudwatch-logs", "cloudwatch-metrics", "auto-scaling",
            "s3-lifecycle", "health-check",
            "datadog-metrics",
        ],
        version="4.0.0",
    )

    def handle_aws_message(message):
        """A2A message handler for AWS operations."""
        packet = message.packet
        action = getattr(packet, "action", None) or packet.__dict__.get("action", "status")

        try:
            if action == "status":
                result = ecs_status()
            elif action == "scale":
                result = ecs_scale(
                    packet.__dict__.get("service", ""),
                    int(packet.__dict__.get("count", 1)),
                )
            elif action == "deploy":
                result = ecs_deploy(packet.__dict__.get("service", ""))
            elif action == "bedrock":
                result = bedrock_invoke(
                    prompt=packet.__dict__.get("prompt", ""),
                    model=packet.__dict__.get("model", DEFAULT_MODEL),
                )
            elif action == "s3-list":
                result = s3_list(packet.__dict__.get("prefix", ""))
            elif action == "logs":
                result = {"logs": cloudwatch_tail(packet.__dict__.get("service", "nats"))}
            elif action == "vps-metrics":
                result = cloudwatch_get_vps_metrics(
                    int(packet.__dict__.get("minutes", 10)),
                )
            elif action == "container-metrics":
                result = cloudwatch_get_container_metrics(
                    int(packet.__dict__.get("minutes", 10)),
                )
            elif action == "scaling":
                result = ecs_describe_scaling(packet.__dict__.get("service", ""))
            elif action == "alarms":
                result = cloudwatch_get_alarms()
            elif action == "s3-stats":
                result = s3_bucket_stats(packet.__dict__.get("prefix", ""))
            elif action == "health-check":
                result = aws_health_check()
            elif action == "ecr-images":
                result = ecr_images(packet.__dict__.get("repo", "runtime"))
            elif action == "ecr-repos":
                result = ecr_list_repos()
            elif action == "register-task":
                result = ecs_register_task(
                    packet.__dict__.get("service", ""),
                    packet.__dict__.get("image", "latest"),
                )
            elif action == "create-service":
                result = ecs_create_service(
                    packet.__dict__.get("service", ""),
                    int(packet.__dict__.get("count", 0)),
                )
            elif action == "target-health":
                result = alb_target_health(packet.__dict__.get("service"))
            elif action == "runtime-health":
                result = runtime_health()
            elif action == "datadog-metrics":
                result = datadog_query_metrics(
                    packet.__dict__.get("metric", "citadel.vps.cpu"),
                    int(packet.__dict__.get("minutes", 10)),
                )
            elif action == "iam-policies":
                result = iam_get_user_policies(
                    packet.__dict__.get("user", IAM_USER),
                )
            elif action == "bedrock-check-access":
                result = iam_check_bedrock_access(
                    packet.__dict__.get("user", IAM_USER),
                    packet.__dict__.get("model"),
                )
            elif action == "bedrock-fix-access":
                result = bedrock_fix_access(
                    packet.__dict__.get("user", IAM_USER),
                    dry_run=packet.__dict__.get("dry_run", False),
                )
            elif action == "iam-remove-deny":
                result = iam_remove_bedrock_deny(
                    packet.__dict__.get("user", IAM_USER),
                    dry_run=packet.__dict__.get("dry_run", False),
                )
            else:
                result = {"error": f"Unknown action: {action}"}
        except Exception as exc:
            result = {"error": str(exc)}

        message.packet.__dict__["aws_result"] = result
        message.from_agent = "aws-agent"
        return message

    protocol.register(card, handle_aws_message)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    """Standalone CLI for AWS agent operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Citadel AWS Agent")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="ECS cluster status")

    scale_p = sub.add_parser("scale", help="Scale ECS service")
    scale_p.add_argument("--service", required=True, choices=list(SERVICES.keys()))
    scale_p.add_argument("--count", type=int, required=True)

    deploy_p = sub.add_parser("deploy", help="Force new deployment")
    deploy_p.add_argument("--service", required=True, choices=list(SERVICES.keys()))

    tasks_p = sub.add_parser("tasks", help="List running tasks")
    tasks_p.add_argument("--service", choices=list(SERVICES.keys()))

    bedrock_p = sub.add_parser("bedrock", help="Invoke Claude via Bedrock")
    bedrock_p.add_argument("--prompt", required=True)
    bedrock_p.add_argument("--model", default=DEFAULT_MODEL, choices=list(CLAUDE_MODELS.keys()))
    bedrock_p.add_argument("--max-tokens", type=int, default=1024)

    s3_p = sub.add_parser("s3", help="S3 operations")
    s3_p.add_argument("--action", choices=["list", "upload", "download"], default="list")
    s3_p.add_argument("--prefix", default="")
    s3_p.add_argument("--local-path", default="")
    s3_p.add_argument("--s3-key", default="")

    logs_p = sub.add_parser("logs", help="Tail CloudWatch logs")
    logs_p.add_argument("--service", default="nats")
    logs_p.add_argument("--lines", type=int, default=50)

    metrics_p = sub.add_parser("vps-metrics", help="VPS CPU/memory from CloudWatch")
    metrics_p.add_argument("--minutes", type=int, default=10)

    cmetrics_p = sub.add_parser("container-metrics", help="Per-container CPU/memory from CloudWatch")
    cmetrics_p.add_argument("--minutes", type=int, default=10)

    scaling_p = sub.add_parser("scaling", help="Describe auto-scaling policies")
    scaling_p.add_argument("--service", required=True, choices=list(SERVICES.keys()))

    sub.add_parser("alarms", help="List CloudWatch alarms")

    stats_p = sub.add_parser("s3-stats", help="S3 bucket size and object count")
    stats_p.add_argument("--prefix", default="")

    sub.add_parser("health-check", help="Comprehensive AWS infrastructure health check")

    # ── New ECS/ECR/ALB commands ──────────────────────────────────
    ecr_p = sub.add_parser("ecr-images", help="List images in an ECR repository")
    ecr_p.add_argument("--repo", default="runtime", choices=list(ECR_REPOS.keys()))

    sub.add_parser("ecr-repos", help="List all ECR repositories")

    reg_p = sub.add_parser("register-task", help="Register/update a task definition")
    reg_p.add_argument("--service", required=True, choices=list(SERVICE_PORTS.keys()))
    reg_p.add_argument("--image", default="latest", help="Image tag")
    reg_p.add_argument("--cpu", default="256", help="CPU units")
    reg_p.add_argument("--memory", default="512", help="Memory MB")
    reg_p.add_argument("--no-datadog", action="store_true", help="Skip Datadog sidecar")

    create_p = sub.add_parser("create-service", help="Create a new ECS service")
    create_p.add_argument("--service", required=True, choices=list(SERVICES.keys()))
    create_p.add_argument("--count", type=int, default=0, help="Initial desired count")

    th_p = sub.add_parser("target-health", help="Check ALB target group health")
    th_p.add_argument("--service", default=None, help="Filter by service name")

    sub.add_parser("runtime-health", help="Query health-monitor for cluster health")

    dd_p = sub.add_parser("datadog-metrics", help="Query Datadog metrics")
    dd_p.add_argument("--metric", default="citadel.vps.cpu")
    dd_p.add_argument("--minutes", type=int, default=10)

    # ── IAM / Bedrock access management commands ─────────────────
    iam_p = sub.add_parser("iam-policies", help="List IAM policies for a user")
    iam_p.add_argument("--user", default=IAM_USER, help=f"IAM user (default: {IAM_USER})")

    iam_inline_p = sub.add_parser("iam-get-policy", help="Get inline IAM policy document")
    iam_inline_p.add_argument("--user", default=IAM_USER)
    iam_inline_p.add_argument("--policy-name", required=True)

    bcheck_p = sub.add_parser("bedrock-check-access", help="Check Bedrock InvokeModel access")
    bcheck_p.add_argument("--user", default=IAM_USER)
    bcheck_p.add_argument("--model", default=None, help="Model ID to check (default: opus)")

    bfix_p = sub.add_parser("bedrock-fix-access",
                            help="Fix Bedrock access: remove denies, create + attach allow policy")
    bfix_p.add_argument("--user", default=IAM_USER)
    bfix_p.add_argument("--dry-run", action="store_true", help="Show what would change without applying")

    brdeny_p = sub.add_parser("iam-remove-deny", help="Remove Bedrock Deny statements from inline policies")
    brdeny_p.add_argument("--user", default=IAM_USER)
    brdeny_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "status":
            result = ecs_status()
        elif args.command == "scale":
            result = ecs_scale(args.service, args.count)
        elif args.command == "deploy":
            result = ecs_deploy(args.service)
        elif args.command == "tasks":
            result = ecs_tasks(args.service)
        elif args.command == "bedrock":
            result = bedrock_invoke(args.prompt, args.model, args.max_tokens)
        elif args.command == "s3":
            if args.action == "list":
                result = s3_list(args.prefix)
            elif args.action == "upload":
                result = s3_upload(args.local_path, args.s3_key)
            elif args.action == "download":
                result = s3_download(args.s3_key, args.local_path)
        elif args.command == "logs":
            result = cloudwatch_tail(args.service, args.lines)
        elif args.command == "vps-metrics":
            result = cloudwatch_get_vps_metrics(args.minutes)
        elif args.command == "container-metrics":
            result = cloudwatch_get_container_metrics(args.minutes)
        elif args.command == "scaling":
            result = ecs_describe_scaling(args.service)
        elif args.command == "alarms":
            result = cloudwatch_get_alarms()
        elif args.command == "s3-stats":
            result = s3_bucket_stats(args.prefix)
        elif args.command == "health-check":
            result = aws_health_check()
        elif args.command == "ecr-images":
            result = ecr_images(args.repo)
        elif args.command == "ecr-repos":
            result = ecr_list_repos()
        elif args.command == "register-task":
            result = ecs_register_task(
                args.service, args.image, args.cpu, args.memory,
                with_datadog=not args.no_datadog,
            )
        elif args.command == "create-service":
            result = ecs_create_service(args.service, args.count)
        elif args.command == "target-health":
            result = alb_target_health(args.service)
        elif args.command == "runtime-health":
            result = runtime_health()
        elif args.command == "datadog-metrics":
            result = datadog_query_metrics(args.metric, args.minutes)
        elif args.command == "iam-policies":
            result = iam_get_user_policies(args.user)
        elif args.command == "iam-get-policy":
            result = iam_get_inline_policy(args.user, args.policy_name)
        elif args.command == "bedrock-check-access":
            result = iam_check_bedrock_access(args.user, args.model)
        elif args.command == "bedrock-fix-access":
            result = bedrock_fix_access(args.user, dry_run=args.dry_run)
        elif args.command == "iam-remove-deny":
            result = iam_remove_bedrock_deny(args.user, dry_run=args.dry_run)
        else:
            result = {"error": "Unknown command"}

        print(json.dumps(result, indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
