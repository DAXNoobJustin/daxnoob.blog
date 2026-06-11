"""Command-line interface for the Helix notebook linter."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .analyzer import Violation, analyze_code
from .notebook_parser import extract_python_code, parse_notebook_content


# ANSI color codes
class Colors:
    """ANSI color codes for terminal output."""

    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def find_notebook_files(path: Path, pattern: str = "notebook-content.*") -> list[Path]:
    """Find all notebook content files in a directory."""
    if path.is_file():
        return [path] if path.match(pattern) else []

    # Exclude __pycache__ directories and .pyc files
    return [p for p in path.rglob(pattern) if "__pycache__" not in p.parts and p.suffix != ".pyc"]


def lint_file(file_path: Path) -> list[tuple[Path, int, Violation]]:
    """
    Lint a single notebook file.

    Returns list of (file_path, original_line, violation) tuples.
    """
    results = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"{Colors.RED}Error reading {file_path}: {e}{Colors.RESET}", file=sys.stderr)
        return results

    cells = parse_notebook_content(content)

    # Collect all Python code and line mappings for cross-cell analysis
    all_code_lines = []
    line_mapping = []  # Maps combined line number to (cell, original_line)

    for cell in cells:
        python_code = extract_python_code(cell)
        if python_code is None:
            continue

        cell_lines = python_code.split("\n")
        for i, line in enumerate(cell_lines):
            all_code_lines.append(line)
            original_line = cell.start_line + i
            line_mapping.append((cell, original_line))

    # Analyze combined code for cross-cell rules (like unused variables)
    if all_code_lines:
        combined_code = "\n".join(all_code_lines)
        combined_violations = analyze_code(combined_code)

        for violation in combined_violations:
            # Map back to original file line
            if 1 <= violation.line <= len(line_mapping):
                cell, original_line = line_mapping[violation.line - 1]
                violation.line = original_line
                results.append((file_path, original_line, violation))

    return results


def format_violation(
    file_path: Path,
    violation: Violation,
    base_path: Optional[Path] = None,
    use_colors: bool = True,
    use_absolute_paths: bool = False,
) -> str:
    """Format a violation for display."""
    c = Colors if use_colors else type("NoColors", (), {k: "" for k in dir(Colors) if not k.startswith("_")})()

    # Use absolute path for clickable links in VS Code terminal
    if use_absolute_paths:
        display_path = file_path.resolve()
    else:
        display_path = file_path.relative_to(base_path) if base_path else file_path

    lines = [
        f"{c.BOLD}{display_path}:{violation.line}:{violation.column}{c.RESET} [{c.CYAN}{violation.rule_id}{c.RESET}]",
        f"  {c.GRAY}{violation.code_snippet}{c.RESET}",
        f"  {violation.message}",
    ]

    if violation.replacement:
        lines.append(f"  {c.GREEN}Replace with: {violation.replacement}{c.RESET}")

    if violation.suggestion:
        lines.append(f"  {c.BLUE}Suggestion: {violation.suggestion}{c.RESET}")

    return "\n".join(lines)


def lint_command(args: argparse.Namespace) -> int:
    """Execute the lint command."""
    # Resolve path
    target_path = args.path.resolve()
    if not target_path.exists():
        print(f"Error: Path does not exist: {target_path}", file=sys.stderr)
        return 1

    # Find files
    files = find_notebook_files(target_path, args.pattern)

    if not files:
        print(f"No files matching '{args.pattern}' found in {target_path}")
        return 0

    # Lint all files
    all_violations = []
    for file_path in files:
        violations = lint_file(file_path)
        all_violations.extend(violations)

    # Output results
    if args.json:
        output = [
            {
                "file": str(fp),
                "line": v.line,
                "column": v.column,
                "rule_id": v.rule_id,
                "message": v.message,
                "code": v.code_snippet,
                "replacement": v.replacement,
                "suggestion": v.suggestion,
            }
            for fp, _, v in all_violations
        ]
        print(json.dumps(output, indent=2))
    elif not args.quiet:
        use_colors = not args.no_color and sys.stdout.isatty()
        use_absolute = args.absolute_paths and not args.relative_paths
        base_path = target_path if target_path.is_dir() else target_path.parent

        for file_path, _, violation in all_violations:
            print(format_violation(file_path, violation, base_path, use_colors, use_absolute))
            print()

    # Return non-zero if violations found
    return 1 if all_violations else 0


def main(args: Optional[list[str]] = None) -> int:
    """Main entry point."""
    # Get actual args from sys.argv if none provided
    if args is None:
        args = sys.argv[1:]

    # Backwards compatibility: if first arg looks like a path (not a known command),
    # treat it as 'lint <path>'
    known_commands = {"lint", "-h", "--help"}
    if args and args[0] not in known_commands and not args[0].startswith("-"):
        args = ["lint", *args]

    parser = argparse.ArgumentParser(
        description="Helix notebook linter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m linter lint ./workspace/HelixFabric-Engineering
  python -m linter ./workspace/HelixFabric-Engineering  (same as above)
  python -m linter lint ./notebook.py --no-color
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Lint subcommand
    lint_parser = subparsers.add_parser(
        "lint",
        help="Lint notebook files for best practices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    lint_parser.add_argument("path", type=Path, help="File or directory to lint")
    lint_parser.add_argument(
        "--pattern",
        default="notebook-content.*",
        help="Glob pattern for finding notebook files (default: notebook-content.*)",
    )
    lint_parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    lint_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    lint_parser.add_argument("-q", "--quiet", action="store_true", help="Only output summary")
    lint_parser.add_argument(
        "--absolute-paths",
        action="store_true",
        default=True,
        help="Use absolute paths for clickable links in VS Code terminal (default: True)",
    )
    lint_parser.add_argument(
        "--relative-paths", action="store_true", help="Use relative paths instead of absolute paths"
    )

    parsed = parser.parse_args(args)

    if parsed.command is None:
        parser.print_help()
        return 0

    if parsed.command == "lint":
        return lint_command(parsed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
