# src/azure/foundry_agents.py
"""
Wraps each Citadel Lite agent as a Microsoft Foundry Agent Service call.

Each agent:
1. Sends the HandoffPacket context to Azure OpenAI via Foundry
2. Parses the structured JSON response
3. Falls back to local agent function if Foundry is unavailable

Requires: pip install openai azure-identity
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from typing import Any, Callable, Dict, Optional

from src.types import HandoffPacket, Decision
from src.a2a.protocol import A2AMessage, AgentCard, AgentHandler, A2AProtocol
from src.azure.config import AzureConfig

# Local fallbacks (v2/v3 agents)
from src.agents.sentinel_v2 import run_sentinel_v2 as run_sentinel
from src.agents.sherlock_v3 import run_sherlock_v3 as run_sherlock
from src.agents.fixer_v3 import run_fixer_v3 as run_fixer
from src.agents.guardian_v3 import run_guardian_v3 as run_guardian

try:
    from openai import AzureOpenAI
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False


# ---------- System Prompts ----------

AGENT_PROMPTS = {
    "sentinel": """You are Sentinel, a CI/CD event detection and classification agent.
Given an event, classify it and assess severity.
Return JSON: {"classification": str, "severity": "low"|"medium"|"high"|"critical", "signals": [str]}""",

    "sherlock": """You are Sherlock, a root cause diagnosis agent.
Given an event and its classification, diagnose the most likely root cause(s).
Use memory_hits if available to inform your diagnosis.
Return JSON: {"hypotheses": [str], "confidence": float(0-1), "evidence": [str]}""",

    "fixer": """You are Fixer, a repair proposal agent.
Given an event, diagnosis, and memory of past fixes, propose a concrete fix.
Return JSON: {"fix_plan": str, "patch": str|null, "risk_estimate": float(0-1)}""",

    "guardian": """You are Guardian, a governance and risk evaluation agent.
Given the full pipeline context, evaluate risk and make a decision.
Return JSON: {"action": "approve"|"need_approval"|"block", "risk_score": float(0-1), "rationale": str, "policy_refs": [str]}""",
}


# ---------- Foundry Agent Wrapper ----------

class FoundryAgentWrapper:
    """
    Wraps a single agent as a Foundry Agent Service / Azure OpenAI call.
    Falls back to local function if the call fails.
    """

    # Env var names for agent IDs (looked up at invoke time, not import time)
    _ASSISTANT_ENV: Dict[str, str] = {
        "sentinel": "AZURE_AGENT_SENTINEL",
        "guardian": "AZURE_AGENT_GUARDIAN",
    }

    def __init__(
        self,
        agent_name: str,
        config: AzureConfig,
        local_fallback: Callable[[HandoffPacket], Any],
    ) -> None:
        self.agent_name = agent_name
        self.config = config
        self.local_fallback = local_fallback
        self._client: Optional[AzureOpenAI] = None

        if _HAS_OPENAI and config.openai_endpoint and config.openai_key:
            self._client = AzureOpenAI(
                azure_endpoint=config.openai_endpoint,
                api_key=config.openai_key,
                api_version="2025-01-01-preview",
            )

    def _get_assistant_id(self) -> str:
        """Read assistant ID from env at call time (not frozen at import)."""
        env_var = self._ASSISTANT_ENV.get(self.agent_name, "")
        return os.environ.get(env_var, "") if env_var else ""

    def invoke(self, packet: HandoffPacket) -> Dict[str, Any]:
        """Call Azure OpenAI — prefers Assistants thread if agent ID is set, else chat completions."""
        if self._client is None:
            return self._run_local(packet)

        try:
            assistant_id = self._get_assistant_id()
            if assistant_id:
                return self._run_thread(packet, assistant_id)
            return self._run_chat(packet)
        except Exception as e:
            print(f"[foundry/{self.agent_name}] call failed ({e}), falling back to local")
            return self._run_local(packet)

    def _run_thread(self, packet: HandoffPacket, assistant_id: str) -> Dict[str, Any]:
        """Run via Assistants thread (stateful, uses pre-configured assistant)."""
        import time
        context = self._build_context(packet)
        thread = self._client.beta.threads.create()
        self._client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=json.dumps(context, ensure_ascii=False),
        )
        run = self._client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id,
        )
        # Poll until done (max 60s)
        deadline = time.time() + 60
        while run.status in ("queued", "in_progress") and time.time() < deadline:
            time.sleep(2)
            run = self._client.beta.threads.runs.retrieve(
                thread_id=thread.id, run_id=run.id
            )

        if run.status != "completed":
            raise RuntimeError(f"Thread run {run.status}: {run.last_error}")

        msgs = self._client.beta.threads.messages.list(thread_id=thread.id)
        for m in msgs.data:
            if m.role == "assistant":
                raw = m.content[0].text.value
                # Strip markdown code fences if present
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                return json.loads(raw)

        raise RuntimeError("No assistant message in thread")

    def _run_chat(self, packet: HandoffPacket) -> Dict[str, Any]:
        """Fallback: chat completions (stateless)."""
        context = self._build_context(packet)
        kwargs: Dict[str, Any] = dict(
            model=self.config.openai_deployment,
            messages=[
                {"role": "system", "content": AGENT_PROMPTS.get(self.agent_name, "You are a helpful agent.")},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
        )
        if self.config.openai_deployment != "o1":
            kwargs["temperature"] = 0.2
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return json.loads(content)

    def _run_local(self, packet: HandoffPacket) -> Any:
        """Run the local agent function as fallback."""
        return self.local_fallback(packet)

    def _build_context(self, packet: HandoffPacket) -> Dict[str, Any]:
        """Build the context payload sent to the LLM."""
        ctx: Dict[str, Any] = {
            "event_type": packet.event.event_type,
            "source": packet.event.source,
            "summary": packet.event.summary,
            "repo": packet.event.repo,
            "ref": packet.event.ref,
        }

        if packet.event.artifacts:
            ctx["log_excerpt"] = packet.event.artifacts.log_excerpt
            ctx["links"] = packet.event.artifacts.links

        if packet.memory_hits:
            ctx["memory_hits"] = packet.memory_hits

        if packet.agent_outputs:
            ctx["previous_agents"] = {
                name: out.payload
                for name, out in packet.agent_outputs.items()
            }

        return ctx


# ---------- A2A Handler Factories ----------

def _make_foundry_dict_handler(wrapper: FoundryAgentWrapper, name: str) -> AgentHandler:
    """Create an A2A handler for a dict-returning Foundry agent."""
    def handler(msg: A2AMessage) -> A2AMessage:
        result = wrapper.invoke(msg.packet)
        msg.packet.add_output(name, result)
        return msg
    return handler


def _make_foundry_guardian_handler(wrapper: FoundryAgentWrapper) -> AgentHandler:
    """Create an A2A handler for the Guardian Foundry agent."""
    def handler(msg: A2AMessage) -> A2AMessage:
        result = wrapper.invoke(msg.packet)

        # Guardian may return Decision-like dict from LLM
        if isinstance(result, dict):
            decision = Decision(
                action=result.get("action", "block"),
                risk_score=float(result.get("risk_score", 1.0)),
                rationale=result.get("rationale", ""),
                policy_refs=result.get("policy_refs", []),
            )
        else:
            decision = result

        msg.packet.add_output("guardian", {
            "action": decision.action,
            "risk_score": decision.risk_score,
            "rationale": decision.rationale,
            "policy_refs": decision.policy_refs,
        })
        msg.packet.risk = {
            "decision": decision,
            "risk_score": decision.risk_score,
        }
        return msg
    return handler


def build_foundry_protocol(config: AzureConfig) -> A2AProtocol:
    """
    Build an A2AProtocol with Foundry-backed agents.
    Falls back to local agents if Foundry is not configured.
    """
    proto = A2AProtocol()

    agents = [
        ("sentinel", run_sentinel, ["detect", "classify"]),
        ("sherlock", run_sherlock, ["diagnose", "root_cause"]),
        ("fixer", run_fixer, ["propose_fix", "patch"]),
    ]

    for name, local_fn, caps in agents:
        wrapper = FoundryAgentWrapper(name, config, local_fn)
        card = AgentCard(name=name, capabilities=caps)
        proto.register(card, _make_foundry_dict_handler(wrapper, name))

    # Guardian
    guardian_wrapper = FoundryAgentWrapper("guardian", config, run_guardian)
    guardian_card = AgentCard(name="guardian", capabilities=["governance", "risk_gate"])
    proto.register(guardian_card, _make_foundry_guardian_handler(guardian_wrapper))

    return proto
