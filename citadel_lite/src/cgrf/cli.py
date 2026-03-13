# src/cgrf/cli.py
"""CGRF v3.0 CLI - Command-line interface for CGRF validation and tooling."""
from __future__ import annotations

import argparse
import json as _json
import sys
from pathlib import Path
from typing import Optional

from .validator import validate_module, ValidationResult


class Style:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"

    @staticmethod
    def safe(text: str) -> str:
        """Safe encode for Windows console."""
        try:
            return text.encode('cp932', errors='replace').decode('cp932')
        except Exception:
            return text


def print_validation_result(result: ValidationResult) -> None:
    """Print validation result with colors."""
    tier_colors = {0: Style.DIM, 1: Style.CYAN, 2: Style.YELLOW, 3: Style.RED}
    tier_labels = {
        0: "Tier 0 (Experimental)",
        1: "Tier 1 (Development)",
        2: "Tier 2 (Production)",
        3: "Tier 3 (Mission-Critical)",
    }

    tier_color = tier_colors.get(result.tier, Style.RESET)
    tier_label = tier_labels.get(result.tier, f"Tier {result.tier}")

    print(f"\n{Style.BOLD}CGRF Validation Report{Style.RESET}")
    print(f"{Style.DIM}{'=' * 60}{Style.RESET}")
    print(f"{Style.BOLD}Module:{Style.RESET} {result.module_path}")
    print(f"{Style.BOLD}Target Tier:{Style.RESET} {tier_color}{tier_label}{Style.RESET}")
    print(f"{Style.DIM}{'=' * 60}{Style.RESET}\n")

    # Print checks
    passed_count = 0
    failed_count = 0

    for check in result.checks:
        name = check["name"]
        passed = check["passed"]
        message = check["message"]
        required = check["required"]

        if passed:
            icon = f"{Style.GREEN}[PASS]{Style.RESET}"
            passed_count += 1
        else:
            if required:
                icon = f"{Style.RED}[FAIL]{Style.RESET}"
                failed_count += 1
            else:
                icon = f"{Style.YELLOW}[WARN]{Style.RESET}"

        req_marker = "" if required else f" {Style.DIM}(optional){Style.RESET}"
        print(f"{icon} {Style.BOLD}{name}{Style.RESET}{req_marker}")
        print(f"     {Style.DIM}{Style.safe(message)}{Style.RESET}\n")

    # Print warnings
    if result.warnings:
        print(f"{Style.YELLOW}{Style.BOLD}Warnings:{Style.RESET}")
        for warning in result.warnings:
            print(f"  {Style.YELLOW}- {Style.safe(warning)}{Style.RESET}")
        print()

    # Print summary
    print(f"{Style.DIM}{'=' * 60}{Style.RESET}")
    print(f"{Style.BOLD}Summary:{Style.RESET} {passed_count} passed, {failed_count} failed")

    if result.compliant:
        print(f"\n{Style.GREEN}{Style.BOLD}[COMPLIANT]{Style.RESET} {tier_color}{tier_label}{Style.RESET}\n")
    else:
        print(f"\n{Style.RED}{Style.BOLD}[NOT COMPLIANT]{Style.RESET} {tier_color}{tier_label}{Style.RESET}\n")


def _result_to_dict(result: ValidationResult) -> dict:
    """Convert ValidationResult to JSON-serializable dict."""
    return {
        "tier": result.tier,
        "module_path": str(result.module_path),
        "compliant": result.compliant,
        "checks": result.checks,
        "warnings": result.warnings,
    }


def cmd_validate(args: argparse.Namespace) -> int:
    """Execute 'cgrf validate' command."""
    module_path = args.module
    tier = args.tier
    use_json = getattr(args, "json", False)

    if not Path(module_path).exists():
        if use_json:
            print(_json.dumps({"error": f"Module not found: {module_path}"}))
        else:
            print(f"{Style.RED}Error:{Style.RESET} Module not found: {module_path}", file=sys.stderr)
        return 1

    if tier not in [0, 1, 2, 3]:
        if use_json:
            print(_json.dumps({"error": f"Invalid tier: {tier}"}))
        else:
            print(f"{Style.RED}Error:{Style.RESET} Invalid tier: {tier} (must be 0-3)", file=sys.stderr)
        return 1

    result = validate_module(module_path, tier)

    if use_json:
        output = {"command": "validate", **_result_to_dict(result)}
        print(_json.dumps(output, indent=2))
    else:
        print_validation_result(result)

    return 0 if result.compliant else 1


def cmd_tier_check(args: argparse.Namespace) -> int:
    """Execute 'cgrf tier-check' command - check multiple modules."""
    modules = args.modules
    tier = args.tier
    use_json = getattr(args, "json", False)

    all_compliant = True
    json_results = []

    for module_path in modules:
        if not Path(module_path).exists():
            if not use_json:
                print(f"{Style.RED}Error:{Style.RESET} Module not found: {module_path}", file=sys.stderr)
            all_compliant = False
            json_results.append({
                "module_path": module_path,
                "compliant": False,
                "failed_checks": [{"name": "file_exists", "message": "Module not found"}],
            })
            continue

        result = validate_module(module_path, tier)

        if use_json:
            failed = [c for c in result.checks if not c["passed"] and c["required"]]
            json_results.append({
                "module_path": str(result.module_path),
                "compliant": result.compliant,
                "failed_checks": [{"name": c["name"], "message": c["message"]} for c in failed],
            })
        else:
            status = f"{Style.GREEN}PASS{Style.RESET}" if result.compliant else f"{Style.RED}FAIL{Style.RESET}"
            print(f"{status} {module_path} (Tier {tier})")

        if not result.compliant:
            all_compliant = False
            if not use_json:
                for check in result.checks:
                    if not check["passed"] and check["required"]:
                        print(f"     {Style.RED}- {check['name']}: {Style.safe(check['message'])}{Style.RESET}")

    if use_json:
        passed = sum(1 for r in json_results if r["compliant"])
        output = {
            "command": "tier-check",
            "tier": tier,
            "results": json_results,
            "summary": {"total": len(json_results), "passed": passed, "failed": len(json_results) - passed},
        }
        print(_json.dumps(output, indent=2))
    else:
        print()

    return 0 if all_compliant else 1


def cmd_report(args: argparse.Namespace) -> int:
    """Execute 'cgrf report' command - generate compliance report."""
    agent_dirs = [
        "src/agents",
        "src/orchestrator_v3.py",
    ]

    tier = args.tier if hasattr(args, 'tier') else 1
    use_json = getattr(args, "json", False)

    if not use_json:
        print(f"\n{Style.BOLD}CGRF Compliance Report{Style.RESET}")
        print(f"{Style.DIM}{'=' * 60}{Style.RESET}\n")

    modules_found = []
    for agent_dir in agent_dirs:
        path = Path(agent_dir)
        if path.is_file() and path.suffix == ".py":
            modules_found.append(path)
        elif path.is_dir():
            modules_found.extend(path.glob("*.py"))

    compliant_count = 0
    total_count = 0
    json_modules = []

    for module_path in modules_found:
        if module_path.name == "__init__.py":
            continue

        total_count += 1
        result = validate_module(str(module_path), tier)

        if use_json:
            json_modules.append({
                "module_path": str(module_path),
                "compliant": result.compliant,
            })
        else:
            status = f"{Style.GREEN}[PASS]{Style.RESET}" if result.compliant else f"{Style.RED}[FAIL]{Style.RESET}"
            print(f"{status} {module_path}")

        if result.compliant:
            compliant_count += 1

    if use_json:
        output = {
            "command": "report",
            "tier": tier,
            "modules": json_modules,
            "summary": {"total": total_count, "compliant": compliant_count, "non_compliant": total_count - compliant_count},
        }
        print(_json.dumps(output, indent=2))
    else:
        print(f"\n{Style.BOLD}Total:{Style.RESET} {compliant_count}/{total_count} modules compliant with Tier {tier}")
        print()

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="cgrf",
        description="CGRF v3.0 CLI - Governance & validation tools for autonomous systems",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # cgrf validate
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a module against CGRF tier requirements"
    )
    validate_parser.add_argument(
        "--module",
        required=True,
        help="Path to the Python module to validate"
    )
    validate_parser.add_argument(
        "--tier",
        type=int,
        required=True,
        choices=[0, 1, 2, 3],
        help="Target CGRF tier (0=Experimental, 1=Development, 2=Production, 3=Mission-Critical)"
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    # cgrf tier-check
    tier_check_parser = subparsers.add_parser(
        "tier-check",
        help="Check multiple modules against a tier"
    )
    tier_check_parser.add_argument(
        "modules",
        nargs="+",
        help="Paths to modules to check"
    )
    tier_check_parser.add_argument(
        "--tier",
        type=int,
        default=1,
        choices=[0, 1, 2, 3],
        help="Target CGRF tier (default: 1)"
    )
    tier_check_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    # cgrf report
    report_parser = subparsers.add_parser(
        "report",
        help="Generate compliance report for all modules"
    )
    report_parser.add_argument(
        "--tier",
        type=int,
        default=1,
        choices=[0, 1, 2, 3],
        help="Target CGRF tier (default: 1)"
    )
    report_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "validate":
        return cmd_validate(args)
    elif args.command == "tier-check":
        return cmd_tier_check(args)
    elif args.command == "report":
        return cmd_report(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
