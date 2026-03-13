# citadel_lite/tests/test_budget_agent.py
"""
Tests for Budget Agent v2 — AWS cost tracking with Datadog + PostHog.

Verifies:
- Budget evaluation logic (thresholds, severity)
- Cost data aggregation
- Datadog/PostHog push formatting
- Agent entry point routing
- CLI argument handling

CGRF v3.0: SRS-TEST-BUDGET-001, Tier 1
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest

CNWB_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(CNWB_ROOT / "citadel_lite"))

from src.agents.budget_v2 import (
    MONTHLY_BUDGET_USD,
    WARNING_THRESHOLD,
    CRITICAL_THRESHOLD,
    HARD_CAP_THRESHOLD,
    evaluate_budget,
    run_budget_v2,
    push_to_datadog,
    push_to_posthog,
    _send_dogstatsd,
)


# ============================================================================
# Budget evaluation tests
# ============================================================================

class TestBudgetEvaluation:
    """Tests for budget rule evaluation."""

    def test_healthy_budget(self):
        cost = {"total_usd": 100.0, "period_start": "2026-02-01", "period_end": "2026-02-05"}
        result = evaluate_budget(cost)
        assert result["severity"] == "info"
        assert result["action"] == "none"
        assert result["remaining_usd"] == 300.0
        assert result["utilization_pct"] == 25.0

    def test_warning_at_80_pct(self):
        cost = {"total_usd": 325.0, "period_start": "2026-02-01", "period_end": "2026-02-15"}
        result = evaluate_budget(cost)
        assert result["severity"] == "warning"
        assert result["action"] == "review_spending"

    def test_critical_at_90_pct(self):
        cost = {"total_usd": 365.0, "period_start": "2026-02-01", "period_end": "2026-02-20"}
        result = evaluate_budget(cost)
        assert result["severity"] == "critical"
        assert result["action"] == "scale_down"

    def test_hard_cap_at_100_pct(self):
        cost = {"total_usd": 410.0, "period_start": "2026-02-01", "period_end": "2026-02-25"}
        result = evaluate_budget(cost)
        assert result["severity"] == "critical"
        assert result["action"] == "halt_non_essential"
        assert "EXCEEDED" in result["message"]

    def test_zero_cost(self):
        cost = {"total_usd": 0.0, "period_start": "2026-02-01", "period_end": "2026-02-01"}
        result = evaluate_budget(cost)
        assert result["severity"] == "info"
        assert result["remaining_usd"] == 400.0
        assert result["utilization_pct"] == 0.0

    def test_forecast_breach_upgrades_severity(self):
        cost = {
            "total_usd": 200.0,
            "period_start": "2026-02-01",
            "period_end": "2026-02-15",
            "forecast": {"forecasted_usd": 500.0},
        }
        result = evaluate_budget(cost)
        assert result["severity"] == "warning"
        assert result["forecast_breach"] is True
        assert "forecast" in result["message"]

    def test_forecast_no_breach(self):
        cost = {
            "total_usd": 100.0,
            "period_start": "2026-02-01",
            "period_end": "2026-02-10",
            "forecast": {"forecasted_usd": 300.0},
        }
        result = evaluate_budget(cost)
        assert result["forecast_breach"] is False

    def test_budget_limit_in_result(self):
        cost = {"total_usd": 50.0, "period_start": "2026-02-01", "period_end": "2026-02-05"}
        result = evaluate_budget(cost)
        assert result["budget_limit_usd"] == 400.0

    def test_exact_thresholds(self):
        # Exactly at 80%
        cost_80 = {"total_usd": 320.0, "period_start": "2026-02-01", "period_end": "2026-02-15"}
        assert evaluate_budget(cost_80)["severity"] == "warning"

        # Exactly at 90%
        cost_90 = {"total_usd": 360.0, "period_start": "2026-02-01", "period_end": "2026-02-20"}
        assert evaluate_budget(cost_90)["severity"] == "critical"

        # Exactly at 100%
        cost_100 = {"total_usd": 400.0, "period_start": "2026-02-01", "period_end": "2026-02-28"}
        assert evaluate_budget(cost_100)["severity"] == "critical"
        assert evaluate_budget(cost_100)["action"] == "halt_non_essential"


# ============================================================================
# Constants tests
# ============================================================================

class TestConstants:
    """Tests for budget constants."""

    def test_budget_limit(self):
        assert MONTHLY_BUDGET_USD == 400.0

    def test_threshold_ordering(self):
        assert WARNING_THRESHOLD < CRITICAL_THRESHOLD < HARD_CAP_THRESHOLD

    def test_thresholds_are_fractions(self):
        assert 0 < WARNING_THRESHOLD < 1
        assert 0 < CRITICAL_THRESHOLD < 1
        assert HARD_CAP_THRESHOLD == 1.0


# ============================================================================
# Datadog integration tests
# ============================================================================

class TestDatadogPush:
    """Tests for Datadog DogStatsD metric formatting."""

    @patch("src.agents.budget_v2._send_dogstatsd")
    def test_push_mtd_total(self, mock_send):
        mock_send.return_value = True
        cost = {"total_usd": 150.0, "period_start": "2026-02-01", "period_end": "2026-02-10"}
        services = [{"service": "Amazon EC2", "cost_usd": 80.0}]
        push_to_datadog(cost, services)

        # Should have been called for total, utilization, remaining, + per-service
        assert mock_send.call_count >= 4

    @patch("socket.socket")
    def test_dogstatsd_format(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        _send_dogstatsd("test_metric", 42.5, tags=["env:prod"])

        mock_sock.sendto.assert_called_once()
        payload = mock_sock.sendto.call_args[0][0].decode()
        assert "citadel.budget.test_metric:42.5|g" in payload
        assert "#env:prod" in payload


# ============================================================================
# PostHog integration tests
# ============================================================================

class TestPostHogPush:
    """Tests for PostHog event push."""

    def test_no_api_key_skips(self):
        with patch("src.agents.budget_v2.POSTHOG_API_KEY", ""):
            result = push_to_posthog(
                {"total_usd": 100.0, "period_start": "2026-02-01", "period_end": "2026-02-05"},
                [],
                "info",
            )
            assert result is False

    @patch("src.agents.budget_v2.POSTHOG_API_KEY", "phc_test_key_123")
    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_posthog_event_sent(self, mock_req_cls, mock_urlopen):
        cost = {"total_usd": 200.0, "period_start": "2026-02-01", "period_end": "2026-02-15"}
        services = [{"service": "S3", "cost_usd": 50.0}]

        result = push_to_posthog(cost, services, "warning")
        assert result is True
        mock_req_cls.assert_called_once()


# ============================================================================
# Agent entry point tests
# ============================================================================

class TestRunBudgetV2:
    """Tests for the agent entry point."""

    @patch("src.agents.budget_v2.push_to_posthog")
    @patch("src.agents.budget_v2.push_to_datadog")
    @patch("src.agents.budget_v2.get_credits_balance")
    @patch("src.agents.budget_v2.get_cost_forecast")
    @patch("src.agents.budget_v2.get_cost_by_service")
    @patch("src.agents.budget_v2.get_month_to_date_cost")
    def test_full_pipeline(self, mock_mtd, mock_svc, mock_forecast, mock_credits,
                           mock_dd, mock_ph):
        mock_mtd.return_value = {
            "total_usd": 150.0,
            "period_start": "2026-02-01",
            "period_end": "2026-02-05",
        }
        mock_svc.return_value = [
            {"service": "Amazon EC2", "cost_usd": 80.0},
            {"service": "Amazon S3", "cost_usd": 30.0},
        ]
        mock_forecast.return_value = {"forecasted_usd": 350.0}
        mock_credits.return_value = {"credits_used_usd": 0.0}

        result = run_budget_v2()

        assert result["cost_data"]["total_usd"] == 150.0
        assert result["evaluation"]["severity"] == "info"
        assert len(result["service_breakdown"]) == 2
        mock_dd.assert_called_once()
        mock_ph.assert_called_once()

    @patch("src.agents.budget_v2.get_month_to_date_cost")
    def test_handles_aws_error(self, mock_mtd):
        mock_mtd.side_effect = RuntimeError("No credentials")

        result = run_budget_v2()
        assert result["evaluation"]["severity"] == "error"
        assert "check_credentials" in result["evaluation"]["action"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
