"""TMDL codec for the ``_COPILOT_INSTRUCTIONS`` calculated table.

The model emitter renders instruction rows as a Power BI *calculated* partition
in the exact hand-authored style already used by the Azure Data Insights model:

    partition _COPILOT_INSTRUCTIONS = calculated
        mode: import
        source =
            UNION (
            ROW (
                "Id", 1,
                "Key", "workflow",
                "Topic", "...",
                "WhenToUse", "...",
                "Instructions",
                            "line 1" & UNICHAR(10) &
                            "line 2"
            ),
            ...
            )

Calculated rows (not an M ``#table`` partition) are required so DirectLake
validation and refresh keep working.  ``"`` is escaped as ``""`` and each
markdown line becomes its own quoted literal joined by ``& UNICHAR(10) &``.
The ``Key`` column is the model-agnostic, position-independent handle the LLM
fetches rows by (``[Key] IN { "workflow", ... }``); ``Id`` stays only for stable
ordering/display.

This module is pure string<->data with no I/O so it can be unit-round-tripped
against the committed table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ROW_INDENT = "\t\t\t"
FIELD_INDENT = "\t\t\t\t"
BODY_INDENT = "\t\t\t\t\t\t\t"
_LINE_JOIN = " & UNICHAR(10) &"

# Matches a single TMDL string literal, honoring ""-escaped inner quotes.
_LITERAL_RE = re.compile(r'"((?:[^"]|"")*)"')


@dataclass
class InstructionRow:
    id: int  # 1-based position; stable ordinal + table isKey, NOT the LLM fetch handle
    key: str  # model-agnostic anchor; the LLM's fetch handle ([Key] IN {...})
    topic: str
    when_to_use: str
    instructions: str  # markdown body, '\n'-separated


def _esc(s: str) -> str:
    return s.replace('"', '""')


def _unesc(s: str) -> str:
    return s.replace('""', '"')


def encode_instructions(body: str) -> str:
    """Encode a markdown body into indented, quote-joined literal lines."""
    lines = body.split("\n")
    out = []
    for i, line in enumerate(lines):
        suffix = _LINE_JOIN if i < len(lines) - 1 else ""
        out.append(f'{BODY_INDENT}"{_esc(line)}"{suffix}')
    return "\n".join(out)


def render_row(row: InstructionRow) -> str:
    """Render one ``ROW ( ... )`` block (no trailing comma/newline)."""
    return (
        f"{ROW_INDENT}ROW (\n"
        f'{FIELD_INDENT}"Id", {row.id},\n'
        f'{FIELD_INDENT}"Key", "{_esc(row.key)}",\n'
        f'{FIELD_INDENT}"Topic", "{_esc(row.topic)}",\n'
        f'{FIELD_INDENT}"WhenToUse", "{_esc(row.when_to_use)}",\n'
        f'{FIELD_INDENT}"Instructions",\n'
        f"{encode_instructions(row.instructions)}\n"
        f"{ROW_INDENT})"
    )


def render_union(rows: list[InstructionRow]) -> str:
    """Render the full ``UNION ( ... )`` body of the calculated partition."""
    blocks = ",\n".join(render_row(r) for r in rows)
    return f"{ROW_INDENT}UNION (\n{blocks}\n{ROW_INDENT})"


def split_union_rows(union_body: str) -> list[str]:
    """Split a ``UNION ( ... )`` body into raw ``ROW ( ... )`` block strings."""
    inner = union_body
    m = re.search(r"UNION \(\n(.*)\n" + re.escape(ROW_INDENT) + r"\)\s*$", union_body, re.S)
    if m:
        inner = m.group(1)
    # Rows are separated by a line that is exactly ``\t\t\t),``.
    parts = re.split(r"\n" + re.escape(ROW_INDENT) + r"\),\n", inner)
    rows = []
    for i, p in enumerate(parts):
        block = p
        if not block.startswith(ROW_INDENT + "ROW ("):
            block = block[block.index(ROW_INDENT + "ROW (") :]
        if not block.rstrip().endswith(")"):
            block = block + "\n" + ROW_INDENT + ")"
        rows.append(block)
    return rows


def parse_row(block: str) -> InstructionRow:
    """Parse a single ``ROW ( ... )`` block back into an ``InstructionRow``."""
    id_m = re.search(r'"Id",\s*(\d+),', block)
    if not id_m:
        raise ValueError("ROW block missing Id")
    row_id = int(id_m.group(1))

    key_m = re.search(r'"Key",\s*' + _LITERAL_RE.pattern + r",", block)
    topic_m = re.search(r'"Topic",\s*' + _LITERAL_RE.pattern + r",", block)
    wtu_m = re.search(r'"WhenToUse",\s*' + _LITERAL_RE.pattern + r",", block)
    key = _unesc(key_m.group(1)) if key_m else ""
    topic = _unesc(topic_m.group(1)) if topic_m else ""
    when_to_use = _unesc(wtu_m.group(1)) if wtu_m else ""

    instr_idx = block.index('"Instructions",')
    instr_section = block[instr_idx + len('"Instructions",') :]
    literals = _LITERAL_RE.findall(instr_section)
    instructions = "\n".join(_unesc(lit) for lit in literals)
    return InstructionRow(
        id=row_id, key=key, topic=topic, when_to_use=when_to_use, instructions=instructions
    )


def parse_union(union_body: str) -> list[InstructionRow]:
    return [parse_row(b) for b in split_union_rows(union_body)]
