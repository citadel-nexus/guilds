"""
CGRF v3.0 Compliance Audit Tool.

Scans all Python modules under ``src/`` and reports which files are missing
any of the four required CGRF metadata fields:

    _MODULE_NAME    (str)
    _MODULE_VERSION (str, semver)
    _CGRF_TIER      (int, 0-3)
    _EXECUTION_ROLE (str)

Usage
-----
    python tools/cgrf_audit.py                # summary to stdout
    python tools/cgrf_audit.py --report       # detailed report to stdout
    python tools/cgrf_audit.py --strict       # exit 1 if any violations
    python tools/cgrf_audit.py --format json  # JSON output
    python tools/cgrf_audit.py --dir src/infra --report

CGRF compliance
---------------
_MODULE_NAME    = "cgrf_audit"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 0
_EXECUTION_ROLE = "TOOL"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "cgrf_audit"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 0
_EXECUTION_ROLE = "TOOL"
# ─────────────────────────────────────────────────────────────────────────────

_REQUIRED_FIELDS = ("_MODULE_NAME", "_MODULE_VERSION", "_CGRF_TIER", "_EXECUTION_ROLE")

# Files to skip (no CGRF header required)
_SKIP_PATTERNS = {
    "__init__.py",
    "conftest.py",
    "setup.py",
    "setup.cfg",
}


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class FileAuditResult:
    path: str
    present: Dict[str, bool] = field(default_factory=dict)
    values: Dict[str, Optional[str]] = field(default_factory=dict)

    @property
    def missing(self) -> List[str]:
        return [f for f, ok in self.present.items() if not ok]

    @property
    def compliant(self) -> bool:
        return len(self.missing) == 0


@dataclass
class AuditReport:
    scanned: int = 0
    skipped: int = 0
    compliant: int = 0
    violations: int = 0
    results: List[FileAuditResult] = field(default_factory=list)

    @property
    def violation_results(self) -> List[FileAuditResult]:
        return [r for r in self.results if not r.compliant]

    def to_dict(self) -> dict:
        return {
            "summary": {
                "scanned": self.scanned,
                "skipped": self.skipped,
                "compliant": self.compliant,
                "violations": self.violations,
            },
            "violations": [
                {
                    "path": r.path,
                    "missing": r.missing,
                    "values": r.values,
                }
                for r in self.violation_results
            ],
        }


# ── Core audit logic ─────────────────────────────────────────────────────────

def _audit_file(path: Path) -> FileAuditResult:
    """Check a single Python file for CGRF 4-field compliance."""
    result = FileAuditResult(path=str(path))
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        for f in _REQUIRED_FIELDS:
            result.present[f] = False
            result.values[f] = None
        return result

    for field_name in _REQUIRED_FIELDS:
        # Match assignments like:  _MODULE_NAME = "value"  or  _CGRF_TIER = 1
        pattern = rf"^{re.escape(field_name)}\s*=\s*(.+)$"
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            result.present[field_name] = True
            raw = match.group(1).strip().strip('"').strip("'")
            result.values[field_name] = raw
        else:
            result.present[field_name] = False
            result.values[field_name] = None

    return result


def _should_skip(path: Path) -> bool:
    """Return True for files that don't require CGRF headers."""
    return path.name in _SKIP_PATTERNS


def audit_directory(src_dir: Path) -> AuditReport:
    """Recursively audit all .py files in *src_dir*."""
    report = AuditReport()
    for py_file in sorted(src_dir.rglob("*.py")):
        if _should_skip(py_file):
            report.skipped += 1
            continue
        report.scanned += 1
        result = _audit_file(py_file)
        # Make path relative to project root for readability
        try:
            result.path = str(py_file.relative_to(src_dir.parent))
        except ValueError:
            pass
        report.results.append(result)
        if result.compliant:
            report.compliant += 1
        else:
            report.violations += 1

    return report


# ── Output formatters ────────────────────────────────────────────────────────

def _print_summary(report: AuditReport) -> None:
    print(f"\nCGRF v3.0 Audit Summary")
    print(f"{'=' * 50}")
    print(f"  Scanned   : {report.scanned}")
    print(f"  Skipped   : {report.skipped}")
    print(f"  Compliant : {report.compliant}")
    print(f"  Violations: {report.violations}")
    if report.violations == 0:
        print("\n  ✓ All scanned modules are CGRF v3.0 compliant.")
    else:
        print(f"\n  ✗ {report.violations} module(s) need CGRF headers.")


def _print_report(report: AuditReport) -> None:
    _print_summary(report)
    if report.violations:
        print(f"\nViolations ({report.violations}):")
        print(f"{'-' * 50}")
        for r in report.violation_results:
            print(f"\n  {r.path}")
            for f in r.missing:
                print(f"    ✗ {f} missing")
            for f, val in r.values.items():
                if val and r.present.get(f):
                    print(f"    ✓ {f} = {val}")


def _print_json(report: AuditReport) -> None:
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


# ── CLI entry point ──────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="CGRF v3.0 compliance audit for Citadel Lite modules."
    )
    parser.add_argument(
        "--dir",
        default="src",
        help="Directory to scan (default: src)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Show detailed per-file report",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any violations found",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    # Resolve scan directory relative to this script's project root
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    src_dir = (project_root / args.dir).resolve()

    if not src_dir.exists():
        print(f"ERROR: Directory not found: {src_dir}", file=sys.stderr)
        return 2

    report = audit_directory(src_dir)

    if args.format == "json":
        _print_json(report)
    elif args.report:
        _print_report(report)
    else:
        _print_summary(report)

    if args.strict and report.violations > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
