"""
Helix Notebook Linter

A lightweight AST-based linter for notebook-content.* files that detects
patterns that must be migrated to helixutils best practices.

Usage:
    python -m linter lint <path>
    python -m linter lint ./workspace/HelixFabric-Engineering
"""

__version__ = "1.0.0"

from .analyzer import Violation, analyze_code
from .cli import find_notebook_files, format_violation, lint_file
from .rules import ALL_RULES, TRACKED_OBJECTS


def lint_files(target_path, pattern="notebook-content.*"):
    """Lint all matching files and return violations."""
    from pathlib import Path

    target_path = Path(target_path)
    files = find_notebook_files(target_path, pattern)
    all_violations = []
    for file_path in files:
        violations = lint_file(file_path)
        all_violations.extend(violations)
    return all_violations


__all__ = [
    "ALL_RULES",
    "TRACKED_OBJECTS",
    "Violation",
    "analyze_code",
    "find_notebook_files",
    "format_violation",
    "lint_file",
    "lint_files",
]
