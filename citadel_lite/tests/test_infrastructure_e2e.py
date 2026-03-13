# citadel_lite/tests/test_infrastructure_e2e.py
"""
End-to-end tests for the new infrastructure components:
- Full 4-agent pipeline: Watcher → Scaler → Curator → Budget
- AWS health check function
- Data migration tool
- Budget agent integration
- Agent registration in A2A protocol

CGRF v3.0: SRS-TEST-INFRA-E2E-001, Tier 1
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.types import HandoffPacket, EventJsonV1, AgentOutput
from src.agents.watcher_v2 import run_watcher_v2
from src.agents.scaler_v2 import run_scaler_v2
from src.agents.curator_v2 import run_curator_v2
from src.agents.budget_v2 import (
    run_budget_v2,
    evaluate_budget,
    MONTHLY_BUDGET_USD,
    WARNING_THRESHOLD,
    CRITICAL_THRESHOLD,
)
from src.agents.aws_agent import aws_health_check, SERVICES, S3_BUCKET
from src.tools.data_migration import (
    MigrationDirection,
    MigrationRecord,
    MIGRATABLE_TABLES,
    run_migration,
)


# ============================================================================
# Full 4-Agent Infrastructure Pipeline E2E
# ============================================================================


class TestFullInfraPipeline:
    """End-to-end: Watcher → Scaler → Curator → Budget pipeline."""

    def test_healthy_pipeline_four_agents(self):
        """Full 4-agent pipeline with healthy metrics produces no critical actions."""
        packet = HandoffPacket(event=EventJsonV1(event_id="e2e-healthy-001"))

        with patch("src.agents.watcher_v2._run_watcher_llm", return_value=None), \
             patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics, \
             patch("src.agents.scaler_v2._get_current_service_count", return_value=1), \
             patch("src.agents.curator_v2._get_bucket_stats") as mock_stats, \
             patch("src.agents.budget_v2.get_month_to_date_cost") as mock_cost, \
             patch("src.agents.budget_v2.get_cost_by_service") as mock_svc_cost, \
             patch("src.agents.budget_v2.get_cost_forecast") as mock_forecast, \
             patch("src.agents.budget_v2.get_credits_balance") as mock_credits, \
             patch("src.agents.budget_v2.push_to_datadog") as mock_dd, \
             patch("src.agents.budget_v2.push_to_posthog") as mock_ph:

            mock_metrics.return_value = {
                "vps_cpu": 45.0,
                "vps_memory": 55.0,
                "ecs_services": [{"name": "workshop-service", "desired": 1, "running": 1}],
                "s3_size_gb": 200.0,
                "alarms": [],
                "collected_at": 1000000.0,
            }
            mock_stats.return_value = {
                "total_size_gb": 200.0,
                "object_count": 15000,
                "monthly_cost_estimate": 4.60,
            }
            mock_cost.return_value = {"total_usd": 85.50, "period_start": "2026-02-01", "period_end": "2026-02-05"}
            mock_svc_cost.return_value = [{"service": "ECS", "cost_usd": 30.0}, {"service": "S3", "cost_usd": 15.0}, {"service": "EC2", "cost_usd": 20.0}]
            mock_forecast.return_value = {"forecasted_usd": 250.0}
            mock_credits.return_value = {"credits_used_usd": 0.0}

            # Run full pipeline
            watcher_result = run_watcher_v2(packet)
            packet.add_output("watcher", watcher_result)

            scaler_result = run_scaler_v2(packet)
            packet.add_output("scaler", scaler_result)

            curator_result = run_curator_v2(packet)
            packet.add_output("curator", curator_result)

            budget_result = run_budget_v2(packet)
            packet.add_output("budget", budget_result)

        # All four agents produced output
        assert "watcher" in packet.agent_outputs
        assert "scaler" in packet.agent_outputs
        assert "curator" in packet.agent_outputs
        assert "budget" in packet.agent_outputs

        # Healthy state
        assert watcher_result["event_type"] == "healthy"
        assert watcher_result["severity"] == "info"
        assert scaler_result["action"] == "no_action"

        # Budget within limits
        assert "error" not in budget_result
        evaluation = budget_result.get("evaluation", {})
        assert evaluation.get("severity") == "info"

    def test_critical_pipeline_triggers_scaling_and_budget(self):
        """CPU critical triggers scale-up; budget remains healthy."""
        packet = HandoffPacket(event=EventJsonV1(event_id="e2e-critical-001"))

        with patch("src.agents.watcher_v2._run_watcher_llm", return_value=None), \
             patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics, \
             patch("src.agents.scaler_v2._get_current_service_count", return_value=0), \
             patch("src.agents.curator_v2._get_bucket_stats") as mock_stats, \
             patch("src.agents.budget_v2.get_month_to_date_cost") as mock_cost, \
             patch("src.agents.budget_v2.get_cost_by_service") as mock_svc_cost, \
             patch("src.agents.budget_v2.get_cost_forecast") as mock_forecast, \
             patch("src.agents.budget_v2.get_credits_balance") as mock_credits, \
             patch("src.agents.budget_v2.push_to_datadog"), \
             patch("src.agents.budget_v2.push_to_posthog"):

            mock_metrics.return_value = {
                "vps_cpu": 96.0,
                "vps_memory": 89.0,
                "ecs_services": [
                    {"name": "workshop-service", "desired": 1, "running": 1},
                    {"name": "worker-service", "desired": 0, "running": 0},
                ],
                "s3_size_gb": 500.0,
                "alarms": [{"name": "vps-cpu-high", "state": "ALARM"}],
                "collected_at": 1000000.0,
            }
            mock_stats.return_value = {
                "total_size_gb": 500.0,
                "object_count": 50000,
                "monthly_cost_estimate": 11.50,
            }
            mock_cost.return_value = {"total_usd": 150.00, "period_start": "2026-02-01", "period_end": "2026-02-05"}
            mock_svc_cost.return_value = [{"service": "ECS", "cost_usd": 60.0}, {"service": "S3", "cost_usd": 30.0}, {"service": "EC2", "cost_usd": 40.0}]
            mock_forecast.return_value = {"forecasted_usd": 320.0}
            mock_credits.return_value = {"credits_used_usd": 0.0}

            watcher_result = run_watcher_v2(packet)
            packet.add_output("watcher", watcher_result)

            scaler_result = run_scaler_v2(packet)
            packet.add_output("scaler", scaler_result)

            curator_result = run_curator_v2(packet)
            packet.add_output("curator", curator_result)

            budget_result = run_budget_v2(packet)
            packet.add_output("budget", budget_result)

        assert watcher_result["severity"] == "critical"
        assert scaler_result["action"] == "scale_up"
        assert scaler_result["proposed_count"] > 0
        assert "error" not in budget_result

    def test_budget_warning_pipeline(self):
        """Budget at 85% should produce warning severity in pipeline."""
        packet = HandoffPacket(event=EventJsonV1(event_id="e2e-budget-warn-001"))

        with patch("src.agents.watcher_v2._run_watcher_llm", return_value=None), \
             patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics, \
             patch("src.agents.scaler_v2._get_current_service_count", return_value=1), \
             patch("src.agents.curator_v2._get_bucket_stats") as mock_stats, \
             patch("src.agents.budget_v2.get_month_to_date_cost") as mock_cost, \
             patch("src.agents.budget_v2.get_cost_by_service") as mock_svc_cost, \
             patch("src.agents.budget_v2.get_cost_forecast") as mock_forecast, \
             patch("src.agents.budget_v2.get_credits_balance") as mock_credits, \
             patch("src.agents.budget_v2.push_to_datadog"), \
             patch("src.agents.budget_v2.push_to_posthog"):

            mock_metrics.return_value = {
                "vps_cpu": 50.0, "vps_memory": 60.0,
                "ecs_services": [], "s3_size_gb": 200.0,
                "alarms": [], "collected_at": 1000000.0,
            }
            mock_stats.return_value = {"total_size_gb": 200.0, "object_count": 10000}
            mock_cost.return_value = {"total_usd": 340.0, "period_start": "2026-02-01", "period_end": "2026-02-05"}
            mock_svc_cost.return_value = [{"service": "ECS", "cost_usd": 150.0}, {"service": "S3", "cost_usd": 90.0}, {"service": "EC2", "cost_usd": 50.0}]
            mock_forecast.return_value = {"forecasted_usd": 380.0}
            mock_credits.return_value = {"credits_used_usd": 0.0}

            watcher_result = run_watcher_v2(packet)
            packet.add_output("watcher", watcher_result)
            scaler_result = run_scaler_v2(packet)
            packet.add_output("scaler", scaler_result)
            curator_result = run_curator_v2(packet)
            packet.add_output("curator", curator_result)
            budget_result = run_budget_v2(packet)
            packet.add_output("budget", budget_result)

        evaluation = budget_result.get("evaluation", {})
        assert evaluation.get("severity") == "warning"
        assert evaluation.get("utilization_pct") == pytest.approx(85.0, abs=0.1)

    def test_s3_critical_triggers_curator_alert(self):
        """S3 > 1TB triggers curator alert action in pipeline."""
        packet = HandoffPacket(event=EventJsonV1(event_id="e2e-s3-critical-001"))

        with patch("src.agents.watcher_v2._run_watcher_llm", return_value=None), \
             patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics, \
             patch("src.agents.scaler_v2._get_current_service_count", return_value=1), \
             patch("src.agents.curator_v2._get_bucket_stats") as mock_stats, \
             patch("src.agents.budget_v2.get_month_to_date_cost") as mock_cost, \
             patch("src.agents.budget_v2.get_cost_by_service") as mock_svc_cost, \
             patch("src.agents.budget_v2.get_cost_forecast") as mock_forecast, \
             patch("src.agents.budget_v2.get_credits_balance") as mock_credits, \
             patch("src.agents.budget_v2.push_to_datadog"), \
             patch("src.agents.budget_v2.push_to_posthog"):

            mock_metrics.return_value = {
                "vps_cpu": 50.0, "vps_memory": 60.0,
                "ecs_services": [], "s3_size_gb": 1100.0,
                "alarms": [], "collected_at": 1000000.0,
            }
            mock_stats.return_value = {
                "total_size_gb": 1100.0, "object_count": 600000,
                "monthly_cost_estimate": 25.30,
            }
            mock_cost.return_value = {"total_usd": 100.0, "period_start": "2026-02-01", "period_end": "2026-02-05"}
            mock_svc_cost.return_value = [{"service": "S3", "cost_usd": 25.0}, {"service": "ECS", "cost_usd": 40.0}]
            mock_forecast.return_value = {"forecasted_usd": 280.0}
            mock_credits.return_value = {"credits_used_usd": 0.0}

            watcher_result = run_watcher_v2(packet)
            packet.add_output("watcher", watcher_result)
            scaler_result = run_scaler_v2(packet)
            packet.add_output("scaler", scaler_result)
            curator_result = run_curator_v2(packet)
            packet.add_output("curator", curator_result)
            budget_result = run_budget_v2(packet)
            packet.add_output("budget", budget_result)

        assert "s3_critical_size" in watcher_result["signals"]
        assert curator_result["action"] == "apply_lifecycle"


# ============================================================================
# AWS Health Check E2E
# ============================================================================


class TestAWSHealthCheck:
    """Tests for the aws_health_check() aggregation function."""

    def test_healthy_infrastructure(self):
        """All subsystems healthy produces overall healthy status."""
        with patch("src.agents.aws_agent.ecs_status") as mock_ecs, \
             patch("src.agents.aws_agent.cloudwatch_get_alarms") as mock_alarms, \
             patch("src.agents.aws_agent.cloudwatch_get_vps_metrics") as mock_metrics, \
             patch("src.agents.aws_agent.s3_bucket_stats") as mock_s3, \
             patch("src.agents.aws_agent.ecs_describe_scaling") as mock_scaling, \
             patch("src.agents.aws_agent._aws") as mock_aws:

            mock_ecs.return_value = {
                "services": [
                    {"name": "workshop-service", "desired": 1, "running": 1},
                    {"name": "nats-service", "desired": 1, "running": 1},
                ],
            }
            mock_alarms.return_value = {"count": 4, "alarms": [
                {"name": "vps-cpu-high", "state": "OK"},
                {"name": "vps-cpu-low", "state": "OK"},
            ]}
            mock_metrics.return_value = {
                "cpu_usage_user": {"average": 45.0, "datapoints": 10},
                "mem_used_percent": {"average": 60.0, "datapoints": 10},
            }
            mock_s3.return_value = {
                "total_size_gb": 250.0, "object_count": 15000,
                "monthly_cost_estimate": 5.75,
            }
            mock_scaling.return_value = {"policies": [{"name": "scale-up"}]}
            mock_aws.return_value = {"repositories": []}  # ECR + budgets

            result = aws_health_check()

        assert result["status"] == "healthy"
        assert result["total_checks"] >= 5
        assert result["healthy_count"] >= 5
        assert result["critical_count"] == 0

    def test_degraded_with_unhealthy_service(self):
        """Unhealthy ECS service produces degraded status."""
        with patch("src.agents.aws_agent.ecs_status") as mock_ecs, \
             patch("src.agents.aws_agent.cloudwatch_get_alarms") as mock_alarms, \
             patch("src.agents.aws_agent.cloudwatch_get_vps_metrics") as mock_metrics, \
             patch("src.agents.aws_agent.s3_bucket_stats") as mock_s3, \
             patch("src.agents.aws_agent.ecs_describe_scaling") as mock_scaling, \
             patch("src.agents.aws_agent._aws") as mock_aws:

            mock_ecs.return_value = {
                "services": [
                    {"name": "workshop-service", "desired": 1, "running": 0},
                    {"name": "nats-service", "desired": 1, "running": 1},
                ],
            }
            mock_alarms.return_value = {"count": 0, "alarms": []}
            mock_metrics.return_value = {
                "cpu_usage_user": {"average": 45.0, "datapoints": 5},
                "mem_used_percent": {"average": 60.0, "datapoints": 5},
            }
            mock_s3.return_value = {"total_size_gb": 100.0, "object_count": 5000}
            mock_scaling.return_value = {"policies": []}
            mock_aws.return_value = {}

            result = aws_health_check()

        assert result["status"] == "degraded"
        assert result["degraded_count"] >= 1

    def test_critical_on_ecs_failure(self):
        """ECS API failure produces critical status."""
        with patch("src.agents.aws_agent.ecs_status", side_effect=RuntimeError("ecs failed")), \
             patch("src.agents.aws_agent.cloudwatch_get_alarms") as mock_alarms, \
             patch("src.agents.aws_agent.cloudwatch_get_vps_metrics") as mock_metrics, \
             patch("src.agents.aws_agent.s3_bucket_stats") as mock_s3, \
             patch("src.agents.aws_agent.ecs_describe_scaling") as mock_scaling, \
             patch("src.agents.aws_agent._aws") as mock_aws:

            mock_alarms.return_value = {"count": 0, "alarms": []}
            mock_metrics.return_value = {"cpu_usage_user": {"datapoints": 0}, "mem_used_percent": {"datapoints": 0}}
            mock_s3.return_value = {"total_size_gb": 100.0, "object_count": 5000}
            mock_scaling.return_value = {"policies": []}
            mock_aws.return_value = {}

            result = aws_health_check()

        assert result["status"] == "critical"
        assert result["critical_count"] >= 1

    def test_active_alarm_causes_degraded(self):
        """Active CloudWatch alarm produces degraded status."""
        with patch("src.agents.aws_agent.ecs_status") as mock_ecs, \
             patch("src.agents.aws_agent.cloudwatch_get_alarms") as mock_alarms, \
             patch("src.agents.aws_agent.cloudwatch_get_vps_metrics") as mock_metrics, \
             patch("src.agents.aws_agent.s3_bucket_stats") as mock_s3, \
             patch("src.agents.aws_agent.ecs_describe_scaling") as mock_scaling, \
             patch("src.agents.aws_agent._aws") as mock_aws:

            mock_ecs.return_value = {"services": [
                {"name": "workshop-service", "desired": 1, "running": 1},
            ]}
            mock_alarms.return_value = {"count": 2, "alarms": [
                {"name": "vps-cpu-high", "state": "ALARM"},
                {"name": "vps-cpu-low", "state": "OK"},
            ]}
            mock_metrics.return_value = {
                "cpu_usage_user": {"average": 92.0, "datapoints": 5},
                "mem_used_percent": {"average": 60.0, "datapoints": 5},
            }
            mock_s3.return_value = {"total_size_gb": 200.0, "object_count": 10000}
            mock_scaling.return_value = {"policies": [{"name": "p1"}]}
            mock_aws.return_value = {}

            result = aws_health_check()

        assert result["status"] == "degraded"
        alarm_check = next(c for c in result["checks"] if c["name"] == "cloudwatch_alarms")
        assert alarm_check["status"] == "degraded"
        assert "vps-cpu-high" in alarm_check["detail"]["active"]

    def test_health_check_result_schema(self):
        """Health check result contains all required fields."""
        with patch("src.agents.aws_agent.ecs_status", return_value={"services": []}), \
             patch("src.agents.aws_agent.cloudwatch_get_alarms", return_value={"count": 0, "alarms": []}), \
             patch("src.agents.aws_agent.cloudwatch_get_vps_metrics", return_value={
                 "cpu_usage_user": {"datapoints": 0}, "mem_used_percent": {"datapoints": 0}}), \
             patch("src.agents.aws_agent.s3_bucket_stats", return_value={"total_size_gb": 0, "object_count": 0}), \
             patch("src.agents.aws_agent.ecs_describe_scaling", return_value={"policies": []}), \
             patch("src.agents.aws_agent._aws", return_value={}):

            result = aws_health_check()

        required = ["status", "timestamp", "checks", "healthy_count",
                     "degraded_count", "critical_count", "total_checks"]
        for field in required:
            assert field in result, f"Missing field: {field}"
        assert isinstance(result["checks"], list)
        assert result["total_checks"] == len(result["checks"])

    def test_no_metrics_produces_degraded(self):
        """Missing VPS metrics (no datapoints) produces degraded."""
        with patch("src.agents.aws_agent.ecs_status", return_value={"services": []}), \
             patch("src.agents.aws_agent.cloudwatch_get_alarms", return_value={"count": 0, "alarms": []}), \
             patch("src.agents.aws_agent.cloudwatch_get_vps_metrics") as mock_metrics, \
             patch("src.agents.aws_agent.s3_bucket_stats", return_value={"total_size_gb": 50.0, "object_count": 1000}), \
             patch("src.agents.aws_agent.ecs_describe_scaling", return_value={"policies": []}), \
             patch("src.agents.aws_agent._aws", return_value={}):

            mock_metrics.return_value = {
                "cpu_usage_user": {"average": None, "datapoints": 0},
                "mem_used_percent": {"average": None, "datapoints": 0},
            }

            result = aws_health_check()

        metrics_check = next(c for c in result["checks"] if c["name"] == "cloudwatch_vps_metrics")
        assert metrics_check["status"] == "degraded"


# ============================================================================
# A2A Protocol Registration E2E
# ============================================================================


class TestA2AProtocolRegistration:
    """Verify all infrastructure agents are properly registered."""

    def test_budget_agent_importable(self):
        """Budget agent entry point should be importable."""
        from src.agents.budget_v2 import run_budget_v2
        assert callable(run_budget_v2)

    def test_watcher_agent_importable(self):
        """Watcher agent entry point should be importable."""
        from src.agents.watcher_v2 import run_watcher_v2
        assert callable(run_watcher_v2)

    def test_scaler_agent_importable(self):
        """Scaler agent entry point should be importable."""
        from src.agents.scaler_v2 import run_scaler_v2
        assert callable(run_scaler_v2)

    def test_curator_agent_importable(self):
        """Curator agent entry point should be importable."""
        from src.agents.curator_v2 import run_curator_v2
        assert callable(run_curator_v2)

    def test_aws_health_check_importable(self):
        """AWS health check function should be importable."""
        from src.agents.aws_agent import aws_health_check
        assert callable(aws_health_check)

    def test_agent_wrapper_has_budget_import(self):
        """agent_wrapper.py should contain budget_v2 import."""
        wrapper_path = Path(__file__).resolve().parent.parent / "src" / "a2a" / "agent_wrapper.py"
        content = wrapper_path.read_text(encoding="utf-8")
        assert "from src.agents.budget_v2 import run_budget_v2" in content
        assert '"budget"' in content


# ============================================================================
# Data Migration Tool E2E
# ============================================================================


class TestDataMigrationE2E:
    """Integration tests for the data migration tool."""

    def test_migration_directions_complete(self):
        """All expected migration directions should exist."""
        directions = [d.value for d in MigrationDirection]
        assert "supabase_to_s3" in directions
        assert "s3_to_supabase" in directions
        assert "s3_to_vps" in directions
        assert "vps_to_s3" in directions
        assert "supabase_to_vps" in directions
        assert "vps_to_supabase" in directions
        assert "full_backup" in directions

    def test_migratable_tables_defined(self):
        """All expected tables should be in MIGRATABLE_TABLES."""
        assert len(MIGRATABLE_TABLES) >= 5
        assert "pipeline_runs" in MIGRATABLE_TABLES

    def test_migration_record_creation(self):
        """MigrationRecord should track migration state correctly."""
        record = MigrationRecord(
            migration_id="test-001",
            direction="supabase_to_s3",
            source="supabase",
            target="s3",
            entity_type="pipeline_runs",
            started_at="2026-02-05T00:00:00Z",
        )
        assert record.status == "pending"
        assert record.direction == "supabase_to_s3"
        assert record.entity_type == "pipeline_runs"

    def test_invalid_direction_returns_error(self):
        """Invalid migration direction should return error."""
        result = run_migration({"direction": "invalid_direction", "table": "test"})
        assert result.get("success") is False or "error" in result

    def test_run_migration_missing_params(self):
        """Missing required params should return error."""
        result = run_migration({})
        assert result.get("success") is False or "error" in result


# ============================================================================
# Budget Agent E2E Integration
# ============================================================================


class TestBudgetAgentE2E:
    """Integration tests for budget agent within the full pipeline context."""

    def test_budget_reads_from_pipeline_context(self):
        """Budget agent should function independently of Watcher output."""
        packet = HandoffPacket(event=EventJsonV1(event_id="budget-e2e-001"))
        # No watcher output — budget should still work
        with patch("src.agents.budget_v2.get_month_to_date_cost") as mock_cost, \
             patch("src.agents.budget_v2.get_cost_by_service") as mock_svc, \
             patch("src.agents.budget_v2.get_cost_forecast") as mock_fc, \
             patch("src.agents.budget_v2.get_credits_balance") as mock_cred, \
             patch("src.agents.budget_v2.push_to_datadog"), \
             patch("src.agents.budget_v2.push_to_posthog"):

            mock_cost.return_value = {"total_usd": 200.0, "period_start": "2026-02-01", "period_end": "2026-02-05"}
            mock_svc.return_value = [{"service": "ECS", "cost_usd": 100.0}, {"service": "S3", "cost_usd": 50.0}]
            mock_fc.return_value = {"forecasted_usd": 350.0}
            mock_cred.return_value = {"credits_used_usd": 0.0}

            result = run_budget_v2(packet)

        assert "error" not in result
        assert "cost_data" in result
        assert "evaluation" in result
        assert result["evaluation"]["budget_limit_usd"] == MONTHLY_BUDGET_USD

    def test_budget_over_limit_detected(self):
        """Budget over 100% should produce critical severity."""
        packet = HandoffPacket(event=EventJsonV1(event_id="budget-e2e-002"))
        with patch("src.agents.budget_v2.get_month_to_date_cost") as mock_cost, \
             patch("src.agents.budget_v2.get_cost_by_service") as mock_svc, \
             patch("src.agents.budget_v2.get_cost_forecast") as mock_fc, \
             patch("src.agents.budget_v2.get_credits_balance") as mock_cred, \
             patch("src.agents.budget_v2.push_to_datadog"), \
             patch("src.agents.budget_v2.push_to_posthog"):

            mock_cost.return_value = {"total_usd": 420.0, "period_start": "2026-02-01", "period_end": "2026-02-05"}
            mock_svc.return_value = [{"service": "ECS", "cost_usd": 200.0}, {"service": "S3", "cost_usd": 100.0}, {"service": "EC2", "cost_usd": 120.0}]
            mock_fc.return_value = {"forecasted_usd": 500.0}
            mock_cred.return_value = {"credits_used_usd": 0.0}

            result = run_budget_v2(packet)

        evaluation = result["evaluation"]
        assert evaluation["severity"] == "critical"
        assert evaluation["utilization_pct"] > 100.0
        assert evaluation["action"] == "halt_non_essential"

    def test_budget_datadog_push_called(self):
        """Budget agent should call push_to_datadog when metrics available."""
        packet = HandoffPacket(event=EventJsonV1(event_id="budget-e2e-003"))
        with patch("src.agents.budget_v2.get_month_to_date_cost") as mock_cost, \
             patch("src.agents.budget_v2.get_cost_by_service") as mock_svc, \
             patch("src.agents.budget_v2.get_cost_forecast") as mock_fc, \
             patch("src.agents.budget_v2.get_credits_balance") as mock_cred, \
             patch("src.agents.budget_v2.push_to_datadog") as mock_dd, \
             patch("src.agents.budget_v2.push_to_posthog"):

            mock_cost.return_value = {"total_usd": 100.0, "period_start": "2026-02-01", "period_end": "2026-02-05"}
            mock_svc.return_value = [{"service": "ECS", "cost_usd": 50.0}]
            mock_fc.return_value = {"forecasted_usd": 200.0}
            mock_cred.return_value = {"credits_used_usd": 0.0}

            run_budget_v2(packet)

        mock_dd.assert_called_once()

    def test_budget_aws_error_handled(self):
        """AWS failure should return valid=False, not crash."""
        packet = HandoffPacket(event=EventJsonV1(event_id="budget-e2e-004"))
        with patch("src.agents.budget_v2.get_month_to_date_cost",
                    side_effect=RuntimeError("Cost Explorer unavailable")):

            result = run_budget_v2(packet)

        assert "error" in result
        assert result["evaluation"]["severity"] == "error"


# ============================================================================
# Cross-cutting: Pipeline Packet Integrity
# ============================================================================


class TestPipelinePacketIntegrity:
    """Verify HandoffPacket maintains integrity across 4-agent pipeline."""

    def test_agent_output_ordering(self):
        """Agent outputs should be retrievable in order they were added."""
        packet = HandoffPacket(event=EventJsonV1(event_id="integrity-001"))

        with patch("src.agents.watcher_v2._run_watcher_llm", return_value=None), \
             patch("src.agents.watcher_v2._collect_raw_metrics") as mock_metrics, \
             patch("src.agents.scaler_v2._get_current_service_count", return_value=1), \
             patch("src.agents.curator_v2._get_bucket_stats") as mock_stats, \
             patch("src.agents.budget_v2.get_month_to_date_cost") as mock_cost, \
             patch("src.agents.budget_v2.get_cost_by_service", return_value=[]), \
             patch("src.agents.budget_v2.get_cost_forecast", return_value={"forecasted_usd": 200.0}), \
             patch("src.agents.budget_v2.get_credits_balance", return_value={"credits_used_usd": 0.0}), \
             patch("src.agents.budget_v2.push_to_datadog"), \
             patch("src.agents.budget_v2.push_to_posthog"):

            mock_metrics.return_value = {
                "vps_cpu": 50.0, "vps_memory": 60.0,
                "ecs_services": [], "s3_size_gb": 200.0,
                "alarms": [], "collected_at": 1000000.0,
            }
            mock_stats.return_value = {"total_size_gb": 200.0, "object_count": 10000}
            mock_cost.return_value = {"total_usd": 100.0, "period_start": "2026-02-01", "period_end": "2026-02-05"}

            for agent_fn, name in [
                (run_watcher_v2, "watcher"),
                (run_scaler_v2, "scaler"),
                (run_curator_v2, "curator"),
                (run_budget_v2, "budget"),
            ]:
                result = agent_fn(packet)
                packet.add_output(name, result)

        output_names = list(packet.agent_outputs.keys())
        assert output_names == ["watcher", "scaler", "curator", "budget"]

    def test_scaler_reads_watcher_output(self):
        """Scaler should be able to read Watcher's signals from packet."""
        packet = HandoffPacket(event=EventJsonV1(event_id="integrity-002"))
        packet.add_output("watcher", {
            "event_type": "cpu_spike",
            "severity": "critical",
            "signals": ["cpu_critical", "memory_high"],
            "recommended_action": "scale_up_immediately",
            "metrics": {"vps_cpu": 95.0, "vps_memory": 85.0},
        })

        with patch("src.agents.scaler_v2._get_current_service_count", return_value=1):
            result = run_scaler_v2(packet)

        assert result["action"] == "scale_up"

    def test_event_id_preserved(self):
        """Event ID should be preserved through the entire pipeline."""
        event_id = "preserve-test-123"
        packet = HandoffPacket(event=EventJsonV1(event_id=event_id))

        with patch("src.agents.watcher_v2._run_watcher_llm", return_value=None), \
             patch("src.agents.watcher_v2._collect_raw_metrics") as mock_m:
            mock_m.return_value = {
                "vps_cpu": 50.0, "vps_memory": 60.0,
                "ecs_services": [], "s3_size_gb": 200.0,
                "alarms": [], "collected_at": 1000000.0,
            }
            run_watcher_v2(packet)

        assert packet.event.event_id == event_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
