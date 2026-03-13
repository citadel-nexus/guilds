import logging
from dataclasses import dataclass, field
from typing import List, Dict, Callable, Any

logger = logging.getLogger(__name__)

@dataclass
class DiagnosticRule:
    """
    Represents a single diagnostic rule.
    """
    name: str
    description: str
    check_function: Callable[[Dict[str, Any]], bool]

@dataclass
class DiagnosticResult:
    """
    Represents the result of a diagnostic check.
    """
    rule_name: str
    passed: bool
    details: str

@dataclass
class DiagnosticFramework:
    """
    A modular diagnostic framework for analyzing system states and logs.
    """
    rules: List[DiagnosticRule] = field(default_factory=list)

    def add_rule(self, rule: DiagnosticRule) -> None:
        """
        Add a diagnostic rule to the framework.
        """
        logger.debug(f"Adding diagnostic rule: {rule.name}")
        self.rules.append(rule)

    def analyze(self, system_state: Dict[str, Any]) -> List[DiagnosticResult]:
        """
        Analyze the system state using the defined rules.

        Args:
            system_state: A dictionary representing the current system state.

        Returns:
            A list of DiagnosticResult objects indicating the outcome of each rule.
        """
        logger.info("Starting system analysis...")
        results = []

        for rule in self.rules:
            try:
                logger.debug(f"Evaluating rule: {rule.name}")
                passed = rule.check_function(system_state)
                details = "Rule passed." if passed else "Rule failed."
                results.append(DiagnosticResult(rule_name=rule.name, passed=passed, details=details))
            except Exception as e:
                logger.error(f"Error evaluating rule '{rule.name}': {e}")
                results.append(DiagnosticResult(rule_name=rule.name, passed=False, details=f"Error: {e}"))

        logger.info("System analysis complete.")
        return results

# Example diagnostic rules
def check_disk_space(system_state: Dict[str, Any]) -> bool:
    """
    Check if the disk space is below a critical threshold.
    """
    threshold = 10  # Minimum acceptable disk space in percentage
    disk_space = system_state.get("disk_space", 100)
    return disk_space >= threshold

def check_cpu_usage(system_state: Dict[str, Any]) -> bool:
    """
    Check if the CPU usage is below a critical threshold.
    """
    threshold = 90  # Maximum acceptable CPU usage in percentage
    cpu_usage = system_state.get("cpu_usage", 0)
    return cpu_usage <= threshold

# Initialize the diagnostic framework
framework = DiagnosticFramework()
framework.add_rule(DiagnosticRule(name="Disk Space Check", description="Ensure disk space is above critical threshold.", check_function=check_disk_space))
framework.add_rule(DiagnosticRule(name="CPU Usage Check", description="Ensure CPU usage is below critical threshold.", check_function=check_cpu_usage))

if __name__ == "__main__":
    # Example system state
    example_state = {
        "disk_space": 8,  # Percentage
        "cpu_usage": 95   # Percentage
    }

    # Run diagnostics
    results = framework.analyze(example_state)
    for result in results:
        print(f"Rule: {result.rule_name}, Passed: {result.passed}, Details: {result.details}")