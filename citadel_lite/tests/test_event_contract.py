import unittest
from src.contracts.event_contract import EventContract
from jsonschema.exceptions import ValidationError

class TestEventContract(unittest.TestCase):
    def setUp(self):
        self.contract = EventContract()

    def test_valid_event(self):
        valid_event = {
            "event_id": "12345",
            "event_type": "user_signup",
            "timestamp": "2023-10-01T12:00:00Z",
            "payload": {"user_id": "67890"},
            "metadata": {"source": "web", "version": "1.0"}
        }
        self.assertTrue(self.contract.validate(valid_event))

    def test_missing_required_field(self):
        invalid_event = {
            "event_type": "user_signup",
            "timestamp": "2023-10-01T12:00:00Z",
            "payload": {"user_id": "67890"},
            "metadata": {"source": "web", "version": "1.0"}
        }
        with self.assertRaises(ValidationError):
            self.contract.validate(invalid_event)

    def test_invalid_field_type(self):
        invalid_event = {
            "event_id": 12345,  # Should be a string
            "event_type": "user_signup",
            "timestamp": "2023-10-01T12:00:00Z",
            "payload": {"user_id": "67890"},
            "metadata": {"source": "web", "version": "1.0"}
        }
        with self.assertRaises(ValidationError):
            self.contract.validate(invalid_event)

    def test_missing_metadata_fields(self):
        invalid_event = {
            "event_id": "12345",
            "event_type": "user_signup",
            "timestamp": "2023-10-01T12:00:00Z",
            "payload": {"user_id": "67890"},
            "metadata": {"source": "web"}  # Missing "version"
        }
        with self.assertRaises(ValidationError):
            self.contract.validate(invalid_event)

if __name__ == "__main__":
    unittest.main()