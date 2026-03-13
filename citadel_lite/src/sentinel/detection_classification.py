from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DetectionResult:
    """Represents the result of the detection process."""
    detected_items: List[str]
    anomalies: List[str]

@dataclass
class ClassificationResult:
    """Represents the result of the classification process."""
    categories: Dict[str, List[str]]

class Detector:
    """Detection module to identify patterns or anomalies in input data."""

    def __init__(self, patterns: List[str]):
        """
        Initialize the detector with predefined patterns.

        :param patterns: List of patterns to detect in the input data.
        """
        self.patterns = patterns
        logger.info("Detector initialized with patterns: %s", patterns)

    def detect(self, data: List[str]) -> DetectionResult:
        """
        Detect predefined patterns and anomalies in the input data.

        :param data: List of input data strings to analyze.
        :return: DetectionResult containing detected items and anomalies.
        """
        detected_items = []
        anomalies = []

        for item in data:
            if any(pattern in item for pattern in self.patterns):
                detected_items.append(item)
            else:
                anomalies.append(item)

        logger.info("Detection complete. Detected items: %s, Anomalies: %s", detected_items, anomalies)
        return DetectionResult(detected_items=detected_items, anomalies=anomalies)

class Classifier:
    """Classification module to categorize detected items."""

    def __init__(self, categories: Dict[str, List[str]]):
        """
        Initialize the classifier with predefined categories.

        :param categories: Dictionary mapping category names to lists of keywords.
        """
        self.categories = categories
        logger.info("Classifier initialized with categories: %s", categories)

    def classify(self, detected_items: List[str]) -> ClassificationResult:
        """
        Classify detected items into predefined categories.

        :param detected_items: List of items to classify.
        :return: ClassificationResult containing categorized items.
        """
        categorized = {category: [] for category in self.categories}

        for item in detected_items:
            categorized_flag = False
            for category, keywords in self.categories.items():
                if any(keyword in item for keyword in keywords):
                    categorized[category].append(item)
                    categorized_flag = True
                    break

            if not categorized_flag:
                categorized.setdefault("Uncategorized", []).append(item)

        logger.info("Classification complete. Categories: %s", categorized)
        return ClassificationResult(categories=categorized)

class DetectionClassificationPipeline:
    """Pipeline to handle detection and classification."""

    def __init__(self, detector: Detector, classifier: Classifier):
        """
        Initialize the pipeline with a detector and classifier.

        :param detector: Instance of the Detector class.
        :param classifier: Instance of the Classifier class.
        """
        self.detector = detector
        self.classifier = classifier
        logger.info("Pipeline initialized.")

    def process(self, data: List[str]) -> Tuple[DetectionResult, ClassificationResult]:
        """
        Process input data through detection and classification.

        :param data: List of input data strings to process.
        :return: Tuple containing DetectionResult and ClassificationResult.
        """
        logger.info("Starting pipeline processing.")
        detection_result = self.detector.detect(data)
        classification_result = self.classifier.classify(detection_result.detected_items)
        logger.info("Pipeline processing complete.")
        return detection_result, classification_result

# Example usage and testing
if __name__ == "__main__":
    # Define patterns and categories for testing
    patterns = ["error", "warning", "critical"]
    categories = {
        "Errors": ["error"],
        "Warnings": ["warning"],
        "Critical": ["critical"]
    }

    # Initialize components
    detector = Detector(patterns=patterns)
    classifier = Classifier(categories=categories)
    pipeline = DetectionClassificationPipeline(detector=detector, classifier=classifier)

    # Sample data
    sample_data = [
        "error: file not found",
        "warning: low disk space",
        "critical: system failure",
        "info: operation successful"
    ]

    # Process data through the pipeline
    detection_result, classification_result = pipeline.process(sample_data)

    # Output results
    print("Detection Result:", detection_result)
    print("Classification Result:", classification_result)