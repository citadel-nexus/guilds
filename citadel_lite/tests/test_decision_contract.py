import unittest
from src.contracts.decision_contract import DecisionContract

class TestDecisionContract(unittest.TestCase):
    def test_valid_data(self):
        valid_data = {
            "decision_id": "12345",
            "timestamp": "2023-10-01T12:00:00",
            "metadata": {"key": "value"},
            "participants": ["Alice", "Bob"]
        }
        self.assertTrue(DecisionContract.validate(valid_data))

    def test_missing_decision_id(self):
        invalid_data = {
            "timestamp": "2023-10-01T12:00:00",
            "metadata": {"key": "value"},
            "participants": ["Alice", "Bob"]
        }
        self.assertFalse(DecisionContract.validate(invalid_data))

    def test_invalid_timestamp_format(self):
        invalid_data = {
            "decision_id": "12345",
            "timestamp": "2023-10-01 12:00:00",  # Invalid format
            "metadata": {"key": "value"},
            "participants": ["Alice", "Bob"]
        }
        self.assertFalse(DecisionContract.validate(invalid_data))

    def test_invalid_metadata_type(self):
        invalid_data = {
            "decision_id": "12345",
            "timestamp": "2023-10-01T12:00:00",
            "metadata": "not_a_dict",  # Invalid type
            "participants": ["Alice", "Bob"]
        }
        self.assertFalse(DecisionContract.validate(invalid_data))

    def test_invalid_participants_type(self):
        invalid_data = {
            "decision_id": "12345",
            "timestamp": "2023-10-01T12:00:00",
            "metadata": {"key": "value"},
            "participants": "not_a_list"  # Invalid type
        }
        self.assertFalse(DecisionContract.validate(invalid_data))

if __name__ == "__main__":
    unittest.main()