# src/mcp_server/server.py
"""
MCP (Model Context Protocol) server for Citadel Lite.

Exposes the pipeline as MCP tools and resources, enabling any MCP-compatible
client (Claude Desktop, VS Code, etc.) to interact with Citadel Lite.

Tools:
    citadel_run_pipeline    — Run full pipeline on an event
    citadel_diagnose        — Run Sentinel + Sherlock on event description
    citadel_propose_fix     — Run Fixer on a diagnosis
    citadel_check_governance — Run Guardian on a fix proposal
    citadel_recall_memory   — Search incident memory
    citadel_audit_trail     — Retrieve audit chain for an event

Resources:
    citadel://agents    — List registered agents
    citadel://policies  — Governance policies

Usage:
    python -m src.mcp_server.server
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _build_server():
    """Build and configure the MCP server. Lazy to avoid import at module level."""
    try:
        from mcp.server import Server
        from mcp.types import Tool, Resource, TextContent
    except ImportError:
        return None, None, None

    server = Server("citadel-lite")

    # ----- Tools -----

    @server.tool()
    async def citadel_run_pipeline(
        event_type: str = "ci_failed",
        summary: str = "CI failed",
        log_excerpt: str = "",
        repo: str = "example/repo",
        source: str = "manual",
    ) -> str:
        """Run the full Citadel Lite pipeline on an event and return results."""
        from src.orchestrator_v3 import OrchestratorV3
        from src.types import EventJsonV1, EventArtifact

        event = EventJsonV1(
            event_type=event_type,
            source=source,
            repo=repo,
            summary=summary,
            artifacts=EventArtifact(log_excerpt=log_excerpt),
        )

        orch = OrchestratorV3()
        orch.run_from_event(event)

        # Read outputs
        base = Path("out") / event.event_id
        result = {"event_id": event.event_id, "outputs": {}}

        for fname in ["handoff_packet.json", "decision.json", "execution_outcome.json", "audit_report.json"]:
            fpath = base / fname
            if fpath.exists():
                result["outputs"][fname] = json.loads(fpath.read_text(encoding="utf-8"))

        return json.dumps(result, indent=2, default=str)

    @server.tool()
    async def citadel_diagnose(
        event_type: str = "ci_failed",
        summary: str = "",
        log_excerpt: str = "",
    ) -> str:
        """Run Sentinel + Sherlock to classify and diagnose an incident."""
        from src.types import EventJsonV1, EventArtifact, HandoffPacket
        from src.agents.sentinel_v2 import run_sentinel_v2
        from src.agents.sherlock_v3 import run_sherlock_v3

        event = EventJsonV1(
            event_type=event_type, source="mcp", summary=summary,
            artifacts=EventArtifact(log_excerpt=log_excerpt),
        )
        packet = HandoffPacket(event=event)

        sentinel_result = run_sentinel_v2(packet)
        packet.add_output("sentinel", sentinel_result)

        sherlock_result = run_sherlock_v3(packet)
        packet.add_output("sherlock", sherlock_result)

        return json.dumps({
            "sentinel": sentinel_result,
            "sherlock": sherlock_result,
        }, indent=2, default=str)

    @server.tool()
    async def citadel_propose_fix(
        hypotheses: str = "",
        confidence: float = 0.5,
        severity: str = "medium",
    ) -> str:
        """Run Fixer to propose a remediation given a diagnosis."""
        from src.types import EventJsonV1, EventArtifact, HandoffPacket, AgentOutput
        from src.agents.fixer_v3 import run_fixer_v3

        event = EventJsonV1(event_type="ci_failed", source="mcp", summary="MCP request")
        packet = HandoffPacket(event=event)
        packet.add_output("sentinel", {"severity": severity, "signals": [], "classification": "ci_failed"})
        packet.add_output("sherlock", {
            "hypotheses": [h.strip() for h in hypotheses.split(";") if h.strip()],
            "confidence": confidence,
            "evidence": [],
        })

        result = run_fixer_v3(packet)
        return json.dumps(result, indent=2, default=str)

    @server.tool()
    async def citadel_check_governance(
        risk_estimate: float = 0.3,
        severity: str = "medium",
        fix_plan: str = "",
    ) -> str:
        """Run Guardian governance gate on a fix proposal."""
        from src.types import EventJsonV1, EventArtifact, HandoffPacket
        from src.agents.guardian_v3 import run_guardian_v3

        event = EventJsonV1(event_type="ci_failed", source="mcp", summary="MCP request")
        packet = HandoffPacket(event=event)
        packet.add_output("sentinel", {"severity": severity, "signals": [], "classification": "ci_failed"})
        packet.add_output("sherlock", {"hypotheses": ["MCP diagnosis"], "confidence": 0.7, "evidence": []})
        packet.add_output("fixer", {"fix_plan": fix_plan, "risk_estimate": risk_estimate, "patch": None})

        decision = run_guardian_v3(packet)
        return json.dumps({
            "action": decision.action,
            "risk_score": decision.risk_score,
            "rationale": decision.rationale,
            "policy_refs": decision.policy_refs,
        }, indent=2)

    @server.tool()
    async def citadel_recall_memory(query: str = "", k: int = 5) -> str:
        """Search incident memory for past similar events."""
        from src.memory.store_v2 import LocalMemoryStore

        store = LocalMemoryStore()
        hits = store.recall(query, k=k)
        return json.dumps(hits, indent=2, default=str)

    @server.tool()
    async def citadel_audit_trail(event_id: str = "") -> str:
        """Retrieve the audit trail for a specific event."""
        base = Path("out") / event_id
        audit_path = base / "audit_report.json"
        if audit_path.exists():
            return audit_path.read_text(encoding="utf-8")
        return json.dumps({"error": f"No audit trail found for {event_id}"})

    # ----- Resources -----

    @server.resource("citadel://agents")
    async def list_agents() -> str:
        """List all registered agents and their capabilities."""
        from src.a2a.agent_wrapper import build_protocol_v2

        proto = build_protocol_v2()
        agents = []
        for name, card in proto._registry.items():
            agents.append({
                "name": card.name,
                "capabilities": card.capabilities,
                "version": card.version,
                "status": card.status,
            })
        return json.dumps({"agents": agents}, indent=2)

    @server.resource("citadel://policies")
    async def list_policies() -> str:
        """List governance policies and compliance mappings."""
        try:
            from src.governance.policy_engine import PolicyEngine
            engine = PolicyEngine()
            return json.dumps(engine.generate_report(), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    return server


def main():
    """Run the MCP server via stdio transport."""
    server = _build_server()
    if server is None:
        print("ERROR: mcp package not installed. Run: pip install mcp", file=sys.stderr)
        sys.exit(1)

    try:
        from mcp.server.stdio import stdio_server
        import asyncio

        async def run():
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream)

        asyncio.run(run())
    except ImportError:
        print("ERROR: mcp package not installed. Run: pip install mcp", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
