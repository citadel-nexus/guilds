import unittest
import numpy as np
from src.modules.sherlock import Sherlock

class TestSherlock(unittest.TestCase):
    def setUp(self):
        """
        Set up the Sherlock instance and train the model for testing.
        """
        self.sherlock = Sherlock()

        # Sample training data
        X_train = np.array([[10], [20], [30], [40], [50]])
        y_train = np.array([0, 0, 1, 1, 1])  # Binary classification labels

        self.sherlock.train_model(X_train, y_train)

    def test_rule_based_diagnostics(self):
        """
        Test the rule-based diagnostic logic.
        """
        data = [150, -10, 50]
        results = self.sherlock.apply_rules(data)

        expected_results = [
            {"rule": "High Value Anomaly", "message": "Value exceeds threshold."},
            {"rule": "Negative Value", "message": "Negative value detected."}
        ]

        self.assertEqual(results, expected_results)

    def test_model_predictions(self):
        """
        Test the machine learning model predictions.
        """
        data = [15, 35]
        predictions = self.sherlock.diagnose(data)["model_predictions"]

        # Expected predictions based on the trained model
        expected_predictions = [0, 1]

        self.assertEqual(predictions, expected_predictions)

    def test_combined_diagnostics(self):
        """
        Test the combined diagnostics (rule-based + model predictions).
        """
        data = [150, -10, 35]
        diagnostics = self.sherlock.diagnose(data)

        # Check rule-based results
        expected_rule_results = [
            {"rule": "High Value Anomaly", "message": "Value exceeds threshold."},
            {"rule": "Negative Value", "message": "Negative value detected."}
        ]
        self.assertEqual(diagnostics["rule_results"], expected_rule_results)

        # Check model predictions
        expected_model_predictions = [1, 0, 1]  # Based on the trained model
        self.assertEqual(diagnostics["model_predictions"], expected_model_predictions)

if __name__ == "__main__":
    unittest.main()
