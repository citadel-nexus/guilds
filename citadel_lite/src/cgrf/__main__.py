# src/cgrf/__main__.py
"""Entry point for running CGRF CLI as a module: python -m src.cgrf"""
import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
