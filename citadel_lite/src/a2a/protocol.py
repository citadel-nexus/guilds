# src/a2a/protocol.py
"""
A2A (Agent-to-Agent) handoff protocol for Citadel Lite.

Provides agent registration, message-based handoff, and sequential pipeline
execution. Each agent receives an A2AMessage containing the HandoffPacket,
processes it, and returns an updated message to the next agent in the chain.

Reference: CNWB src/ais/orchestrator.py CouncilPipeline pattern.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.types import HandoffPacket, Decision


# ---------- Data Contracts ----------

@dataclass
class AgentCard:
    """Identity and capability declaration for a registered agent."""
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    capabilities: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    status: str = "active"  # active | suspended | offline


@dataclass
class A2AMessage:
    """Single handoff message between two agents."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str = "orchestrator"
    to_agent: str = ""
    stage: str = ""
    packet: HandoffPacket = field(default_factory=HandoffPacket)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error: Optional[str] = None


# Handler signature: receives A2AMessage, returns updated A2AMessage
AgentHandler = Callable[[A2AMessage], A2AMessage]


# ---------- Protocol ----------

class A2AProtocol:
    """
    Agent registry and message-based handoff dispatcher.

    Usage:
        proto = A2AProtocol()
        proto.register(card, handler_fn)
        result_packet = proto.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])
    """

    def __init__(self) -> None:
        self._registry: Dict[str, AgentCard] = {}
        self._handlers: Dict[str, AgentHandler] = {}
        self._trace: List[A2AMessage] = []

    # ---- registration ----

    def register(self, card: AgentCard, handler: AgentHandler) -> None:
        """Register an agent with its handler function."""
        self._registry[card.name] = card
        self._handlers[card.name] = handler

    def get_card(self, name: str) -> Optional[AgentCard]:
        return self._registry.get(name)

    def list_agents(self) -> List[AgentCard]:
        return list(self._registry.values())

    # ---- handoff ----

    def handoff(self, message: A2AMessage) -> A2AMessage:
        """
        Dispatch a single handoff message to the target agent.
        Returns the agent's response message.
        """
        handler = self._handlers.get(message.to_agent)
        if handler is None:
            message.error = f"agent '{message.to_agent}' not registered"
            self._trace.append(message)
            return message

        response = handler(message)
        response.from_agent = message.to_agent
        response.to_agent = "orchestrator"
        self._trace.append(response)
        return response

    # ---- pipeline ----

    def pipeline(
        self,
        packet: HandoffPacket,
        stages: List[str],
        trace_id: Optional[str] = None,
    ) -> HandoffPacket:
        """
        Run the packet through a sequence of agents via A2A handoff.
        Each agent receives the cumulative packet and appends its output.
        Returns the final packet (with all agent_outputs populated).
        """
        tid = trace_id or str(uuid.uuid4())

        for stage_name in stages:
            msg = A2AMessage(
                trace_id=tid,
                from_agent="orchestrator",
                to_agent=stage_name,
                stage=stage_name,
                packet=packet,
            )
            response = self.handoff(msg)

            if response.error:
                raise RuntimeError(
                    f"A2A handoff failed at stage '{stage_name}': {response.error}"
                )

            # The handler updates packet in-place via add_output;
            # also accept packet replacement if handler returns a new one.
            packet = response.packet

        return packet

    # ---- trace ----

    def get_trace(self) -> List[A2AMessage]:
        """Return the full handoff trace for audit purposes."""
        return list(self._trace)

    def clear_trace(self) -> None:
        self._trace.clear()
