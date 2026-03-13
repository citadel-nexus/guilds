import unittest
import jsonschema
from src.contracts.handoff_packet import HandoffPacket


class TestHandoffPacket(unittest.TestCase):
    def setUp(self):
        self.valid_data = {
            "source_agent_id": "agent_123",
            "target_agent_id": "agent_456",
            "payload": {"key": "value"},
            "timestamp": "2023-10-01T12:00:00Z",
            "metadata": {"priority": "high"},
        }

    def test_handoff_packet_validation(self):
        packet = HandoffPacket.from_dict(self.valid_data)
        self.assertTrue(packet.validate())

    def test_handoff_packet_serialization(self):
        packet = HandoffPacket.from_dict(self.valid_data)
        serialized = packet.to_dict()
        self.assertEqual(serialized, self.valid_data)

    def test_handoff_packet_deserialization(self):
        packet = HandoffPacket.from_dict(self.valid_data)
        self.assertEqual(packet.source_agent_id, "agent_123")
        self.assertEqual(packet.target_agent_id, "agent_456")
        self.assertEqual(packet.payload, {"key": "value"})
        self.assertEqual(packet.timestamp, "2023-10-01T12:00:00Z")
        self.assertEqual(packet.metadata, {"priority": "high"})

    def test_handoff_packet_empty_source_agent_id_is_schema_valid(self):
        # Schema validates types only; empty string is a valid string per JSON Schema
        data = self.valid_data.copy()
        data["source_agent_id"] = ""
        packet = HandoffPacket.from_dict(data)
        self.assertTrue(packet.validate())

    def test_handoff_packet_empty_target_agent_id_is_schema_valid(self):
        # Schema validates types only; empty string is a valid string per JSON Schema
        data = self.valid_data.copy()
        data["target_agent_id"] = ""
        packet = HandoffPacket.from_dict(data)
        self.assertTrue(packet.validate())

    def test_handoff_packet_invalid_payload(self):
        # payload must be an object (dict); wrong type raises jsonschema.ValidationError
        invalid_data = self.valid_data.copy()
        invalid_data["payload"] = "not_a_dict"
        with self.assertRaises(jsonschema.ValidationError):
            HandoffPacket.from_dict(invalid_data)

    def test_handoff_packet_empty_timestamp_is_schema_valid(self):
        # timestamp is ["string", "null"]; empty string is a valid string per JSON Schema
        data = self.valid_data.copy()
        data["timestamp"] = ""
        packet = HandoffPacket.from_dict(data)
        self.assertTrue(packet.validate())


if __name__ == "__main__":
    unittest.main()
