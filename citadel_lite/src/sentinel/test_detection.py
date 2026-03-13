import unittest
from sentinel.detection import DetectionModule, ClassificationModule, SentinelPipeline, DetectionResult, ClassificationResult

class TestDetectionModule(unittest.TestCase):
    def test_detect(self):
        detection_rules = {
            "pattern1": "Description of pattern1",
            "pattern2": "Description of pattern2"
        }
        detection_module = DetectionModule(detection_rules=detection_rules)

        data = ["pattern1", "pattern2", "unknown_pattern"]
        result = detection_module.detect(data)

        self.assertEqual(result.detected_patterns, ["pattern1", "pattern2"])
        self.assertEqual(result.anomalies, ["unknown_pattern"])

class TestClassificationModule(unittest.TestCase):
    def test_classify(self):
        classification_rules = {
            "pattern1": "ClassA",
            "pattern2": "ClassB"
        }
        classification_module = ClassificationModule(classification_rules=classification_rules)

        detection_result = DetectionResult(detected_patterns=["pattern1", "pattern2"], anomalies=["unknown_pattern"])
        result = classification_module.classify(detection_result)

        self.assertEqual(result.classifications, {
            "pattern1": "ClassA",
            "pattern2": "ClassB"
        })

class TestSentinelPipeline(unittest.TestCase):
    def test_pipeline(self):
        detection_rules = {
            "pattern1": "Description of pattern1",
            "pattern2": "Description of pattern2"
        }
        classification_rules = {
            "pattern1": "ClassA",
            "pattern2": "ClassB"
        }

        detection_module = DetectionModule(detection_rules=detection_rules)
        classification_module = ClassificationModule(classification_rules=classification_rules)
        pipeline = SentinelPipeline(detection_module, classification_module)

        data = ["pattern1", "pattern2", "unknown_pattern"]
        results = pipeline.process(data)

        self.assertEqual(results["detection"].detected_patterns, ["pattern1", "pattern2"])
        self.assertEqual(results["detection"].anomalies, ["unknown_pattern"])
        self.assertEqual(results["classification"].classifications, {
            "pattern1": "ClassA",
            "pattern2": "ClassB"
        })

if __name__ == "__main__":
    unittest.main()