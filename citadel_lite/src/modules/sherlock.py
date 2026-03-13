from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
import logging
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Sherlock:
    """
    Sherlock is a modular diagnostic system that analyzes input data, identifies anomalies,
    and provides actionable insights using a combination of rule-based logic and machine learning models.
    """
    model: Pipeline = field(init=False)
    rules: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        """
        Initialize the machine learning model and define rule-based logic.
        """
        logger.info("Initializing Sherlock diagnostic system.")

        # Initialize a simple RandomForestClassifier pipeline with scaling
        self.model = Pipeline([
            ('scaler', StandardScaler()),
            ('classifier', RandomForestClassifier(random_state=42))
        ])

        # Define rule-based logic as a list of rules
        self.rules = [
            {"name": "High Value Anomaly", "condition": lambda x: x > 100, "message": "Value exceeds threshold."},
            {"name": "Negative Value", "condition": lambda x: x < 0, "message": "Negative value detected."}
        ]

    def train_model(self, X: np.ndarray, y: np.ndarray) -> None:
        """
        Train the machine learning model using the provided data.

        Args:
            X (np.ndarray): Feature matrix.
            y (np.ndarray): Target labels.
        """
        logger.info("Training the machine learning model.")
        self.model.fit(X, y)
        logger.info("Model training complete.")

    def apply_rules(self, data: List[float]) -> List[Dict[str, str]]:
        """
        Apply rule-based logic to the input data.

        Args:
            data (List[float]): List of numerical values to analyze.

        Returns:
            List[Dict[str, str]]: List of rule violations with messages.
        """
        logger.info("Applying rule-based diagnostics.")
        results = []
        for value in data:
            for rule in self.rules:
                if rule["condition"](value):
                    results.append({"rule": rule["name"], "message": rule["message"]})
        return results

    def diagnose(self, data: List[float]) -> Dict[str, Any]:
        """
        Perform diagnostics on the input data using both rule-based logic and the machine learning model.

        Args:
            data (List[float]): List of numerical values to analyze.

        Returns:
            Dict[str, Any]: Diagnostic results including rule violations and model predictions.
        """
        logger.info("Starting diagnostics.")

        # Apply rule-based diagnostics
        rule_results = self.apply_rules(data)

        # Prepare data for model prediction
        data_array = np.array(data).reshape(-1, 1)
        model_predictions = self.model.predict(data_array).tolist()

        logger.info("Diagnostics complete.")
        return {
            "rule_results": rule_results,
            "model_predictions": model_predictions
        }
