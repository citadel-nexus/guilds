# tests/test_a2a_protocol.py
"""Tests for the A2A handoff protocol."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.types import HandoffPacket, EventJsonV1, EventArtifact
from src.a2a.protocol import A2AProtocol, AgentCard, A2AMessage
from src.a2a.agent_wrapper import build_protocol, get_decision_from_packet


def _make_test_event() -> EventJsonV1:
    return EventJsonV1(
        event_id="test-001",
        event_type="ci_failed",
        source="github_actions",
        repo="test/repo",
        ref="main",
        summary="CI failed on unit tests",
        artifacts=EventArtifact(
            log_excerpt="ModuleNotFoundError: No module named 'requests'",
            links=["https://example.com/log"],
        ),
    )


def test_agent_registration():
    proto = A2AProtocol()
    card = AgentCard(name="test_agent", capabilities=["test"])
    proto.register(card, lambda msg: msg)

    assert proto.get_card("test_agent") is not None
    assert proto.get_card("nonexistent") is None
    assert len(proto.list_agents()) == 1


def test_handoff_dispatch():
    proto = A2AProtocol()
    card = AgentCard(name="echo", capabilities=["echo"])

    def echo_handler(msg: A2AMessage) -> A2AMessage:
        msg.packet.add_output("echo", {"echoed": True})
        return msg

    proto.register(card, echo_handler)

    packet = HandoffPacket(event=_make_test_event())
    msg = A2AMessage(to_agent="echo", packet=packet)
    response = proto.handoff(msg)

    assert response.error is None
    assert "echo" in response.packet.agent_outputs
    assert response.packet.agent_outputs["echo"].payload["echoed"] is True


def test_handoff_unknown_agent():
    proto = A2AProtocol()
    packet = HandoffPacket(event=_make_test_event())
    msg = A2AMessage(to_agent="nonexistent", packet=packet)
    response = proto.handoff(msg)

    assert response.error is not None
    assert "not registered" in response.error


def test_full_pipeline():
    proto = build_protocol()
    event = _make_test_event()
    packet = HandoffPacket(event=event)

    result = proto.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])

    assert "sentinel" in result.agent_outputs
    assert "sherlock" in result.agent_outputs
    assert "fixer" in result.agent_outputs
    assert "guardian" in result.agent_outputs

    decision = get_decision_from_packet(result)
    assert decision.action in ("approve", "need_approval", "block")
    assert 0 <= decision.risk_score <= 1


def test_trace_recorded():
    proto = build_protocol()
    event = _make_test_event()
    packet = HandoffPacket(event=event)

    proto.pipeline(packet, ["sentinel", "sherlock", "fixer", "guardian"])
    trace = proto.get_trace()

    assert len(trace) == 4
    assert trace[0].stage == "sentinel"
    assert trace[3].stage == "guardian"


if __name__ == "__main__":
    test_agent_registration()
    test_handoff_dispatch()
    test_handoff_unknown_agent()
    test_full_pipeline()
    test_trace_recorded()
    print("All A2A protocol tests passed.")
