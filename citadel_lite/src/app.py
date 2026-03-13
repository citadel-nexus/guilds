# src/app.py
"""
Citadel Lite FastAPI application.

Ties together:
- Webhook ingestion (/webhook/*) — async pipeline via BackgroundTasks
- Pipeline status (/pipeline/*)
- SSE streaming (/stream/*)
- Agent registry (/agents)
- Audit trail (/audit/*)
- Reflex rules (/reflex/rules)
- Governance policies (/governance/policies)
- Web dashboard (/dashboard)
- Config summary (/config)
- Health check (/health)

Usage:
    uvicorn src.app:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends
    from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse, FileResponse
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from fastapi.staticfiles import StaticFiles
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

from src.types import EventJsonV1
from src.config import get_config
from src.orchestrator_v3 import OrchestratorV3
from src.a2a.agent_wrapper import build_protocol_v2
from src.audit.logger import AuditLogger
from src.memory.store_v2 import LocalMemoryStore
from src.execution.runner_V2 import ExecutionRunner
from src.execution.outcome_store import OutcomeStore
from src.reflex.dispatcher import ReflexDispatcher
from src.ingest.normalizer import normalize
from src.ingest.outbox import FileOutbox
from src.streaming.emitter import pipeline_emitter
from src.github.client import GitHubClient
from src.skills.registry import SkillRegistry
from src.integrations.supabase_client import SupabaseStore
from src.integrations.notion_client import NotionClient
from src.integrations.slack_enhanced import SlackBot
from src.integrations.azure_ai_search import AzureSearchMemory

# Roadmap Tracker (MS-3)
try:
    from src.roadmap.api import create_roadmap_router
    _HAS_ROADMAP = True
except ImportError:
    _HAS_ROADMAP = False

# Conditionally import FAISS vector store
try:
    from src.memory.vector_store import FaissMemoryStore
    _HAS_FAISS_STORE = True
except ImportError:
    _HAS_FAISS_STORE = False

# Monitoring (Phase 26)
try:
    from src.monitoring.metrics import get_metrics_response, is_enabled as _metrics_enabled
    _HAS_MONITORING = True
except ImportError:
    _HAS_MONITORING = False

logger = logging.getLogger(__name__)

# Conditionally import Azure modules
try:
    from src.azure.config import load_azure_config, is_azure_enabled
    from src.azure.foundry_agents import build_foundry_protocol
    from src.azure.cosmos_memory import CosmosMemoryStore
    from src.azure.servicebus_adapter import ServiceBusOutbox
    from src.azure.telemetry import TelemetryClient
except ImportError:
    is_azure_enabled = lambda: False


# ---- Config-driven orchestrator builder ----

def _build_orchestrator() -> OrchestratorV3:
    """Build orchestrator with backends determined by citadel.config.yaml."""
    cfg = get_config()

    # Protocol
    if is_azure_enabled() and callable(is_azure_enabled):
        try:
            azure_cfg = load_azure_config()
            protocol = build_foundry_protocol(azure_cfg)
        except Exception:
            protocol = build_protocol_v2()
    else:
        protocol = build_protocol_v2()

    # Memory — select backend from config
    memory = LocalMemoryStore()
    if cfg.memory_backend == "azure_search" and cfg.has_azure_search:
        try:
            memory = AzureSearchMemory(
                endpoint=cfg.azure_search_endpoint,
                api_key=cfg.azure_search_key,
                index_name=cfg.azure_search_index,
            )
        except Exception:
            pass
    elif cfg.memory_backend == "faiss" and _HAS_FAISS_STORE:
        try:
            memory = FaissMemoryStore(
                azure_endpoint=cfg.azure_openai_endpoint,
                azure_key=cfg.azure_openai_key,
                openai_key=cfg.openai_api_key,
            )
        except Exception:
            pass
    elif cfg.azure_cosmos_connection:
        try:
            azure_cfg = load_azure_config()
            memory = CosmosMemoryStore(azure_cfg)
        except Exception:
            pass

    # Execution runner — driven by config
    executor = ExecutionRunner(mode=cfg.execution_mode)

    # GitHub client
    github_client = GitHubClient()

    return OrchestratorV3(
        protocol=protocol,
        memory=memory,
        audit=AuditLogger(),
        executor=executor,
        outcome_store=OutcomeStore(),
        reflex=ReflexDispatcher(),
        github_client=github_client,
    )


# ---- FastAPI App ----

if not _HAS_FASTAPI:
    raise ImportError("FastAPI is required. Install with: pip install fastapi uvicorn")

app = FastAPI(
    title="Citadel Lite — Agentic DevOps Pipeline",
    description="Multi-agent CI/CD incident response with A2A protocol, memory, governance, and audit",
    version="2.1.0",
)

# Shared state
_orchestrator = _build_orchestrator()
_outbox = FileOutbox()
_config = get_config()
_skill_registry = SkillRegistry()
_supabase_store = SupabaseStore(url=_config.supabase_url, key=_config.supabase_key)
_notion_client = NotionClient(api_key=_config.notion_api_key, database_id=_config.notion_database_id)
_slack_bot = SlackBot(
    bot_token=_config.slack_bot_token,
    signing_secret=_config.slack_signing_secret,
    default_channel=_config.slack_channel,
)

# Track in-flight pipeline runs (capped to avoid unbounded memory growth)
_MAX_PIPELINE_STATUS = 1_000
_pipeline_status: OrderedDict[str, str] = OrderedDict()  # event_id -> "running" | "completed" | "error"

# Mount Roadmap Tracker router (MS-3)
if _HAS_ROADMAP:
    _roadmap_ir_path = Path(__file__).resolve().parent.parent / "roadmap_ir.json"
    app.include_router(create_roadmap_router(_roadmap_ir_path))

# Mount Sentinel memory-loop webhook routers
try:
    from src.webhooks.sentinel_post_call import router as _sentinel_post_call_router
    from src.webhooks.sentinel_pre_call import router as _sentinel_pre_call_router
    app.include_router(_sentinel_post_call_router)
    app.include_router(_sentinel_pre_call_router)
    logger.info("Sentinel memory-loop webhooks registered")
except ImportError as e:
    logger.warning("Sentinel webhooks not loaded: %s", e)


# ---- Background pipeline execution ----

def _run_pipeline_background(event: EventJsonV1) -> None:
    """Execute pipeline in background thread. Emits SSE events as stages complete."""
    event_id = event.event_id
    if len(_pipeline_status) >= _MAX_PIPELINE_STATUS:
        _pipeline_status.popitem(last=False)  # drop oldest entry
    _pipeline_status[event_id] = "running"

    try:
        # Emit pipeline start
        pipeline_emitter.emit(event_id, "pipeline", "running", {
            "event_type": event.event_type,
            "source": event.source,
            "summary": event.summary,
        })

        # Emit event received
        pipeline_emitter.emit(event_id, "event", "completed", {
            "event_type": event.event_type,
            "summary": event.summary,
        })

        # Run the orchestrator (synchronous — runs in background thread)
        _orchestrator.run_from_event(event)

        # Read outputs to emit final SSE events
        base = Path("out") / event_id

        # Emit agent outputs
        hp_path = base / "handoff_packet.json"
        if hp_path.exists():
            hp = json.loads(hp_path.read_text(encoding="utf-8"))
            for agent_name in ["sentinel", "sherlock", "fixer"]:
                agent_data = (hp.get("agent_outputs") or {}).get(agent_name, {})
                if agent_data:
                    pipeline_emitter.emit(event_id, agent_name, "completed", agent_data)
            if hp.get("memory_hits"):
                pipeline_emitter.emit(event_id, "memory", "completed", {
                    "memory_hits": hp["memory_hits"]
                })

        # Emit decision
        dec_path = base / "decision.json"
        if dec_path.exists():
            decision_data = json.loads(dec_path.read_text(encoding="utf-8"))
            pipeline_emitter.emit(event_id, "guardian", "completed", decision_data)

        # Emit execution outcome
        exec_path = base / "execution_outcome.json"
        if exec_path.exists():
            exec_data = json.loads(exec_path.read_text(encoding="utf-8"))
            pipeline_emitter.emit(event_id, "execution", "completed", exec_data)

        # Emit audit
        audit_path = base / "audit_report.json"
        if audit_path.exists():
            audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
            pipeline_emitter.emit(event_id, "audit", "completed", {
                "hash_chain": audit_data.get("hash_chain", []),
                "pipeline_duration_ms": audit_data.get("pipeline_duration_ms"),
            })

        # Send notifications if configured
        _send_notifications(event, base)

        pipeline_emitter.emit(event_id, "pipeline", "completed", {"status": "success"})
        _pipeline_status[event_id] = "completed"

    except Exception as e:
        logger.exception("Pipeline failed for %s", event_id)
        pipeline_emitter.emit(event_id, "pipeline", "error", {"error": str(e)})
        _pipeline_status[event_id] = "error"


def _send_notifications(event: EventJsonV1, base: Path) -> None:
    """Send notifications if configured."""
    cfg = get_config()
    if not cfg.has_notifications:
        return

    try:
        from src.notifications.dispatcher import NotificationDispatcher
        notifier = NotificationDispatcher(cfg)

        dec_path = base / "decision.json"
        if not dec_path.exists():
            return

        decision = json.loads(dec_path.read_text(encoding="utf-8"))
        action = decision.get("action", "")
        risk = decision.get("risk_score", 0)

        if action == "need_approval":
            notifier.send_approval_request(
                event_id=event.event_id,
                event_type=event.event_type,
                summary=event.summary or "",
                risk_score=risk,
                decision_action=action,
                rationale=decision.get("rationale", ""),
            )
        else:
            pr_url = ""
            exec_path = base / "execution_outcome.json"
            if exec_path.exists():
                exec_data = json.loads(exec_path.read_text(encoding="utf-8"))
                pr_url = exec_data.get("pr_url", "") or ""

            notifier.send_pipeline_complete(
                event_id=event.event_id,
                event_type=event.event_type,
                decision_action=action,
                risk_score=risk,
                pr_url=pr_url,
            )
    except Exception as e:
        logger.warning("Notification dispatch failed: %s", e)


# ---- Webhook Endpoints (async — returns 202, runs pipeline in background) ----

@app.post("/webhook/github", tags=["ingest"], status_code=202)
async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    """Receive GitHub Actions webhook, normalize, and process async."""
    # Verify signature if configured
    cfg = get_config()
    if cfg.github_webhook_secret:
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not GitHubClient.verify_webhook_signature(body, signature, cfg.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        raw = json.loads(body)
    else:
        raw = await request.json()

    event = normalize(raw, source="github_actions")
    background_tasks.add_task(_run_pipeline_background, event)
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "event_id": event.event_id, "event_type": event.event_type},
    )


@app.post("/webhook/azure", tags=["ingest"], status_code=202)
async def azure_webhook(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    """Receive Azure Monitor alert and process async."""
    raw = await request.json()
    event = normalize(raw, source="azure_alert")
    background_tasks.add_task(_run_pipeline_background, event)
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "event_id": event.event_id},
    )


@app.post("/webhook/event", tags=["ingest"], status_code=202)
async def manual_event(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    """Receive pre-formatted EventJsonV1 and process async."""
    raw = await request.json()
    event = normalize(raw, source="manual")
    background_tasks.add_task(_run_pipeline_background, event)
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "event_id": event.event_id},
    )


# ---- SSE Streaming ----

@app.get("/stream/{event_id}", tags=["streaming"])
async def stream_pipeline(event_id: str) -> StreamingResponse:
    """SSE stream of pipeline events. Connect before or after pipeline starts."""
    return StreamingResponse(
        pipeline_emitter.sse_generator(event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- Pipeline Status ----

@app.get("/pipeline/{event_id}", tags=["pipeline"])
async def get_pipeline_result(event_id: str) -> Dict[str, Any]:
    """Get full pipeline results for an event."""
    base = Path("out") / event_id

    if not base.exists():
        # Check if it's in-flight
        status = _pipeline_status.get(event_id)
        if status == "running":
            return {"event_id": event_id, "status": "running", "stream_url": f"/stream/{event_id}"}
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    result: Dict[str, Any] = {
        "event_id": event_id,
        "status": _pipeline_status.get(event_id, "completed"),
    }

    for filename in ["handoff_packet.json", "decision.json", "audit_report.json",
                     "execution_outcome.json", "stop_report.json", "approval_request.json"]:
        path = base / filename
        if path.exists():
            result[filename.replace(".json", "")] = json.loads(path.read_text(encoding="utf-8"))

    return result


@app.get("/pipeline/{event_id}/decision", tags=["pipeline"])
async def get_decision(event_id: str) -> Dict[str, Any]:
    """Get Guardian decision for an event."""
    path = Path("out") / event_id / "decision.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Decision for {event_id} not found")
    return json.loads(path.read_text(encoding="utf-8"))


# ---- Agent Registry ----

@app.get("/agents", tags=["agents"])
async def list_agents() -> List[Dict[str, Any]]:
    """List all registered A2A agents with memory/KB metadata."""
    cards = _orchestrator.protocol.list_agents()
    # Count memory corpus entries for KB stats
    mem_count = 0
    try:
        corpus = _orchestrator.memory._corpus if hasattr(_orchestrator.memory, "_corpus") else []
        mem_count = len(corpus)
    except Exception:
        pass

    result = []
    for c in cards:
        entry: Dict[str, Any] = {
            "agent_id": c.agent_id,
            "name": c.name,
            "capabilities": c.capabilities,
            "version": c.version,
            "status": c.status,
            "memory_hits": mem_count,
            "kb_entries": mem_count,
            "kb_summary": f"{mem_count} incidents in knowledge base. Use Memory menu to inspect.",
        }
        result.append(entry)
    return result


# ---- Governance ----

@app.get("/governance/policies", tags=["governance"])
async def list_policies() -> Dict[str, Any]:
    """List governance policies and compliance mappings."""
    try:
        from src.governance.policy_engine import PolicyEngine
        engine = PolicyEngine()
        return engine.generate_report()
    except Exception as e:
        return {"error": str(e)}


# ---- Audit ----

@app.get("/audit/{event_id}", tags=["audit"])
async def get_audit_report(event_id: str) -> Dict[str, Any]:
    """Get audit report for an event."""
    path = Path("out") / event_id / "audit_report.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Audit report for {event_id} not found")
    return json.loads(path.read_text(encoding="utf-8"))


# ---- Reflex Rules ----

@app.get("/reflex/rules", tags=["governance"])
async def list_reflex_rules() -> List[Dict[str, Any]]:
    """List all loaded reflex rules."""
    return [
        {
            "id": r.id,
            "trigger": r.trigger,
            "condition": r.condition,
            "action": r.action,
            "description": r.description,
            "enabled": r.enabled,
        }
        for r in _orchestrator.reflex.manifest.rules
    ]


# ---- Test Scenarios ----

_SCENARIOS_PATH = Path(__file__).resolve().parent.parent / "demo" / "events" / "test_scenarios.json"


@app.get("/scenarios", tags=["scenarios"])
async def list_scenarios() -> List[Dict[str, Any]]:
    """List all test scenarios for the dashboard scenario loader."""
    if not _SCENARIOS_PATH.exists():
        return []
    try:
        data = json.loads(_SCENARIOS_PATH.read_text(encoding="utf-8"))
        # File is a wrapper object with "scenarios" key
        if isinstance(data, dict) and "scenarios" in data:
            return data["scenarios"]
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


# ---- Memory / Knowledge Base ----

@app.get("/memory/corpus", tags=["memory"])
async def memory_corpus(q: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search the memory knowledge base. Returns all entries if no query, or filtered by keyword."""
    try:
        corpus = _orchestrator.memory._corpus if hasattr(_orchestrator.memory, "_corpus") else []
    except Exception:
        corpus = []

    if not q:
        return corpus

    # Simple keyword filter across title, snippet, tags
    q_lower = q.lower()
    results = []
    for entry in corpus:
        searchable = " ".join([
            entry.get("title", ""),
            entry.get("snippet", ""),
            " ".join(entry.get("tags", [])),
            entry.get("event_id", ""),
        ]).lower()
        if q_lower in searchable:
            results.append(entry)
    return results


# ---- Dashboard ----

_DASHBOARD_DIR = Path(__file__).parent / "dashboard"


@app.get("/dashboard", tags=["dashboard"], response_class=HTMLResponse)
async def dashboard():
    """Serve the web dashboard."""
    index_path = _DASHBOARD_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.get("/dashboard/{filename}", tags=["dashboard"])
async def dashboard_static(filename: str):
    """Serve dashboard static files (JS, CSS)."""
    file_path = _DASHBOARD_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    media_types = {".js": "application/javascript", ".css": "text/css", ".html": "text/html"}
    media_type = media_types.get(file_path.suffix, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type)


# ---- Config (safe summary) ----

@app.get("/config", tags=["system"])
async def config_summary() -> Dict[str, Any]:
    """Configuration summary (no secrets exposed)."""
    return get_config().summary()


# ---- Config Editor (read/write YAML) ----

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "citadel.config.yaml"

# Fields that contain secrets — returned masked, only written when changed
_SECRET_FIELDS = {
    "llm.azure_openai.api_key",
    "llm.openai.api_key",
    "github.token",
    "github.webhook_secret",
    "notifications.slack.webhook_url",
    "notifications.teams.webhook_url",
    "notifications.webhook.url",
    "azure.service_bus.connection_string",
    "azure.cosmos.connection_string",
    "azure.foundry.api_key",
    "azure.app_insights.connection_string",
    "azure.storage.connection_string",
    "azure.ai_search.api_key",
    "supabase.api_key",
    "notion.api_key",
    "slack.bot_token",
    "slack.signing_secret",
}

_MASK = "••••••••"

# ---- Admin auth (for /config/* endpoints) ----
_admin_bearer = HTTPBearer(auto_error=True) if _HAS_FASTAPI else None

def _require_admin(
    creds: "HTTPAuthorizationCredentials" = Depends(_admin_bearer),  # type: ignore[assignment]
) -> None:
    """Validate Bearer token against CITADEL_ADMIN_KEY env var."""
    expected = os.environ.get("CITADEL_ADMIN_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="CITADEL_ADMIN_KEY not configured")
    if not secrets.compare_digest(creds.credentials, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


def _mask_secrets(data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Replace secret values with mask for safe transmission."""
    out: Dict[str, Any] = {}
    for k, v in data.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out[k] = _mask_secrets(v, path)
        elif path in _SECRET_FIELDS and v:
            out[k] = _MASK
        else:
            out[k] = v
    return out


def _merge_secrets(new_data: Dict[str, Any], old_data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Keep original secret values when the client sends the mask back unchanged."""
    out: Dict[str, Any] = {}
    for k, v in new_data.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            old_sub = old_data.get(k, {}) if isinstance(old_data.get(k), dict) else {}
            out[k] = _merge_secrets(v, old_sub, path)
        elif path in _SECRET_FIELDS and v == _MASK:
            # User didn't change the secret — keep the original
            out[k] = old_data.get(k, "")
        else:
            out[k] = v
    return out


@app.get("/config/edit", tags=["system"], dependencies=[Depends(_require_admin)])
async def config_edit() -> Dict[str, Any]:
    """Return full config for editing. Secrets are masked."""
    try:
        import yaml as _yaml
    except ImportError:
        raise HTTPException(status_code=500, detail="pyyaml not installed")

    if not _CONFIG_PATH.exists():
        return {}

    raw = _yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return _mask_secrets(raw)


@app.post("/config/save", tags=["system"], dependencies=[Depends(_require_admin)])
async def config_save(request: Request) -> Dict[str, Any]:
    """Save config edits to citadel.config.yaml. Masked secrets are preserved."""
    try:
        import yaml as _yaml
    except ImportError:
        raise HTTPException(status_code=500, detail="pyyaml not installed")

    new_data = await request.json()

    # Load existing to preserve masked secrets
    old_data: Dict[str, Any] = {}
    if _CONFIG_PATH.exists():
        old_data = _yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}

    merged = _merge_secrets(new_data, old_data)

    # Write back
    _CONFIG_PATH.write_text(
        _yaml.dump(merged, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # Reload the singleton config
    import src.config as _cfg_mod
    _cfg_mod._config = None  # reset singleton so next get_config() reloads

    return {"status": "saved", "summary": get_config().summary()}


# ---- Skills ----

@app.get("/skills", tags=["skills"])
async def list_skills(agent: Optional[str] = None, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all registered skills, optionally filtered by agent or event type."""
    if event_type:
        skills = _skill_registry.skills_for_event(event_type)
    else:
        skills = _skill_registry.list_skills(agent_name=agent)
    return [s.to_dict() for s in skills]


@app.get("/skills/stats", tags=["skills"])
async def skill_stats() -> Dict[str, Any]:
    """Aggregate skill execution statistics."""
    return _skill_registry.get_stats()


@app.get("/skills/history", tags=["skills"])
async def skill_history(
    agent: Optional[str] = None,
    skill_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Skill execution history, optionally filtered."""
    history = _skill_registry.get_history(agent_name=agent, skill_id=skill_id, limit=limit)
    return [e.to_dict() for e in history]


# ---- Integrations Status ----

@app.get("/integrations/status", tags=["integrations"])
async def integrations_status() -> Dict[str, Any]:
    """Status of all optional integrations."""
    cfg = get_config()
    return {
        "supabase": {"configured": cfg.has_supabase, "connected": _supabase_store.is_available},
        "notion": {"configured": cfg.has_notion, "connected": _notion_client.is_available},
        "slack_bot": {"configured": cfg.has_slack_bot, "connected": _slack_bot.is_available},
        "azure_ai_search": {"configured": cfg.has_azure_search},
        "faiss": {"enabled": cfg.faiss_enabled},
        "memory_backend": cfg.memory_backend,
    }


# ---- Supabase ----

@app.get("/supabase/runs", tags=["integrations"])
async def supabase_recent_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """Recent pipeline runs from Supabase (if connected)."""
    return _supabase_store.get_recent_runs(limit=limit)


@app.get("/supabase/rehydrate/{event_id}", tags=["integrations"])
async def supabase_rehydrate(event_id: str) -> Dict[str, Any]:
    """Rehydrate full pipeline state from Supabase."""
    result = _supabase_store.rehydrate(event_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No Supabase record for {event_id}")
    return result


# ---- Notion ----

@app.get("/notion/kb", tags=["integrations"])
async def notion_kb(limit: int = 50) -> List[Dict[str, Any]]:
    """Pull KB articles from Notion database."""
    return _notion_client.pull_kb_articles(limit=limit)


# ---- Slack Enhanced ----

@app.post("/slack/interaction", tags=["integrations"])
async def slack_interaction(request: Request) -> Dict[str, Any]:
    """Handle Slack interactive message callbacks (approve/reject buttons)."""
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not _slack_bot.verify_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = json.loads((await request.form()).get("payload", "{}"))
    return _slack_bot.handle_interaction(payload)


@app.post("/slack/command", tags=["integrations"])
async def slack_command(request: Request) -> Dict[str, Any]:
    """Handle /citadel slash commands from Slack."""
    form = await request.form()
    command = form.get("command", "")
    text = form.get("text", "")
    user_id = form.get("user_id", "")
    return _slack_bot.handle_slash_command(command, text, user_id)


# ---- Metrics (Phase 26) ----

@app.get("/metrics", tags=["system"])
async def prometheus_metrics():
    """Prometheus metrics endpoint.  Returns text/plain exposition format."""
    from fastapi.responses import Response
    if _HAS_MONITORING:
        body, content_type = get_metrics_response()
        return Response(content=body, media_type=content_type)
    return Response(
        content=b"# monitoring module not available\n",
        media_type="text/plain",
    )


# ---- Health ----

@app.get("/health", tags=["system"])
async def health() -> Dict[str, Any]:
    """System health check."""
    cfg = get_config()
    agents = _orchestrator.protocol.list_agents()
    return {
        "status": "ok",
        "service": "citadel-lite",
        "version": "2.1.0",
        "agents_registered": len(agents),
        "agent_names": [a.name for a in agents],
        "execution_mode": cfg.execution_mode,
        "llm_configured": cfg.has_llm,
        "github_configured": cfg.has_github,
        "azure_configured": cfg.has_azure,
        "notifications_configured": cfg.has_notifications,
        "dashboard_enabled": cfg.dashboard_enabled,
        "sse_enabled": cfg.sse_enabled,
        "memory_backend": cfg.memory_backend,
        "skills_registered": _skill_registry.get_stats().get("skills_registered", 0),
        "supabase_connected": _supabase_store.is_available,
        "notion_connected": _notion_client.is_available,
        "slack_bot_connected": _slack_bot.is_available,
        "reflex_rules_loaded": len(_orchestrator.reflex.manifest.rules),
        "pipelines_in_flight": sum(1 for s in _pipeline_status.values() if s == "running"),
        "monitoring_enabled": _HAS_MONITORING and _metrics_enabled() if _HAS_MONITORING else False,
    }
