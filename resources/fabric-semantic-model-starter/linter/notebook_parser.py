"""
Parser for notebook-content.py files (Fabric notebook format).
Extracts Python cells and handles magic commands.
"""

import re
import warnings
from dataclasses import dataclass
from typing import Optional


@dataclass
class NotebookCell:
    """Represents a single cell in a notebook."""

    content: str
    start_line: int  # 1-indexed line number in original file
    language: str  # python, sparksql, etc.
    is_magic: bool = False  # True if cell starts with %%magic


def parse_notebook_content(content: str) -> list[NotebookCell]:
    """
    Parse a notebook-content.py file into cells.

    The format uses:
    - # CELL ******************** to mark cell boundaries
    - # META { "language": "..." } for cell metadata
    - # MAGIC for magic commands
    """
    cells = []
    lines = content.split("\n")

    current_cell_lines = []
    current_start_line = 1
    current_language = "python"
    in_cell = False
    in_metadata = False
    metadata_lines = []

    for i, line in enumerate(lines, 1):
        # Detect cell boundary
        if line.strip().startswith("# CELL **"):
            # Save previous cell if exists
            if current_cell_lines:
                cell_content = "\n".join(current_cell_lines)
                if cell_content.strip():
                    cells.append(
                        NotebookCell(
                            content=cell_content,
                            start_line=current_start_line,
                            language=current_language,
                            is_magic=cell_content.strip().startswith("# MAGIC %%"),
                        )
                    )

            current_cell_lines = []
            current_start_line = i + 1
            current_language = "python"  # Reset to default
            in_cell = True
            in_metadata = False
            continue

        # Detect metadata block
        if line.strip().startswith("# METADATA **"):
            in_metadata = True
            metadata_lines = []
            continue

        if in_metadata:
            if line.strip().startswith("# META {"):
                metadata_lines.append(line)
            elif line.strip().startswith("# META"):
                metadata_lines.append(line)
                # Try to extract language
                full_meta = "\n".join(metadata_lines)
                lang_match = re.search(r'"language":\s*"([^"]+)"', full_meta)
                if lang_match:
                    current_language = lang_match.group(1)
            continue

        # Accumulate cell content
        if in_cell:
            current_cell_lines.append(line)

    # Don't forget last cell
    if current_cell_lines:
        cell_content = "\n".join(current_cell_lines)
        if cell_content.strip():
            cells.append(
                NotebookCell(
                    content=cell_content,
                    start_line=current_start_line,
                    language=current_language,
                    is_magic=cell_content.strip().startswith("# MAGIC %%"),
                )
            )

    return cells


def extract_python_code(cell: NotebookCell) -> Optional[str]:
    """
    Extract lintable Python code from a cell.

    - Skips SQL cells (%%sql magic)
    - Strips # MAGIC prefixes
    - Returns None if cell shouldn't be linted
    """
    # Skip non-Python cells
    if cell.language not in ("python", "synapse_pyspark"):
        return None

    # Skip cells that are entirely SQL or other magic
    if cell.is_magic:
        first_line = cell.content.strip().split("\n")[0]
        if "%%sql" in first_line or "%%configure" in first_line:
            return None

    # Process the cell content
    lines = cell.content.split("\n")
    processed_lines = []

    for line in lines:
        # Strip MAGIC prefix if present
        if line.strip().startswith("# MAGIC"):
            # Remove the MAGIC prefix but keep the content
            magic_content = line.replace("# MAGIC", "", 1).strip()
            # Skip magic commands (lines starting with %%)
            if magic_content.startswith("%%"):
                continue
            processed_lines.append(magic_content)
        else:
            processed_lines.append(line)

    code = "\n".join(processed_lines)

    # Verify it's parseable Python
    # Suppress SyntaxWarnings from user code (e.g., invalid escape sequences in their strings)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            compile(code, "<string>", "exec")
        return code
    except SyntaxError:
        # Not valid Python, skip this cell
        return None
