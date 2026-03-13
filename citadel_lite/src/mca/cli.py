"""MCA CLI — ``evolve`` command for running the Evolution Cycle.

Usage::

    python -m src.mca.cli evolve --meta config/mca_meta_001.yaml
    python -m src.mca.cli evolve --roadmap-ir roadmap_ir.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "mca_cli"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca",
        description="MCA Evolution Cycle CLI",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── evolve ─────────────────────────────────────────────────────────────
    evolve = sub.add_parser("evolve", help="Run the MCA Evolution Cycle")
    evolve.add_argument(
        "--meta",
        default="config/mca_meta_001.yaml",
        help="Path to MCA-META-001 system constitution YAML (default: config/mca_meta_001.yaml)",
    )
    evolve.add_argument(
        "--roadmap-ir",
        default=None,
        help="Path to Roadmap IR JSON for metrics injection",
    )
    evolve.add_argument(
        "--out",
        default=None,
        help="Output path for evolution result JSON",
    )
    evolve.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without executing proposals",
    )
    evolve.add_argument(
        "--files",
        type=int,
        default=0,
        help="Total source files count for code metrics",
    )
    evolve.add_argument(
        "--lines",
        type=int,
        default=0,
        help="Total source lines count for code metrics",
    )
    evolve.add_argument(
        "--tests",
        type=int,
        default=0,
        help="Total test count for code metrics",
    )

    return parser


def _cmd_evolve(args: argparse.Namespace) -> int:
    """Execute the evolve command."""
    from src.mca.evolution_engine import EvolutionEngine
    from src.mca.metrics_aggregator import MetricsAggregator

    # Build aggregator with CLI-provided metrics
    aggregator = MetricsAggregator()
    if args.files or args.lines or args.tests:
        aggregator.set_code_metrics(
            total_files=args.files,
            total_lines=args.lines,
            test_count=args.tests,
        )

    # Create engine
    meta_path = args.meta if Path(args.meta).exists() else None
    engine = EvolutionEngine(
        meta_path=meta_path,
        dry_run=args.dry_run,
    )

    # Run
    print(f"[MCA] Starting Evolution Cycle (dry_run={args.dry_run})")
    result = engine.run(
        aggregator,
        roadmap_ir_path=args.roadmap_ir,
    )

    # Output
    result_dict = result.to_dict()
    result_json = json.dumps(result_dict, ensure_ascii=False, indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result_json, encoding="utf-8")
        print(f"[MCA] Result written to: {args.out}")
    else:
        print(result_json)

    # Summary
    phases = len(result.phases_completed)
    proposals = len(result.proposals)
    errors = len(result.errors)
    print(f"\n[MCA] Complete: {phases} phases, {proposals} proposals, {errors} errors")

    return 0 if errors == 0 else 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    # Load .env so AWS_BEDROCK_* credentials are available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "evolve":
        return _cmd_evolve(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
