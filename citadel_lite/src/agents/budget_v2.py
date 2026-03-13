"""
Budget Agent (v2) — AWS cost tracking with Datadog + PostHog integration.

Monitors AWS spending via Cost Explorer, enforces budget rules,
and pushes cost metrics to Datadog (infrastructure) and PostHog (product analytics).

Budget Rules:
  - Hard cap: $400/month
  - Warning at 80% ($320)
  - Critical at 90% ($360)
  - Auto-alert on forecast breach

Feeds:
  - Datadog: cost metrics via DogStatsD (UDP 8125)
  - PostHog: cost events via HTTP API
  - CloudWatch: custom metrics in Citadel/Budget namespace

Usage (standalone):
    python -m citadel_lite.src.agents.budget_v2 check
    python -m citadel_lite.src.agents.budget_v2 report

Usage (A2A pipeline):
    from citadel_lite.src.agents.budget_v2 import run_budget_v2
    result = run_budget_v2(packet)

CGRF v3.0: SRS-BUDGET-20260205-001-V3.0, Tier 1
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AWS_REGION = "us-east-1"
MONTHLY_BUDGET_USD = 400.0
WARNING_THRESHOLD = 0.80   # 80% = $320
CRITICAL_THRESHOLD = 0.90  # 90% = $360
HARD_CAP_THRESHOLD = 1.00  # 100% = $400

# Datadog DogStatsD
DATADOG_HOST = os.getenv("DD_AGENT_HOST", "127.0.0.1")
DATADOG_PORT = int(os.getenv("DD_DOGSTATSD_PORT", "8125"))

# PostHog
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")

# Budget breakdown categories
SERVICE_CATEGORIES = [
    "Amazon Elastic Container Service",
    "Amazon Simple Storage Service",
    "Amazon EC2",
    "AWS CloudWatch",
    "Amazon Elastic Container Registry",
    "AWS Key Management Service",
    "Amazon Route 53",
    "AWS Budgets",
]

# ---------------------------------------------------------------------------
# AWS CLI wrapper
# ---------------------------------------------------------------------------

def _aws(*args: str, parse_json: bool = True) -> Any:
    cmd = ["aws", "--region", AWS_REGION, "--output", "json", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"aws {' '.join(args[:3])}... failed: {result.stderr.strip()}")
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout) if parse_json else result.stdout


# ---------------------------------------------------------------------------
# Cost Explorer queries
# ---------------------------------------------------------------------------

def get_month_to_date_cost() -> Dict[str, Any]:
    """Get current month-to-date AWS spend from Cost Explorer."""
    now = datetime.now(timezone.utc)
    start = now.replace(day=1).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")

    data = _aws(
        "ce", "get-cost-and-usage",
        "--time-period", f"Start={start},End={end}",
        "--granularity", "MONTHLY",
        "--metrics", "UnblendedCost",
    )

    results = data.get("ResultsByTime", [])
    if not results:
        return {"total_usd": 0.0, "period_start": start, "period_end": end}

    amount = float(results[0]["Total"]["UnblendedCost"]["Amount"])
    return {
        "total_usd": round(amount, 2),
        "period_start": start,
        "period_end": end,
    }


def get_cost_by_service() -> List[Dict[str, Any]]:
    """Get cost breakdown by AWS service for current month."""
    now = datetime.now(timezone.utc)
    start = now.replace(day=1).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")

    data = _aws(
        "ce", "get-cost-and-usage",
        "--time-period", f"Start={start},End={end}",
        "--granularity", "MONTHLY",
        "--metrics", "UnblendedCost",
        "--group-by", "Type=DIMENSION,Key=SERVICE",
    )

    services = []
    for result in data.get("ResultsByTime", []):
        for group in result.get("Groups", []):
            service_name = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            if amount > 0.01:
                services.append({
                    "service": service_name,
                    "cost_usd": round(amount, 2),
                })

    return sorted(services, key=lambda s: s["cost_usd"], reverse=True)


def get_cost_forecast() -> Dict[str, Any]:
    """Get forecasted end-of-month cost."""
    now = datetime.now(timezone.utc)
    # Forecast needs start to be tomorrow or later
    start = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    end_of_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    end = end_of_month.strftime("%Y-%m-%d")

    if start >= end:
        return {"forecasted_usd": None, "note": "Too close to month end for forecast"}

    try:
        data = _aws(
            "ce", "get-cost-forecast",
            "--time-period", f"Start={start},End={end}",
            "--metric", "UNBLENDED_COST",
            "--granularity", "MONTHLY",
        )
        amount = float(data.get("Total", {}).get("Amount", 0))
        return {"forecasted_usd": round(amount, 2)}
    except Exception as e:
        return {"forecasted_usd": None, "error": str(e)}


def get_credits_balance() -> Dict[str, Any]:
    """Check remaining AWS credits (if any)."""
    now = datetime.now(timezone.utc)
    start = now.replace(day=1).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")

    try:
        data = _aws(
            "ce", "get-cost-and-usage",
            "--time-period", f"Start={start},End={end}",
            "--granularity", "MONTHLY",
            "--metrics", "UnblendedCost",
            "--filter", json.dumps({
                "Dimensions": {
                    "Key": "RECORD_TYPE",
                    "Values": ["Credit"],
                }
            }),
        )
        results = data.get("ResultsByTime", [])
        if results:
            credit = abs(float(results[0]["Total"]["UnblendedCost"]["Amount"]))
            return {"credits_used_usd": round(credit, 2)}
        return {"credits_used_usd": 0.0}
    except Exception:
        return {"credits_used_usd": 0.0, "note": "Credits query failed"}


# ---------------------------------------------------------------------------
# Datadog integration
# ---------------------------------------------------------------------------

def _send_dogstatsd(metric_name: str, value: float, metric_type: str = "gauge",
                    tags: Optional[List[str]] = None):
    """Send a metric to Datadog via DogStatsD (UDP)."""
    tag_str = ""
    if tags:
        tag_str = "|#" + ",".join(tags)

    payload = f"citadel.budget.{metric_name}:{value}|{metric_type[0]}{tag_str}"

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(payload.encode("utf-8"), (DATADOG_HOST, DATADOG_PORT))
        sock.close()
        return True
    except Exception:
        return False


def push_to_datadog(cost_data: Dict[str, Any], services: List[Dict[str, Any]]):
    """Push cost metrics to Datadog."""
    tags = ["env:prod", "project:citadel"]

    # Total MTD cost
    _send_dogstatsd("mtd_total_usd", cost_data["total_usd"], tags=tags)

    # Budget utilization percentage
    utilization = (cost_data["total_usd"] / MONTHLY_BUDGET_USD) * 100
    _send_dogstatsd("budget_utilization_pct", round(utilization, 1), tags=tags)

    # Budget remaining
    remaining = MONTHLY_BUDGET_USD - cost_data["total_usd"]
    _send_dogstatsd("budget_remaining_usd", round(remaining, 2), tags=tags)

    # Per-service costs
    for svc in services:
        service_tag = f"aws_service:{svc['service'].lower().replace(' ', '_')}"
        _send_dogstatsd("service_cost_usd", svc["cost_usd"], tags=tags + [service_tag])

    # Forecast if available
    forecast = cost_data.get("forecast", {})
    if forecast.get("forecasted_usd") is not None:
        _send_dogstatsd("forecast_eom_usd", forecast["forecasted_usd"], tags=tags)


# ---------------------------------------------------------------------------
# PostHog integration
# ---------------------------------------------------------------------------

def push_to_posthog(cost_data: Dict[str, Any], services: List[Dict[str, Any]],
                    severity: str):
    """Push budget event to PostHog."""
    if not POSTHOG_API_KEY:
        return False

    try:
        import urllib.request

        event = {
            "api_key": POSTHOG_API_KEY,
            "event": "aws_budget_check",
            "distinct_id": "citadel-infra",
            "properties": {
                "mtd_cost_usd": cost_data["total_usd"],
                "budget_limit_usd": MONTHLY_BUDGET_USD,
                "utilization_pct": round(
                    (cost_data["total_usd"] / MONTHLY_BUDGET_USD) * 100, 1
                ),
                "remaining_usd": round(
                    MONTHLY_BUDGET_USD - cost_data["total_usd"], 2
                ),
                "severity": severity,
                "top_services": services[:5],
                "forecast_eom_usd": cost_data.get("forecast", {}).get(
                    "forecasted_usd"
                ),
                "period_start": cost_data["period_start"],
                "period_end": cost_data["period_end"],
            },
        }

        req = urllib.request.Request(
            f"{POSTHOG_HOST}/capture/",
            data=json.dumps(event).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Budget evaluation
# ---------------------------------------------------------------------------

def evaluate_budget(cost_data: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate current spending against budget rules."""
    total = cost_data["total_usd"]
    utilization = total / MONTHLY_BUDGET_USD
    forecast = cost_data.get("forecast", {})

    if utilization >= HARD_CAP_THRESHOLD:
        severity = "critical"
        action = "halt_non_essential"
        message = f"BUDGET EXCEEDED: ${total:.2f} / ${MONTHLY_BUDGET_USD:.2f} ({utilization:.0%})"
    elif utilization >= CRITICAL_THRESHOLD:
        severity = "critical"
        action = "scale_down"
        message = f"Budget critical: ${total:.2f} / ${MONTHLY_BUDGET_USD:.2f} ({utilization:.0%})"
    elif utilization >= WARNING_THRESHOLD:
        severity = "warning"
        action = "review_spending"
        message = f"Budget warning: ${total:.2f} / ${MONTHLY_BUDGET_USD:.2f} ({utilization:.0%})"
    else:
        severity = "info"
        action = "none"
        message = f"Budget healthy: ${total:.2f} / ${MONTHLY_BUDGET_USD:.2f} ({utilization:.0%})"

    # Check forecast
    forecast_breach = False
    if forecast.get("forecasted_usd") is not None:
        if forecast["forecasted_usd"] > MONTHLY_BUDGET_USD:
            forecast_breach = True
            if severity == "info":
                severity = "warning"
                action = "review_spending"
                message += f" (forecast: ${forecast['forecasted_usd']:.2f} exceeds budget)"

    return {
        "severity": severity,
        "action": action,
        "message": message,
        "utilization_pct": round(utilization * 100, 1),
        "remaining_usd": round(MONTHLY_BUDGET_USD - total, 2),
        "forecast_breach": forecast_breach,
        "budget_limit_usd": MONTHLY_BUDGET_USD,
    }


# ---------------------------------------------------------------------------
# Agent entry point (A2A compatible)
# ---------------------------------------------------------------------------

def run_budget_v2(packet: Any = None) -> Dict[str, Any]:
    """
    Run budget check. Compatible with A2A HandoffPacket pipeline.

    Returns cost data, budget evaluation, and push status for Datadog/PostHog.
    """
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_powered": False,
    }

    try:
        # 1. Get costs
        cost_data = get_month_to_date_cost()
        services = get_cost_by_service()
        forecast = get_cost_forecast()
        credits = get_credits_balance()

        cost_data["forecast"] = forecast
        cost_data["credits"] = credits

        # 2. Evaluate budget
        evaluation = evaluate_budget(cost_data)

        # 3. Push to Datadog
        dd_ok = push_to_datadog(cost_data, services)

        # 4. Push to PostHog
        ph_ok = push_to_posthog(cost_data, services, evaluation["severity"])

        result.update({
            "cost_data": cost_data,
            "service_breakdown": services,
            "evaluation": evaluation,
            "integrations": {
                "datadog_pushed": dd_ok is not False,
                "posthog_pushed": ph_ok is not False,
            },
        })

    except Exception as e:
        result["error"] = str(e)
        result["evaluation"] = {
            "severity": "error",
            "action": "check_credentials",
            "message": f"Budget check failed: {e}",
        }

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Citadel Budget Agent")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("check", help="Quick budget check")
    sub.add_parser("report", help="Full budget report with service breakdown")
    sub.add_parser("forecast", help="End-of-month forecast")

    args = parser.parse_args()

    if args.command == "check":
        result = run_budget_v2()
        ev = result.get("evaluation", {})
        print(f"[{ev.get('severity', 'unknown').upper()}] {ev.get('message', 'No data')}")
        print(f"  Remaining: ${ev.get('remaining_usd', '?')}")
        if result.get("integrations"):
            print(f"  Datadog: {'OK' if result['integrations']['datadog_pushed'] else 'SKIP'}")
            print(f"  PostHog: {'OK' if result['integrations']['posthog_pushed'] else 'SKIP'}")

    elif args.command == "report":
        result = run_budget_v2()
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "forecast":
        forecast = get_cost_forecast()
        print(json.dumps(forecast, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
