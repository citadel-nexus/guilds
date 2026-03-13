import unittest
from src.sherlock.diagnosis import DiagnosticFramework, DiagnosticRule, check_disk_space, check_cpu_usage

class TestDiagnosticFramework(unittest.TestCase):

    def setUp(self):
        self.framework = DiagnosticFramework()
        self.framework.add_rule(DiagnosticRule(name="Disk Space Check", description="Ensure disk space is above critical threshold.", check_function=check_disk_space))
        self.framework.add_rule(DiagnosticRule(name="CPU Usage Check", description="Ensure CPU usage is below critical threshold.", check_function=check_cpu_usage))

    def test_disk_space_check_pass(self):
        system_state = {"disk_space": 20}
        results = self.framework.analyze(system_state)
        self.assertTrue(results[0].passed)

    def test_disk_space_check_fail(self):
        system_state = {"disk_space": 5}
        results = self.framework.analyze(system_state)
        self.assertFalse(results[0].passed)

    def test_cpu_usage_check_pass(self):
        system_state = {"cpu_usage": 50}
        results = self.framework.analyze(system_state)
        self.assertTrue(results[1].passed)

    def test_cpu_usage_check_fail(self):
        system_state = {"cpu_usage": 95}
        results = self.framework.analyze(system_state)
        self.assertFalse(results[1].passed)

if __name__ == "__main__":
    unittest.main()