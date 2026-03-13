# tests/test_migrate_orchestrator.py
"""
Unit tests for MigrateOrchestrator agent.

SRS: SRS-MIGRATE-ORCH-20260205-001-V3.0
"""
from __future__ import annotations

import json
import os
import tempfile
import pytest

from src.types import HandoffPacket, EventJsonV1, AgentOutput
from src.agents.migrate_orchestrator import (
    RUNTIME_SERVICES,
    ServiceState,
    _TRANSITIONS,
    _select_migration_candidates,
    _select_reverse_candidates,
    get_service_state,
    load_migration_state,
    save_migration_state,
    transition_service,
    run_migrate_v2,
)


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    """Use a temp file for migration state and disable LLM in all tests."""
    state_file = str(tmp_path / "migration-state.json")
    monkeypatch.setenv("MIGRATION_STATE_FILE", state_file)
    # Also patch the module-level constant
    import src.agents.migrate_orchestrator as mod
    monkeypatch.setattr(mod, "MIGRATION_STATE_FILE", state_file)
    # Force rule-based path (no LLM calls in tests)
    monkeypatch.setattr(mod, "_run_migrate_llm", lambda packet: None)
    yield


def _make_packet(
    vps_cpu: float = 50.0,
    vps_memory: float = 60.0,
    container_stats: dict | None = None,
    budget_pct: float = 30.0,
) -> HandoffPacket:
    """Build a HandoffPacket with Watcher + Budget outputs."""
    packet = HandoffPacket(event=EventJsonV1())

    watcher_payload = {
        "event_type": "healthy",
        "severity": "info",
        "signals": [],
        "metrics": {
            "vps_cpu": vps_cpu,
            "vps_memory": vps_memory,
            "container_stats": container_stats or {},
        },
        "recommended_action": "none",
    }
    packet.add_output("watcher", watcher_payload)

    budget_payload = {
        "evaluation": {"utilization_pct": budget_pct},
    }
    packet.add_output("budget", budget_payload)

    return packet


# ── State Machine Tests ───────────────────────────────────────────

class TestStateMachine:
    def test_default_state_is_vps_running(self):
        assert get_service_state("event-listener") == ServiceState.VPS_RUNNING

    def test_valid_transition(self):
        ok = transition_service("event-listener", ServiceState.MIGRATING_TO_ECS)
        assert ok
        assert get_service_state("event-listener") == ServiceState.MIGRATING_TO_ECS

    def test_invalid_transition_rejected(self):
        # Cannot go directly from VPS_RUNNING to ECS_RUNNING
        ok = transition_service("event-listener", ServiceState.ECS_RUNNING)
        assert not ok
        assert get_service_state("event-listener") == ServiceState.VPS_RUNNING

    def test_full_migration_cycle(self):
        svc = "governance-gateway"
        assert transition_service(svc, ServiceState.MIGRATING_TO_ECS)
        assert transition_service(svc, ServiceState.ECS_RUNNING)
        assert transition_service(svc, ServiceState.MIGRATING_TO_VPS)
        assert transition_service(svc, ServiceState.VPS_RUNNING)

    def test_failed_state_recovery(self):
        svc = "smartbank"
        assert transition_service(svc, ServiceState.MIGRATING_TO_ECS)
        assert transition_service(svc, ServiceState.FAILED)
        # Can recover from FAILED
        assert transition_service(svc, ServiceState.VPS_RUNNING)

    def test_all_transitions_defined(self):
        for state in ServiceState:
            assert state in _TRANSITIONS, f"Missing transitions for {state}"

    def test_state_persistence(self):
        transition_service("council", ServiceState.MIGRATING_TO_ECS)
        # Reload from file
        states = load_migration_state()
        assert states["council"] == ServiceState.MIGRATING_TO_ECS.value


# ── Service Registry Tests ────────────────────────────────────────

class TestServiceRegistry:
    def test_all_services_have_required_fields(self):
        for name, info in RUNTIME_SERVICES.items():
            assert "port" in info, f"{name} missing port"
            assert "tier" in info, f"{name} missing tier"
            assert "redis_dependent" in info, f"{name} missing redis_dependent"
            assert "stateful" in info, f"{name} missing stateful"
            assert "ecs_service" in info, f"{name} missing ecs_service"

    def test_tiers_are_1_2_or_3(self):
        for name, info in RUNTIME_SERVICES.items():
            assert info["tier"] in (1, 2, 3), f"{name} has invalid tier {info['tier']}"

    def test_redis_not_in_registry(self):
        assert "redis" not in RUNTIME_SERVICES


# ── Candidate Selection Tests ─────────────────────────────────────

class TestCandidateSelection:
    def test_selects_high_cpu_container(self):
        container_stats = {
            "cnwb-event-listener-1": {"cpu_percent": 25.0, "mem_percent": 40.0},
            "cnwb-sake-builder-1": {"cpu_percent": 5.0, "mem_percent": 30.0},
        }
        candidates = _select_migration_candidates(container_stats)
        assert len(candidates) == 1
        assert candidates[0]["name"] == "event-listener"

    def test_sorts_by_tier_then_cpu(self):
        container_stats = {
            "cnwb-council-1": {"cpu_percent": 30.0, "mem_percent": 40.0},
            "cnwb-governance-gateway-1": {"cpu_percent": 20.0, "mem_percent": 40.0},
            "cnwb-event-listener-1": {"cpu_percent": 25.0, "mem_percent": 40.0},
        }
        candidates = _select_migration_candidates(container_stats)
        assert len(candidates) == 3
        # Tier 1 first (event-listener: 25%, governance-gateway: 20%), then tier 2 (council: 30%)
        assert candidates[0]["name"] == "event-listener"
        assert candidates[1]["name"] == "governance-gateway"
        assert candidates[2]["name"] == "council"

    def test_ignores_low_cpu_containers(self):
        container_stats = {
            "cnwb-event-listener-1": {"cpu_percent": 5.0, "mem_percent": 40.0},
        }
        candidates = _select_migration_candidates(container_stats)
        assert len(candidates) == 0

    def test_reverse_candidates_highest_tier_first(self):
        # Set two services to ECS_RUNNING
        transition_service("event-listener", ServiceState.MIGRATING_TO_ECS)
        transition_service("event-listener", ServiceState.ECS_RUNNING)
        transition_service("council", ServiceState.MIGRATING_TO_ECS)
        transition_service("council", ServiceState.ECS_RUNNING)

        candidates = _select_reverse_candidates(50.0)
        assert len(candidates) == 2
        # Tier 2 (council) should come before tier 1 (event-listener)
        assert candidates[0]["name"] == "council"
        assert candidates[1]["name"] == "event-listener"


# ── Decision Engine Tests ─────────────────────────────────────────

class TestDecisionEngine:
    def test_healthy_no_action(self):
        packet = _make_packet(vps_cpu=50.0)
        result = run_migrate_v2(packet)
        assert result["action"] == "no_action"
        assert len(result["services"]) == 0

    def test_high_cpu_triggers_migration(self):
        container_stats = {
            "containers": {
                "cnwb-event-listener-1": {
                    "cpu_percent": {"average": 25.0},
                    "mem_percent": {"average": 40.0},
                },
            }
        }
        packet = _make_packet(vps_cpu=85.0, container_stats=container_stats)
        result = run_migrate_v2(packet)
        assert result["action"] == "migrate_to_ecs"
        assert len(result["services"]) == 1
        assert result["services"][0]["name"] == "event-listener"
        assert result["services"][0]["to"] == "ecs"

    def test_low_cpu_triggers_reverse(self):
        # First migrate a service to ECS
        transition_service("event-listener", ServiceState.MIGRATING_TO_ECS)
        transition_service("event-listener", ServiceState.ECS_RUNNING)

        packet = _make_packet(vps_cpu=30.0)
        result = run_migrate_v2(packet)
        assert result["action"] == "migrate_to_vps"
        assert result["services"][0]["name"] == "event-listener"

    def test_budget_critical_forces_all_back(self):
        # Migrate two services
        transition_service("event-listener", ServiceState.MIGRATING_TO_ECS)
        transition_service("event-listener", ServiceState.ECS_RUNNING)
        transition_service("sake-builder", ServiceState.MIGRATING_TO_ECS)
        transition_service("sake-builder", ServiceState.ECS_RUNNING)

        packet = _make_packet(vps_cpu=50.0, budget_pct=92.0)
        result = run_migrate_v2(packet)
        assert result["action"] == "force_reverse_all"
        assert len(result["services"]) == 2

    def test_budget_warning_reverses_low_priority(self):
        # Migrate tier 1 and tier 2 services
        transition_service("event-listener", ServiceState.MIGRATING_TO_ECS)
        transition_service("event-listener", ServiceState.ECS_RUNNING)
        transition_service("council", ServiceState.MIGRATING_TO_ECS)
        transition_service("council", ServiceState.ECS_RUNNING)

        packet = _make_packet(vps_cpu=70.0, budget_pct=82.0)
        result = run_migrate_v2(packet)
        assert result["action"] == "migrate_to_vps"
        # Should reverse highest tier first (council = tier 2)
        assert result["services"][0]["name"] == "council"

    def test_no_migration_during_active_migration(self):
        # Set one service to migrating
        transition_service("event-listener", ServiceState.MIGRATING_TO_ECS)

        container_stats = {
            "containers": {
                "cnwb-sake-builder-1": {
                    "cpu_percent": {"average": 30.0},
                    "mem_percent": {"average": 40.0},
                },
            }
        }
        packet = _make_packet(vps_cpu=85.0, container_stats=container_stats)
        result = run_migrate_v2(packet)
        # Should not start another migration while one is in progress
        assert result["action"] == "no_action"

    def test_no_migration_if_budget_high(self):
        container_stats = {
            "containers": {
                "cnwb-event-listener-1": {
                    "cpu_percent": {"average": 25.0},
                    "mem_percent": {"average": 40.0},
                },
            }
        }
        packet = _make_packet(vps_cpu=85.0, budget_pct=82.0, container_stats=container_stats)
        result = run_migrate_v2(packet)
        # Budget warning prevents new migrations
        assert result["action"] == "no_action"

    def test_output_schema_complete(self):
        packet = _make_packet()
        result = run_migrate_v2(packet)
        required_keys = {
            "action", "services", "current_state", "budget_check",
            "risk_estimate", "rationale", "llm_powered",
        }
        assert required_keys.issubset(result.keys())
        assert isinstance(result["services"], list)
        assert isinstance(result["current_state"], dict)
        assert isinstance(result["budget_check"], dict)
        assert "utilization_pct" in result["budget_check"]
        assert "safe_to_migrate" in result["budget_check"]
