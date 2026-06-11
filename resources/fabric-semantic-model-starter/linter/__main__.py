"""
Entry point for running the linter as a module.
Usage:
    python -m linter lint <path>
"""

from .cli import main

if __name__ == "__main__":
    exit(main())
