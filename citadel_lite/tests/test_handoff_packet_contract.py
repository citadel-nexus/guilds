import pytest
from src.contracts.handoff_packet_contract import HandoffPacketContract


def test_missing_required_fields():
    """Test that missing required fields raise a ValueError."""
    # Test case with missing 'id'
    with pytest.raises(ValueError, match="Missing required fields: \['id'\]"):
        HandoffPacketContract(timestamp="2023-10-10T10:00:00Z", payload={})

    # Test case with missing 'timestamp'
    with pytest.raises(ValueError, match="Missing required fields: \['timestamp'\]"):
        HandoffPacketContract(id="12345", payload={})

    # Test case with missing 'payload'
    with pytest.raises(ValueError, match="Missing required fields: \['payload'\]"):
        HandoffPacketContract(id="12345", timestamp="2023-10-10T10:00:00Z")


def test_from_json_validation():
    """Test that from_json validates the deserialized instance."""
    # Valid JSON input
    valid_json = '{"id": "12345", "timestamp": "2023-10-10T10:00:00Z", "payload": {"key": "value"}}'
    instance = HandoffPacketContract.from_json(valid_json)
    assert instance.id == "12345"
    assert instance.timestamp == "2023-10-10T10:00:00Z"
    assert instance.payload == {"key": "value"}

    # Invalid JSON input (missing 'id')
    invalid_json = '{"timestamp": "2023-10-10T10:00:00Z", "payload": {"key": "value"}}'
    with pytest.raises(ValueError, match="Missing required fields: \['id'\]"):
        HandoffPacketContract.from_json(invalid_json)

    # Invalid JSON input (malformed JSON)
    malformed_json = '{"id": "12345", "timestamp": "2023-10-10T10:00:00Z", "payload": {"key": "value"}'
    with pytest.raises(Exception):
        HandoffPacketContract.from_json(malformed_json)


def test_to_json():
    """Test that to_json serializes the instance correctly."""
    instance = HandoffPacketContract(id="12345", timestamp="2023-10-10T10:00:00Z", payload={"key": "value"})
    json_output = instance.to_json()
    assert json_output == '{"id": "12345", "timestamp": "2023-10-10T10:00:00Z", "payload": {"key": "value"}}'
