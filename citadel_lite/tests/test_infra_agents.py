# citadel_lite/tests/test_infra_agents.py
"""
Behavioral tests for the infrastructure agent chain:
Watcher → Scaler → Curator

Tests verify:
- Watcher correctly classifies infrastructure events by severity
- Scaler makes appropriate scaling decisions from Watcher signals
- Curator proposes lifecycle transitions based on S3 state
- Full pipeline produces coherent end-to-end results

CGRF v3.0: SRS-TEST-INFRA-001, Tier 1
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.types import HandoffPacket, EventJsonV1, AgentOutput
from src.agents.watcher_v2 import run_watcher_v2, _run_watcher_rules
from src.agents.scaler_v2 import run_scaler_v2, _run_scaler_rules
from src.agents.curator_v2 import run_curator_v2, _run_curator_rules


# ============================================================================
# Watcher Agent Tests
# ============================================================================

class TestWatcherAgent:
    """Behavioral tests for the Watcher (Infrastructure Sentinel)."""

    def test_healthy_state_returns_info(self, packet_with_watcher_healthy):
        """When all metrics are normal, Watcher should report healthy/info."""
        # We test the rules engine directly with mocked metrics
        packet = HandoffPacket(event=EventJsonV1(event_id="w-test-1"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "vps_cpu": 35.0,
                "vps_memory": 55.0,
                "ecs_services": [
                    {"name": "workshop-service", "desired": 1, "running": 1},
                ],
                "s3_size_gb": 200.0,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            result = _run_watcher_rules(packet)

        assert result["event_type"] == "healthy"
        assert result["severity"] == "info"
        assert result["llm_powered"] is False

    def test_cpu_critical_detected(self):
        """CPU >= 90% should trigger cpu_spike/critical."""
        packet = HandoffPacket(event=EventJsonV1(event_id="w-test-2"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "vps_cpu": 95.0,
                "vps_memory": 60.0,
                "ecs_services": [],
                "s3_size_gb": 100.0,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            result = _run_watcher_rules(packet)

        assert result["event_type"] == "cpu_spike"
        assert result["severity"] == "critical"
        assert "cpu_critical" in result["signals"]
        assert result["recommended_action"] == "scale_up_immediately"

    def test_cpu_warning_detected(self):
        """CPU 80-89% should trigger scaling_needed/warning."""
        packet = HandoffPacket(event=EventJsonV1(event_id="w-test-3"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "vps_cpu": 85.0,
                "vps_memory": 60.0,
                "ecs_services": [],
                "s3_size_gb": 100.0,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            result = _run_watcher_rules(packet)

        assert result["severity"] == "warning"
        assert "cpu_high" in result["signals"]
        assert result["recommended_action"] == "scale_up"

    def test_cpu_low_suggests_scale_down(self):
        """CPU <= 40% should suggest consider_scale_down."""
        packet = HandoffPacket(event=EventJsonV1(event_id="w-test-4"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "vps_cpu": 20.0,
                "vps_memory": 40.0,
                "ecs_services": [],
                "s3_size_gb": 100.0,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            result = _run_watcher_rules(packet)

        assert "cpu_low" in result["signals"]
        assert result["recommended_action"] == "consider_scale_down"

    def test_memory_critical_overrides_severity(self):
        """Memory >= 90% should set critical severity even if CPU is fine."""
        packet = HandoffPacket(event=EventJsonV1(event_id="w-test-5"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "vps_cpu": 50.0,
                "vps_memory": 95.0,
                "ecs_services": [],
                "s3_size_gb": 100.0,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            result = _run_watcher_rules(packet)

        assert result["severity"] == "critical"
        assert "memory_critical" in result["signals"]

    def test_s3_critical_size_detected(self):
        """S3 >= 1000GB should trigger s3_critical_size signal."""
        packet = HandoffPacket(event=EventJsonV1(event_id="w-test-6"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "vps_cpu": 50.0,
                "vps_memory": 60.0,
                "ecs_services": [],
                "s3_size_gb": 1050.0,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            result = _run_watcher_rules(packet)

        assert "s3_critical_size" in result["signals"]

    def test_unhealthy_service_detected(self):
        """Service with desired > running should trigger service_unhealthy."""
        packet = HandoffPacket(event=EventJsonV1(event_id="w-test-7"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "vps_cpu": 50.0,
                "vps_memory": 60.0,
                "ecs_services": [
                    {"name": "workshop-service", "desired": 1, "running": 0},
                ],
                "s3_size_gb": 100.0,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            result = _run_watcher_rules(packet)

        assert result["event_type"] == "service_unhealthy"
        assert any("service_unhealthy" in s for s in result["signals"])

    def test_active_alarm_detected(self):
        """Active CloudWatch alarms should appear in signals."""
        packet = HandoffPacket(event=EventJsonV1(event_id="w-test-8"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "vps_cpu": 50.0,
                "vps_memory": 60.0,
                "ecs_services": [],
                "s3_size_gb": 100.0,
                "alarms": [{"name": "vps-cpu-high", "state": "ALARM"}],
                "collected_at": 1000000.0,
            }
            result = _run_watcher_rules(packet)

        assert any("alarm_active" in s for s in result["signals"])

    def test_metrics_always_present(self):
        """Result should always contain metrics dict."""
        packet = HandoffPacket(event=EventJsonV1(event_id="w-test-9"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "vps_cpu": None,
                "vps_memory": None,
                "ecs_services": [],
                "s3_size_gb": None,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            result = _run_watcher_rules(packet)

        assert "metrics" in result
        assert result["event_type"] == "healthy"


# ============================================================================
# Scaler Agent Tests
# ============================================================================

class TestScalerAgent:
    """Behavioral tests for the Scaler (Infrastructure Fixer)."""

    def test_no_action_on_healthy_state(self, packet_with_watcher_healthy):
        """Healthy Watcher output should result in no_action."""
        with patch("src.agents.scaler_v2._get_current_service_count", return_value=1):
            result = _run_scaler_rules(packet_with_watcher_healthy)

        assert result["action"] == "no_action"
        assert result["llm_powered"] is False

    def test_scale_up_on_cpu_critical(self, packet_with_watcher_cpu_critical):
        """CPU critical signal should trigger scale_up."""
        with patch("src.agents.scaler_v2._get_current_service_count", return_value=0):
            result = _run_scaler_rules(packet_with_watcher_cpu_critical)

        assert result["action"] == "scale_up"
        assert result["proposed_count"] > result["current_count"]
        assert len(result["execution_plan"]) > 0
        assert len(result["verification_steps"]) > 0

    def test_scale_up_respects_max_tasks(self, packet_with_watcher_cpu_critical):
        """Scaling should never exceed _MAX_TASKS (3)."""
        with patch("src.agents.scaler_v2._get_current_service_count", return_value=3):
            result = _run_scaler_rules(packet_with_watcher_cpu_critical)

        # Already at max, so no action or same count
        assert result["proposed_count"] <= 3

    def test_scale_down_on_low_cpu(self):
        """Low CPU with healthy state should propose scale_down."""
        packet = HandoffPacket(event=EventJsonV1(event_id="s-test-1"))
        packet.add_output("watcher", {
            "event_type": "healthy",
            "severity": "info",
            "signals": ["cpu_low"],
            "recommended_action": "consider_scale_down",
        })

        with patch("src.agents.scaler_v2._get_current_service_count", return_value=2):
            result = _run_scaler_rules(packet)

        assert result["action"] == "scale_down"
        assert result["proposed_count"] < 2

    def test_scale_down_respects_min_tasks(self):
        """Worker scale_down should go to 0 (min), workshop to 1."""
        packet = HandoffPacket(event=EventJsonV1(event_id="s-test-2"))
        packet.add_output("watcher", {
            "event_type": "healthy",
            "severity": "info",
            "signals": ["cpu_low"],
            "recommended_action": "consider_scale_down",
        })

        with patch("src.agents.scaler_v2._get_current_service_count", return_value=1):
            result = _run_scaler_rules(packet)

        # Worker min is 0, so going from 1 to 0 is valid
        assert result["proposed_count"] >= 0

    def test_lifecycle_deferred_to_curator(self):
        """apply_lifecycle_rules recommendation should pass through as no_action."""
        packet = HandoffPacket(event=EventJsonV1(event_id="s-test-3"))
        packet.add_output("watcher", {
            "event_type": "s3_growth",
            "severity": "warning",
            "signals": ["s3_warning_size"],
            "recommended_action": "apply_lifecycle_rules",
        })

        with patch("src.agents.scaler_v2._get_current_service_count", return_value=1):
            result = _run_scaler_rules(packet)

        assert result["action"] == "no_action"
        # Scaler passes through — no scaling action taken
        assert result["proposed_count"] == result["current_count"]

    def test_result_schema(self, packet_with_watcher_cpu_critical):
        """Scaler output should contain all required fields."""
        with patch("src.agents.scaler_v2._get_current_service_count", return_value=1):
            result = _run_scaler_rules(packet_with_watcher_cpu_critical)

        required_fields = [
            "action", "target", "current_count", "proposed_count",
            "risk_estimate", "rationale", "execution_plan",
            "verification_steps", "llm_powered",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"


# ============================================================================
# Curator Agent Tests
# ============================================================================

class TestCuratorAgent:
    """Behavioral tests for the Curator (Data Lifecycle Guardian)."""

    def test_no_action_small_bucket(self, packet_with_watcher_healthy):
        """Small S3 bucket with no signals should result in no_action."""
        with patch("src.agents.curator_v2._get_bucket_stats") as mock_stats:
            mock_stats.return_value = {
                "total_size_gb": 50.0,
                "object_count": 5000,
                "monthly_cost_estimate": 1.15,
            }
            result = _run_curator_rules(packet_with_watcher_healthy)

        assert result["action"] == "no_action"
        assert result["llm_powered"] is False

    def test_s3_critical_triggers_alert(self):
        """S3 critical signal from Watcher should trigger alert."""
        packet = HandoffPacket(event=EventJsonV1(event_id="c-test-1"))
        packet.add_output("watcher", {
            "signals": ["s3_critical_size"],
            "metrics": {"s3_size_gb": 1050.0},
        })

        with patch("src.agents.curator_v2._get_bucket_stats") as mock_stats:
            mock_stats.return_value = {
                "total_size_gb": 1050.0,
                "object_count": 500000,
                "monthly_cost_estimate": 24.15,
            }
            result = _run_curator_rules(packet)

        assert result["action"] == "alert"
        assert result["risk_score"] >= 0.3

    def test_result_schema(self, packet_with_watcher_healthy):
        """Curator output should contain all required fields."""
        with patch("src.agents.curator_v2._get_bucket_stats") as mock_stats:
            mock_stats.return_value = {
                "total_size_gb": 200.0,
                "object_count": 15000,
            }
            result = _run_curator_rules(packet_with_watcher_healthy)

        required_fields = [
            "action", "bucket_stats", "transitions_proposed",
            "deletions_proposed", "risk_score", "rationale", "llm_powered",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_bucket_stats_in_output(self, packet_with_watcher_healthy):
        """Bucket stats should always be present in output."""
        with patch("src.agents.curator_v2._get_bucket_stats") as mock_stats:
            mock_stats.return_value = {
                "total_size_gb": 300.0,
                "object_count": 20000,
                "monthly_cost_estimate": 6.90,
            }
            result = _run_curator_rules(packet_with_watcher_healthy)

        stats = result["bucket_stats"]
        assert "total_size_gb" in stats
        assert "monthly_cost" in stats


# ============================================================================
# Full Pipeline Tests
# ============================================================================

class TestInfraPipeline:
    """End-to-end infrastructure pipeline: Watcher → Scaler → Curator."""

    def test_healthy_pipeline(self):
        """Full pipeline with healthy metrics should produce no actions."""
        packet = HandoffPacket(event=EventJsonV1(event_id="pipe-1"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics, \
             patch("src.agents.scaler_v2._get_current_service_count", return_value=1), \
             patch("src.agents.curator_v2._get_bucket_stats") as mock_stats:

            mock_metrics.return_value = {
                "vps_cpu": 40.0,
                "vps_memory": 55.0,
                "ecs_services": [{"name": "workshop-service", "desired": 1, "running": 1}],
                "s3_size_gb": 200.0,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            mock_stats.return_value = {
                "total_size_gb": 200.0,
                "object_count": 15000,
            }

            # Run pipeline manually
            watcher_result = run_watcher_v2(packet)
            packet.add_output("watcher", watcher_result)

            scaler_result = run_scaler_v2(packet)
            packet.add_output("scaler", scaler_result)

            curator_result = run_curator_v2(packet)
            packet.add_output("curator", curator_result)

        # Verify all three agents ran
        assert "watcher" in packet.agent_outputs
        assert "scaler" in packet.agent_outputs
        assert "curator" in packet.agent_outputs

        # Verify healthy state produces no actions
        assert watcher_result["event_type"] == "healthy"

    def test_cpu_critical_pipeline(self):
        """Full pipeline with CPU critical should scale up and check S3."""
        packet = HandoffPacket(event=EventJsonV1(event_id="pipe-2"))

        with patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics, \
             patch("src.agents.scaler_v2._get_current_service_count", return_value=0), \
             patch("src.agents.curator_v2._get_bucket_stats") as mock_stats:

            mock_metrics.return_value = {
                "vps_cpu": 95.0,
                "vps_memory": 88.0,
                "ecs_services": [],
                "s3_size_gb": 500.0,
                "alarms": [{"name": "vps-cpu-high", "state": "ALARM"}],
                "collected_at": 1000000.0,
            }
            mock_stats.return_value = {
                "total_size_gb": 500.0,
                "object_count": 50000,
            }

            watcher_result = run_watcher_v2(packet)
            packet.add_output("watcher", watcher_result)

            scaler_result = run_scaler_v2(packet)
            packet.add_output("scaler", scaler_result)

            curator_result = run_curator_v2(packet)
            packet.add_output("curator", curator_result)

        assert watcher_result["severity"] == "critical"
        assert scaler_result["action"] == "scale_up"
        assert scaler_result["proposed_count"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
