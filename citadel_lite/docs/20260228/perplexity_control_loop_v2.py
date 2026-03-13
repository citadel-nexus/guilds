#!/usr/bin/env python3
"""
perplexity_control_loop_v2.py — Live Telemetry
=================================================
READ:  Datadog + PostHog + Supabase + Notion + GitLab + Stripe + Metabase
RAG:   Cycle history retrieval (SQLite FTS5, SAKE pattern) — before/after data from past cycles
THINK: 3-layer — Bedrock Claude Haiku (root-cause) → Azure OpenAI GPT-4o → Bedrock Claude Opus (cross-check)
WRITE: Notion diagnostic page + tracker callout patch + Supabase audit log + Linear issues + GitLab issues/MR comments

Usage:
    python tools/perplexity_control_loop_v2.py
    python tools/perplexity_control_loop_v2.py --dry-run
    python tools/perplexity_control_loop_v2.py --json-out out.json
    python tools/perplexity_control_loop_v2.py --dd-window 6 --ph-window 14
    python tools/perplexity_control_loop_v2.py --model sonar-pro

Env var names (from workspace.env):
    NOTION_TOKEN                — Notion integration token
    # PERPLEXITY_API_KEY          — Perplexity API key (no longer required; Bedrock Haiku is default for L1)
    DD_API_KEY                  — Datadog API key
    DD_APP_KEY                  — Datadog application key (required for queries)
    DD_SITE                     — Datadog site (e.g. us5.datadoghq.com)
    POSTHOG_API_KEY             — PostHog personal API key
    POSTHOG_PROJECT_ID          — PostHog project ID
    POSTHOG_HOST                — PostHog host URL
    SUPABASE_URL                — Supabase project URL
    SUPABASE_SERVICE_KEY        — Supabase service role key
    EVO_TRACKER_PAGE_ID         — Notion EVO Tracker page ID
    EVO_CYCLE_HISTORY_DB_ID     — Notion EVO Cycle History DB (optional, has default)
    CITADEL_TASKS_DB_ID         — Notion open tasks DB (optional, falls back to NOTION_TASKS_DATABASE_ID)
    LINEAR_API_TOKEN            — Linear API token
    LINEAR_TEAM_ID              — Linear team ID for CNWB
    LINEAR_CNWB_PROJECT_ID      — Linear project ID for CNWB Upgrades
    GITLAB_TOKEN                — GitLab personal/project access token (api scope)
    GITLAB_URL                  — https://gitlab.citadel-nexus.com
    GITLAB_PROJECT_ID           — Numeric project ID (75)
    STRIPE_SECRET_KEY           — Stripe live secret key (sk_live_*)
    METABASE_API_KEY            — Metabase API key (for /api/* access)
    METABASE_SITE_URL           — https://metabase.citadel-nexus.com (optional, has default)
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

# ── Env ─────────────────────────────────────────────────────────────────────
import sys as _sys; _sys.path.insert(0, str(Path(__file__).parent))
from vault_loader import bootstrap as _vault_bootstrap; _vault_bootstrap()

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("control_loop_v2")

# ── Gap-fill imports (G2–G5) ────────────────────────────────────────────────
try:
    from analytics_retry import retry_with_backoff, dd_submit_with_retry, ph_capture_with_retry
    HAS_ANALYTICS_RETRY = True
except ImportError:
    HAS_ANALYTICS_RETRY = False
    log.debug("analytics_retry not available — using single-shot submission")

try:
    from ph_event_schemas import (
        think_cycle_complete,
        codegen_cycle_complete,
    )
    HAS_PH_SCHEMAS = True
except ImportError:
    HAS_PH_SCHEMAS = False
    log.debug("ph_event_schemas not available — using inline properties")

try:
    from nats_publisher import AegisNATSPublisher
    HAS_NATS_PUB = True
except ImportError:
    HAS_NATS_PUB = False
    log.debug("nats_publisher not available — NATS publishing disabled")

try:
    from supabase_persistence import AegisCycleStore
    HAS_SB_PERSIST = True
except ImportError:
    HAS_SB_PERSIST = False
    log.debug("supabase_persistence not available — cycle history disabled")

# Blueprint Drift Scanner (Reflex 7)
try:
    from blueprint_drift.scanner import run_blueprint_drift_scan, drift_report_summary
    HAS_BLUEPRINT_DRIFT = True
except ImportError:
    HAS_BLUEPRINT_DRIFT = False
    log.debug("blueprint_drift not available — drift scanning disabled")

# Sentinel ElevenLabs integration
try:
    from sentinel_integration import (
        sentinel_pre_call, read_elevenlabs_telemetry, compute_sentinel_l0_flags,
    )
    HAS_SENTINEL = True
except ImportError:
    HAS_SENTINEL = False
    log.debug("sentinel_integration not available — Sentinel DVs disabled")

# ── Per-run API failure accumulator ──────────────────────────────────────────
# _api_get/_api_post append here on permanent HTTP failures (401/403/404).
# run() flushes these into _errors → they get logged to Supabase + Linear.
_run_api_errors: list[dict] = []


def _record_failure(label: str, status: int, detail: str) -> None:
    """Record a permanent API failure for end-of-run reporting."""
    _run_api_errors.append({
        "phase": f"API/{label}",
        "type": f"HTTP{status}",
        "detail": detail[:400],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    log.warning(f"[FAILURE] {label} → HTTP {status} (queued for Linear)")


# Cycle RAG — SQLite FTS5 store for before/after cycle data (SAKE pattern)
try:
    from cycle_rag import CycleRAGStore
    _cycle_rag = CycleRAGStore()
    HAS_CYCLE_RAG = True
    log.debug(f"cycle_rag: loaded ({_cycle_rag.count()} stored cycles)")
except Exception as _rag_err:
    _cycle_rag = None
    HAS_CYCLE_RAG = False
    log.debug(f"cycle_rag unavailable: {_rag_err}")

# GitLab module — imported lazily so missing file doesn't break the loop
try:
    from gitlab_source import read_gitlab, write_gitlab as _write_gitlab
    HAS_GITLAB_MODULE = True
except ImportError:
    HAS_GITLAB_MODULE = False
    log.debug("gitlab_source.py not found — GitLab source disabled")

# ── Config ──────────────────────────────────────────────────────────────────
NOTION_API  = "https://api.notion.com/v1"
NOTION_VER  = "2022-06-28"
PPLX_API    = "https://api.perplexity.ai/chat/completions"
PPLX_MODEL  = os.getenv("PPLX_MODEL", "sonar-pro")

_DD_SITE    = os.getenv("DD_SITE", "datadoghq.com")
DD_API_BASE = f"https://api.{_DD_SITE}/api"

PH_HOST     = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
SB_URL      = os.getenv("SUPABASE_URL", "")

EVO_TRACKER_PAGE    = os.getenv("EVO_TRACKER_PAGE_ID", "ad11e93e-eb47-49f7-bc4f-97c471b24837")
EVO_CALLOUT_ID      = "a84bf6c2-cbd9-438c-a6bb-110e787e0786"
CYCLE_DB            = os.getenv("EVO_CYCLE_HISTORY_DB_ID", "791d5abb-b7e8-4e33-912f-5c53155bca0f")
TASKS_DB            = os.getenv("CITADEL_TASKS_DB_ID", os.getenv("NOTION_TASKS_DATABASE_ID", ""))
DIAG_PARENT         = os.getenv("DIAGNOSTICS_PARENT_PAGE_ID", EVO_TRACKER_PAGE)
LEADS_DB            = os.getenv("NOTION_LEADS_DB_ID", "")

STRIPE_API          = "https://api.stripe.com/v1"
METABASE_URL        = os.getenv("METABASE_SITE_URL", "https://metabase.citadel-nexus.com")

LINEAR_TOKEN      = os.getenv("LINEAR_API_TOKEN", "")
LINEAR_TEAM_ID    = os.getenv("LINEAR_TEAM_ID", "9530222c-668c-4e1a-98e7-2351fa26564d")
LINEAR_PROJECT_ID = os.getenv("LINEAR_CNWB_PROJECT_ID", "5f8ef928-c33b-4a5e-ba79-350f6fea05d7")

# Azure OpenAI (GPT-4o primary THINK layer)
AZURE_OPENAI_KEY        = os.getenv("AZURE_OPENAI_KEY", "") or os.getenv("AZURE_FOUNDRY_KEY", "")
AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "") or os.getenv("AZURE_FOUNDRY_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
_USE_AZURE = bool(AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT)

# Bedrock (Claude Opus cross-check / fallback THINK layer)
# Force us-west-2 for Bedrock — workspace.env AWS_REGION may be us-east-1 (for other services)
AWS_REGION     = os.getenv("BEDROCK_REGION", "us-west-2")
BEDROCK_MODEL  = os.getenv("BEDROCK_MODEL", "us.anthropic.claude-opus-4-5-20251101-v1:0")
BEDROCK_HAIKU  = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# ── Auth headers ─────────────────────────────────────────────────────────────

def _notion_h() -> dict:
    token = os.getenv("NOTION_TOKEN", os.getenv("NOTION_INTERNAL_TOKEN", ""))
    return {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VER,
            "Content-Type": "application/json"}


def _dd_h() -> dict:
    return {"DD-API-KEY": os.getenv("DD_API_KEY", os.getenv("DATADOG_API_KEY", "")),
            "DD-APPLICATION-KEY": os.getenv("DD_APP_KEY", os.getenv("DATADOG_APP_KEY", "")),
            "Content-Type": "application/json"}


def _ph_h() -> dict:
    # POSTHOG_PERSONAL_API_KEY (phx_*) is required for query API.
    # POSTHOG_API_KEY (phc_*) is a capture/ingestion key only and returns 403 on queries.
    key = os.getenv("POSTHOG_PERSONAL_API_KEY") or os.getenv("POSTHOG_API_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _sb_h() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "Prefer": "return=representation"}


def _linear_h() -> dict:
    return {"Authorization": LINEAR_TOKEN, "Content-Type": "application/json"}


# ── API helpers ──────────────────────────────────────────────────────────────

def _api_get(url: str, headers: dict, params: dict | None = None, label: str = "") -> dict | list | None:
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code in (401, 403, 404):
            _record_failure(label, r.status_code, r.text[:300])
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.warning(f"[{label}] GET failed: {exc}")
        return None


def _api_post(url: str, headers: dict, payload: dict | None = None, label: str = "") -> dict | None:
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=45)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 2))
                log.info(f"[{label}] Rate limited — waiting {wait}s")
                time.sleep(wait)
                continue
            # Don't retry on permanent client errors
            if r.status_code in (400, 401, 403, 404):
                log.warning(f"[{label}] POST {r.status_code}: {r.text[:200]}")
                if r.status_code in (401, 403, 404):
                    _record_failure(label, r.status_code, r.text[:300])
                return None
            r.raise_for_status()
            return r.json()
        except requests.HTTPError:
            return None
        except Exception as exc:
            if attempt == 2:
                log.warning(f"[{label}] POST failed after 3 attempts: {exc}")
                return None


def _api_patch(url: str, headers: dict, payload: dict | None = None, label: str = "") -> dict | None:
    try:
        r = requests.patch(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.warning(f"[{label}] PATCH failed: {exc}")
        return None


# ── READ: DATADOG ─────────────────────────────────────────────────────────────

def read_datadog(window_hours: int = 4) -> dict:
    now = int(time.time())
    start = now - (window_hours * 3600)
    result: dict = {
        "source": "datadog", "window_hours": window_hours,
        "site": _DD_SITE, "metrics": {}, "monitors": [],
        "alerting_monitor_count": 0, "total_monitor_count": 0, "events": [],
    }

    # Metrics confirmed working on VPS host (us5.datadoghq.com agent)
    queries = {
        "cpu_pct":         "avg:system.cpu.user{*}",
        "load_1":          "avg:system.load.1{*}",
        "mem_pct_usable":  "avg:system.mem.pct_usable{*}",
        "disk_used_pct":   "avg:system.disk.in_use{*}",
        "docker_cpu_pct":  "avg:docker.cpu.usage{*}",
        "docker_mem_rss":  "avg:docker.mem.rss{*}",
        "net_rcvd_bps":    "avg:system.net.bytes_rcvd{*}",
    }
    for key, q in queries.items():
        data = _api_get(f"{DD_API_BASE}/v1/query", _dd_h(),
                        params={"from": start, "to": now, "query": q}, label=f"DD:{key}")
        if data and data.get("series"):
            pts = [p[1] for p in data["series"][0].get("pointlist", []) if p[1] is not None]
            if pts:
                val = {
                    "current": round(pts[-1], 2),
                    "avg":     round(sum(pts) / len(pts), 2),
                    "max":     round(max(pts), 2),
                    "min":     round(min(pts), 2),
                }
                # Convert docker RSS bytes → MB for readability
                if key == "docker_mem_rss":
                    val = {k: round(v / (1024 * 1024), 1) for k, v in val.items()}
                    key = "docker_mem_rss_mb"
                result["metrics"][key] = val
        log.info(f"[DD] {key}: {result['metrics'].get(key, 'no data')}")

    monitors = _api_get(f"{DD_API_BASE}/v1/monitor", _dd_h(),
                        params={"page_size": 50}, label="DD:monitors")
    if monitors:
        result["total_monitor_count"] = len(monitors)
        for m in monitors:
            state = m.get("overall_state", "OK")
            if state in ("Alert", "Warn", "No Data"):
                result["monitors"].append({
                    "name": m.get("name", ""), "state": state, "id": m.get("id")
                })
        result["alerting_monitor_count"] = len(result["monitors"])
        log.info(f"[DD] monitors: {result['total_monitor_count']} total, "
                 f"{result['alerting_monitor_count']} alerting")

    events = _api_get(f"{DD_API_BASE}/v1/events", _dd_h(),
                      params={"start": start, "end": now}, label="DD:events")
    if events and events.get("events"):
        for e in events["events"][:10]:
            result["events"].append({"title": e.get("title", ""), "source": e.get("source", "")})

    return result


# ── READ: POSTHOG ─────────────────────────────────────────────────────────────

def read_posthog(window_days: int = 7) -> dict:
    """Query PostHog via HogQL (replaces deprecated /insights/trend/ endpoint).

    Events tracked in this project:
      - $pageview, $pageleave, $autocapture          — browser (autocapture)
      - fg_* events                                  — Finance Guild (events.ts)
      - agent_tool_called, agent_session_*            — Python backend agents
      - assessment_check_result, diagnostic_cycle_*  — OAD loop
      - mcp.pre_call, mcp.post_call, mcp.tools.*     — CREW Voice MCP server
      - council.stage.*, council.pipeline.*           — Council governance
      - rehydration.*, elevenlabs.webhook.*           — Voice system layers
      - mission_started, mission_completed            — Brotherhood gamification

    Voice system dashboard: https://us.posthog.com/project/269641/dashboard/1303082
    """
    pid = os.getenv("POSTHOG_PROJECT_ID", "")
    result: dict = {
        "source": "posthog", "window_days": window_days,
        "unique_users": None, "pageviews": 0,
        "top_events": {},
        "fg_events": {},        # Finance Guild product events (fg_ prefix)
        "agent_events": {},     # Backend agent telemetry (agent_ prefix)
        "voice_events": {},     # CREW voice system events (mcp.*, council.*, rehydration.*)
        "feature_flags": [],
        "voice_system": {},     # Voice-specific aggregated metrics
        "note": "",
    }

    ph_url = f"{PH_HOST}/api/projects/{pid}/query"

    def hogql(sql: str) -> list:
        resp = _api_post(ph_url, _ph_h(),
                         payload={"query": {"kind": "HogQLQuery", "query": sql}},
                         label="PH:hogql")
        return resp.get("results", []) if resp else []

    # All events grouped by name — top 30 by count
    rows = hogql(
        f"SELECT event, count(*) as cnt FROM events "
        f"WHERE timestamp > now() - interval {window_days} day "
        f"GROUP BY event ORDER BY cnt DESC LIMIT 30"
    )
    for row in rows:
        event, count = row[0], int(row[1])
        result["top_events"][event] = count
        if event.startswith("fg_"):
            result["fg_events"][event] = count
        elif event.startswith("agent_"):
            result["agent_events"][event] = count
        elif any(event.startswith(p) for p in ("mcp.", "council.", "rehydration.", "elevenlabs.")):
            result["voice_events"][event] = count

    # Pageviews
    pv_rows = hogql(
        f"SELECT count(*) FROM events "
        f"WHERE event = '$pageview' AND timestamp > now() - interval {window_days} day"
    )
    if pv_rows:
        result["pageviews"] = int(pv_rows[0][0] or 0)

    # Unique users (persons) — all events
    uu_rows = hogql(
        f"SELECT count(distinct person_id) FROM events "
        f"WHERE timestamp > now() - interval {window_days} day"
    )
    if uu_rows:
        result["unique_users"] = int(uu_rows[0][0] or 0)

    # Voice system aggregates — pre-call latency, Council verdicts, webhook health
    if result["voice_events"] or True:  # run even if no voice events yet (shows gaps)
        # Pre-call total volume
        pc_rows = hogql(
            f"SELECT count(*), avg(toFloatOrDefault(properties.total_ms)) "
            f"FROM events WHERE event = 'mcp.pre_call' "
            f"AND timestamp > now() - interval {window_days} day"
        )
        if pc_rows and pc_rows[0][0]:
            result["voice_system"]["pre_call_count"] = int(pc_rows[0][0])
            result["voice_system"]["pre_call_avg_ms"] = round(pc_rows[0][1] or 0, 1)

        # Council allow/deny split
        council_rows = hogql(
            f"SELECT properties.verdict, count(*) FROM events "
            f"WHERE event = 'council.stage.verdict' "
            f"AND timestamp > now() - interval {window_days} day "
            f"GROUP BY properties.verdict"
        )
        if council_rows:
            result["voice_system"]["council_verdicts"] = {r[0]: int(r[1]) for r in council_rows}

        # Rehydration drift
        drift_rows = hogql(
            f"SELECT avg(toFloatOrDefault(properties.drift_ratio)) FROM events "
            f"WHERE event = 'rehydration.complete' "
            f"AND timestamp > now() - interval {window_days} day"
        )
        if drift_rows and drift_rows[0][0]:
            result["voice_system"]["rehydration_avg_drift"] = round(drift_rows[0][0], 3)

    # Feature flags
    flags = _api_get(f"{PH_HOST}/api/projects/{pid}/feature_flags/",
                     _ph_h(), label="PH:flags")
    if flags and flags.get("results"):
        for f in flags["results"][:20]:
            result["feature_flags"].append({
                "key": f.get("key", ""), "active": f.get("active", False)
            })

    if result["pageviews"] == 0:
        result["note"] = (
            "pageviews=0: VITE_POSTHOG_API_KEY not injected into frontend build env — "
            "browser autocapture is not firing. Add to VITE_ENV_DEFAULTS in cnwb_site_rebuild.py."
        )

    log.info(
        f"[PH] unique_users={result['unique_users']} pageviews={result['pageviews']} "
        f"fg_events={len(result['fg_events'])} agent_events={len(result['agent_events'])}"
    )
    return result


# ── READ: SUPABASE ────────────────────────────────────────────────────────────

def read_supabase(window_hours: int = 24) -> dict:
    after = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    result: dict = {
        "source": "supabase", "window_hours": window_hours,
        "automation_events": [], "sanctum_decisions": [], "oad_missions": [],
        "error_summary": {}, "table_health": {},
    }

    events = _api_get(f"{SB_URL}/rest/v1/automation_events", _sb_h(),
        params={"select": "id,event_type,status,created_at",
                "created_at": f"gte.{after}", "order": "created_at.desc", "limit": "50"},
        label="SB:events")
    if events:
        result["automation_events"] = events
        errors = [e for e in events if e.get("status") == "error"]
        result["error_summary"] = {
            "total":           len(events),
            "errors":          len(errors),
            "error_rate_pct":  round(len(errors) / max(len(events), 1) * 100, 1),
        }

    decisions = _api_get(f"{SB_URL}/rest/v1/sanctum_decisions", _sb_h(),
        params={"select": "id,evo_id,status,health,created_at",
                "created_at": f"gte.{after}", "order": "created_at.desc", "limit": "20"},
        label="SB:decisions")
    if decisions:
        result["sanctum_decisions"] = decisions

    missions = _api_get(f"{SB_URL}/rest/v1/oad_missions", _sb_h(),
        params={"select": "id,scope,kind,status,created_at",
                "status": "neq.completed", "order": "created_at.desc", "limit": "20"},
        label="SB:missions")
    if missions:
        result["oad_missions"] = missions

    for table in ["automation_events", "sanctum_decisions", "oad_missions"]:
        resp = _api_get(f"{SB_URL}/rest/v1/{table}", _sb_h(),
                        params={"select": "id", "limit": "1"}, label=f"SB:health:{table}")
        result["table_health"][table] = "ok" if resp is not None else "error"

    return result


def read_codegen_history(window_hours: int = 48, limit: int = 10) -> dict:
    """Read recent codegen cycle events from Supabase for THINK context.

    Returns a summary of recent code generation activity including rollback
    data so the THINK layer can factor past codegen health into assessments.
    """
    if not SB_URL:
        return {}
    after = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    events = _api_get(f"{SB_URL}/rest/v1/automation_events", _sb_h(), params={
        "select": "id,event,status,payload,created_at",
        "event_type": "eq.sanctum.codegen.cycle",
        "created_at": f"gte.{after}",
        "order": "created_at.desc",
        "limit": str(limit),
    }, label="SB:codegen_history")
    if not events:
        return {"source": "supabase_codegen", "cycles_found": 0}

    total_patches = 0
    total_rollbacks = 0
    total_branch_nukes = 0
    total_diff_guard_rejected = 0
    cycles: list[dict] = []
    for ev in events:
        p = ev.get("payload") or {}
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = {}
        total_patches += p.get("corrections_generated", 0)
        total_rollbacks += p.get("rollback_count", 0)
        total_branch_nukes += 1 if p.get("branch_rolled_back") else 0
        total_diff_guard_rejected += p.get("diff_guard_rejected", 0)
        cycles.append({
            "cycle_id": ev.get("event", "?"),
            "status": ev.get("status", "?"),
            "patches": p.get("corrections_generated", 0),
            "committed": len(p.get("committed_files", [])),
            "rollbacks": p.get("rollback_count", 0),
            "diff_guard_rejected": p.get("diff_guard_rejected", 0),
            "branch_nuked": p.get("branch_rolled_back", False),
            "mr": p.get("gitlab_mr"),
            "created_at": ev.get("created_at"),
        })

    return {
        "source": "supabase_codegen",
        "window_hours": window_hours,
        "cycles_found": len(cycles),
        "total_patches_generated": total_patches,
        "total_rollbacks": total_rollbacks,
        "total_branch_nukes": total_branch_nukes,
        "total_diff_guard_rejected": total_diff_guard_rejected,
        "codegen_health": "RED" if total_branch_nukes > 0
                          else "YELLOW" if total_rollbacks > 0 or total_diff_guard_rejected > 2
                          else "GREEN",
        "recent_cycles": cycles,
    }


# ── READ: NOTION ──────────────────────────────────────────────────────────────

def read_notion() -> dict:
    state: dict = {
        "source": "notion", "last_cycle": None,
        "open_tasks": [], "open_task_count": 0,
    }

    if CYCLE_DB:
        resp = _api_post(f"{NOTION_API}/databases/{CYCLE_DB}/query", _notion_h(),
            payload={
                "sorts": [{"timestamp": "created_time", "direction": "descending"}],
                "page_size": 1,
            }, label="NOTION:cycle")
        if resp and resp.get("results"):
            props = resp["results"][0].get("properties", {})
            evo_title = props.get("EVO ID", {}).get("title", [])
            mca_raw = props.get("MCA Changes", {}).get("rich_text", [])
            mca_text = "".join(t.get("plain_text", "") for t in mca_raw)
            status = props.get("Status", {}).get("select", {})
            state["last_cycle"] = {
                "evo_id": evo_title[0]["plain_text"] if evo_title else "unknown",
                "status": status.get("name", "?") if status else "?",
                "mca":    json.loads(mca_text) if mca_text else {},
            }

    if TASKS_DB:
        resp = _api_post(f"{NOTION_API}/databases/{TASKS_DB}/query", _notion_h(),
            payload={
                # Use select filter — the Status property is a select, not a status type
                "filter": {"property": "Status", "select": {"does_not_equal": "Done"}},
                "page_size": 50,
            }, label="NOTION:tasks")
        if resp:
            for page in resp.get("results", []):
                title_prop = page.get("properties", {}).get("Task", {}).get("title", [])
                title_text = "".join(t.get("plain_text", "") for t in title_prop)
                if title_text:
                    state["open_tasks"].append({"title": title_text})
            state["open_task_count"] = len(state["open_tasks"])

    return state


# ── READ: LEAD HUNTER ─────────────────────────────────────────────────────────

def read_lead_hunter(window_days: int = 7) -> dict:
    """Read Finance Guild Lead Hunter pipeline state from Notion leads DB.

    Requires NOTION_LEADS_DB_ID in workspace.env.
    DB properties expected: Business Name (title), Lead Score (number),
    Recommendation (select), Source (select), Status (select),
    Tags (multi_select), Scraped At (date).
    """
    if not LEADS_DB:
        log.warning("[LEADS] NOTION_LEADS_DB_ID not set — skipping")
        return {"source": "leads", "error": "NOTION_LEADS_DB_ID not configured"}

    after = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    result: dict = {
        "source": "leads",
        "window_days": window_days,
        "total_in_db": 0,
        "new_in_window": 0,
        "by_status": {},
        "by_recommendation": {},
        "by_source": {},
        "avg_score": None,
        "high_value_count": 0,   # score >= 0.7
        "top_leads": [],
        "pipeline_health": "unknown",
    }

    # Query ALL leads (up to 200) for aggregates
    all_resp = _api_post(f"{NOTION_API}/databases/{LEADS_DB}/query", _notion_h(),
        payload={"page_size": 200, "sorts": [{"property": "Lead Score", "direction": "descending"}]},
        label="LEADS:all")
    if all_resp:
        pages = all_resp.get("results", [])
        result["total_in_db"] = len(pages)
        scores = []
        for page in pages:
            props = page.get("properties", {})

            # Lead Score
            score_val = props.get("Lead Score", {}).get("number")
            if score_val is not None:
                scores.append(score_val)
                if score_val >= 0.7:
                    result["high_value_count"] += 1

            # Status
            status = props.get("Status", {}).get("select", {})
            status_name = status.get("name", "Unknown") if status else "Unknown"
            result["by_status"][status_name] = result["by_status"].get(status_name, 0) + 1

            # Recommendation
            rec = props.get("Recommendation", {}).get("select", {})
            rec_name = rec.get("name", "Unknown") if rec else "Unknown"
            result["by_recommendation"][rec_name] = result["by_recommendation"].get(rec_name, 0) + 1

            # Source
            src = props.get("Source", {}).get("select", {})
            src_name = src.get("name", "Unknown") if src else "Unknown"
            result["by_source"][src_name] = result["by_source"].get(src_name, 0) + 1

            # Top leads (up to 5, already sorted by score desc)
            if len(result["top_leads"]) < 5:
                title_prop = props.get("Business Name", {}).get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_prop)
                result["top_leads"].append({
                    "name":           title[:80],
                    "score":          score_val,
                    "recommendation": rec_name,
                    "status":         status_name,
                })

        if scores:
            result["avg_score"] = round(sum(scores) / len(scores), 3)

    # New leads in window
    new_resp = _api_post(f"{NOTION_API}/databases/{LEADS_DB}/query", _notion_h(),
        payload={
            "filter": {"property": "Scraped At", "date": {"after": after}},
            "page_size": 100,
        }, label="LEADS:new")
    if new_resp:
        result["new_in_window"] = len(new_resp.get("results", []))

    # Pipeline health heuristic
    total = result["total_in_db"]
    new = result["new_in_window"]
    high = result["high_value_count"]
    if total == 0:
        result["pipeline_health"] = "empty"
    elif new == 0 and total > 0:
        result["pipeline_health"] = "stale"       # no new leads
    elif high > 5:
        result["pipeline_health"] = "healthy"
    elif new > 0:
        result["pipeline_health"] = "active"
    else:
        result["pipeline_health"] = "low_yield"

    log.info(
        f"[LEADS] total={total} new={new} high_value={high} "
        f"avg_score={result['avg_score']} health={result['pipeline_health']}"
    )
    return result


# ── READ: STRIPE ──────────────────────────────────────────────────────────────

def read_stripe() -> dict:
    """Read live Stripe products, prices, subscriptions, and revenue data."""
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        return {"source": "stripe", "error": "STRIPE_SECRET_KEY not configured"}

    headers = {"Authorization": f"Bearer {key}"}
    result: dict = {
        "source": "stripe",
        "products": [],
        "active_subscriptions": 0,
        "trialing_subscriptions": 0,
        "past_due_subscriptions": 0,
        "total_customers": 0,
        "mrr_cents": 0,
        "prices_by_product": {},
        "health": "unknown",
    }

    # Products
    prod_resp = _api_get(f"{STRIPE_API}/products?limit=100&active=true", headers, label="STRIPE:products")
    if prod_resp:
        for p in prod_resp.get("data", []):
            result["products"].append({"id": p["id"], "name": p["name"], "active": p["active"]})

    # Prices
    price_resp = _api_get(f"{STRIPE_API}/prices?limit=100&active=true", headers, label="STRIPE:prices")
    if price_resp:
        for pr in price_resp.get("data", []):
            pid = pr.get("product", "")
            amount = pr.get("unit_amount", 0) or 0
            interval = pr.get("recurring", {}).get("interval", "one_time") if pr.get("recurring") else "one_time"
            result["prices_by_product"].setdefault(pid, []).append({
                "price_id": pr["id"],
                "amount_cents": amount,
                "currency": pr.get("currency", "usd"),
                "interval": interval,
            })

    # Subscriptions — active
    sub_resp = _api_get(f"{STRIPE_API}/subscriptions?limit=100&status=active", headers, label="STRIPE:subs_active")
    if sub_resp:
        subs = sub_resp.get("data", [])
        result["active_subscriptions"] = len(subs)
        for s in subs:
            for item in s.get("items", {}).get("data", []):
                result["mrr_cents"] += (item.get("price", {}).get("unit_amount", 0) or 0)

    # Subscriptions — trialing
    trial_resp = _api_get(f"{STRIPE_API}/subscriptions?limit=100&status=trialing", headers, label="STRIPE:subs_trial")
    if trial_resp:
        result["trialing_subscriptions"] = len(trial_resp.get("data", []))

    # Subscriptions — past_due
    pd_resp = _api_get(f"{STRIPE_API}/subscriptions?limit=100&status=past_due", headers, label="STRIPE:subs_past_due")
    if pd_resp:
        result["past_due_subscriptions"] = len(pd_resp.get("data", []))

    # Customers count
    cust_resp = _api_get(f"{STRIPE_API}/customers?limit=1", headers, label="STRIPE:customers")
    if cust_resp:
        result["total_customers"] = cust_resp.get("total_count", 0) or len(cust_resp.get("data", []))

    total_subs = result["active_subscriptions"] + result["trialing_subscriptions"]
    result["health"] = "healthy" if total_subs > 0 else "no_subscribers"
    result["mrr_usd"] = round(result["mrr_cents"] / 100, 2)

    log.info(
        f"[STRIPE] products={len(result['products'])} active_subs={result['active_subscriptions']} "
        f"trialing={result['trialing_subscriptions']} past_due={result['past_due_subscriptions']} "
        f"mrr=${result['mrr_usd']}"
    )
    return result


# ── READ: SIGNUP FUNNEL ───────────────────────────────────────────────────────

def read_signup_funnel(window_hours: int = 48) -> dict:
    """Read signup conversion funnel health from Supabase economic_events + subscriptions.

    Metrics returned:
        checkouts_started   — subscription_started events in window
        payments_succeeded  — payment_received events in window
        payments_failed     — payment_failed events in window
        payment_success_rate — payments_succeeded / (succeeded + failed) %
        active_subs         — subscriptions with status=active
        past_due_subs       — subscriptions with status=past_due
        revenue_window_usd  — sum of payment_received amounts in window
        health              — GREEN / YELLOW / RED
    """
    if not SB_URL:
        return {"source": "signup_funnel", "error": "SUPABASE_URL not configured"}

    after = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    result: dict = {
        "source": "signup_funnel",
        "window_hours": window_hours,
        "checkouts_started": 0,
        "payments_succeeded": 0,
        "payments_failed": 0,
        "payment_success_rate": 100.0,
        "active_subs": 0,
        "past_due_subs": 0,
        "revenue_window_usd": 0.0,
        "health": "unknown",
        "notes": [],
    }

    # ── economic_events: funnel event counts + revenue in window ─────────────
    events = _api_get(
        f"{SB_URL}/rest/v1/economic_events",
        _sb_h(),
        params={
            "select": "event_type,amount_usd,occurred_at",
            "occurred_at": f"gte.{after}",
            "order": "occurred_at.desc",
            "limit": "500",
        },
        label="SB:signup_funnel:events",
    )
    if events:
        for ev in events:
            et = ev.get("event_type", "")
            amt = float(ev.get("amount_usd") or 0)
            if et == "subscription_started":
                result["checkouts_started"] += 1
            elif et == "payment_received":
                result["payments_succeeded"] += 1
                result["revenue_window_usd"] += amt
            elif et == "payment_failed":
                result["payments_failed"] += 1

    total_payment_attempts = result["payments_succeeded"] + result["payments_failed"]
    if total_payment_attempts > 0:
        result["payment_success_rate"] = round(
            result["payments_succeeded"] / total_payment_attempts * 100, 1
        )

    # ── subscriptions: live counts ────────────────────────────────────────────
    subs = _api_get(
        f"{SB_URL}/rest/v1/subscriptions",
        _sb_h(),
        params={"select": "status", "limit": "500"},
        label="SB:signup_funnel:subs",
    )
    if subs:
        for s in subs:
            st = s.get("status", "")
            if st == "active":
                result["active_subs"] += 1
            elif st == "past_due":
                result["past_due_subs"] += 1

    # ── health scoring ────────────────────────────────────────────────────────
    health = "GREEN"
    if result["payment_success_rate"] < 70 and total_payment_attempts >= 3:
        health = "RED"
        result["notes"].append(
            f"Payment success rate critical: {result['payment_success_rate']}%"
        )
    elif result["payment_success_rate"] < 90 and total_payment_attempts >= 3:
        health = "YELLOW"
        result["notes"].append(
            f"Payment success rate degraded: {result['payment_success_rate']}%"
        )
    if result["past_due_subs"] > 0 and result["active_subs"] > 0:
        pct = result["past_due_subs"] / result["active_subs"] * 100
        if pct > 20:
            health = "RED" if health != "RED" else health
            result["notes"].append(f"{result['past_due_subs']} past-due subs ({pct:.0f}% of active)")
    result["health"] = health
    result["notes"] = "; ".join(result["notes"]) if result["notes"] else ""
    result["revenue_window_usd"] = round(result["revenue_window_usd"], 2)

    log.info(
        f"[SIGNUP_FUNNEL] checkouts={result['checkouts_started']} "
        f"payments_ok={result['payments_succeeded']} failed={result['payments_failed']} "
        f"success_rate={result['payment_success_rate']}% "
        f"active_subs={result['active_subs']} past_due={result['past_due_subs']} "
        f"revenue_window=${result['revenue_window_usd']}"
    )
    return result


# ── READ: METABASE ────────────────────────────────────────────────────────────

def read_metabase() -> dict:
    """Read Metabase dashboard and question summary data via API key."""
    api_key = os.getenv("METABASE_API_KEY", "")
    if not api_key:
        return {"source": "metabase", "error": "METABASE_API_KEY not configured"}

    base = METABASE_URL.rstrip("/")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    result: dict = {
        "source": "metabase",
        "dashboards": [],
        "total_dashboards": 0,
        "total_questions": 0,
        "database_count": 0,
        "health": "unknown",
    }

    # Databases
    db_resp = _api_get(f"{base}/api/database", headers, label="METABASE:databases")
    if db_resp:
        dbs = db_resp.get("data", db_resp) if isinstance(db_resp, dict) else db_resp
        result["database_count"] = len(dbs) if isinstance(dbs, list) else 0

    # Dashboards list
    dash_resp = _api_get(f"{base}/api/dashboard", headers, label="METABASE:dashboards")
    if dash_resp:
        dashboards = dash_resp if isinstance(dash_resp, list) else dash_resp.get("data", [])
        result["total_dashboards"] = len(dashboards)
        for d in dashboards[:10]:  # top 10 only
            result["dashboards"].append({
                "id": d.get("id"),
                "name": d.get("name"),
                "description": (d.get("description") or "")[:100],
            })

    # Questions/cards count
    card_resp = _api_get(f"{base}/api/card?f=all", headers, label="METABASE:cards")
    if card_resp:
        cards = card_resp if isinstance(card_resp, list) else card_resp.get("data", [])
        result["total_questions"] = len(cards) if isinstance(cards, list) else 0

    result["health"] = "healthy" if result["total_dashboards"] > 0 else "no_dashboards"
    log.info(
        f"[METABASE] dashboards={result['total_dashboards']} questions={result['total_questions']} "
        f"databases={result['database_count']}"
    )
    return result


# ── READ: NATS ────────────────────────────────────────────────────────────────

def read_nats() -> dict:
    """Read JetStream health via NATS monitoring HTTP endpoint (:8222)."""
    import re as _re

    nats_url = os.getenv("NATS_URL", "")
    monitor_base = os.getenv("NATS_MONITOR_URL", "")
    if not monitor_base:
        # Derive from NATS_URL: nats://token@host:4222 → http://host:8222
        m = _re.search(r"@([^:/]+):\d+", nats_url) or _re.search(r"nats://([^:/]+):\d+", nats_url)
        monitor_base = f"http://{m.group(1)}:8222" if m else "http://127.0.0.1:8222"

    # If derived host is a Docker-internal name that won't resolve from here,
    # fall back to localhost:8222 (NATS always exposes monitor on the VPS host)
    _localhost_fallback = "http://127.0.0.1:8222"
    _probe = _api_get(f"{monitor_base}/healthz", {}, label="NATS:healthz")
    if _probe is None and monitor_base != _localhost_fallback:
        log.debug("[NATS] monitor %s unreachable, retrying localhost:8222", monitor_base)
        monitor_base = _localhost_fallback

    result: dict = {
        "source": "nats",
        "monitor_url": monitor_base,
        "uptime_seconds": None,
        "connections": None,
        "total_connections": None,
        "streams": None,
        "consumers": None,
        "total_messages": None,
        "total_bytes": None,
        "slow_consumers": None,
        "stream_details": [],
        "health": "unknown",
    }

    # Server vars
    varz = _api_get(f"{monitor_base}/varz", {}, label="NATS:varz")
    if varz:
        result["uptime_seconds"] = varz.get("uptime_seconds") or varz.get("now")
        result["connections"]    = varz.get("connections", 0)
        result["total_connections"] = varz.get("total_connections", 0)
        result["slow_consumers"] = varz.get("slow_consumers", 0)
        result["uptime_str"]     = varz.get("uptime", "")

    # JetStream stats
    jsz = _api_get(f"{monitor_base}/jsz?accounts=true", {}, label="NATS:jsz")
    if jsz:
        acc = jsz.get("account_details", [{}])[0] if jsz.get("account_details") else jsz
        result["streams"]        = acc.get("streams", jsz.get("streams", 0))
        result["consumers"]      = acc.get("consumers", jsz.get("consumers", 0))
        result["total_messages"] = acc.get("messages", jsz.get("messages", 0))
        result["total_bytes"]    = acc.get("bytes", jsz.get("bytes", 0))

        # Per-stream detail
        stream_list = _api_get(f"{monitor_base}/jsz?streams=true", {}, label="NATS:jsz_streams")
        if stream_list:
            for s in (stream_list.get("account_details", [{}])[0].get("stream_detail", [])
                      or stream_list.get("stream_detail", [])):
                result["stream_details"].append({
                    "name":      s.get("name"),
                    "messages":  s.get("state", {}).get("messages", 0),
                    "consumers": s.get("state", {}).get("consumer_count", 0),
                })

    if varz or jsz:
        result["health"] = (
            "unhealthy" if result["slow_consumers"] else
            "degraded"  if result["connections"] == 0 else
            "healthy"
        )
    else:
        result["health"] = "unreachable"

    log.info(
        f"[NATS] streams={result['streams']} consumers={result['consumers']} "
        f"msgs={result['total_messages']} conns={result['connections']} "
        f"health={result['health']}"
    )
    return result


# ── READ: LINEAR ───────────────────────────────────────────────────────────────

def read_linear() -> dict:
    """Read open issues and in-progress work from Linear via GraphQL."""
    token = os.getenv("LINEAR_API_KEY", os.getenv("LINEAR_API_TOKEN", ""))
    team_id = LINEAR_TEAM_ID
    if not token:
        return {"source": "linear", "error": "LINEAR_API_KEY not configured"}

    headers = {"Authorization": token, "Content-Type": "application/json"}
    result: dict = {
        "source":       "linear",
        "team_id":      team_id,
        "open":         0,
        "in_progress":  0,
        "backlog":      0,
        "done_7d":      0,
        "oldest_open_days": None,
        "priority_urgent":  0,
        "health":       "unknown",
    }

    # Active issues (not completed / cancelled)
    q_active = """
    query($teamId: ID!) {
      issues(filter: {
        team: { id: { eq: $teamId } }
        state: { type: { nin: ["completed", "cancelled"] } }
      }, first: 100, orderBy: createdAt) {
        nodes {
          id title priority createdAt
          state { name type }
        }
      }
    }"""
    resp = _api_post("https://api.linear.app/graphql", headers,
                     payload={"query": q_active, "variables": {"teamId": team_id}},
                     label="LINEAR:active_issues")
    if resp and not resp.get("errors"):
        nodes = resp.get("data", {}).get("issues", {}).get("nodes", [])
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)
        oldest_days = None
        for issue in nodes:
            stype = issue.get("state", {}).get("type", "")
            if stype in ("started",):
                result["in_progress"] += 1
            elif stype in ("unstarted", "backlog"):
                result["open" if stype == "unstarted" else "backlog"] += 1
            if issue.get("priority", 0) == 1:  # 1 = urgent
                result["priority_urgent"] += 1
            try:
                created = _dt.fromisoformat(issue["createdAt"].replace("Z", "+00:00"))
                age = (now - created).days
                if oldest_days is None or age > oldest_days:
                    oldest_days = age
            except Exception:
                pass
        result["oldest_open_days"] = oldest_days

    # Completed in last 7 days
    from datetime import timedelta as _td
    since = (datetime.now(timezone.utc) - _td(days=7)).isoformat()
    q_done = """
    query($teamId: ID!, $since: DateTimeOrDuration!) {
      issues(filter: {
        team: { id: { eq: $teamId } }
        state: { type: { eq: "completed" } }
        completedAt: { gt: $since }
      }, first: 50) {
        nodes { id }
      }
    }"""
    resp2 = _api_post("https://api.linear.app/graphql", headers,
                      payload={"query": q_done, "variables": {"teamId": team_id, "since": since}},
                      label="LINEAR:done_7d")
    if resp2 and not resp2.get("errors"):
        result["done_7d"] = len(resp2.get("data", {}).get("issues", {}).get("nodes", []))

    total_active = result["open"] + result["in_progress"] + result["backlog"]
    result["health"] = (
        "blocked"  if result["priority_urgent"] > 3 else
        "busy"     if total_active > 20 else
        "healthy"  if total_active <= 10 else
        "loaded"
    )

    log.info(
        f"[LINEAR] open={result['open']} in_progress={result['in_progress']} "
        f"backlog={result['backlog']} done_7d={result['done_7d']} "
        f"urgent={result['priority_urgent']} oldest={result['oldest_open_days']}d"
    )
    return result


# ── READ: ELEVENLABS ──────────────────────────────────────────────────────────

def read_elevenlabs() -> dict:
    """Read ElevenLabs agent fleet status and character usage."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return {"source": "elevenlabs", "error": "ELEVENLABS_API_KEY not configured"}

    el_base = "https://api.elevenlabs.io"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    result: dict = {
        "source":             "elevenlabs",
        "agent_count":        0,
        "agents":             [],
        "character_limit":    None,
        "character_count":    None,
        "character_used_pct": None,
        "next_reset":         None,
        "health":             "unknown",
    }

    # Subscription / usage
    sub = _api_get(f"{el_base}/v1/user/subscription", headers, label="ELEVENLABS:subscription")
    if sub:
        result["character_limit"] = sub.get("character_limit")
        result["character_count"] = sub.get("character_count")
        result["next_reset"]      = sub.get("next_character_count_reset_unix")
        if result["character_limit"]:
            result["character_used_pct"] = round(
                result["character_count"] / result["character_limit"] * 100, 1
            )

    # Conversational AI agents
    agents_resp = _api_get(f"{el_base}/v1/convai/agents",
                           headers, params={"page_size": 100},
                           label="ELEVENLABS:agents")
    if agents_resp:
        agents_list = agents_resp.get("agents", agents_resp if isinstance(agents_resp, list) else [])
        result["agent_count"] = len(agents_list)
        for a in agents_list[:10]:
            result["agents"].append({
                "agent_id": a.get("agent_id", a.get("id")),
                "name":     a.get("name", ""),
            })

    # Conversation history count (last 24h via created_after)
    from datetime import timedelta as _td
    since_ts = int((datetime.now(timezone.utc) - _td(hours=24)).timestamp())
    convs = _api_get(f"{el_base}/v1/convai/conversations",
                     headers,
                     params={"page_size": 100, "created_after_unix_secs": since_ts},
                     label="ELEVENLABS:conversations_24h")
    if convs:
        conv_list = convs.get("conversations", convs if isinstance(convs, list) else [])
        result["conversations_24h"] = len(conv_list)
    else:
        result["conversations_24h"] = None

    used_pct = result["character_used_pct"] or 0
    result["health"] = (
        "critical" if used_pct > 90 else
        "warning"  if used_pct > 75 else
        "healthy"  if result["agent_count"] > 0 else
        "no_agents"
    )

    log.info(
        f"[ELEVENLABS] agents={result['agent_count']} "
        f"chars={result['character_count']}/{result['character_limit']} "
        f"({used_pct}%) convs_24h={result.get('conversations_24h')} "
        f"health={result['health']}"
    )
    return result


# ── READ: CAL.COM (direct PostgreSQL via SSH) ────────────────────────────────

_CALCOM_SSH = [
    r"C:\Windows\System32\OpenSSH\ssh.exe",
    "-o", "StrictHostKeyChecking=no",
    "-o", "IdentitiesOnly=yes",
    "-i", "C:/Users/raizoken/.ssh/citadel_helper",
    "root@147.93.43.117",
]


def _calcom_db_query(sql: str) -> str:
    """Execute a SQL query against the Cal.com PostgreSQL DB on the VPS.

    The Cal.com v2 API service (port 5555) is not running inside the Docker
    image — only the web app exists.  We query the DB directly via SSH → Docker
    exec piped stdin → psql.
    """
    import subprocess
    cmd = f"echo '{sql}' | docker exec -i calcom-postgres psql -U calcom -d calcom -t -A"
    try:
        proc = subprocess.run(
            _CALCOM_SSH + [cmd],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            log.warning(f"[CALCOM:DB] stderr: {proc.stderr.strip()[:200]}")
        return proc.stdout.strip()
    except Exception as exc:
        log.warning(f"[CALCOM:DB] SSH/psql failed: {exc}")
        return ""


def read_calcom() -> dict:
    """Read upcoming and recent bookings from Cal.com PostgreSQL (via SSH).

    Falls back gracefully if the VPS or database is unreachable.
    """
    result: dict = {
        "source":         "calcom",
        "upcoming_count": 0,
        "upcoming":       [],
        "past_7d":        0,
        "cancelled_7d":   0,
        "health":         "unknown",
    }

    # ── Upcoming bookings ─────────────────────────────────────────
    upcoming_count = _calcom_db_query(
        'SELECT count(*) FROM "Booking" WHERE "startTime" > now()'
    )
    try:
        result["upcoming_count"] = int(upcoming_count)
    except (ValueError, TypeError):
        log.warning(f"[CALCOM] Could not parse upcoming count: {upcoming_count!r}")
        result["error"] = "DB query failed — VPS unreachable or container down"
        return result

    # Upcoming details (top 5)
    upcoming_json = _calcom_db_query(
        "SELECT json_agg(row_to_json(t)) FROM ("
        "SELECT title, \"startTime\", status "
        "FROM \"Booking\" WHERE \"startTime\" > now() "
        "ORDER BY \"startTime\" LIMIT 5"
        ") t"
    )
    if upcoming_json and upcoming_json != "":
        try:
            rows = json.loads(upcoming_json)
            for r in (rows or []):
                result["upcoming"].append({
                    "title": r.get("title", ""),
                    "start": r.get("startTime", ""),
                    "status": r.get("status", ""),
                })
        except json.JSONDecodeError:
            pass

    # ── Past 7 days (ACCEPTED) ────────────────────────────────────
    past_count = _calcom_db_query(
        "SELECT count(*) FROM \"Booking\" "
        "WHERE \"startTime\" BETWEEN now() - interval '7 days' AND now() "
        "AND status = 'ACCEPTED'"
    )
    try:
        result["past_7d"] = int(past_count)
    except (ValueError, TypeError):
        pass

    # ── Cancelled 7 days ──────────────────────────────────────────
    cancelled_count = _calcom_db_query(
        "SELECT count(*) FROM \"Booking\" "
        "WHERE \"startTime\" BETWEEN now() - interval '7 days' AND now() "
        "AND status = 'CANCELLED'"
    )
    try:
        result["cancelled_7d"] = int(cancelled_count)
    except (ValueError, TypeError):
        pass

    result["health"] = (
        "active"      if result["upcoming_count"] > 0 else
        "quiet"       if result["past_7d"] > 0 else
        "no_bookings"
    )

    log.info(
        f"[CALCOM] upcoming={result['upcoming_count']} past_7d={result['past_7d']} "
        f"cancelled_7d={result['cancelled_7d']} health={result['health']}"
    )
    return result


# ── READ: NOTION CODE CORRECTIONS (Code Blueprint DB) ────────────────────────
CODE_BLUEPRINT_DB = os.getenv("NOTION_CODE_BLUEPRINT_DB_ID", "311bcff4-93cb-8183-b7f9-dd72458e5121")


def read_notion_code_corrections(limit: int = 20) -> list[dict]:
    """Fetch recent code corrections/blueprints from Notion Code Blueprint DB.

    Returns a list of correction dicts with name, source_file, action, status,
    caps_grade, risk, confidence, sake_id, tags, type.
    These are surfaced in the Notion report under '🔧 Code Corrections' and
    passed to Perplexity so the loop can see what has already been addressed.
    """
    if not CODE_BLUEPRINT_DB:
        return []

    payload = {
        "page_size": limit,
        "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
    }
    resp = _api_post(
        f"{NOTION_API}/databases/{CODE_BLUEPRINT_DB}/query",
        _notion_h(), payload=payload, label="NOTION:code_blueprints",
    )
    if not resp:
        return []

    corrections: list[dict] = []
    for page in resp.get("results", []):
        props = page.get("properties", {})

        def _title(p):
            for t in p.get("title", []):
                return t.get("plain_text", "")
            return ""

        def _rt_text(p):
            return "".join(t.get("plain_text", "") for t in p.get("rich_text", []))

        def _select(p):
            s = p.get("select")
            return s.get("name", "") if s else ""

        def _multi(p):
            return [ms.get("name", "") for ms in p.get("multi_select", [])]

        def _num(p):
            return p.get("number")

        corrections.append({
            "name":        _title(props.get("Name", {})),
            "source_file": _rt_text(props.get("Source File", {})),
            "action":      _select(props.get("Action", {})),
            "status":      _select(props.get("Status", {})),
            "caps_grade":  _select(props.get("CAPS Grade", {})),
            "risk":        _num(props.get("Risk", {})),
            "confidence":  _num(props.get("Confidence", {})),
            "sake_id":     _rt_text(props.get("SAKE ID", {})),
            "tags":        _multi(props.get("Tags", {})),
            "type":        _select(props.get("Type", {})),
            "page_id":     page.get("id", ""),
            "last_edited": page.get("last_edited_time", ""),
        })

    log.info(f"[READ] Code Blueprint DB: {len(corrections)} corrections fetched")
    return corrections


# ── THINK: LAYER 0 — DETERMINISTIC SCORING ───────────────────────────────────
#
# Pure Python threshold engine.  Every scoring rule that was previously
# buried in LLM system prompts is now applied here with math, not vibes.
# Returns a fully-scored diagnostic dict with per-domain status flags.
# The LLM layers receive this and focus on root-cause reasoning / actions.

def _grade(score: int) -> str:
    if score >= 90: return "HEALTHY"
    if score >= 60: return "DEGRADING"
    return "CRITICAL"


def score_deterministic(telemetry: dict) -> dict:
    """Layer 0: Deterministic threshold scoring — no LLM.

    Applies every defined rule to raw telemetry and produces:
      - per-domain status (GREEN/YELLOW/RED) + notes
      - a hard health_score floor (0-100)
      - pre-populated blockers list
      - blind_spots list for missing data sources

    The score is a WEIGHTED AVERAGE of domain scores:
      infrastructure 20%, code_health 20%, platform 10%, product 10%,
      revenue 10%, lead_pipeline 5%, nats 5%, linear 5%, voice 5%,
      bookings 5%, analytics 5%.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    domains: dict[str, dict] = {}
    blockers: list[str] = []
    blind_spots: list[str] = []

    # ── Infrastructure (Datadog) ─────────────────────────────────────────
    dd = telemetry.get("datadog", {})
    infra = {"status": "GREEN", "score": 100, "notes": []}
    if not dd or dd.get("error"):
        blind_spots.append("datadog")
        infra["status"] = "YELLOW"
        infra["score"] = 70
        infra["notes"].append("Datadog data missing — blind spot")
    else:
        metrics = dd.get("metrics", {})
        cpu = metrics.get("cpu_pct", {}).get("current")
        if cpu is not None:
            infra["cpu_pct"] = cpu
            if cpu > 80:
                infra["status"] = "RED"; infra["score"] -= 30
                blockers.append(f"CPU at {cpu}% (>80% threshold)")
            elif cpu > 60:
                infra["status"] = max(infra["status"], "YELLOW"); infra["score"] -= 10
        load_1 = metrics.get("load_1", {}).get("current")
        if load_1 is not None:
            infra["load_1"] = load_1
            if load_1 > 4.0:
                infra["status"] = "RED"; infra["score"] -= 25
                blockers.append(f"Load average {load_1} (>4.0)")
            elif load_1 > 2.0:
                infra["score"] -= 10
        disk = metrics.get("disk_used_pct", {}).get("current")
        if disk is not None:
            infra["disk_used_pct"] = disk
            if disk > 0.85:
                infra["status"] = "RED"; infra["score"] -= 25
                blockers.append(f"Disk at {disk*100:.0f}% (>85%)")
            elif disk > 0.70:
                infra["score"] -= 10
        docker_mem = metrics.get("docker_mem_rss_mb", {}).get("current")
        if docker_mem is not None:
            infra["docker_mem_rss_mb"] = docker_mem
            if docker_mem > 3000:
                if infra["status"] == "GREEN": infra["status"] = "YELLOW"
                infra["score"] -= 15
        mem = metrics.get("mem_pct_usable", {}).get("current")
        if mem is not None:
            infra["mem_pct_usable"] = mem
            if mem < 0.10:
                infra["status"] = "RED"; infra["score"] -= 20

        alerting = dd.get("alerting_monitor_count", 0)
        total_mon = dd.get("total_monitor_count", 0)
        infra["alerting_monitors"] = alerting
        infra["total_monitors"] = total_mon
        if alerting > 0:
            names = [m.get("name", "?") for m in dd.get("monitors", [])]
            infra["notes"].append(f"Alerting: {', '.join(names[:5])}")
            infra["score"] -= min(alerting * 5, 20)
            if infra["status"] == "GREEN": infra["status"] = "YELLOW"

    infra["score"] = max(infra["score"], 0)
    infra["notes"] = "; ".join(infra["notes"]) if infra["notes"] else ""
    domains["infrastructure"] = infra

    # ── Code Health (GitLab) ─────────────────────────────────────────────
    gl = telemetry.get("gitlab", {})
    code = {"status": "GREEN", "score": 100, "notes": []}
    if not gl or gl.get("error"):
        blind_spots.append("gitlab")
        code["status"] = "YELLOW"; code["score"] = 70
        code["notes"].append("GitLab data missing — blind spot")
    else:
        ppr = gl.get("pipeline_pass_rate_pct")
        if ppr is not None:
            code["pipeline_pass_rate_pct"] = ppr
            if ppr == 0:
                code["status"] = "RED"; code["score"] -= 40
                blockers.append(f"Pipeline pass rate 0% — every build broken")
            elif ppr < 80:
                code["status"] = "RED"; code["score"] -= 25
                blockers.append(f"Pipeline pass rate {ppr}% (<80%)")
            elif ppr < 95:
                if code["status"] == "GREEN": code["status"] = "YELLOW"
                code["score"] -= 10
        cfr = gl.get("change_failure_rate_pct")
        if cfr is not None:
            code["change_failure_rate_pct"] = cfr
            if cfr == 100:
                code["status"] = "RED"; code["score"] -= 30
                blockers.append("Change failure rate 100% — no successful pipeline")
            elif cfr > 50:
                code["score"] -= 15
        stuck = gl.get("stuck_pipelines", 0)
        code["stuck_pipelines"] = stuck
        if stuck > 3:
            code["status"] = "RED"; code["score"] -= 20
        elif stuck > 0:
            if code["status"] == "GREEN": code["status"] = "YELLOW"
            code["score"] -= 5 * stuck
        crit_issues = gl.get("open_critical_issues", 0)
        code["critical_open_issues"] = crit_issues
        if crit_issues > 10:
            code["status"] = "RED"; code["score"] -= 15
            blockers.append(f"{crit_issues} critical open issues")
        elif crit_issues > 0:
            if code["status"] == "GREEN": code["status"] = "YELLOW"
            code["score"] -= min(crit_issues * 2, 10)
        stale = gl.get("stale_mrs", 0)
        code["stale_mrs"] = stale
        if stale > 0:
            code["notes"].append(f"{stale} stale MRs (>7d)")
            code["score"] -= min(stale * 2, 10)
        failed_dep = gl.get("failed_deployments", 0)
        total_dep = gl.get("total_deployments", 1) or 1
        if total_dep > 0 and failed_dep / total_dep > 0.20:
            if code["status"] == "GREEN": code["status"] = "YELLOW"
            code["score"] -= 10
        open_iss = gl.get("open_issues")
        closed_7d = gl.get("issues_closed_7d", 0)
        if open_iss and open_iss > 200 and closed_7d == 0:
            if code["status"] == "GREEN": code["status"] = "YELLOW"
            code["notes"].append(f"{open_iss} open issues, 0 closed in 7d — debt accumulating")
        # DORA metrics — original field names
        for k in ("deployment_frequency_per_day", "lead_time_for_changes_hours",
                   "commit_velocity_per_day"):
            if gl.get(k) is not None:
                code[k] = gl[k]
        # VCC namespace aliases so devanalytics_bridge + DD monitors read same keys
        # citadel.dora.lead_time uses "lead_time_hours"; citadel.git.velocity uses "commit_velocity_per_day"
        if gl.get("lead_time_for_changes_hours") is not None:
            code["lead_time_hours"] = gl["lead_time_for_changes_hours"]
        code.setdefault("open_issues", gl.get("open_issues", 0))
        code.setdefault("failed_deployments", gl.get("failed_deployments", 0))
        code.setdefault("open_critical_vulns", gl.get("security_vulns_critical", 0))
        # Security
        sec_crit = gl.get("security_vulns_critical", 0)
        sec_high = gl.get("security_vulns_high", 0)
        if sec_crit > 0:
            code["status"] = "RED"; code["score"] -= 20
            blockers.append(f"{sec_crit} critical security vulnerabilities")
        if sec_high > 0:
            code["score"] -= min(sec_high * 5, 15)

    # Codegen health factor
    cg_hist = telemetry.get("codegen_history", {})
    if cg_hist.get("codegen_health") == "RED":
        if code["status"] == "GREEN": code["status"] = "YELLOW"
        code["score"] -= 10
        blockers.append("CodeGen: branch nuked in recent cycle — LLM patch quality regression")
    elif cg_hist.get("codegen_health") == "YELLOW":
        code["score"] -= 5
        code["notes"].append("CodeGen: rollbacks or diff_guard rejections in recent cycles")

    code["score"] = max(code["score"], 0)
    code["notes"] = "; ".join(code["notes"]) if code["notes"] else ""
    domains["code_health"] = code

    # ── Platform (Supabase automation) ───────────────────────────────────
    sb = telemetry.get("supabase", {})
    plat = {"status": "GREEN", "score": 100, "notes": []}
    if not sb or sb.get("error"):
        blind_spots.append("supabase")
        plat["score"] = 75
    else:
        err_rate = sb.get("error_summary", {}).get("error_rate_pct", 0)
        plat["automation_error_rate_pct"] = err_rate
        if err_rate > 30:
            plat["status"] = "RED"; plat["score"] -= 30
            blockers.append(f"Automation error rate {err_rate}%")
        elif err_rate > 10:
            plat["status"] = "YELLOW"; plat["score"] -= 15
        pending = len(sb.get("oad_missions", []))
        plat["pending_missions"] = pending
        decisions = len(sb.get("sanctum_decisions", []))
        plat["sanctum_decisions_24h"] = decisions
        for tbl, st in sb.get("table_health", {}).items():
            if st == "error":
                plat["notes"].append(f"Table {tbl} unreachable")
                plat["score"] -= 5
    plat["score"] = max(plat["score"], 0)
    plat["notes"] = "; ".join(plat["notes"]) if plat["notes"] else ""
    domains["platform"] = plat

    # ── Product (PostHog) ────────────────────────────────────────────────
    ph = telemetry.get("posthog", {})
    prod = {"status": "GREEN", "score": 100, "notes": []}
    if not ph or ph.get("error"):
        blind_spots.append("posthog")
        prod["score"] = 75
    else:
        uu = ph.get("unique_users")
        pv = ph.get("pageviews", 0)
        prod["unique_users_7d"] = uu
        prod["pageviews_7d"] = pv
        prod["fg_events"] = ph.get("fg_events", {})
        prod["agent_events"] = ph.get("agent_events", {})
        prod["voice_events"] = ph.get("voice_events", {})
        prod["voice_system"] = ph.get("voice_system", {})
        if pv == 0:
            prod["notes"].append("pageviews=0 — VITE_POSTHOG_API_KEY not in build; tracking blind spot")
        if uu == 0 and not ph.get("agent_events") and not ph.get("fg_events"):
            prod["status"] = "YELLOW"; prod["score"] -= 20
            prod["notes"].append("No users or agent activity in 7d")
        active_flags = sum(1 for f in ph.get("feature_flags", []) if f.get("active"))
        prod["feature_flags_active"] = active_flags
    prod["score"] = max(prod["score"], 0)
    prod["notes"] = "; ".join(prod["notes"]) if prod["notes"] else ""
    domains["product"] = prod

    # ── Revenue (Stripe) ─────────────────────────────────────────────────
    st = telemetry.get("stripe", {})
    rev = {"status": "GREEN", "score": 100, "notes": []}
    if not st or st.get("error"):
        blind_spots.append("stripe")
        rev["score"] = 75
        rev["notes"].append("Stripe data missing — blind spot")
    else:
        active = st.get("active_subscriptions", 0)
        trialing = st.get("trialing_subscriptions", 0)
        past_due = st.get("past_due_subscriptions", 0)
        mrr = st.get("mrr_usd", 0)
        rev["active_subscriptions"] = active
        rev["trialing_subscriptions"] = trialing
        rev["past_due_subscriptions"] = past_due
        rev["mrr_usd"] = mrr
        rev["product_count"] = len(st.get("products", []))
        if active == 0 and trialing == 0:
            rev["status"] = "RED"; rev["score"] -= 40
            blockers.append("No active or trialing subscriptions — zero paying users")
        if mrr == 0:
            rev["status"] = "RED"; rev["score"] -= 20
        if active > 0 and past_due > 0 and past_due / active > 0.20:
            if rev["status"] == "GREEN": rev["status"] = "YELLOW"
            rev["score"] -= 15
            rev["notes"].append(f"{past_due} past-due subs ({past_due/active*100:.0f}% of active) — churn risk")
    # ── Signup Funnel (augments revenue domain) ──────────────────────────
    sf = telemetry.get("signup_funnel", {})
    if sf and not sf.get("error"):
        rev["signup_checkouts_48h"]      = sf.get("checkouts_started", 0)
        rev["signup_payments_ok_48h"]    = sf.get("payments_succeeded", 0)
        rev["signup_payments_fail_48h"]  = sf.get("payments_failed", 0)
        rev["signup_payment_success_pct"]= sf.get("payment_success_rate", 100.0)
        rev["signup_revenue_48h_usd"]    = sf.get("revenue_window_usd", 0.0)
        if sf.get("health") == "RED":
            if rev["status"] == "GREEN": rev["status"] = "YELLOW"
            rev["score"] -= 20
            rev["notes"].append(sf.get("notes", "Signup funnel RED"))
        elif sf.get("health") == "YELLOW":
            rev["notes"].append(sf.get("notes", "Signup funnel degraded"))

    rev["score"] = max(rev["score"], 0)
    rev["notes"] = "; ".join(rev["notes"]) if rev["notes"] else ""
    domains["revenue"] = rev

    # ── Lead Pipeline ────────────────────────────────────────────────────
    ld = telemetry.get("leads", {})
    lead = {"status": "GREEN", "score": 100, "notes": []}
    if not ld or ld.get("error"):
        blind_spots.append("leads")
        lead["score"] = 75
    else:
        total = ld.get("total_in_db", 0)
        new = ld.get("new_in_window", 0)
        high = ld.get("high_value_count", 0)
        avg_s = ld.get("avg_score")
        health = ld.get("pipeline_health", "unknown")
        lead["total_leads"] = total
        lead["new_leads_7d"] = new
        lead["high_value_count"] = high
        lead["avg_score"] = avg_s
        lead["pipeline_health"] = health
        if health in ("stale", "empty"):
            lead["status"] = "RED"; lead["score"] -= 30
        elif health == "low_yield":
            lead["status"] = "YELLOW"; lead["score"] -= 15
        if avg_s is not None and avg_s < 0.3:
            if lead["status"] == "GREEN": lead["status"] = "YELLOW"
            lead["score"] -= 10
        if high == 0 and total > 0:
            if lead["status"] == "GREEN": lead["status"] = "YELLOW"
            lead["score"] -= 10
        if new == 0 and total > 0:
            if lead["status"] == "GREEN": lead["status"] = "YELLOW"
            lead["notes"].append("No new leads in window")
    lead["score"] = max(lead["score"], 0)
    lead["notes"] = "; ".join(lead["notes"]) if lead["notes"] else ""
    domains["lead_pipeline"] = lead

    # ── NATS ─────────────────────────────────────────────────────────────
    ns = telemetry.get("nats", {})
    nats_d = {"status": "GREEN", "score": 100, "notes": []}
    if not ns or ns.get("error"):
        blind_spots.append("nats")
        nats_d["score"] = 75
    else:
        nh = ns.get("health", "unknown")
        if nh == "unreachable":
            nats_d["status"] = "RED"; nats_d["score"] -= 40
            blockers.append("NATS bus unreachable")
        elif nh == "unhealthy":
            nats_d["status"] = "RED"; nats_d["score"] -= 25
        elif nh == "degraded":
            nats_d["status"] = "YELLOW"; nats_d["score"] -= 15
        nats_d["streams"] = ns.get("streams")
        nats_d["consumers"] = ns.get("consumers")
        nats_d["total_messages"] = ns.get("total_messages")
        nats_d["connections"] = ns.get("connections")
        nats_d["slow_consumers"] = ns.get("slow_consumers", 0)
        nats_d["uptime_str"] = ns.get("uptime_str", "")
        if ns.get("streams") == 0:
            nats_d["status"] = "RED"; nats_d["score"] -= 20
        if ns.get("connections") == 0:
            if nats_d["status"] == "GREEN": nats_d["status"] = "YELLOW"
            nats_d["score"] -= 10
            nats_d["notes"].append("No services connected to bus")
        if ns.get("slow_consumers", 0) > 0:
            if nats_d["status"] == "GREEN": nats_d["status"] = "YELLOW"
            nats_d["score"] -= 10
    nats_d["score"] = max(nats_d["score"], 0)
    nats_d["notes"] = "; ".join(nats_d["notes"]) if nats_d["notes"] else ""
    domains["nats"] = nats_d

    # ── Linear ───────────────────────────────────────────────────────────
    li = telemetry.get("linear", {})
    lin = {"status": "GREEN", "score": 100, "notes": []}
    if not li or li.get("error"):
        blind_spots.append("linear")
        lin["score"] = 75
    else:
        lin["open"] = li.get("open", 0)
        lin["in_progress"] = li.get("in_progress", 0)
        lin["backlog"] = li.get("backlog", 0)
        lin["done_7d"] = li.get("done_7d", 0)
        lin["oldest_open_days"] = li.get("oldest_open_days")
        lin["priority_urgent"] = li.get("priority_urgent", 0)
        if li.get("priority_urgent", 0) > 5:
            lin["status"] = "RED"; lin["score"] -= 25
            blockers.append(f"{li['priority_urgent']} urgent Linear issues")
        elif li.get("priority_urgent", 0) > 0:
            if lin["status"] == "GREEN": lin["status"] = "YELLOW"
            lin["score"] -= 5
        if li.get("in_progress", 0) == 0 and li.get("open", 0) > 0:
            if lin["status"] == "GREEN": lin["status"] = "YELLOW"
            lin["score"] -= 10
            lin["notes"].append("Work stalled — 0 in-progress with open items")
        if li.get("oldest_open_days") and li["oldest_open_days"] > 30:
            if lin["status"] == "GREEN": lin["status"] = "YELLOW"
            lin["score"] -= 5
            lin["notes"].append(f"Oldest open issue: {li['oldest_open_days']}d")
    lin["score"] = max(lin["score"], 0)
    lin["notes"] = "; ".join(lin["notes"]) if lin["notes"] else ""
    domains["linear"] = lin

    # ── Voice Agents (ElevenLabs) ────────────────────────────────────────
    el = telemetry.get("elevenlabs", {})
    voice = {"status": "GREEN", "score": 100, "notes": []}
    if not el or el.get("error"):
        blind_spots.append("elevenlabs")
        voice["score"] = 75
    else:
        voice["agent_count"] = el.get("agent_count", 0)
        voice["character_used_pct"] = el.get("character_used_pct")
        voice["character_limit"] = el.get("character_limit")
        voice["conversations_24h"] = el.get("conversations_24h")
        used = el.get("character_used_pct") or 0
        if used > 90:
            voice["status"] = "RED"; voice["score"] -= 30
            blockers.append(f"ElevenLabs character usage {used}% — budget critical")
        elif used > 75:
            voice["status"] = "YELLOW"; voice["score"] -= 15
        if el.get("agent_count", 0) == 0:
            voice["status"] = "RED"; voice["score"] -= 25
            blockers.append("No voice agents deployed")
        if el.get("conversations_24h") == 0:
            if voice["status"] == "GREEN": voice["status"] = "YELLOW"
            voice["score"] -= 10
            voice["notes"].append("No conversations in 24h")
    voice["score"] = max(voice["score"], 0)
    voice["notes"] = "; ".join(voice["notes"]) if voice["notes"] else ""
    domains["voice_agents"] = voice

    # ── Bookings (Cal.com) ───────────────────────────────────────────────
    cc = telemetry.get("calcom", {})
    book = {"status": "GREEN", "score": 100, "notes": []}
    if not cc or cc.get("error"):
        blind_spots.append("calcom")
        book["score"] = 75
    else:
        book["upcoming_count"] = cc.get("upcoming_count", 0)
        book["past_7d"] = cc.get("past_7d", 0)
        book["cancelled_7d"] = cc.get("cancelled_7d", 0)
        if cc.get("upcoming_count", 0) == 0:
            if book["status"] == "GREEN": book["status"] = "YELLOW"
            book["score"] -= 15
            book["notes"].append("No upcoming bookings")
        past = cc.get("past_7d", 0) or 1
        if cc.get("cancelled_7d", 0) > past * 0.5:
            if book["status"] == "GREEN": book["status"] = "YELLOW"
            book["score"] -= 10
            book["notes"].append("High cancellation rate")
    book["score"] = max(book["score"], 0)
    book["notes"] = "; ".join(book["notes"]) if book["notes"] else ""
    domains["bookings"] = book

    # ── Analytics Platform (Metabase) ────────────────────────────────────
    mb = telemetry.get("metabase", {})
    ana = {"status": "GREEN", "score": 100, "notes": []}
    if not mb or mb.get("error"):
        blind_spots.append("metabase")
        ana["score"] = 75
        ana["notes"].append("Metabase data missing — blind spot")
    else:
        ana["total_dashboards"] = mb.get("total_dashboards", 0)
        ana["total_questions"] = mb.get("total_questions", 0)
        ana["database_count"] = mb.get("database_count", 0)
        if mb.get("total_dashboards", 0) == 0:
            if ana["status"] == "GREEN": ana["status"] = "YELLOW"
            ana["score"] -= 15
            ana["notes"].append("No dashboards — analytics blind spot")
    ana["score"] = max(ana["score"], 0)
    ana["notes"] = "; ".join(ana["notes"]) if ana["notes"] else ""
    domains["analytics_platform"] = ana

    # ── Blueprint Conformance (Drift Scanner) ────────────────────────────
    drift_data = telemetry.get("_drift_report", {})
    bp = {"status": "GREEN", "score": 100, "notes": []}
    if not drift_data or drift_data.get("error"):
        blind_spots.append("blueprint_drift")
        bp["score"] = 80  # minor penalty for missing drift data
    else:
        conformance = drift_data.get("overall_conformance_pct", 100)
        bp["conformance_pct"] = conformance
        bp["total_drifted"] = drift_data.get("total_drifted", 0)
        bp["critical_count"] = drift_data.get("critical_count", 0)
        bp["high_count"] = drift_data.get("high_count", 0)
        bp["score_penalty"] = drift_data.get("total_score_penalty", 0)
        # Apply penalty from drift scoring
        penalty = min(drift_data.get("total_score_penalty", 0), 30)
        bp["score"] = max(0, 100 - penalty)
        if conformance < 50:
            bp["status"] = "RED"
            blockers.append(f"Blueprint conformance {conformance:.0f}% — critical drift")
        elif conformance < 80:
            bp["status"] = "YELLOW"
        if drift_data.get("critical_count", 0) > 0:
            bp["status"] = "RED"
            bp["score"] = min(bp["score"], 40)
            blockers.append(f"{drift_data['critical_count']} critical blueprint drifts")
    bp["score"] = max(bp["score"], 0)
    bp["notes"] = "; ".join(bp["notes"]) if bp["notes"] else ""
    domains["blueprint_conformance"] = bp

    # ── Weighted composite score ─────────────────────────────────────────
    # Weights rebalanced to include blueprint_conformance at 0.10.
    # infrastructure + code_health each drop from 0.20 → 0.15 to make room.
    weights = {
        "infrastructure": 0.15, "code_health": 0.15, "platform": 0.10,
        "product": 0.10, "revenue": 0.10, "lead_pipeline": 0.05,
        "nats": 0.05, "linear": 0.05, "voice_agents": 0.05,
        "bookings": 0.05, "analytics_platform": 0.05,
        "blueprint_conformance": 0.10,
    }
    weighted_sum = sum(domains[d]["score"] * weights.get(d, 0) for d in domains)
    health_score = max(0, min(100, round(weighted_sum)))
    health_grade = _grade(health_score)

    # Any RED domain floors the health_score
    red_domains = [d for d in domains if domains[d]["status"] == "RED"]
    if red_domains and health_score > 59:
        health_score = min(health_score, 59)
        health_grade = "CRITICAL"

    diag = {
        "cycle_id": f"DIAG-{now_str}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "health_grade": health_grade,
        "health_score": health_score,
        "summary": "",  # filled by LLM layers
        **{d: {k: v for k, v in domains[d].items() if k != "score"}
           for d in domains},
        "_domain_scores": {d: domains[d]["score"] for d in domains},
        "blockers": blockers,
        "blind_spots": blind_spots,
        "recommendations": [],
        "reasoning": "",
        "next_cycle_focus": "",
    }
    log.info(f"[THINK:L0] Deterministic → {health_grade} ({health_score}/100) | "
             f"RED={red_domains or 'none'} | blind_spots={blind_spots or 'none'}")
    return diag


# ── THINK: ANOMALY DETECTION + TRENDS ─────────────────────────────────────────

def detect_anomalies(telemetry: dict, l0_diag: dict) -> dict:
    """Pre-LLM anomaly detection: z-scores, trends, actioned items.

    Uses the SQLite RAG store to compare current metrics against recent
    history.  Flags any metric >2σ from its 10-cycle mean and computes
    trend direction + velocity on open Linear issues.

    Returns a structured dict ready for LLM prompt injection.
    """
    anomalies: list[str] = []
    trends: list[str] = []
    actioned: list[str] = []
    still_open: list[str] = []

    # ── Z-score anomalies from RAG history ────────────────────────────────
    recent_cycles: list[dict] = []
    if HAS_CYCLE_RAG and _cycle_rag:
        try:
            recent_cycles = _cycle_rag.get_recent(n=10)
        except Exception as e:
            log.warning(f"[THINK:ANOMALY] RAG fetch failed: {e}")

    if len(recent_cycles) >= 3:
        # Extract historical metric values for z-score comparison
        def _extract_metric(cycles: list[dict], path: list[str]) -> list[float]:
            vals = []
            for c in cycles:
                before = c.get("before", {})
                obj = before
                for key in path:
                    obj = obj.get(key, {}) if isinstance(obj, dict) else {}
                if isinstance(obj, (int, float)):
                    vals.append(float(obj))
            return vals

        # Metrics to check for anomalies
        metric_paths = [
            (["datadog", "metrics", "cpu_pct", "current"], "cpu_pct"),
            (["datadog", "metrics", "docker_mem_rss_mb", "current"], "docker_mem_rss_mb"),
            (["datadog", "metrics", "load_1", "current"], "load_1"),
            (["datadog", "metrics", "disk_used_pct", "current"], "disk_used_pct"),
            (["gitlab", "open_critical_issues"], "open_critical_issues"),
            (["gitlab", "stuck_pipelines"], "stuck_pipelines"),
            (["nats", "slow_consumers"], "nats_slow_consumers"),
        ]
        for path, label in metric_paths:
            hist = _extract_metric(recent_cycles, path)
            if len(hist) < 3:
                continue
            # Get current value from telemetry
            current_obj = telemetry
            for key in path:
                current_obj = current_obj.get(key, {}) if isinstance(current_obj, dict) else {}
            if not isinstance(current_obj, (int, float)):
                continue
            current_val = float(current_obj)
            mean = sum(hist) / len(hist)
            if mean == 0 and current_val == 0:
                continue
            variance = sum((x - mean) ** 2 for x in hist) / len(hist)
            std = variance ** 0.5
            if std > 0:
                z = (current_val - mean) / std
                if abs(z) > 2.0:
                    direction = "above" if z > 0 else "below"
                    anomalies.append(
                        f"{label} {abs(z):.1f}σ {direction} 10-cycle mean "
                        f"({current_val:.1f} vs avg {mean:.1f})"
                    )

        # Health score trend
        hist_scores = [c.get("health_score") for c in recent_cycles
                       if c.get("health_score") is not None]
        if len(hist_scores) >= 3:
            declining = sum(1 for i in range(len(hist_scores) - 1)
                           if hist_scores[i] < hist_scores[i + 1])
            # hist_scores is newest-first, so hist_scores[i] < hist_scores[i+1] means decline
            # Correction: newest first, so [i] is newer. If newer < older → declining
            if declining >= 3:
                trends.append(
                    f"health_score declining {declining}/{len(hist_scores)-1} cycles "
                    f"({hist_scores[-1]}→{hist_scores[0]})"
                )
            elif declining == 0 and len(hist_scores) >= 3:
                trends.append(
                    f"health_score improving ({hist_scores[-1]}→{hist_scores[0]})"
                )

        # Docker memory trend (rising?)
        mem_hist = _extract_metric(recent_cycles, ["datadog", "metrics", "docker_mem_rss_mb", "current"])
        if len(mem_hist) >= 3:
            rising = sum(1 for i in range(len(mem_hist) - 1) if mem_hist[i] > mem_hist[i + 1])
            if rising >= 3:
                trends.append(
                    f"docker_mem_rss_mb rising {rising}/{len(mem_hist)-1} cycles "
                    f"({mem_hist[-1]:.0f}→{mem_hist[0]:.0f} MB)"
                )

    # ── Linear velocity: recently closed [CLv2] issues ────────────────────
    linear_data = telemetry.get("linear", {})
    done_7d = linear_data.get("done_7d", 0)
    open_count = linear_data.get("open", 0) + linear_data.get("in_progress", 0)
    if done_7d > 0:
        actioned.append(f"{done_7d} Linear issues closed in 7d")
    if open_count > 0:
        still_open.append(f"{open_count} Linear issues still open")
    urgent = linear_data.get("priority_urgent", 0)
    if urgent > 0:
        still_open.append(f"{urgent} urgent priority issues")

    result = {
        "anomalies": anomalies,
        "trends": trends,
        "actioned": actioned,
        "still_open": still_open,
    }
    if anomalies:
        log.info(f"[THINK:ANOMALY] {len(anomalies)} anomalies detected")
    if trends:
        log.info(f"[THINK:ANOMALY] Trends: {trends}")
    return result


def _format_anomaly_block(anomaly_data: dict) -> str:
    """Format anomaly detection results into a structured text block for LLM prompts."""
    lines: list[str] = []
    for a in anomaly_data.get("anomalies", []):
        lines.append(f"ANOMALY: {a}")
    for t in anomaly_data.get("trends", []):
        lines.append(f"TREND: {t}")
    for a in anomaly_data.get("actioned", []):
        lines.append(f"ACTIONED: {a}")
    for s in anomaly_data.get("still_open", []):
        lines.append(f"STILL OPEN: {s}")
    return "\n".join(lines)



# ── THINK: L1 DIAGNOSIS (Bedrock Haiku, Perplexity fallback) ───────────────
def l1_diagnose(l0_diag: dict, anomaly_data: dict,
                rag_context: str = "", model: str = BEDROCK_HAIKU, use_perplexity: bool = False) -> dict:
    """L1: Bedrock Claude Haiku — root-cause analysis (default). Perplexity fallback available.

    Receives the pre-scored L0 diagnostic and anomaly signals.
    Does NOT re-score.  Instead focuses on:
      - Root-cause reasoning across domains
      - Cross-domain correlation
      - (If Perplexity: web-search for known outages / CVEs / advisories)
      - Identifying interconnected failures
    Returns a diagnosis dict (reasoning, root_causes, external_context, blockers).
    """
    system = (
        "You are a JSON-only root-cause analyst for a SaaS platform. You receive "
        "PRE-SCORED domain metrics (scores + status flags already computed by code). "
        "DO NOT re-score or re-grade. Your job is DIAGNOSIS:\n\n"
        "1. Explain WHY each RED/YELLOW domain has that status — root cause analysis\n"
        "2. Identify cross-domain correlations (e.g., stuck pipelines → stale MRs → "
        "   issue debt)\n"
        "3. If you have web-search, check for known outages, CVEs, or "
        "   library advisories that match the observed failures\n"
        "4. Flag any anomalies or trends that suggest a developing problem\n"
        "5. Identify what was missed — blind spots in the data\n\n"
        "Respond with a SINGLE valid JSON object — no markdown, no prose, no code fences.\n\n"
        "REQUIRED JSON SCHEMA:\n"
        "{\n"
        '  "summary": "<2-3 sentence diagnosis in plain English>",\n'
        '  "root_causes": [\n'
        '    {"domain": "<domain_name>", "cause": "<what is wrong and why>", '
        '"severity": "critical|high|medium|low", "evidence": "<data points>"}\n'
        "  ],\n"
        '  "cross_domain_links": [\n'
        '    {"from": "<domain_A>", "to": "<domain_B>", "link": "<how A causes/affects B>"}\n'
        "  ],\n"
        '  "external_context": [\n'
        '    {"topic": "<advisory/outage/CVE>", "relevance": "<how it relates>", '
        '"url": "<source if found>"}\n'
        "  ],\n"
        '  "additional_blockers": ["<blocker not caught by L0>"],\n'
        '  "missed_signals": ["<blind spots or data gaps>"],\n'
        '  "reasoning": "<detailed chain-of-thought explaining the full diagnosis>"\n'
        "}"
    )

    # Build user message with L0 scores + anomaly data
    anomaly_block = _format_anomaly_block(anomaly_data)
    user_msg = (
        f"DETERMINISTIC SCORES (Layer 0 — computed by code, DO NOT change):\n\n"
        f"{json.dumps(l0_diag, indent=2, default=str)}\n\n"
    )
    if anomaly_block:
        user_msg += f"STATISTICAL SIGNALS:\n{anomaly_block}\n\n"
    if rag_context:
        user_msg += f"{rag_context}\n\n"
    user_msg += "Diagnose the root causes and cross-domain correlations. Return JSON only."

    if use_perplexity:
        # --- Perplexity fallback (original code, commented for reference) ---
        # resp = requests.post(
        #     PPLX_API,
        #     headers={
        #         "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY', '')}",
        #         "Content-Type": "application/json",
        #     },
        #     json={
        #         "model": model,
        #         "messages": [
        #             {"role": "system", "content": system},
        #             {"role": "user",   "content": user_msg},
        #         ],
        #         "temperature": 0.2,
        #         "max_tokens": 4096,
        #         "return_images": False,
        #         "return_related_questions": False,
        #         "search_domain_filter": [],
        #     },
        #     timeout=90,
        # )
        # if not resp.ok:
        #     log.error(f"[THINK:L1] Perplexity error {resp.status_code}: {resp.text[:300]}")
        # resp.raise_for_status()
        # resp_json = resp.json()
        # raw = resp_json["choices"][0]["message"]["content"].strip()
        # _usage = resp_json.get("usage", {})
        # _token_meta = {
        #     "prompt_tokens": _usage.get("prompt_tokens", 0),
        #     "completion_tokens": _usage.get("completion_tokens", 0),
        #     "total_tokens": _usage.get("total_tokens", 0),
        #     "model": model,
        # }
        # try:
        #     result = _parse_llm_json(raw)
        # except Exception:
        #     log.warning(f"[THINK:L1] JSON parse failed — raw:\n{raw[:400]}")
        #     result = {
        #         "summary": raw[:500],
        #         "root_causes": [],
        #         "cross_domain_links": [],
        #         "external_context": [],
        #         "additional_blockers": ["Perplexity L1 response could not be parsed as JSON"],
        #         "missed_signals": [],
        #         "reasoning": raw[:1000],
        #     }
        # result["_tokens"] = _token_meta
        # log.info(f"[THINK:L1] Diagnosis: {len(result.get('root_causes', []))} root causes, "
        #          f"{len(result.get('external_context', []))} external refs, "
        #          f"tokens={_token_meta.get('total_tokens', 0)}")
        # return result
        raise NotImplementedError("Perplexity fallback is currently disabled. Set use_perplexity=False.")

    # --- Bedrock Haiku (default) ---
    import boto3  # type: ignore
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.2,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    client = boto3.Session(region_name=AWS_REGION).client("bedrock-runtime")
    resp = client.invoke_model(
        modelId=model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    result = json.loads(resp["body"].read())
    raw = result.get("content", [{}])[0].get("text", "")
    try:
        diagnosis = _parse_llm_json(raw)
    except Exception:
        log.warning(f"[THINK:L1] JSON parse failed — raw:\n{raw[:400]}")
        diagnosis = {
            "summary": raw[:500],
            "root_causes": [],
            "cross_domain_links": [],
            "external_context": [],
            "additional_blockers": ["Bedrock L1 response could not be parsed as JSON"],
            "missed_signals": [],
            "reasoning": raw[:1000],
        }

    # Token tracking from Bedrock response
    _usage = result.get("usage", {})
    _token_meta = {
        "prompt_tokens": _usage.get("input_tokens", 0),
        "completion_tokens": _usage.get("output_tokens", 0),
        "total_tokens": _usage.get("input_tokens", 0) + _usage.get("output_tokens", 0),
        "model": model,
    }
    diagnosis["_tokens"] = _token_meta
    log.info(f"[THINK:L1] Diagnosis: {len(diagnosis.get('root_causes', []))} root causes, "
             f"{len(diagnosis.get('external_context', []))} external refs, "
             f"tokens={_token_meta.get('total_tokens', 0)}")
    return diagnosis


# ── THINK: AZURE OPENAI (L2 — Structured Action Planning) ───────────────────

def _parse_llm_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON, using raw_decode to ignore trailing prose."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    idx = raw.find("{")
    if idx == -1:
        raise ValueError("No JSON object found in LLM response")
    decoder = json.JSONDecoder()
    parsed, _ = decoder.raw_decode(raw[idx:])
    return parsed


def azure_action_plan(l0_diag: dict, l1_diagnosis: dict,
                      anomaly_data: dict, rag_context: str = "") -> dict:
    """L2: Azure GPT-4o — structured action planning.

    Receives L0 scores + L1 diagnosis.  Outputs a prioritized action plan
    with specific commands, file paths, and estimated impact.  This is
    where CODEGEN patches originate from.
    """
    import openai  # type: ignore

    if not _USE_AZURE:
        raise RuntimeError("Azure OpenAI not configured")

    system = (
        "You are a JSON-only action planner for a SaaS platform operations team. "
        "You receive:\n"
        "  1. Pre-scored domain metrics (scores computed by code)\n"
        "  2. A root-cause diagnosis from a previous analysis layer\n"
        "  3. Anomaly/trend signals from statistical analysis\n\n"
        "Your job is to generate a PRIORITIZED ACTION PLAN. For each action:\n"
        "  - Be specific: include exact commands, file paths, config changes\n"
        "  - Estimate impact (which domain score improves, by how much)\n"
        "  - Estimate effort (quick-fix / 1-hour / half-day / multi-day)\n"
        "  - Flag prerequisites and risks\n\n"
        "DO NOT re-score or re-grade. The scores are final.\n\n"
        "Respond with a SINGLE valid JSON object — no markdown, no prose.\n\n"
        "REQUIRED JSON SCHEMA:\n"
        "{\n"
        '  "actions": [\n'
        '    {\n'
        '      "priority": "IMMEDIATE|HIGH|MEDIUM|LOW",\n'
        '      "action": "<specific action description>",\n'
        '      "commands": ["<shell command or code change>"],\n'
        '      "target_files": ["<file paths if applicable>"],\n'
        '      "target_domain": "<infrastructure|code_health|platform|etc>",\n'
        '      "impact_estimate": "<which score improves, by how much>",\n'
        '      "effort": "<quick-fix|1-hour|half-day|multi-day>",\n'
        '      "risk": "<what could go wrong>",\n'
        '      "prerequisites": ["<what must be true first>"]\n'
        "    }\n"
        "  ],\n"
        '  "summary": "<1-2 sentence action plan summary>",\n'
        '  "estimated_score_after": <int 0-100>,\n'
        '  "next_cycle_focus": "<what to monitor after these actions>"\n'
        "}"
    )
    if rag_context:
        system += (
            "\n\nHISTORICAL CONTEXT from past cycles is provided. "
            "Avoid recommending actions that were already taken and fixed. "
            "Prioritize recurring issues that persist across cycles."
        )

    anomaly_block = _format_anomaly_block(anomaly_data)
    user_msg = (
        f"DETERMINISTIC SCORES (Layer 0):\n"
        f"{json.dumps(l0_diag, indent=2, default=str)}\n\n"
        f"ROOT-CAUSE DIAGNOSIS (Layer 1 — Perplexity):\n"
        f"{json.dumps(l1_diagnosis, indent=2, default=str)}\n\n"
    )
    if anomaly_block:
        user_msg += f"STATISTICAL SIGNALS:\n{anomaly_block}\n\n"
    if rag_context:
        user_msg += f"{rag_context}\n\n"
    user_msg += "Generate the prioritized action plan. Return JSON only."

    client = openai.AzureOpenAI(
        api_key=AZURE_OPENAI_KEY,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_version="2024-12-01-preview",
    )
    resp = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.15,
        max_tokens=3000,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    result = json.loads(raw)

    # Token tracking from Azure response
    _usage = resp.usage
    _token_meta = {
        "prompt_tokens": getattr(_usage, "prompt_tokens", 0) if _usage else 0,
        "completion_tokens": getattr(_usage, "completion_tokens", 0) if _usage else 0,
        "total_tokens": getattr(_usage, "total_tokens", 0) if _usage else 0,
        "model": AZURE_OPENAI_DEPLOYMENT,
    }
    result["_tokens"] = _token_meta

    actions = result.get("actions", [])
    log.info(f"[THINK:L2] Azure → {len(actions)} actions planned, "
             f"estimated_score_after={result.get('estimated_score_after', '?')}, "
             f"tokens={_token_meta.get('total_tokens', 0)}")
    return result


# ── THINK: BEDROCK OPUS (L3 — Adversarial Review Gate) ──────────────────────

def bedrock_adversarial_review(l0_diag: dict, l1_diagnosis: dict,
                               l2_action_plan: dict) -> dict:
    """L3: Bedrock Claude Opus — adversarial review / governance gate.

    Challenges the diagnosis + action plan:
      - What's wrong with this plan?
      - What was missed?
      - What could make things worse?
      - Confidence score (0-1) per action
    This is the Council gate — it can downgrade action confidence or
    flag dangerous recommendations.
    """
    import boto3  # type: ignore

    system = (
        "You are an ADVERSARIAL REVIEWER for a SaaS platform operations team. "
        "You receive:\n"
        "  1. Pre-scored domain metrics (Layer 0 — deterministic)\n"
        "  2. Root-cause diagnosis (Layer 1 — Perplexity)\n"
        "  3. Proposed action plan (Layer 2 — GPT-4o)\n\n"
        "Your job is to CHALLENGE this plan:\n"
        "  - What is wrong or risky about each proposed action?\n"
        "  - What root causes or failure modes were MISSED?\n"
        "  - Which actions could make things WORSE if executed?\n"
        "  - Rate your confidence in each action (0.0 = reject, 1.0 = approve)\n"
        "  - Flag any actions that should be BLOCKED (confidence < 0.3)\n\n"
        "You are the governance gate. Be skeptical. Err on the side of caution.\n\n"
        "Respond with a SINGLE valid JSON object — no markdown, no prose.\n\n"
        "REQUIRED JSON SCHEMA:\n"
        "{\n"
        '  "review_summary": "<1-2 sentence overall assessment of the plan>",\n'
        '  "action_reviews": [\n'
        '    {\n'
        '      "action_index": <0-based index into L2 actions array>,\n'
        '      "confidence": <float 0.0-1.0>,\n'
        '      "verdict": "APPROVE|CAUTION|BLOCK",\n'
        '      "risk_assessment": "<what could go wrong>",\n'
        '      "missing_context": "<what L2 failed to consider>",\n'
        '      "suggested_modification": "<how to make the action safer>"\n'
        "    }\n"
        "  ],\n"
        '  "missed_root_causes": ["<root cause not addressed by L1/L2>"],\n'
        '  "dangerous_interactions": ["<action X + action Y could cause Z>"],\n'
        '  "overall_plan_confidence": <float 0.0-1.0>,\n'
        '  "recommended_execution_order": [<action indices in safest order>],\n'
        '  "reasoning": "<detailed adversarial reasoning>"\n'
        "}"
    )

    user_msg = (
        f"DETERMINISTIC SCORES (Layer 0):\n"
        f"{json.dumps(l0_diag, indent=2, default=str)}\n\n"
        f"ROOT-CAUSE DIAGNOSIS (Layer 1 — Perplexity):\n"
        f"{json.dumps(l1_diagnosis, indent=2, default=str)}\n\n"
        f"PROPOSED ACTION PLAN (Layer 2 — GPT-4o):\n"
        f"{json.dumps(l2_action_plan, indent=2, default=str)}\n\n"
        "Challenge this plan. Return JSON only."
    )

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 3000,
        "temperature": 0.2,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    client = boto3.Session(region_name=AWS_REGION).client("bedrock-runtime")
    resp = client.invoke_model(
        modelId=BEDROCK_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    result = json.loads(resp["body"].read())
    raw = result.get("content", [{}])[0].get("text", "")
    review = _parse_llm_json(raw)

    # Token tracking from Bedrock response
    _bedrock_usage = result.get("usage", {})
    _token_meta = {
        "prompt_tokens": _bedrock_usage.get("input_tokens", 0),
        "completion_tokens": _bedrock_usage.get("output_tokens", 0),
        "total_tokens": _bedrock_usage.get("input_tokens", 0) + _bedrock_usage.get("output_tokens", 0),
        "model": BEDROCK_MODEL,
    }
    review["_tokens"] = _token_meta

    confidence = review.get("overall_plan_confidence", 0)
    approved = sum(1 for a in review.get("action_reviews", [])
                   if a.get("verdict") == "APPROVE")
    blocked = sum(1 for a in review.get("action_reviews", [])
                  if a.get("verdict") == "BLOCK")
    log.info(f"[THINK:L3] Bedrock adversarial → confidence={confidence:.2f}, "
             f"approved={approved}, blocked={blocked}, "
             f"tokens={_token_meta.get('total_tokens', 0)}")
    return review


# ── THINK: MULTILAYER ORCHESTRATOR ────────────────────────────────────────────

def think_multilayer(telemetry: dict, model: str = PPLX_MODEL) -> dict:
    """Redesigned THINK pipeline with specialized layers + conditional execution.

    Flow:
      Layer 0: Deterministic scoring (Python thresholds → hard score + flags)
      Anomaly: Z-score + trends + velocity from RAG
      Gate:    Conditional execution based on health_score:
               - HEALTHY (≥95)  → L0 only, skip LLMs
               - MODERATE (60–94) → L0 + L1 (Perplexity diagnosis)
               - CRITICAL (<60) → L0 + L1 + L2 (action plan) + L3 (adversarial gate)
      Merge:   L0 score is ANCHORED (never overridden by LLMs).
               LLM layers add reasoning, actions, and confidence.

    Each layer adds unique value instead of redundant opinions:
      L0 = math  |  L1 = diagnosis  |  L2 = actions  |  L3 = challenge
    """
    _t_think_start = time.time()
    _timing: dict = {}        # Per-layer wall-clock timing (ms)
    _tokens: dict = {}        # Per-layer token usage
    layers_used = ["deterministic"]

    # ── Layer 0: Deterministic scoring ────────────────────────────────────────
    _t0 = time.time()
    l0_diag = score_deterministic(telemetry)
    _timing["l0_ms"] = round((time.time() - _t0) * 1000, 1)
    score = l0_diag["health_score"]
    grade = l0_diag["health_grade"]

    # ── Anomaly detection + trends ────────────────────────────────────────────
    anomaly_data = detect_anomalies(telemetry, l0_diag)
    if anomaly_data.get("anomalies") or anomaly_data.get("trends"):
        layers_used.append("anomaly")

    # ── RAG context retrieval ─────────────────────────────────────────────────
    rag_context = ""
    if HAS_CYCLE_RAG and _cycle_rag:
        try:
            rag_context = _cycle_rag.build_rag_context(telemetry)
            if rag_context:
                log.info(f"[THINK:RAG] Retrieved {_cycle_rag.count()} stored cycles, "
                         f"RAG context: {len(rag_context)} chars")
            else:
                log.info("[THINK:RAG] No historical cycles found (first run?)")
        except Exception as e:
            log.warning(f"[THINK:RAG] Retrieval failed (non-fatal): {e}")

    # ── Conditional execution gate ────────────────────────────────────────────
    l1_diagnosis: dict = {}
    l2_action_plan: dict = {}
    l3_review: dict = {}
    _timing["anomaly_ms"] = round((time.time() - _t0) * 1000, 1)  # includes RAG

    if score >= 95:
        # HEALTHY — no LLMs needed, just log the score
        log.info(f"[THINK:GATE] Score {score} ≥ 95 → HEALTHY path (L0 only, skipping LLMs)")
        l0_diag["summary"] = (
            f"System healthy ({score}/100). All domains within thresholds. "
            f"No LLM analysis required this cycle."
        )
        l0_diag["reasoning"] = (
            f"[deterministic] All domain scores above threshold. "
            f"Blind spots: {l0_diag.get('blind_spots') or 'none'}. "
            f"No anomalies detected." if not anomaly_data.get("anomalies")
            else f"[deterministic] Healthy but {len(anomaly_data['anomalies'])} anomalies noted."
        )

    else:
        # DEGRADING or CRITICAL — run L1 (Perplexity diagnosis)
        log.info(f"[THINK:GATE] Score {score} → {'CRITICAL' if score < 60 else 'DEGRADING'} "
                 f"path (L1{'+ L2 + L3' if score < 60 else ' only'})")
        _t1 = time.time()
        try:
            l1_diagnosis = perplexity_diagnose(
                l0_diag, anomaly_data, rag_context=rag_context, model=model
            )
            _timing["l1_ms"] = round((time.time() - _t1) * 1000, 1)
            layers_used.append("perplexity")

            # Merge L1 into final diag
            l0_diag["summary"] = l1_diagnosis.get("summary", l0_diag.get("summary", ""))
            l0_diag["reasoning"] = l1_diagnosis.get("reasoning", "")
            # Additional blockers from L1
            for b in l1_diagnosis.get("additional_blockers", []):
                if b and b not in l0_diag["blockers"]:
                    l0_diag["blockers"].append(f"[perplexity] {b}")
            l0_diag["root_causes"] = l1_diagnosis.get("root_causes", [])
            l0_diag["cross_domain_links"] = l1_diagnosis.get("cross_domain_links", [])
            l0_diag["external_context"] = l1_diagnosis.get("external_context", [])

        except Exception as e:
            _timing["l1_ms"] = round((time.time() - _t1) * 1000, 1)
            log.error(f"[THINK:L1] Perplexity diagnosis failed: {e}")
            l0_diag["summary"] = (
                f"System {grade.lower()} ({score}/100). "
                f"LLM diagnosis unavailable — relying on deterministic scores only."
            )
            l0_diag["reasoning"] = f"[deterministic] L1 failed: {e}"

        # CRITICAL path: also run L2 (action plan) + L3 (adversarial gate)
        if score < 60:
            # L2: Azure GPT-4o action planning
            if _USE_AZURE:
                _t2 = time.time()
                try:
                    l2_action_plan = azure_action_plan(
                        l0_diag, l1_diagnosis, anomaly_data, rag_context=rag_context
                    )
                    _timing["l2_ms"] = round((time.time() - _t2) * 1000, 1)
                    layers_used.append("azure-openai")

                    # Convert L2 actions into recommendations
                    for action in l2_action_plan.get("actions", []):
                        l0_diag.setdefault("recommendations", []).append({
                            "priority": action.get("priority", "MEDIUM"),
                            "action": action.get("action", ""),
                            "effort": action.get("effort", ""),
                            "target_domain": action.get("target_domain", ""),
                            "impact_estimate": action.get("impact_estimate", ""),
                            "commands": action.get("commands", []),
                            "target_files": action.get("target_files", []),
                        })
                    l0_diag["next_cycle_focus"] = l2_action_plan.get(
                        "next_cycle_focus", l0_diag.get("next_cycle_focus", "")
                    )

                except Exception as e:
                    _timing["l2_ms"] = round((time.time() - _t2) * 1000, 1)
                    log.warning(f"[THINK:L2] Azure action plan failed (non-fatal): {e}")
            else:
                log.info("[THINK:L2] Azure OpenAI not configured — skipping action plan")

            # L3: Bedrock adversarial gate (only if L2 produced actions)
            if l2_action_plan.get("actions"):
                _t3 = time.time()
                try:
                    l3_review = bedrock_adversarial_review(
                        l0_diag, l1_diagnosis, l2_action_plan
                    )
                    _timing["l3_ms"] = round((time.time() - _t3) * 1000, 1)
                    layers_used.append("bedrock-opus")

                    # Annotate recommendations with L3 confidence
                    for ar in l3_review.get("action_reviews", []):
                        idx = ar.get("action_index", -1)
                        recs = l0_diag.get("recommendations", [])
                        if 0 <= idx < len(recs):
                            recs[idx]["_l3_confidence"] = ar.get("confidence", 0)
                            recs[idx]["_l3_verdict"] = ar.get("verdict", "UNKNOWN")
                            recs[idx]["_l3_risk"] = ar.get("risk_assessment", "")
                            if ar.get("suggested_modification"):
                                recs[idx]["_l3_modification"] = ar["suggested_modification"]

                    # Append missed root causes from L3
                    for mc in l3_review.get("missed_root_causes", []):
                        if mc and mc not in l0_diag["blockers"]:
                            l0_diag["blockers"].append(f"[bedrock-adversarial] {mc}")

                    l0_diag["_adversarial"] = {
                        "overall_confidence": l3_review.get("overall_plan_confidence", 0),
                        "blocked_actions": sum(
                            1 for a in l3_review.get("action_reviews", [])
                            if a.get("verdict") == "BLOCK"
                        ),
                        "dangerous_interactions": l3_review.get("dangerous_interactions", []),
                        "execution_order": l3_review.get("recommended_execution_order", []),
                    }

                except Exception as e:
                    _timing["l3_ms"] = round((time.time() - _t3) * 1000, 1)
                    log.warning(f"[THINK:L3] Bedrock adversarial failed (non-fatal): {e}")

    # ── Finalize ──────────────────────────────────────────────────────────────
    _timing["total_ms"] = round((time.time() - _t_think_start) * 1000, 1)

    # Collect token metadata from each layer
    if l1_diagnosis.get("_tokens"):
        _tokens["perplexity"] = l1_diagnosis.pop("_tokens")
    if l2_action_plan.get("_tokens"):
        _tokens["azure-openai"] = l2_action_plan.pop("_tokens")
    if l3_review.get("_tokens"):
        _tokens["bedrock-opus"] = l3_review.pop("_tokens")
    _tokens["_total"] = sum(t.get("total_tokens", 0) for t in _tokens.values()
                            if isinstance(t, dict))

    l0_diag["_layers"] = "+".join(layers_used)
    l0_diag["_anomalies"] = anomaly_data
    l0_diag["_timing"] = _timing
    l0_diag["_tokens"] = _tokens
    l0_diag.setdefault("summary", "")
    l0_diag.setdefault("reasoning", "")
    l0_diag.setdefault("recommendations", [])
    l0_diag.setdefault("next_cycle_focus", "")

    log.info(f"[THINK:FINAL] {l0_diag['health_grade']} ({l0_diag['health_score']}) | "
             f"layers={l0_diag['_layers']} | timing={_timing}")
    return l0_diag


# ── WRITE: SUPABASE failure log ───────────────────────────────────────────────

def write_supabase_failures(errors: list[dict]) -> None:
    """Write each API-level failure as a separate automation_events row.

    These rows have status='error' so read_supabase() picks them up in the
    next run and Perplexity sees the failure history in platform.error_summary.
    """
    if not SB_URL:
        return
    for err in errors:
        if not err.get("phase", "").startswith("API/"):
            continue
        _api_post(f"{SB_URL}/rest/v1/automation_events", _sb_h(), payload={
            "event_type": "control_loop.api_failure",
            "source":     "sanctum",
            "scope":      err.get("phase", ""),
            "event":      err.get("type", ""),
            "status":     "error",
            "payload":    err,
        }, label="SB:failure_log")


# ── WRITE helpers ─────────────────────────────────────────────────────────────

def _rt(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": str(text)[:2000]}}]


def _code_block(content: str, lang: str = "json") -> dict:
    return {"object": "block", "type": "code",
            "code": {"rich_text": _rt(str(content)[:1990]), "language": lang}}


def _heading(text: str, level: int = 2) -> dict:
    return {"object": "block", "type": f"heading_{level}",
            f"heading_{level}": {"rich_text": _rt(text)}}


def _bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rt(text)}}


def _numbered(text: str) -> dict:
    return {"object": "block", "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": _rt(text)}}


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _dot(status: str) -> str:
    return {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(status, "⚪")


# ── WRITE: NOTION ─────────────────────────────────────────────────────────────

def write_notion_page(diag: dict, telemetry: dict) -> str | None:
    cid     = diag.get("cycle_id", f"DIAG-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    grade   = diag.get("health_grade", "UNKNOWN")
    score   = diag.get("health_score", 0)
    emoji   = {"HEALTHY": "✅", "DEGRADING": "⚠️", "CRITICAL": "🔴"}.get(grade, "❓")
    color   = {"HEALTHY": "green_background", "DEGRADING": "yellow_background",
               "CRITICAL": "red_background"}.get(grade, "default")

    inf  = diag.get("infrastructure", {})
    prod = diag.get("product", {})
    plat = diag.get("platform", {})

    title = (
        f"{emoji} {cid} | {grade} ({score}) | "
        f"I:{inf.get('status', '?')} P:{prod.get('status', '?')} S:{plat.get('status', '?')}"
    )

    blocks: list[dict] = [
        {"object": "block", "type": "callout",
         "callout": {
             "rich_text": _rt(f"{grade} | Score: {score}/100\n{diag.get('summary', '')}"),
             "icon": {"type": "emoji", "emoji": emoji},
             "color": color,
         }},
        _divider(),
        _heading(f"{_dot(inf.get('status', ''))} Infrastructure (Datadog)", 2),
        _code_block(json.dumps(inf, indent=2, default=str)),
        _heading(f"{_dot(prod.get('status', ''))} Product (PostHog)", 2),
        _code_block(json.dumps(prod, indent=2, default=str)),
        _heading(f"{_dot(plat.get('status', ''))} Platform (Supabase)", 2),
        _code_block(json.dumps(plat, indent=2, default=str)),
    ]

    # Lead pipeline section — only if data was collected
    lp = diag.get("lead_pipeline", {})
    if lp and lp.get("status"):
        blocks += [
            _heading(f"{_dot(lp.get('status', ''))} Lead Pipeline (Finance Guild)", 2),
            _code_block(json.dumps(lp, indent=2, default=str)),
        ]

    # Code health section
    ch = diag.get("code_health", {})
    if ch and ch.get("status"):
        blocks += [
            _heading(f"{_dot(ch.get('status', ''))} Code Health (GitLab)", 2),
            _code_block(json.dumps(ch, indent=2, default=str)),
        ]

    blocks.append(_divider())

    blockers = diag.get("blockers", [])
    if blockers:
        blocks.append(_heading("🚧 Blockers", 2))
        blocks.extend(_bullet(b) for b in blockers)

    recs = diag.get("recommendations", [])
    if recs:
        blocks.append(_heading("🎯 Recommendations", 2))
        blocks.extend(_numbered(r) for r in recs)

    # Reasoning — chain-of-thought logic behind the diagnosis
    reasoning = diag.get("reasoning", "")
    if reasoning:
        blocks.append(_heading("🧠 Reasoning", 2))
        # Split by layer tags if present
        for chunk in reasoning.split("\n\n"):
            chunk = chunk.strip()
            if chunk:
                blocks.append({"object": "block", "type": "paragraph",
                               "paragraph": {"rich_text": _rt(chunk[:2000])}})

    # Code corrections from Notion (if available in telemetry)
    code_corrections = telemetry.get("_code_corrections", [])
    if code_corrections:
        blocks.append(_heading("🔧 Code Corrections (from Notion Blueprints)", 2))
        for cc in code_corrections[:10]:
            name   = cc.get("name", "untitled")
            src    = cc.get("source_file", "")
            action = cc.get("action", "")
            status = cc.get("status", "")
            grade  = cc.get("caps_grade", "")
            blocks.append(_bullet(
                f"**{name}** — {src} | Action: {action} | Status: {status} | Grade: {grade}"
            ))

    if diag.get("next_cycle_focus"):
        blocks.append(_heading("🔭 Next Cycle Focus", 2))
        blocks.append({"object": "block", "type": "paragraph",
                        "paragraph": {"rich_text": _rt(diag["next_cycle_focus"])}})

    # Source coverage summary
    sources = list(telemetry.keys())
    blocks += [
        _divider(),
        _heading("📡 Source Coverage", 3),
        _bullet(f"Active sources: {', '.join(sources)}"),
        _heading("🗂 Raw Diagnostics JSON", 3),
        _code_block(json.dumps(diag, indent=2, default=str)[:1990]),
    ]

    resp = _api_post(f"{NOTION_API}/pages", _notion_h(), payload={
        "parent": {"page_id": DIAG_PARENT},
        "icon": {"type": "emoji", "emoji": emoji},
        "properties": {
            "title": [{"type": "text", "text": {"content": title}}]
        },
        "children": blocks[:100],
    }, label="NOTION:create")

    page_id = resp.get("id", "") if resp else ""
    if page_id:
        log.info(f"[WRITE] Notion page: https://notion.so/{page_id.replace('-', '')}")
    return page_id or None


def patch_tracker_callout(diag: dict, codegen_result: dict | None = None) -> None:
    grade  = diag.get("health_grade", "UNKNOWN")
    score  = diag.get("health_score", 0)
    cid    = diag.get("cycle_id", "?")
    emoji  = {"HEALTHY": "✅", "DEGRADING": "⚠️", "CRITICAL": "🔴"}.get(grade, "❓")
    color  = {"HEALTHY": "green_background", "DEGRADING": "yellow_background",
              "CRITICAL": "red_background"}.get(grade, "default")

    inf  = diag.get("infrastructure", {})
    prod = diag.get("product", {})

    cpu = inf.get("cpu_avg", "?")
    dau = prod.get("dau", "?")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    text = (
        f"Control Loop v2 — {cid}\n"
        f"Health: {grade} | Score: {score}/100\n"
        f"CPU: {cpu}% | DAU: {dau}\n"
        f"Infra: {inf.get('status','?')} | Product: {prod.get('status','?')} | "
        f"Platform: {diag.get('platform',{}).get('status','?')}\n"
    )

    # Append codegen/rollback summary to EVO callout
    cg = codegen_result or {}
    if cg.get("corrections_generated"):
        patches = cg.get("corrections_generated", 0)
        committed = len(cg.get("gitlab_files", []))
        dg_pass = cg.get("diff_guard_passed", 0)
        dg_fail = cg.get("diff_guard_rejected", 0)
        rb_count = cg.get("rollback_count", 0)
        rb_reverted = cg.get("rollback_reverted", 0)
        text += (
            f"CodeGen: {patches} patches → {committed} committed | "
            f"DiffGuard {dg_pass}✓/{dg_fail}✗"
        )
        if rb_count:
            text += f" | Rollbacks: {rb_count} ({rb_reverted} reverted)"
        if cg.get("branch_rolled_back"):
            text += " | 🔴 BRANCH NUKED"
        if cg.get("gitlab_mr"):
            text += f"\nMR: {cg['gitlab_mr']}"
        text += "\n"

    text += f"Updated: {now_str}"

    _api_patch(f"{NOTION_API}/blocks/{EVO_CALLOUT_ID}", _notion_h(),
               payload={"callout": {"rich_text": _rt(text),
                                     "icon": {"type": "emoji", "emoji": emoji},
                                     "color": color}},
               label="NOTION:patch_callout")
    log.info("[WRITE] Tracker callout patched.")


def append_codegen_to_notion(page_id: str, codegen_result: dict) -> None:
    """Append codegen/rollback summary blocks to the existing Notion diagnostic page.

    Called AFTER write_codegen completes so we have the full rollback data.
    Uses the Notion API 'append children' endpoint to add blocks to the page.
    """
    if not page_id or not codegen_result:
        return
    cg = codegen_result
    if not cg.get("corrections_generated"):
        return

    blocks: list[dict] = [
        _divider(),
        _heading("🔧 Code Generation Results", 2),
    ]

    summary = (
        f"Patches generated: {cg.get('corrections_generated', 0)} | "
        f"Blueprints stored: {cg.get('blueprints_stored', 0)}\n"
        f"Phantom paths rejected: {cg.get('paths_rejected', 0)}\n"
        f"Diff Guard: {cg.get('diff_guard_passed', 0)} passed, "
        f"{cg.get('diff_guard_rejected', 0)} rejected\n"
        f"Files committed: {len(cg.get('gitlab_files', []))}"
    )
    if cg.get("gitlab_mr"):
        summary += f"\nMR: {cg['gitlab_mr']}"

    blocks.append({"object": "block", "type": "paragraph",
                   "paragraph": {"rich_text": _rt(summary)}})

    # Rollback section
    rollbacks = cg.get("rollbacks", [])
    if rollbacks or cg.get("branch_rolled_back"):
        blocks.append(_heading("⚠️ Rollbacks", 3))
        if cg.get("branch_rolled_back"):
            blocks.append(_bullet(
                f"🔴 BRANCH NUKED — checkpoint {cg.get('checkpoint_sha', '?')[:12]}"
            ))
        for rb in rollbacks:
            status = "reverted ✅" if rb.get("reverted") else "revert failed ❌"
            blocks.append(_bullet(
                f"`{rb.get('file', '?')}`: {rb.get('reason', '?')} — {status} "
                f"(expected {rb.get('expected_lines', '?')} lines, "
                f"got {rb.get('actual_lines', '?')} lines)"
            ))

    # Diff guard detail
    if cg.get("diff_guard_passed", 0) + cg.get("diff_guard_rejected", 0) > 0:
        blocks.append(_heading("🏆 Diff Guard Scores", 3))
        blocks.append(_code_block(json.dumps({
            "diff_guard_passed": cg.get("diff_guard_passed", 0),
            "diff_guard_rejected": cg.get("diff_guard_rejected", 0),
            "rollback_count": cg.get("rollback_count", 0),
            "rollback_reverted": cg.get("rollback_reverted", 0),
            "branch_rolled_back": cg.get("branch_rolled_back", False),
            "committed_files": cg.get("gitlab_files", []),
        }, indent=2, default=str)[:1990]))

    try:
        _api_patch(
            f"{NOTION_API}/blocks/{page_id}/children",
            _notion_h(),
            payload={"children": blocks[:20]},
            label="NOTION:append_codegen",
        )
        log.info("[WRITE] Codegen results appended to Notion page")
    except Exception as exc:
        log.warning(f"[WRITE] Codegen Notion append failed: {exc}")


def write_supabase_codegen_event(codegen_result: dict, cycle_id: str) -> None:
    """Log codegen cycle results (incl rollback data) as a Supabase automation event."""
    if not SB_URL or not codegen_result.get("corrections_generated"):
        return
    _api_post(f"{SB_URL}/rest/v1/automation_events", _sb_h(), payload={
        "event_type": "sanctum.codegen.cycle",
        "source":     "sanctum",
        "scope":      "codegen",
        "event":      cycle_id,
        "status":     "rolled_back" if codegen_result.get("branch_rolled_back")
                      else "ok" if codegen_result.get("gitlab_mr") else "no_mr",
        "payload": {
            "corrections_generated": codegen_result.get("corrections_generated", 0),
            "blueprints_stored":     codegen_result.get("blueprints_stored", 0),
            "paths_rejected":        codegen_result.get("paths_rejected", 0),
            "diff_guard_passed":     codegen_result.get("diff_guard_passed", 0),
            "diff_guard_rejected":   codegen_result.get("diff_guard_rejected", 0),
            "rollback_count":        codegen_result.get("rollback_count", 0),
            "rollback_reverted":     codegen_result.get("rollback_reverted", 0),
            "branch_rolled_back":    codegen_result.get("branch_rolled_back", False),
            "committed_files":       codegen_result.get("gitlab_files", []),
            "gitlab_mr":             codegen_result.get("gitlab_mr"),
            "rollbacks":             codegen_result.get("rollbacks", []),
        },
    }, label="SB:codegen_event")
    log.info("[WRITE] Supabase codegen event logged.")


# ── WRITE: SUPABASE audit log ─────────────────────────────────────────────────

def write_supabase_audit(diag: dict, telemetry: dict) -> None:
    if not SB_URL:
        return
    # automation_events columns: id, source, scope, event, status, payload, created_at, event_type, project_path, provider
    _api_post(f"{SB_URL}/rest/v1/automation_events", _sb_h(), payload={
        "event_type": "perplexity.control_loop.v2",
        "source":     "sanctum",
        "scope":      "system",
        "event":      diag.get("cycle_id", "diag"),
        "status":     "ok" if diag["health_grade"] == "HEALTHY" else "flagged",
        "payload": {
            "cycle_id":     diag.get("cycle_id"),
            "health_grade": diag["health_grade"],
            "health_score": diag["health_score"],
            "sources":      list(telemetry.keys()),
        },
    }, label="SB:audit")
    log.info("[WRITE] Supabase audit event logged.")


# ── WRITE: LINEAR ─────────────────────────────────────────────────────────────

def _linear_gql(query: str, variables: dict | None = None) -> dict:
    if not LINEAR_TOKEN:
        return {}
    r = requests.post(
        "https://api.linear.app/graphql",
        headers=_linear_h(),
        json={"query": query, "variables": variables or {}},
        timeout=20,
    )
    if not r.ok:
        log.warning(f"[LINEAR] API error {r.status_code}: {r.text[:200]}")
        return {}
    data = r.json()
    if data.get("errors"):
        log.warning(f"[LINEAR] GraphQL errors: {data['errors'][:2]}")
    return data.get("data", {})


def _linear_state_id(state_name: str = "Todo") -> str | None:
    data = _linear_gql(
        """query($teamId: String!) {
            team(id: $teamId) { states { nodes { id name } } }
        }""",
        {"teamId": LINEAR_TEAM_ID},
    )
    for s in data.get("team", {}).get("states", {}).get("nodes", []):
        if s["name"].lower() == state_name.lower():
            return s["id"]
    return None


def linear_create_issue(title: str, description: str, priority: int = 2) -> str | None:
    if not LINEAR_TOKEN:
        return None
    state_id = _linear_state_id("Todo")
    data = _linear_gql("""
        mutation($title: String!, $desc: String!, $teamId: String!,
                 $priority: Int, $projectId: String, $stateId: String) {
            issueCreate(input: {
                title: $title, description: $desc,
                teamId: $teamId, priority: $priority,
                projectId: $projectId, stateId: $stateId
            }) { success issue { id url identifier } }
        }
    """, {"title": title, "desc": description, "teamId": LINEAR_TEAM_ID,
          "priority": priority, "projectId": LINEAR_PROJECT_ID, "stateId": state_id})
    issue = data.get("issueCreate", {}).get("issue", {})
    url = issue.get("url")
    if url:
        log.info(f"[LINEAR] Created {issue.get('identifier', '?')}: {url}")
    return url


def _linear_fetch_open_issues(prefix: str = "[CLv2]") -> set[str]:
    """Fetch open Linear issues that start with *prefix* and return normalised titles for dedup."""
    data = _linear_gql(
        """query($filter: IssueFilter) {
            issues(filter: $filter, first: 100) {
                nodes { id title state { name } }
            }
        }""",
        {"filter": {
            "team": {"id": {"eq": LINEAR_TEAM_ID}},
            "state": {"type": {"nin": ["completed", "canceled"]}},
        }},
    )
    titles: set[str] = set()
    for iss in data.get("issues", {}).get("nodes", []):
        t = iss.get("title", "")
        if t.startswith(prefix):
            titles.add(t.lower().strip())
    return titles


def write_linear(diag: dict, errors: list[dict]) -> list[str]:
    """Create Linear issues for errors AND each individual recommendation.

    Mirrors the GitLab per-recommendation pattern with title-based dedup so
    the same action is never filed twice while open.
    """
    urls: list[str] = []
    grade = diag.get("health_grade", "UNKNOWN")
    score = diag.get("health_score", 0)
    cycle_id = diag.get("cycle_id", "?")

    # ── Dedup: fetch existing open issues once ────────────────────
    existing_titles: set[str] = set()
    try:
        existing_titles = _linear_fetch_open_issues("[CLv2]")
        if existing_titles:
            log.info(f"[LINEAR:DEDUP] {len(existing_titles)} open [CLv2] issues — will skip duplicates")
    except Exception as exc:
        log.warning(f"[LINEAR:DEDUP] fetch failed (non-fatal): {exc}")

    def _dedup_create(title: str, desc: str, prio: int) -> str | None:
        if title.lower().strip() in existing_titles:
            log.info(f"[LINEAR:DEDUP] Skipping — already open: {title[:70]}")
            return None
        url = linear_create_issue(title, desc, prio)
        if url:
            existing_titles.add(title.lower().strip())
        return url

    # ── 1. Issue for READ/THINK/WRITE errors ─────────────────────
    if errors:
        body = "## Control Loop v2 Errors\n\n"
        for e in errors:
            body += f"### {e.get('phase')} — {e.get('type')}\n```\n{e.get('detail')}\n```\n\n"
        title = f"[CLv2] Errors ({len(errors)}) — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        url = _dedup_create(title, body, priority=1)
        if url:
            urls.append(url)

    # ── 2. Per-recommendation issues (DEGRADING or CRITICAL) ─────
    if grade in ("DEGRADING", "CRITICAL"):
        recs = diag.get("recommendations", [])
        blockers_text = "\n".join(f"- {b}" for b in diag.get("blockers", []))

        for i, rec in enumerate(recs, 1):
            # Normalise rec to string
            if isinstance(rec, dict):
                action = rec.get("action", "") or json.dumps(rec, default=str)
                effort = rec.get("effort", "")
                prio_label = rec.get("priority", "MEDIUM")
            else:
                action = str(rec)
                effort = ""
                prio_label = "MEDIUM"

            lin_priority = {"IMMEDIATE": 1, "HIGH": 2, "MEDIUM": 3}.get(prio_label, 3)
            if grade == "CRITICAL":
                lin_priority = min(lin_priority, 2)

            title = f"[CLv2] [{cycle_id}] Action {i}: {action[:100]}"
            body = (
                f"## Source\nAuto-generated by Perplexity Control Loop v2 diagnostic.\n\n"
                f"- **Cycle:** `{cycle_id}`\n"
                f"- **Health:** {grade} ({score}/100)\n"
                f"- **Layers:** {diag.get('_layers', 'unknown')}\n\n"
                f"## Recommended Action\n{action}\n\n"
            )
            if effort:
                body += f"**Effort:** {effort}\n\n"
            if blockers_text:
                body += f"## Related Blockers\n{blockers_text}\n\n"
            body += f"## Summary\n{diag.get('summary', '')}\n"

            url = _dedup_create(title, body, lin_priority)
            if url:
                urls.append(url)

    return urls


# ── WRITE: AUTOMATED CODE GENERATION (v2 — AEGIS-gated) ─────────────────────
# Generates surgical patches for EXISTING files only; validates every path
# against the real repo tree; integrates AEGIS lineage (F977) for diff tracking;
# rejects hallucinated phantom paths; never creates new files (that's a human
# decision tracked via Linear / GitLab issues instead).
# ─────────────────────────────────────────────────────────────────────────────

# Lazy-init caches
_codegen_client = None
_repo_tree_cache: dict | None = None          # {path: size} for all files on main
_REPO_TREE_TTL = 600                          # seconds
_repo_tree_ts: float = 0.0


def _gl_read_raw(filepath: str, ref: str = "main") -> str:
    """Read raw file content from GitLab.

    Cannot use gl_get() because it calls .json() but /raw returns plain text.
    Returns the file content as a string, or empty string on failure.
    """
    if not HAS_GITLAB_MODULE:
        return ""
    from gitlab_source import GL_PID, GL_API, GL_TOK
    if not GL_PID:
        return ""
    try:
        encoded = requests.utils.quote(filepath, safe="")
        url = f"{GL_API}/projects/{GL_PID}/repository/files/{encoded}/raw"
        r = requests.get(
            url,
            headers={"PRIVATE-TOKEN": GL_TOK},
            params={"ref": ref},
            timeout=30,
        )
        if r.status_code == 200:
            return r.text
        return ""
    except Exception:
        return ""

def _get_codegen_client():
    """Lazy-init the orchestrator BedrockClient (Sonnet) for code generation."""
    global _codegen_client
    if _codegen_client is None:
        try:
            from orchestrator.bedrock_client import BedrockClient, BedrockConfig
            _codegen_client = BedrockClient(BedrockConfig(
                region="us-west-2",
                primary_model="us.anthropic.claude-sonnet-4-20250514-v1:0",
                fallback_model="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                max_tokens=6000,
                temperature=0.15,
            ))
        except Exception as exc:
            log.warning(f"[CODEGEN] Could not init BedrockClient: {exc}")
    return _codegen_client


# ── Repo tree resolver ────────────────────────────────────────────────────────

def _fetch_repo_tree(ref: str = "main") -> dict[str, int]:
    """Fetch a targeted file tree from GitLab (main branch).

    The repo has 61k+ items — a full recursive tree fetch is not viable
    (the first 2500+ items are all directories).  Instead we:
      1. Fetch top-level items (non-recursive) for root blobs
      2. Fetch key project directories recursively via per-path queries
    This gets ~500–800 actionable files in ~5s instead of hanging forever.

    Returns a dict mapping every file path → 0.
    Cached for _REPO_TREE_TTL seconds.
    """
    global _repo_tree_cache, _repo_tree_ts
    if _repo_tree_cache is not None and (time.time() - _repo_tree_ts) < _REPO_TREE_TTL:
        return _repo_tree_cache

    if not HAS_GITLAB_MODULE:
        return {}
    from gitlab_source import gl_get, GL_PID
    if not GL_PID:
        return {}

    # Key directories where actionable code lives.  Ordered by priority.
    KEY_DIRS = [
        "tools", "tools/orchestrator", ".gitlab", ".github/workflows",
        "services", "citadel_lite/src", "citadel_lite", "docker",
        "scripts", "data", ".nexus", "config", "src", "lib",
        "api", "public", "pages", "supabase",
    ]

    tree: dict[str, int] = {}
    t0 = time.time()

    # Step 1: top-level blobs (package.json, .gitlab-ci.yml, etc.)
    top = gl_get(
        f"/projects/{GL_PID}/repository/tree",
        {"ref": ref},
        "codegen:tree:root",
    )
    if top:
        for item in top:
            if item.get("type") == "blob":
                tree[item["path"]] = 0

    # Step 2: targeted per-directory recursive listing
    for kd in KEY_DIRS:
        if len(tree) >= 2000:       # safety cap
            break
        items = gl_get(
            f"/projects/{GL_PID}/repository/tree",
            {"ref": ref, "path": kd, "recursive": "true"},
            f"codegen:tree:{kd}",
        )
        if items:
            for item in items:
                if item.get("type") == "blob":
                    tree[item["path"]] = 0

    elapsed = time.time() - t0
    _repo_tree_cache = tree
    _repo_tree_ts = time.time()
    log.info(f"[CODEGEN:TREE] Fetched {len(tree)} files from {ref} "
             f"({len(KEY_DIRS)} dirs scanned, {elapsed:.1f}s)")
    return tree


def _resolve_path(hint: str, repo_tree: dict[str, int]) -> str | None:
    """Resolve a fuzzy file hint to an actual path in the repo tree.

    Strategy (ordered):
      1. Exact match           → return it
      2. Basename match        → return the real path
      3. Suffix match (a/b.py) → return the closest real path
      4. No match              → None  (reject — this is a phantom path)
    """
    # Strip leading ./ or .\ path prefixes, but NOT lone leading dots
    # (e.g. "./tools/x.py" → "tools/x.py", but ".gitlab-ci.yml" stays as-is)
    while hint.startswith("./") or hint.startswith(".\\"):
        hint = hint[2:]
    hint = hint.lstrip("/\\")
    if not hint:
        return None

    # 1) Exact
    if hint in repo_tree:
        return hint

    # 2) Basename
    base = os.path.basename(hint)
    candidates = [p for p in repo_tree if os.path.basename(p) == base]
    if len(candidates) == 1:
        return candidates[0]

    # If multiple basename matches, try suffix match
    if candidates:
        for c in candidates:
            if c.endswith(hint):
                return c

    # 3) Suffix match (e.g. "src/nats_client.py" matches "services/nats/src/nats_client.py")
    suffix_candidates = [p for p in repo_tree if p.endswith(hint)]
    if len(suffix_candidates) == 1:
        return suffix_candidates[0]

    # 4) Dot-prefix retry — Sonnet sometimes drops leading dots from dotfiles
    #    e.g. outputs "gitlab-ci.yml" instead of ".gitlab-ci.yml"
    if not hint.startswith(".") and "." not in os.path.dirname(hint):
        dot_hint = "." + hint
        if dot_hint in repo_tree:
            return dot_hint
        dot_base = "." + base
        dot_candidates = [p for p in repo_tree if os.path.basename(p) == dot_base]
        if len(dot_candidates) == 1:
            return dot_candidates[0]

    return None


def _build_tree_summary(repo_tree: dict[str, int], max_entries: int = 300) -> str:
    """Build a compact directory-tree string for the LLM context.

    Only includes top-level directories and 2 levels of depth to keep
    the prompt short but grounded in reality.
    """
    dirs: dict[str, list[str]] = {}
    for path in sorted(repo_tree):
        parts = path.split("/")
        if len(parts) >= 2:
            top = parts[0]
            rest = "/".join(parts[1:])
            dirs.setdefault(top, []).append(rest)
        else:
            dirs.setdefault("(root)", []).append(path)

    lines: list[str] = []
    for d in sorted(dirs):
        files = dirs[d]
        # Show up to 5 files per top-level dir
        shown = files[:5]
        lines.append(f"{d}/")
        for f in shown:
            lines.append(f"  {f}")
        if len(files) > 5:
            lines.append(f"  … (+{len(files) - 5} more)")
        if len(lines) >= max_entries:
            lines.append(f"… ({len(repo_tree) - max_entries} files omitted)")
            break
    return "\n".join(lines)


# ── Golden Copy Diff Guard (Book Maker pattern) ─────────────────────────────
# Mirrors the BookMaker BOOK_GOV golden copy approach:
#   1. Snapshot the original ("golden copy") and compute its SHA-256 fingerprint
#   2. Compare structural metrics: preservation, API surface, imports, size
#   3. Reject patches that destroy the original instead of surgically fixing it
#   4. Attach rollback metadata (golden_sha, scores) for Notion rollback feature
# ─────────────────────────────────────────────────────────────────────────────

_GOLDEN_THRESHOLDS = {
    "min_preservation":  0.50,   # must keep ≥50% of original non-blank lines
    "max_size_ratio":    3.0,    # patched may not exceed 3× original size
    "min_size_ratio":    0.30,   # patched may not shrink below 30% of original
    "max_api_lost":      0,      # zero tolerance for lost public functions/classes
}


def _golden_copy_analysis(
    original: str,
    patched: str,
    filepath: str,
    thresholds: dict | None = None,
) -> dict:
    """Compare patched code against the golden copy (original from main).

    Returns a dict with:
      - golden_sha256:  SHA-256 of the unmodified original
      - patched_sha256: SHA-256 of the generated output
      - preservation_ratio: fraction of original non-blank lines kept
      - api_preserved / api_lost: public function/class signatures kept vs lost
      - import_preserved / import_lost / import_added: import statement drift
      - size_ratio: patched_bytes / original_bytes
      - scores: {preservation, api_surface, import_stability, size} 0-10 each
      - verdict: "PASS" or "REJECT"
      - reject_reasons: list of why it failed (empty on PASS)
    """
    import hashlib
    import difflib

    t = {**_GOLDEN_THRESHOLDS, **(thresholds or {})}

    golden_sha = hashlib.sha256(original.encode()).hexdigest()
    patched_sha = hashlib.sha256(patched.encode()).hexdigest()

    orig_lines = original.splitlines()
    patch_lines = patched.splitlines()
    orig_nonblank = {l.rstrip() for l in orig_lines if l.strip()}
    patch_nonblank = {l.rstrip() for l in patch_lines if l.strip()}

    # ── Preservation ratio ──
    preserved = orig_nonblank & patch_nonblank
    preservation_ratio = len(preserved) / max(len(orig_nonblank), 1)

    # ── API surface (functions + classes) ──
    def extract_api(lines):
        api = set()
        for l in lines:
            s = l.strip()
            if s.startswith("def ") or s.startswith("async def "):
                # Extract function name
                name = s.split("(")[0].replace("async ", "").replace("def ", "").strip()
                if not name.startswith("_"):  # public API only
                    api.add(f"def {name}")
            elif s.startswith("class "):
                name = s.split("(")[0].split(":")[0].replace("class ", "").strip()
                api.add(f"class {name}")
        return api

    orig_api = extract_api(orig_lines)
    patch_api = extract_api(patch_lines)
    api_preserved = orig_api & patch_api
    api_lost = orig_api - patch_api
    api_added = patch_api - orig_api

    # ── Import drift ──
    def extract_imports(lines):
        return {l.strip() for l in lines if l.strip().startswith(("import ", "from "))}

    orig_imports = extract_imports(orig_lines)
    patch_imports = extract_imports(patch_lines)
    import_preserved = orig_imports & patch_imports
    import_lost = orig_imports - patch_imports
    import_added = patch_imports - orig_imports

    # ── Size ratio ──
    size_ratio = len(patched) / max(len(original), 1)

    # ── Unified diff (for Notion rollback) ──
    unified_diff = "".join(difflib.unified_diff(
        orig_lines, patch_lines,
        fromfile=f"a/{filepath}", tofile=f"b/{filepath}",
        lineterm="",
    ))

    # ── Scores (0–10, Book Maker self-grade pattern) ──
    preservation_score = min(10.0, preservation_ratio * 10)
    api_score = 10.0 if not api_lost else max(0.0, 10.0 - len(api_lost) * 5.0)
    import_score = 10.0 if not import_lost else max(0.0, 10.0 - len(import_lost) * 2.0)
    size_score = 10.0 if 0.5 <= size_ratio <= 2.0 else max(0.0, 10.0 - abs(size_ratio - 1.0) * 3.0)

    # ── Verdict ──
    reject_reasons: list[str] = []
    if preservation_ratio < t["min_preservation"]:
        reject_reasons.append(
            f"Preservation {preservation_ratio:.0%} < {t['min_preservation']:.0%} — "
            f"original code destroyed ({len(orig_nonblank) - len(preserved)}/{len(orig_nonblank)} lines lost)"
        )
    if size_ratio > t["max_size_ratio"]:
        reject_reasons.append(
            f"Size ratio {size_ratio:.1f}x > {t['max_size_ratio']:.1f}x — "
            f"LLM bloated file from {len(original)} to {len(patched)} bytes"
        )
    if size_ratio < t["min_size_ratio"] and len(original) > 100:  # don't flag tiny files
        reject_reasons.append(
            f"Size ratio {size_ratio:.1f}x < {t['min_size_ratio']:.1f}x — "
            f"LLM gutted file from {len(original)} to {len(patched)} bytes"
        )
    if len(api_lost) > t["max_api_lost"]:
        reject_reasons.append(
            f"Lost {len(api_lost)} public API(s): {sorted(api_lost)[:5]} — "
            f"callers will break"
        )

    verdict = "REJECT" if reject_reasons else "PASS"

    return {
        "golden_sha256":     golden_sha,
        "patched_sha256":    patched_sha,
        "preservation_ratio": round(preservation_ratio, 3),
        "api_preserved":     sorted(api_preserved),
        "api_lost":          sorted(api_lost),
        "api_added":         sorted(api_added),
        "import_preserved":  sorted(import_preserved),
        "import_lost":       sorted(import_lost),
        "import_added":      sorted(import_added),
        "size_ratio":        round(size_ratio, 3),
        "unified_diff":      unified_diff[:8000],   # cap for Notion
        "scores": {
            "preservation":     round(preservation_score, 1),
            "api_surface":      round(api_score, 1),
            "import_stability": round(import_score, 1),
            "size":             round(size_score, 1),
        },
        "verdict":           verdict,
        "reject_reasons":    reject_reasons,
    }


# ── AEGIS lineage integration ────────────────────────────────────────────────

def _compute_aegis_diff(original: str, patched: str, filepath: str) -> dict:
    """Run AEGIS F977 diff engine on before/after code.

    Returns a lightweight dict with LID and diff stats, or empty dict on failure.
    """
    try:
        sake_dir = Path(__file__).parent.parent / "CITADEL_LLM" / "SAKE"
        if not sake_dir.exists():
            return {}

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "F977_aegis_lineage_tracker",
            str(sake_dir / "F977_aegis_lineage_tracker.py"),
        )
        if not spec or not spec.loader:
            return {}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        tracker = mod.AEGISLineageTracker(patched, domain_tag="CODE")
        tracker.extract_genome()
        tracker.compute_lid()
        tracker.compare_to_prior(prior_source=original)
        output = tracker.emit_output()
        return {
            "lid":          output.get("lid", ""),
            "diff_stats":   output.get("diff_stats", {}),
            "regen_count":  output.get("regen_count", 0),
        }
    except Exception as exc:
        log.debug(f"[CODEGEN:AEGIS] Diff failed for {filepath}: {exc}")
        return {}


# ── Classifier ────────────────────────────────────────────────────────────────

def _classify_recommendation(rec) -> dict:
    """Extract structured fields from a recommendation (str or dict).

    Returns: {action, priority, effort, is_code_actionable, source_hint}
    """
    if isinstance(rec, dict):
        action = rec.get("action", "") or json.dumps(rec, default=str)
        priority = rec.get("priority", "MEDIUM")
        effort = rec.get("effort", "")
    else:
        action = str(rec)
        priority = "MEDIUM"
        effort = ""
        upper = action.upper()
        if upper.startswith("IMMEDIATE:") or "[IMMEDIATE]" in upper:
            priority = "IMMEDIATE"
        elif upper.startswith("HIGH:") or "[HIGH]" in upper:
            priority = "HIGH"

    # Heuristics: does this look like a code-fixable issue?
    CODE_SIGNALS = [
        "fix", "refactor", "update", "patch", "resolve", "debug",
        "configure", "restore",
        ".py", ".ts", ".js", ".yaml", ".yml", ".json", ".sql",
        "pipeline", "Dockerfile", "nginx",
    ]
    is_code = any(sig.lower() in action.lower() for sig in CODE_SIGNALS)

    # Try to extract a file path hint from the action text
    file_match = re.search(
        r'[\w./\\-]+\.(?:py|ts|js|tsx|jsx|yaml|yml|json|sql|toml|cfg|env|sh|ps1)',
        action,
    )
    source_hint = file_match.group(0) if file_match else ""

    return {
        "action":             action,
        "priority":           priority,
        "effort":             effort,
        "is_code_actionable": is_code,
        "source_hint":        source_hint,
        # L3 adversarial annotations (if present)
        "_l3_verdict":        rec.get("_l3_verdict") if isinstance(rec, dict) else None,
        "_l3_confidence":     rec.get("_l3_confidence") if isinstance(rec, dict) else None,
        "_l3_risk":           rec.get("_l3_risk", "") if isinstance(rec, dict) else "",
    }


# ── Core generation ──────────────────────────────────────────────────────────

def generate_code_corrections(diag: dict, telemetry: dict, max_patches: int = 5) -> list[dict]:
    """Use Bedrock Sonnet to generate surgical patches for EXISTING files.

    Key differences from v1:
    - Fetches the real repo tree and feeds it to the prompt
    - Requires all ### FILE: paths to resolve to real files
    - Reads the original file content so the LLM can produce a real diff
    - Runs AEGIS F977 lineage on before/after for traceability
    - Rejects any patch targeting a non-existent file
    """
    grade = diag.get("health_grade", "UNKNOWN")
    if grade not in ("DEGRADING", "CRITICAL"):
        return []

    client = _get_codegen_client()
    if client is None:
        log.warning("[CODEGEN] BedrockClient unavailable — skipping")
        return []

    # Fetch the real repo tree from GitLab
    repo_tree = _fetch_repo_tree()
    if not repo_tree:
        log.warning("[CODEGEN] Empty repo tree — cannot ground code generation")
        return []
    tree_summary = _build_tree_summary(repo_tree)

    recs = diag.get("recommendations", [])
    classified = [_classify_recommendation(r) for r in recs]
    actionable = [c for c in classified if c["is_code_actionable"]]
    if not actionable:
        log.info("[CODEGEN] No code-actionable recommendations")
        return []

    # ── L3 ADVERSARIAL GATE ──────────────────────────────────────────────
    # Filter out actions that L3 marked as BLOCK.
    # If overall_plan_confidence < 0.3, skip codegen entirely.
    adversarial = diag.get("_adversarial", {})
    overall_confidence = adversarial.get("overall_confidence", 1.0)
    if overall_confidence < 0.3:
        log.warning(f"[CODEGEN:L3_GATE] overall_plan_confidence={overall_confidence:.2f} "
                    f"< 0.3 — skipping ALL code generation this cycle")
        return []

    pre_filter = len(actionable)
    actionable = [
        c for c in actionable
        if c.get("_l3_verdict", "APPROVE") != "BLOCK"
    ]
    blocked = pre_filter - len(actionable)
    if blocked:
        log.info(f"[CODEGEN:L3_GATE] Filtered {blocked}/{pre_filter} actions "
                 f"marked BLOCK by L3 adversarial review")
    if not actionable:
        log.info("[CODEGEN:L3_GATE] All actions blocked by L3 — skipping codegen")
        return []

    prio_order = {"IMMEDIATE": 0, "HIGH": 1, "MEDIUM": 2}
    actionable.sort(key=lambda c: prio_order.get(c["priority"], 9))
    actionable = actionable[:max_patches]

    corrections: list[dict] = []
    cycle_id = diag.get("cycle_id", "unknown")

    context_summary = json.dumps({
        "health_grade": grade,
        "health_score": diag.get("health_score", 0),
        "blockers":     diag.get("blockers", [])[:5],
        "reasoning":    diag.get("reasoning", "")[:800],
    }, indent=2, default=str)

    for i, rec in enumerate(actionable, 1):
        log.info(f"[CODEGEN] Generating patch {i}/{len(actionable)}: "
                 f"{rec['action'][:80]}…")

        # Resolve the file hint to a real path
        resolved = _resolve_path(rec["source_hint"], repo_tree) if rec["source_hint"] else None

        # Read the original file content from GitLab for context
        original_content = ""
        if resolved:
            original_content = _gl_read_raw(resolved)

        system_prompt = (
            "You are a senior platform engineer at Citadel Nexus.\n"
            "You produce MINIMAL, SURGICAL patches to EXISTING files.\n\n"
            "GOLDEN COPY RULES (violation = automatic rejection):\n"
            "- You will be given the ORIGINAL file content (the 'golden copy').\n"
            "- You MUST preserve the ENTIRE original file structure.\n"
            "- ADD or MODIFY only the specific lines that fix the issue.\n"
            "- You MUST keep ALL existing functions, classes, imports, and comments.\n"
            "- Do NOT rewrite, reorganize, or 'improve' unrelated code.\n"
            "- Do NOT change function signatures, class names, or module-level API.\n"
            "- Do NOT remove the graceful-fallback patterns (try/except ImportError).\n"
            "- Do NOT change logger names, env var references, or config patterns.\n"
            "- Your output is diff-checked: if >50% of original lines are missing,\n"
            "  or any public function/class is removed, or size bloats >3x,\n"
            "  your patch is REJECTED and discarded automatically.\n\n"
            "OUTPUT FORMAT:\n"
            "- Use ### FILE: <exact-repo-path> headers (from REPOSITORY TREE only).\n"
            "- Output the COMPLETE file content with your surgical additions.\n"
            "- Mark each change with # FIX: <brief explanation>.\n"
            "- If no fix is needed, output NOTHING.\n"
            "- NEVER create new files. NEVER invent paths.\n\n"
            "## REPOSITORY TREE (abridged)\n"
            f"{tree_summary}\n"
        )

        user_message = (
            f"## Diagnostic Context\n{context_summary}\n\n"
            f"## Recommendation to Implement\n"
            f"Priority: {rec['priority']}\n"
            f"Action: {rec['action']}\n"
        )
        if resolved:
            user_message += f"Target file: {resolved}\n"
            if original_content:
                # Include the FULL golden copy — the LLM must preserve it
                user_message += (
                    f"\n## GOLDEN COPY of {resolved} (you MUST preserve this structure)\n"
                    f"```\n{original_content[:6000]}\n```\n"
                    f"\nIMPORTANT: Your output must contain ALL of the above code, "
                    f"with ONLY the minimal lines added/changed to fix the issue. "
                    f"Do NOT rewrite, reorganize, or remove anything.\n"
                )
        elif rec["source_hint"]:
            user_message += (
                f"Hint: {rec['source_hint']} (does NOT exist in repo — "
                f"find the closest real file from the tree above)\n"
            )

        # Pipeline failure context
        gl_data = telemetry.get("gitlab", {})
        failed_pipelines = gl_data.get("pipelines", {}).get("failed_pipelines", [])
        if failed_pipelines and "pipeline" in rec["action"].lower():
            user_message += (
                "\n## Recent Pipeline Failures\n"
                + json.dumps(failed_pipelines[:3], indent=2, default=str)
            )

        try:
            result = client.converse(
                system_prompt=system_prompt,
                user_message=user_message,
                max_tokens=4000,
                temperature=0.1,
            )
            generated_code = result["text"].strip()

            # Parse ### FILE: blocks
            file_blocks: dict[str, str] = {}
            if "### FILE:" in generated_code:
                parts = re.split(r"### FILE:\s*(.+)", generated_code)
                for j in range(1, len(parts), 2):
                    fp = parts[j].strip()
                    # Strip ./ or .\ prefixes but preserve leading dots on dotfiles
                    while fp.startswith("./") or fp.startswith(".\\"):
                        fp = fp[2:]
                    fp = fp.lstrip("/\\")
                    content = parts[j + 1].strip() if j + 1 < len(parts) else ""
                    content = re.sub(r"^```\w*\n?", "", content)
                    content = re.sub(r"\n?```$", "", content)
                    file_blocks[fp] = content
            elif resolved:
                code = generated_code
                if code.startswith("```"):
                    code = code.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                file_blocks[resolved] = code

            # ── PATH VALIDATION GATE ──
            # Reject any path that doesn't exist in the real repo tree
            validated: dict[str, str] = {}
            rejected: list[str] = []
            for fp, content in file_blocks.items():
                real_path = _resolve_path(fp, repo_tree)
                if real_path:
                    validated[real_path] = content
                else:
                    rejected.append(fp)

            if rejected:
                log.warning(f"[CODEGEN:GATE] Rejected {len(rejected)} phantom path(s): "
                            f"{rejected[:3]}")
            if not validated:
                log.warning(f"[CODEGEN:GATE] Patch {i} produced 0 valid files — skipping")
                continue

            # ── GOLDEN COPY DIFF GUARD (Book Maker pattern) ──
            # Compare each file against the golden copy from main.
            # Reject patches that destroy the original instead of fixing it.
            golden_data: dict[str, dict] = {}
            diff_rejected: list[str] = []
            for fp in list(validated.keys()):
                orig = _gl_read_raw(fp)
                if not orig:
                    continue  # new-ish file, skip diff guard
                analysis = _golden_copy_analysis(orig, validated[fp], fp)
                golden_data[fp] = analysis
                if analysis["verdict"] == "REJECT":
                    reasons = "; ".join(analysis["reject_reasons"])
                    log.warning(f"[CODEGEN:DIFF_GUARD] REJECTED {fp}: {reasons}")
                    diff_rejected.append(fp)
                    del validated[fp]  # remove from validated set
                else:
                    log.info(f"[CODEGEN:DIFF_GUARD] PASS {fp} — "
                             f"preserved={analysis['preservation_ratio']:.0%} "
                             f"size={analysis['size_ratio']:.1f}x "
                             f"api_lost={len(analysis['api_lost'])} "
                             f"scores={analysis['scores']}")

            rejected.extend(diff_rejected)
            if not validated:
                log.warning(f"[CODEGEN:DIFF_GUARD] Patch {i} — all files rejected "
                            f"by diff guard — skipping")
                continue

            # ── AEGIS LINEAGE ──
            aegis_data: dict[str, dict] = {}
            for fp, content in validated.items():
                # Try to read original for diff
                orig = _gl_read_raw(fp)
                if orig:
                    aegis = _compute_aegis_diff(orig, content, fp)
                    if aegis:
                        aegis_data[fp] = aegis

            correction = {
                "index":       i,
                "action":      rec["action"],
                "priority":    rec["priority"],
                "source_hint": rec["source_hint"],
                "files":       validated,
                "rejected":    rejected,
                "golden":      golden_data,
                "aegis":       aegis_data,
                "model":       result.get("model", ""),
                "latency_ms":  result.get("latency_ms", 0),
                "usage":       {
                    "input":  getattr(result.get("usage"), "input_tokens", 0),
                    "output": getattr(result.get("usage"), "output_tokens", 0),
                    "cost":   round(getattr(result.get("usage"), "total_cost", 0), 4),
                },
                "cycle_id":    cycle_id,
            }
            corrections.append(correction)
            total_lines = sum(c.count("\n") + 1 for c in validated.values())
            log.info(f"[CODEGEN] Patch {i}: {len(validated)} valid file(s), "
                     f"{len(rejected)} rejected, {total_lines} lines, "
                     f"{correction['usage']['cost']:.4f}$"
                     + (f" AEGIS LIDs: {[a.get('lid','') for a in aegis_data.values()]}"
                        if aegis_data else ""))

        except Exception as exc:
            log.warning(f"[CODEGEN] Patch {i} failed: {exc}")

    log.info(f"[CODEGEN] Generated {len(corrections)}/{len(actionable)} patches "
             f"(all paths validated against repo tree)")
    return corrections


# ── Notion blueprint storage ─────────────────────────────────────────────────

# --- Property mapping constants (Fix 1 — Notion Code Blueprint DB selects) ---
CAPS_GRADE_MAP = {
    "IMMEDIATE": "F",
    "CRITICAL":  "F",
    "HIGH":      "D",
    "MEDIUM":    "C",
    "LOW":       "B",
    "INFO":      "A",
}

PATCH_ACTION_MAP = {
    "FIX":       "GENERATE",
    "PATCH":     "GENERATE",
    "REFACTOR":  "REFACTOR",
    "DOCUMENT":  "DOCUMENT",
    "ANALYZE":   "ANALYZE",
}

PATCH_TYPE_MAP = {
    "FILE":      "MODULE",
    "FUNCTION":  "FUNCTION",
    "CLASS":     "CLASS",
    "ENDPOINT":  "ENDPOINT",
    "SCHEMA":    "SCHEMA",
}


def _map_blueprint_properties(raw: dict) -> dict:
    """Map internal codegen labels → Notion Code Blueprint DB select options."""
    return {
        "CAPS Grade": CAPS_GRADE_MAP.get(raw.get("severity", "MEDIUM"), "C"),
        "Status":     "PENDING",
        "Action":     PATCH_ACTION_MAP.get(raw.get("action", "FIX"), "GENERATE"),
        "Type":       PATCH_TYPE_MAP.get(raw.get("patch_type", "FILE"), "MODULE"),
    }


# --- Code language mapping (Fix 2 — "text" → "plain text" + extensions) ------
EXT_TO_NOTION_LANG = {
    ".py":    "python",
    ".js":    "javascript",
    ".ts":    "typescript",
    ".cs":    "c#",
    ".yaml":  "yaml",
    ".yml":   "yaml",
    ".json":  "json",
    ".sh":    "bash",
    ".bash":  "bash",
    ".sql":   "sql",
    ".html":  "html",
    ".css":   "css",
    ".toml":  "toml",
    ".rs":    "rust",
    ".go":    "go",
    ".java":  "java",
    ".rb":    "ruby",
    ".md":    "markdown",
    ".xml":   "xml",
    ".dockerfile": "docker",
    ".tf":    "hcl",
    ".conf":  "plain text",
    ".cfg":   "plain text",
    ".env":   "plain text",
    ".ini":   "plain text",
}


def _resolve_code_language(filepath: str, fallback: str = "plain text") -> str:
    """Resolve Notion-compatible code language from file path.

    Falls back to 'plain text' (NOT 'text' — Notion rejects that).
    """
    ext = os.path.splitext(filepath)[1].lower()
    return EXT_TO_NOTION_LANG.get(ext, fallback)


def write_code_blueprints(corrections: list[dict]) -> list[str]:
    """Store generated code corrections in the Notion Code Blueprint DB.

    Each correction becomes a page with the generated code in a code block,
    linked to the source action, cycle ID, and AEGIS LID.
    """
    if not CODE_BLUEPRINT_DB or not corrections:
        return []

    page_ids: list[str] = []

    for corr in corrections:
        action_short = corr["action"][:100]
        files = corr.get("files", {})
        first_file = next(iter(files), "unknown")
        aegis = corr.get("aegis", {})

        children: list[dict] = [
            _heading(f"🔧 Auto-generated patch — {corr['priority']}", 2),
            {"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": _rt(corr["action"][:2000])}},
            _divider(),
        ]

        golden = corr.get("golden", {})

        for fp, code in files.items():
            children.append(_heading(f"📄 {fp}", 3))
            lang = _resolve_code_language(fp)
            children.append(_code_block(code[:1990], lang=lang))

            # Append AEGIS lineage info if available
            fp_aegis = aegis.get(fp, {})
            if fp_aegis:
                children.append({"object": "block", "type": "paragraph",
                                 "paragraph": {"rich_text": _rt(
                                     f"AEGIS LID: {fp_aegis.get('lid', '?')} | "
                                     f"Regen: {fp_aegis.get('regen_count', 0)} | "
                                     f"Changed: {fp_aegis.get('diff_stats', {}).get('changed', '?')}"
                                 )}})

            # Golden Copy Diff Guard scores + rollback data
            fp_golden = golden.get(fp, {})
            if fp_golden:
                scores = fp_golden.get("scores", {})
                children.append({"object": "block", "type": "paragraph",
                                 "paragraph": {"rich_text": _rt(
                                     f"🏆 Diff Guard: {fp_golden['verdict']} | "
                                     f"Preserved: {fp_golden.get('preservation_ratio', 0):.0%} | "
                                     f"Size: {fp_golden.get('size_ratio', 0):.1f}x | "
                                     f"Scores: P={scores.get('preservation', 0)}/10 "
                                     f"API={scores.get('api_surface', 0)}/10 "
                                     f"Import={scores.get('import_stability', 0)}/10 "
                                     f"Size={scores.get('size', 0)}/10"
                                 )}})
                children.append({"object": "block", "type": "paragraph",
                                 "paragraph": {"rich_text": _rt(
                                     f"Golden SHA: {fp_golden.get('golden_sha256', '?')[:16]}… | "
                                     f"API lost: {fp_golden.get('api_lost', [])} | "
                                     f"Imports lost: {fp_golden.get('import_lost', [])}"
                                 )}})
                # Unified diff for Notion rollback feature
                udiff = fp_golden.get("unified_diff", "")
                if udiff:
                    children.append(_heading("📋 Unified Diff (for rollback)", 3))
                    children.append(_code_block(udiff[:1990], lang="diff"))

        children.append(_divider())
        children.append({"object": "block", "type": "paragraph",
                         "paragraph": {"rich_text": _rt(
                             f"Model: {corr.get('model', '?')} | "
                             f"Latency: {corr.get('latency_ms', 0)}ms | "
                             f"Cost: ${corr['usage'].get('cost', 0):.4f} | "
                             f"Cycle: {corr['cycle_id']}"
                         )}})

        if corr.get("rejected"):
            children.append({"object": "block", "type": "paragraph",
                             "paragraph": {"rich_text": _rt(
                                 f"⚠️ Rejected phantom paths: {corr['rejected']}"
                             )}})

        # Use property mapper — severity falls back to priority for grade
        props = _map_blueprint_properties({
            "severity": corr.get("priority", "MEDIUM"),
            "action":   "FIX",
            "patch_type": "FILE",
        })
        caps_grade = props["CAPS Grade"]
        sake_id_parts = [corr["cycle_id"][:100]]
        if aegis:
            sake_id_parts.extend(a.get("lid", "") for a in aegis.values() if a.get("lid"))
        sake_id_str = " | ".join(sake_id_parts)[:200]

        resp = _api_post(f"{NOTION_API}/pages", _notion_h(), payload={
            "parent": {"database_id": CODE_BLUEPRINT_DB},
            "icon": {"type": "emoji", "emoji": "🔧"},
            "properties": {
                "Name":        {"title": [{"text": {"content": action_short}}]},
                "Source File": {"rich_text": [{"text": {"content": first_file[:200]}}]},
                "Action":      {"select": {"name": props["Action"]}},
                "Status":      {"select": {"name": props["Status"]}},
                "CAPS Grade":  {"select": {"name": caps_grade}},
                "Type":        {"select": {"name": props["Type"]}},
                "SAKE ID":     {"rich_text": [{"text": {"content": sake_id_str}}]},
                "Type":        {"select": {"name": "MODULE"}},
            },
            "children": children[:100],
        }, label=f"NOTION:blueprint:{corr['index']}")

        if resp and resp.get("id"):
            page_ids.append(resp["id"])
            log.info(f"[CODEGEN:NOTION] Blueprint page created: {resp['id']}")

    log.info(f"[CODEGEN:NOTION] {len(page_ids)}/{len(corrections)} blueprints stored")
    return page_ids


# ── GitLab push (UPDATE only — no phantom creates) + ROLLBACK ───────────────

_ROLLBACK_THRESHOLD = 2   # >N failed diff checks → nuke the whole branch

def _gl_file_meta(project_id: str, filepath: str, ref: str, headers: dict) -> dict | None:
    """GET /repository/files/:path — returns metadata incl. last_commit_id and content_sha256."""
    encoded = requests.utils.quote(filepath, safe="")
    try:
        r = requests.get(
            f"{GL_API}/projects/{project_id}/repository/files/{encoded}",
            headers=headers, params={"ref": ref}, timeout=30,
        )
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def _gl_verify_commit(
    project_id: str, branch: str, filepath: str,
    expected_content: str, pre_commit_sha: str, headers: dict,
) -> dict:
    """Post-commit diff check.  Returns verification dict.

    Compares the file content on the branch after the commit against what we
    intended to write.  If it doesn't match, automatically reverts the file
    to its pre-commit state via a revert commit.

    Returns:
        {"ok": True} on clean commit, or
        {"ok": False, "reason": ..., "expected_lines": ..., "actual_lines": ...,
         "pre_commit_sha": ..., "reverted": bool, "reverted_at": ...}
    """
    from gitlab_source import GL_API as _api
    import base64

    # 1. Fetch what's actually on the branch now
    meta = _gl_file_meta(project_id, filepath, branch, headers)
    if not meta:
        return {"ok": False, "reason": "post_commit_read_failed",
                "pre_commit_sha": pre_commit_sha, "reverted": False}

    try:
        actual = base64.b64decode(meta.get("content", "")).decode("utf-8")
    except Exception:
        actual = ""

    # 2. Diff check — compare stripped content to handle trailing newline drift
    if actual.strip() == expected_content.strip():
        return {"ok": True}

    expected_lines = expected_content.count("\n") + 1
    actual_lines = actual.count("\n") + 1

    log.warning(f"[CODEGEN:VERIFY] Mismatch for {filepath}: "
                f"expected {expected_lines} lines, got {actual_lines}")

    # 3. Revert — read golden copy from pre-commit SHA and write it back
    reverted = False
    reverted_at = ""
    if pre_commit_sha:
        golden = _gl_read_raw(filepath, ref=pre_commit_sha)
        if golden:
            revert_resp = _api_post(
                f"{_api}/projects/{project_id}/repository/commits",
                headers,
                payload={
                    "branch":         branch,
                    "commit_message": (
                        f"AEGIS ROLLBACK: {filepath} — diff mismatch, "
                        f"reverting to {pre_commit_sha[:8]}"
                    ),
                    "actions": [{
                        "action":    "update",
                        "file_path": filepath,
                        "content":   golden,
                    }],
                },
                label=f"codegen:rollback:{filepath}",
            )
            if revert_resp:
                reverted = True
                reverted_at = datetime.now(timezone.utc).isoformat()
                log.info(f"[CODEGEN:ROLLBACK] Reverted {filepath} → {pre_commit_sha[:8]}")
            else:
                log.warning(f"[CODEGEN:ROLLBACK] Revert commit failed for {filepath}")

    return {
        "ok":              False,
        "reason":          "diff_mismatch",
        "expected_lines":  expected_lines,
        "actual_lines":    actual_lines,
        "pre_commit_sha":  pre_commit_sha,
        "reverted":        reverted,
        "reverted_at":     reverted_at,
    }


def push_corrections_to_gitlab(corrections: list[dict], cycle_id: str) -> dict | None:
    """Push generated patches as a GitLab branch + MR.

    Includes two-level rollback:
      Level 1 — per-file: after each commit, verify content; revert on mismatch.
      Level 2 — branch:   if >_ROLLBACK_THRESHOLD files fail, delete the branch.

    ONLY updates existing files — never creates new ones.
    All paths have already been validated against the repo tree.
    """
    if not HAS_GITLAB_MODULE:
        return None
    from gitlab_source import gl_post, gl_get, GL_PID, GL_API, _gl_h
    if not GL_PID:
        log.warning("[CODEGEN:GL] No GITLAB_PROJECT_ID — skipping push")
        return None

    ts_suffix = datetime.now(timezone.utc).strftime("%H%M%S")
    branch_name = f"sanctum/auto-fix-{cycle_id.lower()}-{ts_suffix}"
    log.info(f"[CODEGEN:GL] Creating branch '{branch_name}'…")

    branch_resp = gl_post(f"/projects/{GL_PID}/repository/branches", {
        "branch": branch_name, "ref": "main",
    }, "codegen:branch")
    if not branch_resp:
        branch_resp = gl_get(
            f"/projects/{GL_PID}/repository/branches/{requests.utils.quote(branch_name, safe='')}",
            {}, "codegen:branch:check"
        )
        if not branch_resp:
            log.warning("[CODEGEN:GL] Branch creation failed — aborting push")
            return None
        log.info(f"[CODEGEN:GL] Reusing existing branch '{branch_name}'")

    # ── Level 2 checkpoint — record branch HEAD before we start committing ──
    checkpoint_sha = branch_resp.get("commit", {}).get("id", "")
    if checkpoint_sha:
        log.info(f"[CODEGEN:GL] Branch checkpoint: {checkpoint_sha[:12]}")

    # Dedup: if the same file appears in multiple patches, keep the LAST version
    deduped_files: dict[str, tuple[str, str]] = {}
    for corr in corrections:
        for filepath, content in corr.get("files", {}).items():
            fp = filepath
            if fp.startswith("./") or fp.startswith(".\\"):
                fp = fp[2:]
            fp = fp.lstrip("/\\")
            if not fp:
                continue
            deduped_files[fp] = (content, corr["action"][:80])

    total_before = sum(len(c.get("files", {})) for c in corrections)
    if total_before != len(deduped_files):
        log.info(f"[CODEGEN:GL] Deduped {total_before} file refs → {len(deduped_files)} unique files")

    # ── Per-file commit + verify loop ──
    committed_files: list[str] = []
    rollbacks: list[dict] = []
    headers = _gl_h()

    for fp, (content, action_desc) in deduped_files.items():
        # Capture pre-commit SHA (restore point) via file metadata
        pre_meta = _gl_file_meta(GL_PID, fp, branch_name, headers)
        pre_commit_sha = pre_meta.get("last_commit_id", "") if pre_meta else ""

        # Commit the update
        commit_resp = _api_post(
            f"{GL_API}/projects/{GL_PID}/repository/commits",
            headers,
            payload={
                "branch":         branch_name,
                "commit_message": f"[SANCTUM:{cycle_id}] Auto-fix: {action_desc}",
                "actions": [{
                    "action":    "update",
                    "file_path": fp,
                    "content":   content,
                }],
            },
            label=f"codegen:commit:{fp}",
        )
        if not commit_resp:
            log.warning(f"[CODEGEN:GL] Commit failed for {fp}")
            continue

        # ── Level 1: Post-commit verification ──
        verify = _gl_verify_commit(GL_PID, branch_name, fp, content, pre_commit_sha, headers)
        if verify["ok"]:
            committed_files.append(fp)
            log.info(f"[CODEGEN:GL] Committed + verified: {fp}")
        else:
            rollbacks.append({"file": fp, **verify})
            log.warning(f"[CODEGEN:GL] File {fp} failed verification — "
                        f"{'reverted' if verify.get('reverted') else 'revert failed'}")

    # ── Level 2: Branch-level rollback if too many failures ──
    branch_rolled_back = False
    if len(rollbacks) > _ROLLBACK_THRESHOLD and checkpoint_sha:
        log.warning(f"[CODEGEN:ROLLBACK] {len(rollbacks)} files failed > threshold "
                    f"{_ROLLBACK_THRESHOLD} — nuking branch")
        # Delete the branch entirely (will be recreated clean next cycle)
        try:
            encoded_branch = requests.utils.quote(branch_name, safe="")
            r = requests.delete(
                f"{GL_API}/projects/{GL_PID}/repository/branches/{encoded_branch}",
                headers=headers, timeout=30,
            )
            if r.status_code in (200, 204):
                branch_rolled_back = True
                log.info(f"[CODEGEN:ROLLBACK] Branch '{branch_name}' deleted (nuclear rollback)")
            else:
                log.warning(f"[CODEGEN:ROLLBACK] Branch delete failed: {r.status_code}")
        except Exception as exc:
            log.warning(f"[CODEGEN:ROLLBACK] Branch delete error: {exc}")

    if branch_rolled_back:
        return {
            "branch": branch_name,
            "files": [],
            "mr": None,
            "rollbacks": rollbacks,
            "branch_rolled_back": True,
            "checkpoint_sha": checkpoint_sha,
        }

    if not committed_files:
        log.warning("[CODEGEN:GL] No files committed — skipping MR creation")
        return {
            "branch": branch_name, "files": [], "mr": None,
            "rollbacks": rollbacks, "branch_rolled_back": False,
        }

    # Collect AEGIS LIDs for MR description
    aegis_lines: list[str] = []
    for c in corrections:
        for fp, a in c.get("aegis", {}).items():
            if a.get("lid"):
                aegis_lines.append(f"- `{fp}` → LID: `{a['lid']}`")

    # Collect golden copy scores for MR description
    golden_lines: list[str] = []
    for c in corrections:
        for fp, g in c.get("golden", {}).items():
            if g.get("verdict"):
                s = g.get("scores", {})
                golden_lines.append(
                    f"- `{fp}` — {g['verdict']} | "
                    f"Preserved: {g.get('preservation_ratio', 0):.0%} | "
                    f"P={s.get('preservation', 0)}/10 API={s.get('api_surface', 0)}/10 "
                    f"Import={s.get('import_stability', 0)}/10 Size={s.get('size', 0)}/10"
                )

    mr_body = (
        f"## 🤖 SANCTUM Auto-Fix — {cycle_id}\n\n"
        f"**Generated by:** Control Loop v2 — AEGIS-gated Code Generation\n"
        f"**Grade:** {corrections[0].get('_grade', 'CRITICAL')}\n"
        f"**Validation:** All paths verified against repo tree (no phantom files)\n"
        f"**Diff Guard:** {len(committed_files)} passed, {len(rollbacks)} rolled back\n\n"
        f"### Files Updated\n"
        + "\n".join(f"- `{f}`" for f in committed_files)
        + "\n\n### Patches Applied\n"
        + "\n".join(f"- **{c['priority']}**: {c['action'][:120]}" for c in corrections)
    )
    if golden_lines:
        mr_body += "\n\n### Golden Copy Diff Guard\n" + "\n".join(golden_lines)
    if aegis_lines:
        mr_body += "\n\n### AEGIS Lineage\n" + "\n".join(aegis_lines)
    if rollbacks:
        mr_body += "\n\n### ⚠️ Rollbacks\n"
        for rb in rollbacks:
            mr_body += (
                f"- `{rb['file']}`: {rb.get('reason', '?')} — "
                f"{'reverted ✅' if rb.get('reverted') else 'revert failed ❌'}\n"
            )
    mr_body += "\n\n---\n_Auto-generated. Review all changes before merging._"

    mr_resp = gl_post(f"/projects/{GL_PID}/merge_requests", {
        "source_branch":        branch_name,
        "target_branch":        "main",
        "title":                f"[SANCTUM] Auto-fix: {cycle_id}",
        "description":          mr_body,
        "labels":               "sanctum::auto-fix,sanctum::diagnostic,aegis::validated",
        "remove_source_branch": True,
    }, "codegen:mr")

    mr_url = mr_resp.get("web_url", "") if mr_resp else ""
    if mr_url:
        log.info(f"[CODEGEN:GL] MR created: {mr_url}")

    return {
        "branch": branch_name,
        "files": committed_files,
        "mr": mr_url,
        "rollbacks": rollbacks,
        "branch_rolled_back": False,
        "checkpoint_sha": checkpoint_sha,
    }


# ── Datadog custom metrics for codegen/rollback ─────────────────────────────

def _dd_submit_series(series: list[dict], label: str = "DD") -> bool:
    """Submit a list of Datadog metric series. Returns True on success."""
    dd_key = os.getenv("DD_API_KEY", os.getenv("DATADOG_API_KEY", ""))
    if not dd_key:
        return False
    try:
        r = requests.post(
            f"{DD_API_BASE}/v1/series",
            headers={"DD-API-KEY": dd_key, "Content-Type": "application/json"},
            json={"series": series},
            timeout=15,
        )
        if r.status_code in (200, 202):
            log.info(f"[{label}] Submitted {len(series)} metrics to Datadog")
            return True
        else:
            log.warning(f"[{label}] Metric submit {r.status_code}: {r.text[:200]}")
            return False
    except Exception as exc:
        log.warning(f"[{label}] Metric submit failed: {exc}")
        return False


def _dd_build_gauge(name: str, value: float, tags: list[str],
                    ts: int | None = None) -> dict:
    """Build a single DD v1/series gauge point with correct format."""
    return {
        "metric": name,
        "type":   "gauge",  # DD v1 API expects string, NOT int 0
        "points": [[ts or int(time.time()), float(value)]],
        "tags":   tags,
    }


def _dd_submit_codegen_metrics(result: dict) -> None:
    """Submit codegen cycle metrics to Datadog as custom gauges.

    Metrics submitted:
      sanctum.codegen.corrections_generated
      sanctum.codegen.blueprints_stored
      sanctum.codegen.paths_rejected
      sanctum.codegen.diff_guard_passed
      sanctum.codegen.diff_guard_rejected
      sanctum.codegen.diff_guard_success_rate
      sanctum.codegen.rollbacks.file_count
      sanctum.codegen.rollbacks.reverted
      sanctum.codegen.rollbacks.branch_nuked
      sanctum.codegen.committed_files
    """
    now_ts = int(time.time())
    tags = [
        f"grade:{result.get('health_grade', 'unknown')}",
        f"cycle:{result.get('cycle_id', 'unknown')[:40]}",
    ]

    generated = result.get("corrections_generated", 0)
    dg_passed = result.get("diff_guard_passed", 0)
    dg_rejected = result.get("diff_guard_rejected", 0)
    dg_total = dg_passed + dg_rejected
    success_rate = (dg_passed / dg_total * 100) if dg_total > 0 else 0.0

    metric_map = {
        "sanctum.codegen.corrections_generated": generated,
        "sanctum.codegen.blueprints_stored":     result.get("blueprints_stored", 0),
        "sanctum.codegen.paths_rejected":        result.get("paths_rejected", 0),
        "sanctum.codegen.diff_guard_passed":     dg_passed,
        "sanctum.codegen.diff_guard_rejected":   dg_rejected,
        "sanctum.codegen.diff_guard_success_rate": success_rate,
        "sanctum.codegen.rollbacks.file_count":  result.get("rollback_count", 0),
        "sanctum.codegen.rollbacks.reverted":    result.get("rollback_reverted", 0),
        "sanctum.codegen.rollbacks.branch_nuked": 1 if result.get("branch_rolled_back") else 0,
        "sanctum.codegen.committed_files":       len(result.get("gitlab_files", [])),
    }
    series = [_dd_build_gauge(name, val, tags, now_ts) for name, val in metric_map.items()]
    _dd_submit_series(series, label="CODEGEN:DD")


def _dd_submit_think_metrics(diag: dict) -> None:
    """Submit THINK pipeline metrics to Datadog.

    Metrics submitted:
      sanctum.think.health_score           — L0 deterministic score (0-100)
      sanctum.think.layer_count            — Number of layers that fired
      sanctum.think.l0_time_ms             — Layer 0 compute time
      sanctum.think.l1_time_ms             — Perplexity API latency
      sanctum.think.l2_time_ms             — Azure API latency
      sanctum.think.l3_time_ms             — Bedrock API latency
      sanctum.think.total_time_ms          — Total THINK wall clock
      sanctum.think.anomaly_count          — Statistical anomalies detected
      sanctum.think.root_cause_count       — Root causes identified by L1
      sanctum.think.blocker_count          — Total blockers
      sanctum.think.l3_confidence          — Adversarial gate overall confidence
      sanctum.think.tokens_total           — Total LLM tokens consumed
      sanctum.think.tokens_perplexity      — L1 tokens
      sanctum.think.tokens_azure           — L2 tokens
      sanctum.think.tokens_bedrock         — L3 tokens

      sanctum.nats.health                  — 1=healthy 0.5=degraded 0=unreachable/unhealthy
      sanctum.nats.domain_score            — L0 NATS domain score (0-100)
      sanctum.nats.streams                 — JetStream stream count
      sanctum.nats.consumers               — JetStream consumer count
      sanctum.nats.connections             — Active NATS client connections
      sanctum.nats.slow_consumers          — Slow consumer count (0 = good)
      sanctum.nats.messages_total          — Total messages across all streams
      sanctum.nats.publisher_connected     — 1 if AegisNATSPublisher connected this cycle
    """
    now_ts = int(time.time())
    timing = diag.get("_timing", {})
    tokens = diag.get("_tokens", {})
    adversarial = diag.get("_adversarial", {})
    anomalies = diag.get("_anomalies", {})

    tags = [
        f"grade:{diag.get('health_grade', 'unknown')}",
        f"cycle:{diag.get('cycle_id', 'unknown')[:40]}",
        f"layers:{diag.get('_layers', 'unknown')}",
    ]

    # ── NATS domain metrics ───────────────────────────────────────────────────
    nats_d = diag.get("nats", {})
    _nats_health_str = nats_d.get("status", "")
    _nats_health_val = {"GREEN": 1.0, "YELLOW": 0.5}.get(_nats_health_str, 0.0)
    # If health key is present and explicitly unreachable/unhealthy, force 0
    if nats_d.get("health") in ("unreachable", "unhealthy"):
        _nats_health_val = 0.0

    nats_metrics = {
        "sanctum.nats.health":              _nats_health_val,
        "sanctum.nats.domain_score":        diag.get("_domain_scores", {}).get("nats", 0),
        "sanctum.nats.streams":             nats_d.get("streams") or 0,
        "sanctum.nats.consumers":           nats_d.get("consumers") or 0,
        "sanctum.nats.connections":         nats_d.get("connections") or 0,
        "sanctum.nats.slow_consumers":      nats_d.get("slow_consumers") or 0,
        "sanctum.nats.messages_total":      nats_d.get("total_messages") or 0,
        "sanctum.nats.publisher_connected": diag.get("_nats_publisher_connected", 0),
    }

    metric_map = {
        "sanctum.think.health_score":      diag.get("health_score", 0),
        "sanctum.think.layer_count":       len(diag.get("_layers", "").split("+")),
        "sanctum.think.l0_time_ms":        timing.get("l0_ms", 0),
        "sanctum.think.l1_time_ms":        timing.get("l1_ms", 0),
        "sanctum.think.l2_time_ms":        timing.get("l2_ms", 0),
        "sanctum.think.l3_time_ms":        timing.get("l3_ms", 0),
        "sanctum.think.total_time_ms":     timing.get("total_ms", 0),
        "sanctum.think.anomaly_count":     len(anomalies.get("anomalies", [])),
        "sanctum.think.root_cause_count":  len(diag.get("root_causes", [])),
        "sanctum.think.blocker_count":     len(diag.get("blockers", [])),
        "sanctum.think.l3_confidence":     adversarial.get("overall_confidence", 0),
        "sanctum.think.tokens_total":      tokens.get("_total", 0),
        "sanctum.think.tokens_perplexity": tokens.get("perplexity", {}).get("total_tokens", 0)
                                           if isinstance(tokens.get("perplexity"), dict) else 0,
        "sanctum.think.tokens_azure":      tokens.get("azure-openai", {}).get("total_tokens", 0)
                                           if isinstance(tokens.get("azure-openai"), dict) else 0,
        "sanctum.think.tokens_bedrock":    tokens.get("bedrock-opus", {}).get("total_tokens", 0)
                                           if isinstance(tokens.get("bedrock-opus"), dict) else 0,
        **nats_metrics,
    }
    series = [_dd_build_gauge(name, val, tags, now_ts) for name, val in metric_map.items()]
    _dd_submit_series(series, label="THINK:DD")


# ── PostHog event capture for code engine telemetry ──────────────────────────

def _ph_capture(event: str, properties: dict) -> bool:
    """Capture an event in PostHog for code engine analytics.

    Uses the PostHog capture API (phc_* key) to send server-side events.
    These events power the codegen funnel:
      patch_generated → diff_guard_pass → committed → verify_ok → MR_merged
    """
    # PostHog capture key (phc_*) — different from personal API key (phx_*)
    capture_key = os.getenv("POSTHOG_API_KEY", "")
    if not capture_key:
        log.debug("[PH:CAPTURE] POSTHOG_API_KEY not set — skipping event %s", event)
        return False
    try:
        r = requests.post(
            f"{PH_HOST}/capture/",
            headers={"Content-Type": "application/json"},
            json={
                "api_key": capture_key,
                "event":   event,
                "distinct_id": "sanctum-control-loop",
                "properties": {
                    **properties,
                    "$lib": "sanctum-control-loop-v2",
                },
            },
            timeout=10,
        )
        if r.status_code in (200, 201):
            log.info(f"[PH:CAPTURE] Sent {event} to PostHog")
        else:
            log.warning(f"[PH:CAPTURE] {event} returned {r.status_code}: {r.text[:200]}")
        return r.status_code in (200, 201)
    except Exception as exc:
        log.warning(f"[PH:CAPTURE] Failed to send {event}: {exc}")
        return False


def _ph_capture_think_cycle(diag: dict) -> None:
    """Capture THINK cycle completion event in PostHog."""
    timing = diag.get("_timing", {})
    tokens = diag.get("_tokens", {})
    adversarial = diag.get("_adversarial", {})
    _ph_capture("think.cycle_complete", {
        "health_grade":     diag.get("health_grade", "UNKNOWN"),
        "health_score":     diag.get("health_score", 0),
        "cycle_id":         diag.get("cycle_id", "unknown"),
        "layers":           diag.get("_layers", ""),
        "layer_count":      len(diag.get("_layers", "").split("+")),
        "total_time_ms":    timing.get("total_ms", 0),
        "l0_time_ms":       timing.get("l0_ms", 0),
        "l1_time_ms":       timing.get("l1_ms", 0),
        "l2_time_ms":       timing.get("l2_ms", 0),
        "l3_time_ms":       timing.get("l3_ms", 0),
        "tokens_total":     tokens.get("_total", 0),
        "anomaly_count":    len(diag.get("_anomalies", {}).get("anomalies", [])),
        "root_cause_count": len(diag.get("root_causes", [])),
        "blocker_count":    len(diag.get("blockers", [])),
        "l3_confidence":    adversarial.get("overall_confidence", 0),
        "l3_blocked":       adversarial.get("blocked_actions", 0),
        "gate_decision":    "HEALTHY" if diag.get("health_score", 0) >= 95
                            else "CRITICAL" if diag.get("health_score", 0) < 60
                            else "DEGRADING",
    })


def _ph_capture_codegen_cycle(result: dict) -> None:
    """Capture codegen cycle completion + per-patch events in PostHog."""
    generated = result.get("corrections_generated", 0)
    dg_passed = result.get("diff_guard_passed", 0)
    dg_rejected = result.get("diff_guard_rejected", 0)
    dg_total = dg_passed + dg_rejected
    success_rate = (dg_passed / dg_total * 100) if dg_total > 0 else 0.0

    _ph_capture("codegen.cycle_complete", {
        "cycle_id":              result.get("cycle_id", "unknown"),
        "health_grade":          result.get("health_grade", "unknown"),
        "corrections_generated": generated,
        "diff_guard_passed":     dg_passed,
        "diff_guard_rejected":   dg_rejected,
        "diff_guard_success_rate": round(success_rate, 1),
        "rollback_count":        result.get("rollback_count", 0),
        "rollback_reverted":     result.get("rollback_reverted", 0),
        "branch_nuked":          result.get("branch_rolled_back", False),
        "committed_files":       len(result.get("gitlab_files", [])),
        "mr_created":            bool(result.get("gitlab_mr")),
    })

    # Individual patch events for funnel analysis
    if result.get("branch_rolled_back"):
        _ph_capture("codegen.branch_nuked", {
            "cycle_id": result.get("cycle_id", "unknown"),
            "rollback_count": result.get("rollback_count", 0),
        })
    for rb in result.get("rollbacks", []):
        _ph_capture("codegen.rollback", {
            "cycle_id": result.get("cycle_id", "unknown"),
            "file":     rb.get("file", ""),
            "reason":   rb.get("reason", ""),
            "reverted": rb.get("reverted", False),
        })


# ── Orchestrator ─────────────────────────────────────────────────────────────

def write_codegen(diag: dict, telemetry: dict) -> dict:
    """Orchestrate the full AEGIS-gated code generation pipeline:
    1. Generate patches via Bedrock Sonnet (grounded by real repo tree)
    2. Validate all paths against the actual project structure
    3. Golden Copy Diff Guard — reject patches that destroy originals
    4. Run AEGIS F977 lineage diffs
    5. Store in Notion Code Blueprint DB (with rollback metadata)
    6. Push branch + MR to GitLab (update-only, no phantom creates)
    7. Post-commit verification + auto-rollback (Level 1 per-file, Level 2 branch)
    8. Submit codegen/rollback metrics to Datadog
    """
    result: dict = {
        "corrections_generated": 0,
        "blueprints_stored":     0,
        "gitlab_mr":             None,
        "paths_rejected":        0,
        "diff_guard_rejected":   0,
        "diff_guard_passed":     0,
        "rollback_count":        0,
        "rollback_reverted":     0,
        "branch_rolled_back":    False,
        "rollbacks":             [],
    }

    grade = diag.get("health_grade", "UNKNOWN")
    if grade not in ("DEGRADING", "CRITICAL"):
        log.info("[CODEGEN] Grade is HEALTHY — skipping code generation")
        return result

    # ── CIRCUIT BREAKER: skip codegen after N consecutive 0%-success cycles ──
    CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive 0-commit cycles to trigger pause
    cg_hist = telemetry.get("codegen_history", {})
    recent = cg_hist.get("recent_cycles", [])
    if recent:
        consecutive_zero = 0
        for cyc in recent:
            if cyc.get("patches", 0) > 0 and cyc.get("committed", 0) == 0:
                consecutive_zero += 1
            else:
                break  # streak broken
        if consecutive_zero >= CIRCUIT_BREAKER_THRESHOLD:
            log.warning(
                f"[CODEGEN:CIRCUIT_BREAKER] {consecutive_zero} consecutive cycles "
                f"with 0 committed patches — pausing codegen to save API credits. "
                f"Fix codegen quality before re-enabling."
            )
            result["circuit_breaker"] = True
            result["consecutive_zero_commit_cycles"] = consecutive_zero
            _dd_submit_codegen_metrics(result)
            return result

    result["health_grade"] = grade
    result["cycle_id"] = diag.get("cycle_id", "unknown")

    corrections = generate_code_corrections(diag, telemetry, max_patches=5)
    result["corrections_generated"] = len(corrections)
    result["paths_rejected"] = sum(len(c.get("rejected", [])) for c in corrections)

    # Count diff guard outcomes from golden copy analysis
    for c in corrections:
        for fp, gd in c.get("golden", {}).items():
            if gd.get("verdict") == "PASS":
                result["diff_guard_passed"] += 1
            elif gd.get("verdict") == "REJECT":
                result["diff_guard_rejected"] += 1

    if not corrections:
        _dd_submit_codegen_metrics(result)
        return result

    for c in corrections:
        c["_grade"] = grade

    try:
        blueprint_ids = write_code_blueprints(corrections)
        result["blueprints_stored"] = len(blueprint_ids)
    except Exception as exc:
        log.warning(f"[CODEGEN:NOTION] Failed: {exc}")

    cycle_id = diag.get("cycle_id", "unknown")
    try:
        gl_result = push_corrections_to_gitlab(corrections, cycle_id)
        if gl_result:
            result["gitlab_mr"] = gl_result.get("mr")
            result["gitlab_files"] = gl_result.get("files", [])
            # Capture rollback data
            rollbacks = gl_result.get("rollbacks", [])
            result["rollbacks"] = rollbacks
            result["rollback_count"] = len(rollbacks)
            result["rollback_reverted"] = sum(1 for r in rollbacks if r.get("reverted"))
            result["branch_rolled_back"] = gl_result.get("branch_rolled_back", False)
            result["checkpoint_sha"] = gl_result.get("checkpoint_sha", "")
    except Exception as exc:
        log.warning(f"[CODEGEN:GL] Push failed: {exc}")

    # Submit all codegen metrics to Datadog
    _dd_submit_codegen_metrics(result)

    log.info(f"[CODEGEN] Done: {result['corrections_generated']} patches, "
             f"{result['blueprints_stored']} blueprints, "
             f"{result['paths_rejected']} phantom paths rejected, "
             f"{result['diff_guard_passed']} diff-guard passed, "
             f"{result['diff_guard_rejected']} diff-guard rejected, "
             f"{result['rollback_count']} rollbacks "
             f"({result['rollback_reverted']} reverted), "
             f"branch_nuked={result['branch_rolled_back']}, "
             f"MR={'yes' if result['gitlab_mr'] else 'no'}")
    return result


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run(args) -> dict:
    log.info("=" * 60)
    log.info("  CONTROL LOOP v2 — Live Telemetry")
    log.info("=" * 60)

    # Required credentials
    if not os.getenv("NOTION_TOKEN") and not os.getenv("NOTION_INTERNAL_TOKEN"):
        log.error("FATAL: NOTION_TOKEN not set"); sys.exit(1)
    if not os.getenv("PERPLEXITY_API_KEY") and not args.dry_run:
        log.error("FATAL: PERPLEXITY_API_KEY not set"); sys.exit(1)

    # Detect active optional sources
    optional_sources = {
        "datadog":    [("DD_API_KEY", "DATADOG_API_KEY"), ("DD_APP_KEY", "DATADOG_APP_KEY")],
        "posthog":    [("POSTHOG_PERSONAL_API_KEY", "POSTHOG_API_KEY"), ("POSTHOG_PROJECT_ID",)],
        "supabase":   [("SUPABASE_URL",), ("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY")],
        "gitlab":     [("GITLAB_TOKEN",), ("GITLAB_PROJECT_ID",)],
        "leads":      [("NOTION_LEADS_DB_ID",), ("NOTION_TOKEN", "NOTION_INTERNAL_TOKEN")],
        "stripe":        [("STRIPE_SECRET_KEY",)],
        "signup_funnel": [("SUPABASE_URL",), ("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY")],
        "metabase":      [("METABASE_API_KEY",)],
        "nats":       [("NATS_URL",)],
        "linear":     [("LINEAR_API_KEY", "LINEAR_API_TOKEN")],
        "elevenlabs": [("ELEVENLABS_API_KEY",)],
        "calcom":     [("CALCOM_API_KEY",)],
    }
    active: list[str] = []
    for source, key_groups in optional_sources.items():
        if all(any(os.getenv(k) for k in group) for group in key_groups):
            if source == "gitlab" and not HAS_GITLAB_MODULE:
                log.warning("[SKIP] gitlab: gitlab_source.py not importable")
            else:
                active.append(source)
        else:
            missing = [group[0] for group in key_groups if not any(os.getenv(k) for k in group)]
            log.warning(f"[SKIP] {source}: missing {missing}")
    log.info(f"Active sources: {active or ['notion only']}")

    # ── G4+G5: Initialize NATS publisher + Supabase persistence ──────────────
    _nats_pub = None
    if HAS_NATS_PUB:
        try:
            _nats_pub = AegisNATSPublisher()
            _nats_pub.connect()
        except Exception as exc:
            log.warning(f"[INIT] NATS publisher failed (non-fatal): {exc}")
            _nats_pub = None

    _cycle_store = None
    if HAS_SB_PERSIST:
        try:
            _cycle_store = AegisCycleStore()
        except Exception as exc:
            log.warning(f"[INIT] Supabase persistence failed (non-fatal): {exc}")
            _cycle_store = None

    t0 = time.time()
    _errors: list[dict] = []
    _run_api_errors.clear()  # reset per-run accumulator

    # ── READ ──────────────────────────────────────────
    telemetry: dict = {}
    for source, reader, kwargs in [
        ("datadog",  read_datadog,  {"window_hours": args.dd_window}),
        ("posthog",  read_posthog,  {"window_days":  args.ph_window}),
        ("supabase", read_supabase, {"window_hours": args.sb_window}),
    ]:
        if source in active:
            try:
                telemetry[source] = reader(**kwargs)
            except Exception as exc:
                log.warning(f"[READ] {source} failed: {exc}")
                _errors.append({"phase": f"READ/{source}", "type": type(exc).__name__, "detail": str(exc)})

    try:
        telemetry["notion"] = read_notion()
    except Exception as exc:
        log.warning(f"[READ] notion failed: {exc}")
        _errors.append({"phase": "READ/notion", "type": type(exc).__name__, "detail": str(exc)})

    if "gitlab" in active:
        try:
            telemetry["gitlab"] = read_gitlab(
                pipeline_window_hours=getattr(args, "gl_pipeline_window", 48),
                mr_window_days=getattr(args, "gl_mr_window", 14),
                commit_window_days=getattr(args, "gl_commit_window", 14),
                deploy_window_days=getattr(args, "gl_deploy_window", 14),
                issue_window_days=getattr(args, "gl_issue_window", 14),
            )
        except Exception as exc:
            log.warning(f"[READ] gitlab failed: {exc}")
            _errors.append({"phase": "READ/gitlab", "type": type(exc).__name__, "detail": str(exc)})

    if "leads" in active:
        try:
            telemetry["leads"] = read_lead_hunter(
                window_days=getattr(args, "leads_window", 7),
            )
        except Exception as exc:
            log.warning(f"[READ] leads failed: {exc}")
            _errors.append({"phase": "READ/leads", "type": type(exc).__name__, "detail": str(exc)})

    if "stripe" in active:
        try:
            telemetry["stripe"] = read_stripe()
        except Exception as exc:
            log.warning(f"[READ] stripe failed: {exc}")
            _errors.append({"phase": "READ/stripe", "type": type(exc).__name__, "detail": str(exc)})

    if "signup_funnel" in active:
        try:
            telemetry["signup_funnel"] = read_signup_funnel()
        except Exception as exc:
            log.warning(f"[READ] signup_funnel failed: {exc}")
            _errors.append({"phase": "READ/signup_funnel", "type": type(exc).__name__, "detail": str(exc)})

    if "metabase" in active:
        try:
            telemetry["metabase"] = read_metabase()
        except Exception as exc:
            log.warning(f"[READ] metabase failed: {exc}")
            _errors.append({"phase": "READ/metabase", "type": type(exc).__name__, "detail": str(exc)})

    if "nats" in active:
        try:
            telemetry["nats"] = read_nats()
        except Exception as exc:
            log.warning(f"[READ] nats failed: {exc}")
            _errors.append({"phase": "READ/nats", "type": type(exc).__name__, "detail": str(exc)})

    if "linear" in active:
        try:
            telemetry["linear"] = read_linear()
        except Exception as exc:
            log.warning(f"[READ] linear failed: {exc}")
            _errors.append({"phase": "READ/linear", "type": type(exc).__name__, "detail": str(exc)})

    if "elevenlabs" in active:
        try:
            telemetry["elevenlabs"] = read_elevenlabs()
        except Exception as exc:
            log.warning(f"[READ] elevenlabs failed: {exc}")
            _errors.append({"phase": "READ/elevenlabs", "type": type(exc).__name__, "detail": str(exc)})

    if "calcom" in active:
        try:
            telemetry["calcom"] = read_calcom()
        except Exception as exc:
            log.warning(f"[READ] calcom failed: {exc}")
            _errors.append({"phase": "READ/calcom", "type": type(exc).__name__, "detail": str(exc)})

    # Code corrections from Notion Code Blueprint DB (always attempt)
    try:
        code_corrections = read_notion_code_corrections()
        if code_corrections:
            telemetry["_code_corrections"] = code_corrections
            # Also inject a summary into telemetry so Perplexity sees it
            telemetry["code_corrections"] = {
                "source": "notion_code_blueprints",
                "total": len(code_corrections),
                "recent": [
                    {"name": c["name"], "file": c["source_file"],
                     "action": c["action"], "status": c["status"],
                     "grade": c["caps_grade"]}
                    for c in code_corrections[:10]
                ],
            }
    except Exception as exc:
        log.warning(f"[READ] code_corrections failed: {exc}")

    # Codegen rollback history — feeds THINK layer with past codegen health
    try:
        cg_history = read_codegen_history(window_hours=48, limit=10)
        if cg_history.get("cycles_found"):
            telemetry["codegen_history"] = cg_history
            log.info(f"[READ] codegen_history: {cg_history['cycles_found']} cycles, "
                     f"health={cg_history.get('codegen_health', '?')}")
    except Exception as exc:
        log.warning(f"[READ] codegen_history failed: {exc}")

    log.info(f"[READ] {time.time()-t0:.1f}s — sources: {list(telemetry.keys())}")

    # ── Phase 1.5: Blueprint Drift Scan ──────────────────────────────────
    _drift_report = None
    if HAS_BLUEPRINT_DRIFT:
        try:
            import asyncio
            _t_drift = time.time()
            _drift_raw = asyncio.run(run_blueprint_drift_scan())
            if _drift_raw:
                # Convert dataclass to dict for downstream .get() calls
                _drift_report = _drift_raw.to_dict() if hasattr(_drift_raw, 'to_dict') else _drift_raw
                telemetry["_drift_report"] = _drift_report
                _drift_conf = _drift_report.get("overall_conformance_pct", 100)
                _drift_items = _drift_report.get("total_drifted", 0)
                log.info(f"[READ:DRIFT] {time.time()-_t_drift:.1f}s — "
                         f"conformance={_drift_conf:.0f}% drifted={_drift_items}")
        except Exception as exc:
            log.warning(f"[READ:DRIFT] Blueprint drift scan failed (non-fatal): {exc}")
            _errors.append({"phase": "READ/blueprint_drift", "type": type(exc).__name__, "detail": str(exc)})

    # Sentinel telemetry (supplements read_elevenlabs)
    if HAS_SENTINEL and "elevenlabs" in active:
        try:
            telemetry["sentinel_telemetry"] = read_elevenlabs_telemetry(hours_back=24)
        except Exception as exc:
            log.warning(f"[READ:SENTINEL] Telemetry read failed: {exc}")

    # Flush any API-level failures recorded during READ into _errors
    if _run_api_errors:
        log.info(f"[READ] {len(_run_api_errors)} API failure(s) recorded → queued for Linear + Supabase")
        _errors.extend(_run_api_errors)
        _run_api_errors.clear()

    if args.dry_run:
        print(json.dumps(telemetry, indent=2, default=str))
        return {"dry_run": True, "sources": list(telemetry.keys())}

    # ── THINK (multi-layer: Perplexity → Azure OpenAI → Bedrock Opus) ────────
    t1 = time.time()
    try:
        model = getattr(args, "model", None) or PPLX_MODEL
        diag = think_multilayer(telemetry, model=model)
    except Exception as exc:
        _errors.append({"phase": "THINK", "type": type(exc).__name__, "detail": str(exc)})
        if not args.dry_run:
            write_linear({"health_grade": "UNKNOWN", "health_score": 0,
                          "cycle_id": f"DIAG-{datetime.now().strftime('%Y%m%d-%H%M%S')}"},
                         _errors)
        raise
    log.info(f"[THINK] {time.time()-t1:.1f}s — {diag['health_grade']} ({diag['health_score']}) "
             f"| layers={diag.get('_layers', 'unknown')}")

    # Inject publisher connection status so DD metrics capture it
    diag["_nats_publisher_connected"] = 1 if _nats_pub else 0

    # Submit THINK metrics to Datadog + PostHog (with retry if available)
    try:
        if HAS_ANALYTICS_RETRY:
            retry_with_backoff(_dd_submit_think_metrics, diag, label="THINK:DD:retry")
        else:
            _dd_submit_think_metrics(diag)
    except Exception as exc:
        log.warning(f"[THINK:DD] Metric submit failed: {exc}")
    try:
        if HAS_ANALYTICS_RETRY and HAS_PH_SCHEMAS:
            _adversarial = diag.get("_adversarial", {})
            props = think_cycle_complete(
                run_id=diag.get("cycle_id", "unknown"),
                cycle_num=1,
                health_score=diag.get("health_score", 0),
                health_grade=diag.get("health_grade", "UNKNOWN"),
                anomaly_count=len(diag.get("anomalies", [])),
                root_cause_count=len(diag.get("root_causes", [])),
                blocker_count=len(diag.get("blockers", [])),
                l3_confidence=_adversarial.get("overall_confidence", 0),
                gate_decision=_adversarial.get("gate_decision", "no_l3"),
                layers=diag.get("_layers", ""),
                timing=diag.get("_timing", {}),
                tokens=diag.get("_tokens", {}),
            )
            ph_capture_with_retry(
                os.getenv("POSTHOG_API_KEY", ""),
                os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
                "aegis_think_cycle_complete",
                props,
            )
        else:
            _ph_capture_think_cycle(diag)
    except Exception as exc:
        log.warning(f"[THINK:PH] PostHog capture failed: {exc}")

    # G4: Publish THINK result to NATS
    if _nats_pub:
        try:
            _nats_pub.publish_think_complete(diag)
        except Exception as exc:
            log.warning(f"[THINK:NATS] Publish failed (non-fatal): {exc}")

    # G4b: Publish drift event to NATS (triggers Reflex 7)
    if _nats_pub and _drift_report and _drift_report.get("total_drifted", 0) > 0:
        try:
            _nats_pub.publish_drift_detected(_drift_report, diag.get("cycle_id", "unknown"))
        except Exception as exc:
            log.warning(f"[DRIFT:NATS] Publish failed (non-fatal): {exc}")

    # Sentinel DV update — inject health context into voice agent
    if HAS_SENTINEL:
        try:
            _sentinel_result = sentinel_pre_call(
                diag,
                drift_report=_drift_report,
            )
            log.info(f"[WRITE:SENTINEL] mode={_sentinel_result.get('mode')} "
                     f"status={_sentinel_result.get('update_status')}")
        except Exception as exc:
            log.warning(f"[WRITE:SENTINEL] DV update failed: {exc}")

    # G5: Persist THINK cycle to Supabase
    if _cycle_store:
        try:
            _cycle_store.store_think_cycle(diag)
        except Exception as exc:
            log.warning(f"[THINK:SB] Supabase persist failed (non-fatal): {exc}")

    # ── RAG: store before/after for future cycles ─────
    if HAS_CYCLE_RAG and _cycle_rag:
        try:
            _cycle_rag.store_cycle(
                cycle_id=diag.get("cycle_id", f"DIAG-{datetime.now().strftime('%Y%m%d-%H%M%S')}"),
                before=telemetry,
                after=diag,
            )
        except Exception as exc:
            log.warning(f"[RAG:STORE] Failed to store cycle (non-fatal): {exc}")

    # ── WRITE ─────────────────────────────────────────
    t2 = time.time()
    page_id = None
    linear_urls: list[str] = []

    try:
        page_id = write_notion_page(diag, telemetry)
    except Exception as exc:
        _errors.append({"phase": "WRITE/notion", "type": type(exc).__name__, "detail": str(exc)})

    # Log any API failures as individual automation_events rows (status=error)
    # so read_supabase() picks them up next cycle and Perplexity sees them
    try:
        write_supabase_failures(_errors)
    except Exception as exc:
        log.warning(f"[WRITE] supabase failure log error: {exc}")

    try:
        write_supabase_audit(diag, telemetry)
    except Exception as exc:
        _errors.append({"phase": "WRITE/supabase", "type": type(exc).__name__, "detail": str(exc)})

    try:
        linear_urls = write_linear(diag, _errors)
    except Exception as exc:
        log.warning(f"[LINEAR] Failed: {exc}")

    # GitLab WRITE — create issues + MR comments on degrading/critical
    gitlab_result: dict = {}
    if HAS_GITLAB_MODULE and "gitlab" in telemetry:
        try:
            grade = diag.get("health_grade", "UNKNOWN")
            gitlab_result = _write_gitlab(
                diag,
                create_issues=(grade in ("DEGRADING", "CRITICAL")),
                comment_mrs=(grade == "CRITICAL"),
                trigger_remediation=False,
            )
        except Exception as exc:
            log.warning(f"[GL:WRITE] Failed: {exc}")
            _errors.append({"phase": "WRITE/gitlab", "type": type(exc).__name__, "detail": str(exc)})

    # Code Generation WRITE — auto-generate patches and push MR
    codegen_result: dict = {}
    try:
        codegen_result = write_codegen(diag, telemetry)
    except Exception as exc:
        log.warning(f"[CODEGEN] Failed: {exc}")
        _errors.append({"phase": "WRITE/codegen", "type": type(exc).__name__, "detail": str(exc)})

    # Post-codegen: append rollback data to Notion page + Supabase event
    if page_id and codegen_result:
        try:
            append_codegen_to_notion(page_id, codegen_result)
        except Exception as exc:
            log.warning(f"[WRITE] Codegen Notion append: {exc}")
    if codegen_result.get("corrections_generated"):
        try:
            write_supabase_codegen_event(codegen_result, diag.get("cycle_id", "unknown"))
        except Exception as exc:
            log.warning(f"[WRITE] Supabase codegen event: {exc}")

    # Capture codegen metrics to PostHog (always, even when 0 patches)
    if codegen_result:
        try:
            if HAS_ANALYTICS_RETRY and HAS_PH_SCHEMAS:
                _dg_pass = codegen_result.get("diff_guard_passed", 0)
                _dg_reject = codegen_result.get("diff_guard_rejected", 0)
                _dg_total = _dg_pass + _dg_reject
                props = codegen_cycle_complete(
                    run_id=diag.get("cycle_id", "unknown"),
                    cycle_num=1,
                    corrections_generated=codegen_result.get("corrections_generated", 0),
                    diff_guard_passed=_dg_pass,
                    diff_guard_rejected=_dg_reject,
                    diff_guard_success_rate=round(_dg_pass / _dg_total, 2) if _dg_total else 0.0,
                    rollback_count=codegen_result.get("rollback_count", 0),
                    rollback_reverted=codegen_result.get("rollback_reverted", 0),
                    branch_nuked=codegen_result.get("branch_rolled_back", False),
                    committed_files=codegen_result.get("committed", 0),
                    mr_created=bool(codegen_result.get("gitlab_mr")),
                    circuit_breaker_fired=codegen_result.get("circuit_breaker_tripped", False),
                    consecutive_zero_commits=codegen_result.get("consecutive_zero_commits", 0),
                )
                ph_capture_with_retry(
                    os.getenv("POSTHOG_API_KEY", ""),
                    os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
                    "aegis_codegen_cycle_complete",
                    props,
                )
            else:
                _ph_capture_codegen_cycle(codegen_result)
        except Exception as exc:
            log.warning(f"[CODEGEN:PH] PostHog capture failed: {exc}")

        # Codegen DD metrics with retry
        try:
            if HAS_ANALYTICS_RETRY:
                retry_with_backoff(_dd_submit_codegen_metrics, codegen_result, label="CODEGEN:DD:retry")
            else:
                _dd_submit_codegen_metrics(codegen_result)
        except Exception as exc:
            log.warning(f"[CODEGEN:DD] Metric submit failed: {exc}")

        # G4: Publish CODEGEN result to NATS
        if _nats_pub:
            try:
                _nats_pub.publish_codegen_complete(codegen_result)
            except Exception as exc:
                log.warning(f"[CODEGEN:NATS] Publish failed (non-fatal): {exc}")

        # G5: Persist CODEGEN cycle to Supabase
        if _cycle_store:
            try:
                _cycle_store.store_codegen_cycle(codegen_result)
            except Exception as exc:
                log.warning(f"[CODEGEN:SB] Supabase persist failed (non-fatal): {exc}")

        # G5: Store alerts for circuit breaker / rollback events
        if _cycle_store:
            if codegen_result.get("circuit_breaker_tripped"):
                try:
                    _cycle_store.store_alert(
                        alert_type="circuit_breaker",
                        severity="critical",
                        run_id=diag.get("cycle_id", "unknown"),
                        details={"reason": "3 consecutive 0-commit cycles"},
                    )
                except Exception:
                    pass
            if codegen_result.get("branch_rolled_back"):
                try:
                    _cycle_store.store_alert(
                        alert_type="rollback",
                        severity="warning",
                        run_id=diag.get("cycle_id", "unknown"),
                        details={
                            "sha": codegen_result.get("checkpoint_sha", ""),
                            "rollback_count": codegen_result.get("rollback_count", 0),
                        },
                    )
                except Exception:
                    pass

    # EVO tracker callout — patched AFTER codegen so it includes rollback data
    try:
        patch_tracker_callout(diag, codegen_result=codegen_result or None)
    except Exception as exc:
        _errors.append({"phase": "WRITE/callout", "type": type(exc).__name__, "detail": str(exc)})

    log.info(f"[WRITE] {time.time()-t2:.1f}s")

    result = {
        "cycle_id":      diag.get("cycle_id"),
        "health_grade":  diag["health_grade"],
        "health_score":  diag["health_score"],
        "page_id":       page_id,
        "linear_issues": linear_urls,
        "gitlab":        gitlab_result,
        "codegen":       codegen_result,
        "drift":         {
            "conformance_pct": _drift_report.get("overall_conformance_pct") if _drift_report else None,
            "total_drifted":   _drift_report.get("total_drifted", 0) if _drift_report else 0,
            "critical_count":  _drift_report.get("critical_count", 0) if _drift_report else 0,
            "score_penalty":   _drift_report.get("total_score_penalty", 0) if _drift_report else 0,
        } if _drift_report else None,
        "sources":       list(telemetry.keys()),
        "errors":        _errors,
        "total_time_s":  round(time.time() - t0, 1),
    }

    log.info("=" * 60)
    log.info(f"  Grade     : {result['health_grade']}")
    log.info(f"  Score     : {result['health_score']}/100")
    log.info(f"  Sources   : {result['sources']}")
    if page_id:
        log.info(f"  Notion pg : https://notion.so/{page_id.replace('-', '')}")
    for u in linear_urls:
        log.info(f"  Linear    : {u}")
    if gitlab_result.get("issues_created"):
        log.info(f"  GL issues : {len(gitlab_result['issues_created'])} created")
    if gitlab_result.get("mrs_commented"):
        log.info(f"  GL MRs    : {len(gitlab_result['mrs_commented'])} commented")
    if codegen_result.get("corrections_generated"):
        log.info(f"  Codegen   : {codegen_result['corrections_generated']} patches, "
                 f"{codegen_result.get('blueprints_stored', 0)} blueprints, "
                 f"diff_guard={codegen_result.get('diff_guard_passed', 0)}✓/"
                 f"{codegen_result.get('diff_guard_rejected', 0)}✗")
    if codegen_result.get("gitlab_mr"):
        log.info(f"  Auto-MR   : {codegen_result['gitlab_mr']}")
    if codegen_result.get("rollback_count"):
        log.info(f"  Rollbacks : {codegen_result['rollback_count']} files "
                 f"({codegen_result.get('rollback_reverted', 0)} reverted)")
    if codegen_result.get("branch_rolled_back"):
        log.warning(f"  BRANCH NUKED: {codegen_result.get('checkpoint_sha', '?')[:12]}")
    if _drift_report:
        _dr = result.get("drift", {})
        log.info(f"  Drift     : {_dr.get('conformance_pct', '?')}% conformance, "
                 f"{_dr.get('total_drifted', 0)} drifted, "
                 f"{_dr.get('critical_count', 0)} critical, "
                 f"penalty=-{_dr.get('score_penalty', 0)}")
    if _errors:
        log.warning(f"  Errors    : {len(_errors)} (logged to Linear)")
    log.info(f"  Time      : {result['total_time_s']}s")
    log.info("=" * 60)

    # G4: Close NATS publisher
    if _nats_pub:
        try:
            _nats_pub.close()
        except Exception as exc:
            log.warning(f"[CLEANUP] NATS close failed: {exc}")

    return result


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(
        description="SANCTUM Perplexity Control Loop v2 — Live Telemetry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dry-run",  action="store_true",
                   help="READ only — print telemetry JSON, skip THINK and WRITE")
    p.add_argument("--json-out", default="",
                   help="Write full result JSON to this file path")
    p.add_argument("--model",    default="",
                   help=f"Perplexity model override (default: {PPLX_MODEL})")
    p.add_argument("--dd-window",  type=int, default=4,
                   help="Datadog lookback window in hours (default: 4)")
    p.add_argument("--ph-window",  type=int, default=7,
                   help="PostHog lookback window in days (default: 7)")
    p.add_argument("--sb-window",  type=int, default=24,
                   help="Supabase lookback window in hours (default: 24)")
    p.add_argument("--leads-window",   type=int, default=7,
                   help="Lead Hunter lookback window in days (default: 7)")
    p.add_argument("--gl-pipeline-window", type=int, default=48,
                   help="GitLab pipeline lookback window in hours (default: 48)")
    p.add_argument("--gl-mr-window",       type=int, default=14,
                   help="GitLab MR lookback window in days (default: 14)")
    p.add_argument("--gl-commit-window",   type=int, default=14,
                   help="GitLab commit lookback window in days (default: 14)")
    p.add_argument("--gl-deploy-window",   type=int, default=14,
                   help="GitLab deployment lookback window in days (default: 14)")
    p.add_argument("--gl-issue-window",    type=int, default=14,
                   help="GitLab issue lookback window in days (default: 14)")
    p.add_argument("--log-file", type=str, default=None,
                   help="Path for log file output (auto-generates if omitted)")
    p.add_argument("--log-level", type=str, default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Log level (default: INFO)")
    args = p.parse_args()

    # G1: File logging handler
    _log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    log.setLevel(_log_level)
    _log_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _log_path = args.log_file
    if not _log_path:
        _ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        _log_path = f"logs/aegis_cl_v2_{_ts}.log"
        Path(_log_path).parent.mkdir(parents=True, exist_ok=True)
    _fh = logging.FileHandler(_log_path, encoding="utf-8")
    _fh.setFormatter(_log_fmt)
    _fh.setLevel(_log_level)
    log.addHandler(_fh)
    log.info(f"[INIT] Logging to {_log_path}")

    result = run(args)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        log.info(f"[OUT] JSON written to {args.json_out}")

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
