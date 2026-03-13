# src/cgrf/validator.py
"""CGRF v3.0 Module Validator - checks compliance with tier requirements."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ValidationResult:
    """Result of CGRF validation check."""

    def __init__(self, tier: int, module_path: Path):
        self.tier = tier
        self.module_path = module_path
        self.checks: List[Dict[str, Any]] = []
        self.compliant = True
        self.warnings: List[str] = []

    def add_check(self, name: str, passed: bool, message: str, required: bool = True) -> None:
        """Add a validation check result."""
        self.checks.append({
            "name": name,
            "passed": passed,
            "message": message,
            "required": required,
        })
        if required and not passed:
            self.compliant = False

    def add_warning(self, message: str) -> None:
        """Add a non-blocking warning."""
        self.warnings.append(message)


class CGRFValidator:
    """Validates Python modules against CGRF tier requirements."""

    TIER_REQUIREMENTS = {
        0: {
            "name": "Experimental",
            "test_coverage": 0,
            "docstring_required": False,
            "cgrf_metadata_required": False,
            "test_file_required": False,
        },
        1: {
            "name": "Development",
            "test_coverage": 50,
            "docstring_required": True,
            "cgrf_metadata_required": True,
            "test_file_required": True,
        },
        2: {
            "name": "Production",
            "test_coverage": 80,
            "docstring_required": True,
            "cgrf_metadata_required": True,
            "test_file_required": True,
            "integration_tests_required": True,
        },
        3: {
            "name": "Mission-Critical",
            "test_coverage": 95,
            "docstring_required": True,
            "cgrf_metadata_required": True,
            "test_file_required": True,
            "integration_tests_required": True,
            "e2e_tests_required": True,
        },
    }

    def __init__(self):
        self.project_root = Path.cwd()

    def validate(self, module_path: Path, target_tier: int) -> ValidationResult:
        """
        Validate a module against CGRF tier requirements.

        Args:
            module_path: Path to the Python module to validate
            target_tier: Target CGRF tier (0-3)

        Returns:
            ValidationResult with compliance status and detailed checks
        """
        if not module_path.exists():
            result = ValidationResult(target_tier, module_path)
            result.add_check("file_exists", False, f"Module not found: {module_path}", required=True)
            return result

        if target_tier not in self.TIER_REQUIREMENTS:
            result = ValidationResult(target_tier, module_path)
            result.add_check("valid_tier", False, f"Invalid tier: {target_tier} (must be 0-3)", required=True)
            return result

        result = ValidationResult(target_tier, module_path)
        requirements = self.TIER_REQUIREMENTS[target_tier]

        # Read module content
        try:
            content = module_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(module_path))
        except Exception as e:
            result.add_check("parse", False, f"Failed to parse module: {e}", required=True)
            return result

        result.add_check("parse", True, "Module parsed successfully")

        # Check docstring
        self._check_docstring(tree, result, requirements)

        # Check CGRF metadata
        self._check_cgrf_metadata(content, tree, result, requirements)

        # Check test file
        self._check_test_file(module_path, result, requirements)

        # Check tier-specific requirements
        if target_tier >= 2:
            self._check_integration_tests(module_path, result, requirements)

        if target_tier >= 3:
            self._check_e2e_tests(module_path, result, requirements)

        return result

    def _check_docstring(self, tree: ast.AST, result: ValidationResult, requirements: Dict) -> None:
        """Check if module has docstring."""
        docstring = ast.get_docstring(tree)
        required = requirements.get("docstring_required", False)

        if docstring:
            result.add_check(
                "module_docstring",
                True,
                f"Module docstring present ({len(docstring)} chars)",
                required=required
            )
        else:
            result.add_check(
                "module_docstring",
                False,
                "Module docstring missing",
                required=required
            )

    def _check_cgrf_metadata(self, content: str, tree: ast.AST, result: ValidationResult, requirements: Dict) -> None:
        """Check if module has CGRF metadata constants."""
        required = requirements.get("cgrf_metadata_required", False)

        # Look for _MODULE_NAME, _MODULE_VERSION, _CGRF_TIER constants
        has_module_name = "_MODULE_NAME" in content
        has_module_version = "_MODULE_VERSION" in content
        has_cgrf_tier = "_CGRF_TIER" in content

        # Also check for _generate_cgrf_metadata function
        has_generator = "_generate_cgrf_metadata" in content or "CGRFMetadata" in content

        metadata_complete = has_module_name and has_module_version and has_cgrf_tier

        if metadata_complete:
            # Extract actual tier value
            tier_match = re.search(r'_CGRF_TIER\s*=\s*(\d+)', content)
            if tier_match:
                declared_tier = int(tier_match.group(1))
                if declared_tier == result.tier:
                    result.add_check(
                        "cgrf_metadata",
                        True,
                        f"CGRF metadata complete (declared tier: {declared_tier})",
                        required=required
                    )
                else:
                    result.add_warning(
                        f"Declared tier ({declared_tier}) does not match target tier ({result.tier})"
                    )
                    result.add_check(
                        "cgrf_metadata",
                        True,
                        f"CGRF metadata present but tier mismatch (declared: {declared_tier}, target: {result.tier})",
                        required=required
                    )
            else:
                result.add_check(
                    "cgrf_metadata",
                    True,
                    "CGRF metadata constants present",
                    required=required
                )
        else:
            missing = []
            if not has_module_name:
                missing.append("_MODULE_NAME")
            if not has_module_version:
                missing.append("_MODULE_VERSION")
            if not has_cgrf_tier:
                missing.append("_CGRF_TIER")

            result.add_check(
                "cgrf_metadata",
                False,
                f"CGRF metadata incomplete: missing {', '.join(missing)}",
                required=required
            )

    def _check_test_file(self, module_path: Path, result: ValidationResult, requirements: Dict) -> None:
        """Check if corresponding test file exists."""
        required = requirements.get("test_file_required", False)

        # Look for test file in tests/ directory
        module_name = module_path.stem
        test_patterns = [
            f"tests/test_{module_name}.py",
            f"test/test_{module_name}.py",
            f"tests/{module_name}_test.py",
        ]

        test_file = None
        for pattern in test_patterns:
            candidate = self.project_root / pattern
            if candidate.exists():
                test_file = candidate
                break

        if test_file:
            result.add_check(
                "test_file",
                True,
                f"Test file found: {test_file.relative_to(self.project_root)}",
                required=required
            )
        else:
            result.add_check(
                "test_file",
                False,
                f"No test file found (searched: {', '.join(test_patterns)})",
                required=required
            )

    def _check_integration_tests(self, module_path: Path, result: ValidationResult, requirements: Dict) -> None:
        """Check for integration tests (Tier 2+)."""
        required = requirements.get("integration_tests_required", False)

        # Look for integration test markers
        integration_test_dir = self.project_root / "tests" / "integration"
        module_name = module_path.stem

        if integration_test_dir.exists():
            integration_files = list(integration_test_dir.glob(f"*{module_name}*.py"))
            if integration_files:
                result.add_check(
                    "integration_tests",
                    True,
                    f"Integration tests found: {len(integration_files)} file(s)",
                    required=required
                )
            else:
                result.add_check(
                    "integration_tests",
                    False,
                    "No integration tests found",
                    required=required
                )
        else:
            result.add_check(
                "integration_tests",
                False,
                "No tests/integration directory found",
                required=required
            )

    def _check_e2e_tests(self, module_path: Path, result: ValidationResult, requirements: Dict) -> None:
        """Check for E2E tests (Tier 3)."""
        required = requirements.get("e2e_tests_required", False)

        # Look for E2E test markers in tests/test_pipeline_e2e.py
        e2e_test_file = self.project_root / "tests" / "test_pipeline_e2e.py"
        module_name = module_path.stem

        if e2e_test_file.exists():
            content = e2e_test_file.read_text(encoding="utf-8")
            # Check if module is imported or referenced in E2E tests
            if module_name in content or module_path.stem in content:
                result.add_check(
                    "e2e_tests",
                    True,
                    "Module referenced in E2E tests",
                    required=required
                )
            else:
                result.add_check(
                    "e2e_tests",
                    False,
                    "Module not found in E2E test suite",
                    required=required
                )
        else:
            result.add_check(
                "e2e_tests",
                False,
                "No E2E test file found (test_pipeline_e2e.py)",
                required=required
            )


def validate_module(module_path: str, tier: int) -> ValidationResult:
    """
    Convenience function to validate a module.

    Args:
        module_path: Path to the module (relative or absolute)
        tier: Target CGRF tier (0-3)

    Returns:
        ValidationResult
    """
    validator = CGRFValidator()
    path = Path(module_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return validator.validate(path, tier)
