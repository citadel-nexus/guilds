# src/ingest/normalizer.py
"""
Normalizes raw webhook payloads from various sources into EventJsonV1.

Supported sources:
- github_actions: GitHub Actions webhook (workflow_run event)
- azure_alert: Azure Monitor alert webhook
- manual: Pre-formatted EventJsonV1 passthrough

Reference: CNWB src/runtime/orchestrator.py EventNormalizer pattern.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from src.types import EventJsonV1, EventArtifact


def normalize(raw: Dict[str, Any], source: str = "auto") -> EventJsonV1:
    """Dispatch to the appropriate normalizer based on source."""
    if source == "auto":
        source = _detect_source(raw)

    normalizers = {
        "github_actions": normalize_github_actions,
        "azure_alert": normalize_azure_alert,
        "manual": normalize_manual,
    }
    fn = normalizers.get(source, normalize_manual)
    return fn(raw)


def _detect_source(raw: Dict[str, Any]) -> str:
    """Auto-detect source from payload shape."""
    if "workflow_run" in raw or "action" in raw and "repository" in raw:
        return "github_actions"
    if "data" in raw and "essentials" in raw.get("data", {}):
        return "azure_alert"
    if "schema_version" in raw and raw.get("schema_version") == "event_json_v1":
        return "manual"
    return "manual"


def normalize_github_actions(raw: Dict[str, Any]) -> EventJsonV1:
    """Convert a GitHub Actions workflow_run webhook payload to EventJsonV1."""
    workflow_run = raw.get("workflow_run", {})
    repo_info = raw.get("repository", {})

    conclusion = workflow_run.get("conclusion", "unknown")
    event_type = "ci_failed" if conclusion == "failure" else f"ci_{conclusion}"

    logs_url = workflow_run.get("logs_url", "")
    html_url = workflow_run.get("html_url", "")

    return EventJsonV1(
        schema_version="event_json_v1",
        event_id=f"gh-{workflow_run.get('id', uuid.uuid4().hex[:8])}",
        event_type=event_type,
        source="github_actions",
        occurred_at=workflow_run.get("updated_at", datetime.now(timezone.utc).isoformat()),
        repo=repo_info.get("full_name"),
        ref=workflow_run.get("head_branch"),
        summary=f"{workflow_run.get('name', 'CI')} {conclusion} on {workflow_run.get('head_branch', 'unknown')}",
        artifacts=EventArtifact(
            log_excerpt=workflow_run.get("conclusion", ""),
            links=[url for url in [html_url, logs_url] if url],
        ),
    )


def normalize_azure_alert(raw: Dict[str, Any]) -> EventJsonV1:
    """Convert an Azure Monitor alert webhook payload to EventJsonV1."""
    data = raw.get("data", {})
    essentials = data.get("essentials", {})

    severity_map = {"Sev0": "critical", "Sev1": "high", "Sev2": "medium", "Sev3": "low", "Sev4": "info"}
    severity = essentials.get("severity", "Sev3")

    return EventJsonV1(
        schema_version="event_json_v1",
        event_id=f"az-{essentials.get('alertId', uuid.uuid4().hex[:8])}",
        event_type="azure_alert",
        source="azure_monitor",
        occurred_at=essentials.get("firedDateTime", datetime.now(timezone.utc).isoformat()),
        repo=None,
        ref=None,
        summary=essentials.get("description", essentials.get("alertRule", "Azure alert")),
        artifacts=EventArtifact(
            log_excerpt=f"Severity: {severity_map.get(severity, severity)}. {essentials.get('description', '')}",
            links=[essentials.get("alertTargetIDs", [""])[0]] if essentials.get("alertTargetIDs") else [],
            extra={"severity": severity, "monitorCondition": essentials.get("monitorCondition")},
        ),
    )


def normalize_manual(raw: Dict[str, Any]) -> EventJsonV1:
    """Passthrough for pre-formatted EventJsonV1 payloads."""
    artifacts = raw.get("artifacts", {}) or {}
    return EventJsonV1(
        schema_version=raw.get("schema_version", "event_json_v1"),
        event_id=raw.get("event_id") or str(uuid.uuid4()),
        event_type=raw.get("event_type", ""),
        source=raw.get("source", "manual"),
        occurred_at=raw.get("occurred_at", datetime.now(timezone.utc).isoformat()),
        repo=raw.get("repo"),
        ref=raw.get("ref"),
        summary=raw.get("summary"),
        artifacts=EventArtifact(
            log_excerpt=artifacts.get("log_excerpt"),
            links=artifacts.get("links", []),
            extra=artifacts.get("extra", {}),
        ),
    )
