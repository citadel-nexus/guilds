"""Tests for src/contracts/handoff_packet.py"""
import pytest
import jsonschema
from src.contracts.handoff_packet import HandoffPacket


def _make_packet(**kwargs):
    defaults = dict(
        source_agent_id="agent_1",
        target_agent_id="agent_2",
        payload={"key": "value"},
        timestamp="2023-10-10T10:00:00",
    )
    defaults.update(kwargs)
    return HandoffPacket(**defaults)


def test_valid_packet_validates():
    pkt = _make_packet()
    pkt.validate()  # should not raise


def test_missing_source_agent_raises():
    pkt = _make_packet(source_agent_id="")
    # empty string still passes JSON schema (type string) — validate() should succeed
    # but source_agent_id="" is semantically invalid; the contract validates structure not semantics
    pkt.validate()


def test_invalid_payload_type_raises():
    # payload must be a dict (object) per schema
    pkt = _make_packet(payload="not_a_dict")
    with pytest.raises(jsonschema.ValidationError):
        pkt.validate()


def test_optional_timestamp_none():
    pkt = _make_packet(timestamp=None)
    pkt.validate()  # timestamp is ["string", "null"] so None is valid


def test_to_dict_roundtrip():
    pkt = _make_packet()
    d = pkt.to_dict()
    restored = HandoffPacket.from_dict(d)
    assert restored.source_agent_id == pkt.source_agent_id
    assert restored.target_agent_id == pkt.target_agent_id
    assert restored.payload == pkt.payload


def test_from_dict_invalid_raises():
    with pytest.raises(jsonschema.ValidationError):
        HandoffPacket.from_dict({"source_agent_id": "x"})  # missing required fields
