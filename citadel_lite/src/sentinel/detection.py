import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import numpy as np
from sklearn.base import BaseEstimator
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DetectionPipeline:
    """
    A modular pipeline for detection and classification.
    """
    detection_rules: List[Callable[[np.ndarray], bool]] = field(default_factory=list)
    classifier: Optional[BaseEstimator] = None
    scaler: Optional[StandardScaler] = None
    categories: List[str] = field(default_factory=list)

    def detect(self, data: np.ndarray) -> List[bool]:
        """
        Apply detection rules to the input data.

        Args:
            data (np.ndarray): Input data to analyze.

        Returns:
            List[bool]: A list of booleans indicating whether each rule detected an anomaly.
        """
        logger.info("Running detection rules...")
        results = []
        for rule in self.detection_rules:
            result = rule(data)
            results.append(result)
            logger.debug(f"Rule {rule.__name__} result: {result}")
        return results

    def classify(self, data: np.ndarray) -> str:
        """
        Classify the input data into predefined categories.

        Args:
            data (np.ndarray): Input data to classify.

        Returns:
            str: The predicted category.
        """
        if self.scaler:
            logger.info("Scaling input data...")
            data = self.scaler.transform(data.reshape(1, -1))

        if self.classifier:
            logger.info("Classifying input data...")
            prediction = self.classifier.predict(data)[0]
            category = self.categories[prediction]
            logger.debug(f"Predicted category: {category}")
            return category
        else:
            logger.error("Classifier not configured.")
            raise ValueError("Classifier not configured.")

# Example detection rules
def rule_high_variance(data: np.ndarray) -> bool:
    """
    Detect if the variance of the data exceeds a threshold.

    Args:
        data (np.ndarray): Input data.

    Returns:
        bool: True if variance exceeds threshold, False otherwise.
    """
    threshold = 10.0
    variance = np.var(data)
    logger.debug(f"Variance: {variance}, Threshold: {threshold}")
    return variance > threshold

def rule_outlier_detection(data: np.ndarray) -> bool:
    """
    Detect if there are outliers in the data based on z-score.

    Args:
        data (np.ndarray): Input data.

    Returns:
        bool: True if outliers are detected, False otherwise.
    """
    z_scores = np.abs((data - np.mean(data)) / np.std(data))
    threshold = 3.0
    outliers = np.any(z_scores > threshold)
    logger.debug(f"Z-scores: {z_scores}, Threshold: {threshold}, Outliers: {outliers}")
    return outliers

# Example usage
if __name__ == "__main__":
    # Sample data
    sample_data = np.array([1, 2, 3, 100, 5])

    # Configure pipeline
    pipeline = DetectionPipeline(
        detection_rules=[rule_high_variance, rule_outlier_detection],
        classifier=RandomForestClassifier(),
        scaler=StandardScaler(),
        categories=["Normal", "Anomalous"]
    )

    # Fit scaler and classifier (mock example)
    X_train = np.random.rand(100, 5)
    y_train = np.random.randint(0, 2, 100)
    pipeline.scaler.fit(X_train)
    pipeline.classifier.fit(pipeline.scaler.transform(X_train), y_train)

    # Run detection
    detection_results = pipeline.detect(sample_data)
    logger.info(f"Detection results: {detection_results}")

    # Run classification
    classification_result = pipeline.classify(np.array([1, 2, 3, 4, 5]))
    logger.info(f"Classification result: {classification_result}")
