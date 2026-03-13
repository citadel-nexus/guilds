# tests/test_migrate_e2e.py
"""
End-to-end tests for the VPS ↔ ECS migration pipeline.

Tests the full agent chain: Watcher → Scaler → Migrator → Curator → Budget
with mocked AWS/SSH calls to verify migration decisions flow correctly.

SRS: SRS-MIGRATE-ORCH-20260205-001-V3.0
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from src.types import HandoffPacket, EventJsonV1, AgentOutput
from src.agents.watcher_v2 import run_watcher_v2
from src.agents.scaler_v2 import run_scaler_v2
from src.agents.migrate_orchestrator import (
    run_migrate_v2,
    ServiceState,
    get_service_state,
    transition_service,
    RUNTIME_SERVICES,
)


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    """Use temp state file and disable LLM for all tests."""
    state_file = str(tmp_path / "migration-state.json")
    import src.agents.migrate_orchestrator as mod
    import src.agents.watcher_v2 as watcher_mod
    import src.agents.scaler_v2 as scaler_mod
    monkeypatch.setattr(mod, "MIGRATION_STATE_FILE", state_file)
    monkeypatch.setenv("MIGRATION_STATE_FILE", state_file)
    # Force rule-based path for all agents (no LLM calls in tests)
    monkeypatch.setattr(mod, "_run_migrate_llm", lambda packet: None)
    monkeypatch.setattr(watcher_mod, "_run_watcher_llm", lambda packet: None)
    monkeypatch.setattr(scaler_mod, "_run_scaler_llm", lambda packet: None)
    yield


def _mock_vps_metrics(cpu: float = 50.0, mem: float = 60.0):
    """Create mock VPS metrics response."""
    return {
        "instance": "vps-147-93-43-117",
        "period_minutes": 5,
        "cpu_usage_user": {"average": cpu, "maximum": cpu + 5, "datapoints": 5},
        "mem_used_percent": {"average": mem, "maximum": mem + 5, "datapoints": 5},
    }


def _mock_container_metrics(containers: dict):
    """Create mock container metrics response."""
    result = {"instance": "vps-147-93-43-117", "period_minutes": 5, "containers": {}}
    for name, stats in containers.items():
        result["containers"][name] = {
            "cpu_percent": {"average": stats.get("cpu", 5.0)},
            "mem_percent": {"average": stats.get("mem", 30.0)},
        }
    return result


def _mock_ecs_status(services=None):
    """Create mock ECS status response."""
    if services is None:
        services = [
            {"name": "workshop-service", "status": "ACTIVE", "desired": 1, "running": 1, "pending": 0},
            {"name": "worker-service", "status": "ACTIVE", "desired": 0, "running": 0, "pending": 0},
        ]
    return {"cluster": "citadel-cluster", "services": services}


# ── Full Pipeline: Watcher → Scaler → Migrator ───────────

class TestFullPipeline:
    """Tests the full agent pipeline with mock AWS calls."""

    @patch("src.agents.aws_agent.cloudwatch_get_vps_metrics")
    @patch("src.agents.aws_agent.ecs_status")
    @patch("src.agents.aws_agent.cloudwatch_get_alarms")
    @patch("src.agents.aws_agent.s3_bucket_stats")
    def test_healthy_pipeline_no_migration(
        self, mock_s3, mock_alarms, mock_ecs, mock_vps
    ):
        """Healthy system → no migration action."""
        mock_vps.return_value = _mock_vps_metrics(50.0, 60.0)
        mock_ecs.return_value = _mock_ecs_status()
        mock_alarms.return_value = {"count": 0, "alarms": []}
        mock_s3.return_value = {"total_size_gb": 50.0}

        packet = HandoffPacket(event=EventJsonV1())

        # Run Watcher
        watcher_result = run_watcher_v2(packet)
        packet.add_output("watcher", watcher_result)
        assert watcher_result["event_type"] == "healthy"

        # Run Scaler
        scaler_result = run_scaler_v2(packet)
        packet.add_output("scaler", scaler_result)

        # Add budget output
        packet.add_output("budget", {"evaluation": {"utilization_pct": 30.0}})

        # Run Migrator
        migrator_result = run_migrate_v2(packet)
        assert migrator_result["action"] == "no_action"
        assert len(migrator_result["services"]) == 0

    @patch("src.agents.aws_agent.cloudwatch_get_container_metrics")
    @patch("src.agents.aws_agent.cloudwatch_get_vps_metrics")
    @patch("src.agents.aws_agent.ecs_status")
    @patch("src.agents.aws_agent.cloudwatch_get_alarms")
    @patch("src.agents.aws_agent.s3_bucket_stats")
    def test_cpu_spike_triggers_migration(
        self, mock_s3, mock_alarms, mock_ecs, mock_vps, mock_containers
    ):
        """VPS CPU > 80% with high container CPU → migrate to ECS."""
        mock_vps.return_value = _mock_vps_metrics(85.0, 70.0)
        mock_ecs.return_value = _mock_ecs_status()
        mock_alarms.return_value = {"count": 0, "alarms": []}
        mock_s3.return_value = {"total_size_gb": 50.0}
        mock_containers.return_value = _mock_container_metrics({
            "cnwb-governance-gateway-1": {"cpu": 25.0, "mem": 40.0},
            "cnwb-event-listener-1": {"cpu": 20.0, "mem": 35.0},
            "cnwb-redis-1": {"cpu": 2.0, "mem": 15.0},
        })

        packet = HandoffPacket(event=EventJsonV1())

        # Run Watcher
        watcher_result = run_watcher_v2(packet)
        packet.add_output("watcher", watcher_result)

        # Verify container signals emitted
        assert any(s.startswith("container_cpu_high:") for s in watcher_result["signals"])

        # Run Scaler
        scaler_result = run_scaler_v2(packet)
        packet.add_output("scaler", scaler_result)

        # Add budget output (safe)
        packet.add_output("budget", {"evaluation": {"utilization_pct": 30.0}})

        # Run Migrator
        migrator_result = run_migrate_v2(packet)
        assert migrator_result["action"] == "migrate_to_ecs"
        assert len(migrator_result["services"]) >= 1
        # Should pick a tier-1 service
        assert migrator_result["services"][0]["to"] == "ecs"

    def test_budget_critical_reversal(self):
        """Budget > 90% with ECS services → force reverse all."""
        # Setup: two services on ECS
        transition_service("event-listener", ServiceState.MIGRATING_TO_ECS)
        transition_service("event-listener", ServiceState.ECS_RUNNING)
        transition_service("governance-gateway", ServiceState.MIGRATING_TO_ECS)
        transition_service("governance-gateway", ServiceState.ECS_RUNNING)

        packet = HandoffPacket(event=EventJsonV1())
        packet.add_output("watcher", {
            "event_type": "healthy",
            "severity": "info",
            "signals": [],
            "metrics": {"vps_cpu": 50.0, "vps_memory": 60.0, "container_stats": {}},
            "recommended_action": "none",
        })
        packet.add_output("budget", {"evaluation": {"utilization_pct": 92.0}})

        result = run_migrate_v2(packet)
        assert result["action"] == "force_reverse_all"
        assert len(result["services"]) == 2
        assert all(s["to"] == "vps" for s in result["services"])

    def test_migration_serialization(self):
        """Only one migration at a time — no new migrations during active one."""
        transition_service("event-listener", ServiceState.MIGRATING_TO_ECS)

        packet = HandoffPacket(event=EventJsonV1())
        packet.add_output("watcher", {
            "event_type": "scaling_needed",
            "severity": "warning",
            "signals": ["cpu_high", "container_cpu_high:cnwb-governance-gateway-1"],
            "metrics": {
                "vps_cpu": 85.0,
                "vps_memory": 70.0,
                "container_stats": {
                    "containers": {
                        "cnwb-governance-gateway-1": {
                            "cpu_percent": {"average": 30.0},
                            "mem_percent": {"average": 40.0},
                        },
                    }
                },
            },
            "recommended_action": "consider_migration",
        })
        packet.add_output("budget", {"evaluation": {"utilization_pct": 30.0}})

        result = run_migrate_v2(packet)
        assert result["action"] == "no_action"

    def test_cpu_drop_reverses_migration(self):
        """VPS CPU drops → reverse migrate to save costs."""
        transition_service("event-listener", ServiceState.MIGRATING_TO_ECS)
        transition_service("event-listener", ServiceState.ECS_RUNNING)

        packet = HandoffPacket(event=EventJsonV1())
        packet.add_output("watcher", {
            "event_type": "healthy",
            "severity": "info",
            "signals": ["cpu_low"],
            "metrics": {"vps_cpu": 30.0, "vps_memory": 50.0, "container_stats": {}},
            "recommended_action": "consider_scale_down",
        })
        packet.add_output("budget", {"evaluation": {"utilization_pct": 40.0}})

        result = run_migrate_v2(packet)
        assert result["action"] == "migrate_to_vps"
        assert result["services"][0]["name"] == "event-listener"
        assert result["services"][0]["to"] == "vps"

    def test_current_state_in_output(self):
        """Output always includes current_state for all services."""
        packet = HandoffPacket(event=EventJsonV1())
        packet.add_output("watcher", {
            "event_type": "healthy",
            "severity": "info",
            "signals": [],
            "metrics": {"vps_cpu": 50.0, "vps_memory": 60.0},
            "recommended_action": "none",
        })
        packet.add_output("budget", {"evaluation": {"utilization_pct": 20.0}})

        result = run_migrate_v2(packet)
        assert "current_state" in result
        for svc_name in RUNTIME_SERVICES:
            assert svc_name in result["current_state"]
