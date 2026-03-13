# citadel_lite/tests/conftest.py
"""
Shared pytest fixtures for citadel_lite agent and pipeline testing.

Provides mock infrastructure data, HandoffPacket factories, and
agent chain fixtures for behavioral testing.

CGRF v3.0 Compliance:
- SRS Code: SRS-TEST-FRAMEWORK-001
- Tier: 1 (DEVELOPMENT)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# Ensure citadel_lite src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from src.types import (
        AgentOutput,
        Decision,
        EventArtifact,
        EventJsonV1,
        HandoffPacket,
        MemoryHit,
    )
    from src.a2a.protocol import A2AProtocol, AgentCard, A2AMessage
except ImportError:
    # Types not yet fully implemented — fixtures will be skipped for missing types
    AgentOutput = Decision = EventArtifact = EventJsonV1 = HandoffPacket = MemoryHit = None
    A2AProtocol = AgentCard = A2AMessage = None


# ============================================================================
# Custom markers
# ============================================================================

def pytest_configure(config):
    config.addinivalue_line("markers", "agents: agent behavioral tests")
    config.addinivalue_line("markers", "infra: infrastructure agent tests")
    config.addinivalue_line("markers", "sake: SAKE pipeline tests")
    config.addinivalue_line("markers", "f993: F993 backend translator tests")
    config.addinivalue_line("markers", "autonomous: autonomous development loop tests")


# ============================================================================
# Event factories
# ============================================================================

@pytest.fixture
def ci_failed_event() -> EventJsonV1:
    """A CI failure event with a missing dependency error."""
    return EventJsonV1(
        event_id="test-ci-001",
        event_type="ci_failed",
        source="github_actions",
        repo="citadel-nexus/CNWB",
        ref="main",
        summary="CI failed on unit tests",
        artifacts=EventArtifact(
            log_excerpt="ModuleNotFoundError: No module named 'requests'",
            links=["https://github.com/citadel-nexus/CNWB/actions/runs/123"],
        ),
    )


@pytest.fixture
def security_event() -> EventJsonV1:
    """A security alert event."""
    return EventJsonV1(
        event_id="test-sec-001",
        event_type="security_alert",
        source="gitlab",
        repo="citadel-nexus/CNWB",
        ref="main",
        summary="CVE-2026-1234 detected in dependency",
        artifacts=EventArtifact(
            log_excerpt="CVE-2026-1234: SQL injection in auth module, CVSS 9.1",
        ),
    )


@pytest.fixture
def healthy_event() -> EventJsonV1:
    """A healthy/normal event (no issues)."""
    return EventJsonV1(
        event_id="test-healthy-001",
        event_type="deploy_succeeded",
        source="gitlab",
        repo="citadel-nexus/CNWB",
        ref="main",
        summary="Deployment completed successfully",
    )


# ============================================================================
# HandoffPacket factories
# ============================================================================

@pytest.fixture
def empty_packet(ci_failed_event) -> HandoffPacket:
    """A fresh HandoffPacket with no agent outputs."""
    return HandoffPacket(event=ci_failed_event)


@pytest.fixture
def packet_with_watcher_healthy() -> HandoffPacket:
    """HandoffPacket with Watcher output indicating healthy state."""
    packet = HandoffPacket(
        event=EventJsonV1(event_id="infra-001", event_type="scheduled_check"),
    )
    packet.add_output("watcher", {
        "event_type": "healthy",
        "severity": "info",
        "signals": [],
        "signal_count": 0,
        "metrics": {
            "vps_cpu": 35.0,
            "vps_memory": 55.0,
            "s3_size_gb": 200.0,
            "ecs_services": [
                {"name": "workshop-service", "desired": 1, "running": 1},
            ],
        },
        "recommended_action": "none",
        "llm_powered": False,
    })
    return packet


@pytest.fixture
def packet_with_watcher_cpu_critical() -> HandoffPacket:
    """HandoffPacket with Watcher output indicating CPU spike."""
    packet = HandoffPacket(
        event=EventJsonV1(event_id="infra-002", event_type="cpu_spike"),
    )
    packet.add_output("watcher", {
        "event_type": "cpu_spike",
        "severity": "critical",
        "signals": ["cpu_critical", "memory_high"],
        "signal_count": 2,
        "metrics": {
            "vps_cpu": 95.0,
            "vps_memory": 85.0,
            "s3_size_gb": 500.0,
            "ecs_services": [
                {"name": "workshop-service", "desired": 1, "running": 1},
                {"name": "worker-service", "desired": 0, "running": 0},
            ],
        },
        "recommended_action": "scale_up_immediately",
        "llm_powered": False,
    })
    return packet


@pytest.fixture
def packet_with_watcher_s3_warning() -> HandoffPacket:
    """HandoffPacket with Watcher output indicating S3 nearing capacity."""
    packet = HandoffPacket(
        event=EventJsonV1(event_id="infra-003", event_type="s3_growth"),
    )
    packet.add_output("watcher", {
        "event_type": "s3_growth",
        "severity": "warning",
        "signals": ["s3_warning_size"],
        "signal_count": 1,
        "metrics": {
            "vps_cpu": 50.0,
            "vps_memory": 60.0,
            "s3_size_gb": 920.0,
            "s3_growth_rate_gb_day": 12.0,
        },
        "recommended_action": "apply_lifecycle_rules",
        "llm_powered": False,
    })
    return packet


@pytest.fixture
def packet_with_scaler_output(packet_with_watcher_cpu_critical) -> HandoffPacket:
    """HandoffPacket with both Watcher + Scaler outputs (CPU critical → scale up)."""
    packet = packet_with_watcher_cpu_critical
    packet.add_output("scaler", {
        "action": "scale_up",
        "target": "worker",
        "current_count": 0,
        "proposed_count": 2,
        "risk_estimate": 0.3,
        "rationale": "Scaling worker from 0 to 2 due to cpu_critical, memory_high",
        "execution_plan": [
            "aws ecs update-service --cluster citadel-cluster --service worker-service --desired-count 2",
        ],
        "verification_steps": ["Confirm worker-service has 2 running tasks"],
        "llm_powered": False,
    })
    return packet


# ============================================================================
# Mock AWS helpers
# ============================================================================

@pytest.fixture
def mock_aws_metrics():
    """Patch aws_agent functions to return controlled metrics."""
    with patch("src.agents.aws_agent.cloudwatch_get_vps_metrics") as mock_cw, \
         patch("src.agents.aws_agent.ecs_status") as mock_ecs, \
         patch("src.agents.aws_agent.cloudwatch_get_alarms") as mock_alarms, \
         patch("src.agents.aws_agent.s3_bucket_stats") as mock_s3:

        mock_cw.return_value = {
            "cpu_usage_user": {"average": 45.0},
            "mem_used_percent": {"average": 60.0},
        }
        mock_ecs.return_value = {
            "services": [
                {"name": "workshop-service", "desired": 1, "running": 1},
                {"name": "worker-service", "desired": 0, "running": 0},
            ],
        }
        mock_alarms.return_value = {"alarms": []}
        mock_s3.return_value = {
            "total_size_gb": 250.0,
            "object_count": 15000,
            "monthly_cost_estimate": 5.75,
        }

        yield {
            "cloudwatch": mock_cw,
            "ecs": mock_ecs,
            "alarms": mock_alarms,
            "s3": mock_s3,
        }


@pytest.fixture
def mock_aws_critical():
    """Patch aws_agent functions to simulate critical infrastructure state."""
    with patch("src.agents.aws_agent.cloudwatch_get_vps_metrics") as mock_cw, \
         patch("src.agents.aws_agent.ecs_status") as mock_ecs, \
         patch("src.agents.aws_agent.cloudwatch_get_alarms") as mock_alarms, \
         patch("src.agents.aws_agent.s3_bucket_stats") as mock_s3:

        mock_cw.return_value = {
            "cpu_usage_user": {"average": 95.0},
            "mem_used_percent": {"average": 92.0},
        }
        mock_ecs.return_value = {
            "services": [
                {"name": "workshop-service", "desired": 1, "running": 0},
                {"name": "worker-service", "desired": 1, "running": 0},
            ],
        }
        mock_alarms.return_value = {
            "alarms": [
                {"name": "vps-cpu-high", "state": "ALARM"},
            ],
        }
        mock_s3.return_value = {
            "total_size_gb": 1050.0,
            "object_count": 500000,
            "monthly_cost_estimate": 24.15,
        }

        yield {
            "cloudwatch": mock_cw,
            "ecs": mock_ecs,
            "alarms": mock_alarms,
            "s3": mock_s3,
        }


# ============================================================================
# A2A Protocol fixtures
# ============================================================================

@pytest.fixture
def a2a_protocol():
    """A fresh A2A protocol instance."""
    return A2AProtocol()


@pytest.fixture
def incident_protocol():
    """A2A protocol with the incident pipeline agents (sentinel→sherlock→fixer→guardian)."""
    from src.a2a.agent_wrapper import build_protocol
    return build_protocol()


@pytest.fixture
def full_protocol():
    """A2A protocol with all v2 agents including infrastructure chain."""
    from src.a2a.agent_wrapper import build_protocol_v2
    return build_protocol_v2()


# ============================================================================
# SAKE / F993 fixtures
# ============================================================================

@pytest.fixture
def minimal_sake_dict() -> Dict[str, Any]:
    """Minimal valid .sake file content as a dict."""
    return {
        "filetype": "SAKE",
        "version": "1.0",
        "taskir_blocks": {
            "task_name": "TestTask",
            "purpose": "Unit test verification",
            "inputs": ["test_data"],
            "outputs": ["test_result"],
            "preconditions": "Test environment ready",
            "postconditions": "Results validated",
            "algorithm_summary": "Run test and return result",
            "pseudocode": "result = run_test(data)\nreturn result",
            "design_notes": "Simple test task",
            "complexity": "O(1)",
            "edge_cases": "Empty input",
            "test_spec": "Verify output is not None",
            "extensibility_hooks": "post_test_hook",
        },
        "sake_layers": {
            "backend_layer": {
                "language": "Python",
                "framework": "Standalone",
                "entrypoint": "TestTask.execute",
            },
            "caps_profile": {
                "confidence": 0.9,
                "cost": 0.1,
                "latency_ms": 100.0,
                "risk": 0.1,
                "precision": 0.95,
                "trust_score": 0.85,
                "grade": "T1",
            },
        },
        "metadata": {
            "srs_code": "F993",
            "generator": "test_conftest",
            "timestamp": "2026-02-04T00:00:00Z",
            "reflex_group": "TEST",
            "code_gen_hooks": ["post_generate"],
        },
    }


@pytest.fixture
def csharp_sake_dict(minimal_sake_dict) -> Dict[str, Any]:
    """Sake dict targeting C# / UnrealCLR output."""
    sake = minimal_sake_dict.copy()
    sake["taskir_blocks"] = {
        **sake["taskir_blocks"],
        "task_name": "NPCBehavior",
        "purpose": "NPC behavior controller",
        "pseudocode": "loop through targets\nselect closest\nengage",
    }
    sake["sake_layers"] = {
        **sake["sake_layers"],
        "backend_layer": {
            "language": "C#",
            "framework": "UnrealCLR",
            "entrypoint": "NPCBehavior.Execute",
            "assemblies": ["UnrealEngine.Runtime"],
        },
        "aegis_layer": {
            "lid": "LID-TEST-001",
            "regen_count": 0,
            "lineage": {"parent": None},
            "diff_stats": {"changed": False},
            "differentiation": "initial",
            "mutation_hooks": [],
            "mutation_type": "INSERT",
        },
    }
    return sake


@pytest.fixture
def typescript_sake_dict(minimal_sake_dict) -> Dict[str, Any]:
    """Sake dict targeting TypeScript output."""
    sake = minimal_sake_dict.copy()
    sake["taskir_blocks"] = {
        **sake["taskir_blocks"],
        "task_name": "DashboardWidget",
        "purpose": "Real-time dashboard widget",
        "pseudocode": "fetch metrics\nrender chart\nupdate on interval",
    }
    sake["sake_layers"] = {
        **sake["sake_layers"],
        "backend_layer": {
            "language": "TypeScript",
            "framework": "React",
            "entrypoint": "DashboardWidget.render",
        },
    }
    return sake


@pytest.fixture
def packet_with_f993_output() -> HandoffPacket:
    """HandoffPacket with valid F993 Python generation output."""
    packet = HandoffPacket(
        event=EventJsonV1(event_id="autodev-001", event_type="autodev_cycle"),
    )
    packet.add_output("intent_generator", {
        "selected_intent": {
            "source": "github_issue",
            "id": 42,
            "title": "Add metrics endpoint",
            "priority": 0.8,
        },
        "queue_depth": 1,
    })
    packet.add_output("f993_python", {
        "valid": True,
        "generation_mode": "template",
        "files": [{
            "path": "generated/addmetricsendpoint.py",
            "content": '"""\nMetrics endpoint.\n"""\nimport logging\nlogger = logging.getLogger(__name__)\n\nclass AddMetricsEndpoint:\n    def execute(self, data: str) -> dict:\n        logger.info("Running")\n        return {"result": None}\n',
            "content_hash": "abc123def456",
            "line_count": 10,
        }],
    })
    return packet


@pytest.fixture
def packet_with_security_issues() -> HandoffPacket:
    """HandoffPacket with F993 output containing security-problematic code."""
    packet = HandoffPacket(
        event=EventJsonV1(event_id="autodev-002", event_type="autodev_cycle"),
    )
    packet.add_output("f993_python", {
        "valid": True,
        "generation_mode": "llm",
        "files": [{
            "path": "generated/dangerous.py",
            "content": 'import os\npassword = "hunter2"\nresult = eval(user_input)\nexec(code)\n',
            "content_hash": "bad123",
            "line_count": 4,
        }],
    })
    return packet
