"""Full-file render/parse for a model's ``_COPILOT_INSTRUCTIONS.tmdl``.

Wraps the row codec in ``tmdl.py`` with the static table/column/annotation
boilerplate so the model emitter can write a complete, deploy-ready
``definition/tables/_COPILOT_INSTRUCTIONS.tmdl`` (and so ``parse_table`` can read
one back into canonical rows for the round-trip test).

The table carries both an ``Id`` column (stable ordering/display) and a ``Key``
column (the model-agnostic handle the LLM fetches rows by). The header/footer
otherwise follow the original hand-authored Azure Data Insights table style.
"""

from __future__ import annotations

from .tmdl import InstructionRow, parse_union, render_union

HEADER = (
    "table _COPILOT_INSTRUCTIONS\n"
    "\n"
    "\tcolumn Id\n"
    "\t\tisKey\n"
    "\t\tformatString: 0\n"
    "\t\tisNameInferred\n"
    "\t\tsourceColumn: [Id]\n"
    "\n"
    "\t\tannotation Copilot_Visibility = Visible\n"
    "\n"
    "\tcolumn Key\n"
    "\t\tisNameInferred\n"
    "\t\tsourceColumn: [Key]\n"
    "\n"
    "\t\tannotation Copilot_Visibility = Visible\n"
    "\n"
    "\tcolumn Topic\n"
    "\t\tisNameInferred\n"
    "\t\tsourceColumn: [Topic]\n"
    "\n"
    "\t\tannotation Copilot_Visibility = Visible\n"
    "\n"
    "\tcolumn WhenToUse\n"
    "\t\tisNameInferred\n"
    "\t\tsourceColumn: [WhenToUse]\n"
    "\n"
    "\t\tannotation Copilot_Visibility = Visible\n"
    "\n"
    "\tcolumn Instructions\n"
    "\t\tisNameInferred\n"
    "\t\tsourceColumn: [Instructions]\n"
    "\n"
    "\t\tannotation Copilot_Visibility = Visible\n"
    "\n"
    "\tpartition _COPILOT_INSTRUCTIONS = calculated\n"
    "\t\tmode: import\n"
    "\t\tsource =\n"
)

FOOTER = (
    "\n\n\tannotation TabularEditor_TableGroup = Other\n"
    "\n"
    "\tannotation BestPracticeAnalyzer_IgnoreRules = "
    '{"RuleIDs":["ROLE_ALL_USERS_MISSING_TABLE_PERMISSION"]}\n'
)


def render_table(rows: list[InstructionRow]) -> str:
    return HEADER + render_union(rows) + FOOTER


def parse_table(text: str) -> list[InstructionRow]:
    start = text.index("\t\t\tUNION (")
    end = text.index(FOOTER, start)
    return parse_union(text[start:end])
