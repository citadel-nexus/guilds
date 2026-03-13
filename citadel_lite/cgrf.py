#!/usr/bin/env python3
# cgrf.py - Standalone entry point for CGRF CLI
"""
CGRF v3.0 CLI - Governance & validation tools for autonomous systems.

Usage:
    python cgrf.py validate --module <path> --tier <0-3>
    python cgrf.py tier-check <module1> <module2> ... --tier <0-3>
    python cgrf.py report --tier <0-3>
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.cgrf.cli import main

if __name__ == "__main__":
    sys.exit(main())
