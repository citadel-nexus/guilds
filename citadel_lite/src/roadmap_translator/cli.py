"""CLI entry point for the Roadmap Translator.

Usage::

    python -m src.roadmap_translator.cli translate \\
        --in README.md Citadel_lite_RoadMap_20260216.md \\
        --out roadmap_ir.json \\
        --report roadmap_ir.report.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.roadmap_translator.pipeline import run_pipeline

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_cli"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="roadmap-translator",
        description="Translate roadmap documents into Roadmap IR JSON.",
    )
    sub = parser.add_subparsers(dest="command")

    # translate sub-command
    tr = sub.add_parser("translate", help="Run the translation pipeline")
    tr.add_argument(
        "--in",
        dest="inputs",
        nargs="+",
        required=True,
        help="Input file paths (README.md, RoadMap.md, etc.)",
    )
    tr.add_argument(
        "--out",
        dest="output",
        default="roadmap_ir.json",
        help="Output JSON path (default: roadmap_ir.json)",
    )
    tr.add_argument(
        "--report",
        dest="report",
        default=None,
        help="Output Markdown report path (optional)",
    )

    args = parser.parse_args(argv)

    if args.command != "translate":
        parser.print_help()
        return 1

    input_paths = [Path(p) for p in args.inputs]
    for p in input_paths:
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            return 1

    output_json = Path(args.output)
    output_report = Path(args.report) if args.report else None

    result = run_pipeline(
        input_paths=input_paths,
        output_json=output_json,
        output_report=output_report,
    )

    print(f"Items: {len(result.ir.items)}")
    print(f"Conflicts: {len(result.ir.conflicts)}")
    print(f"Notes: {len(result.notes)}")
    print(f"Output: {result.json_path}")
    if result.report_path:
        print(f"Report: {result.report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
