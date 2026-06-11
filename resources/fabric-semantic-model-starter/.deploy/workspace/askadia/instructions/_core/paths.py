"""Canonical path resolvers for the instruction store.

One place owns the on-disk layout so every caller (emitter, deploy op, routing,
tests) stays consistent. The instruction store lives under
``<canonical_root>/`` (i.e. ``askadia/instructions/``) and is split into
two halves:

  - ``common/`` — content authored ONCE and identical across every model:
      ``common/manifest.json``       structural map: which blocks compose each
                                     shared row, plus row topic / whenToUse /
                                     routerHint metadata and ordering
      ``common/blocks/<block>.md``   shared block bodies
      ``common/router-preamble.md``  the always-on router preamble
  - ``models/<slug>/`` — everything specific to one model, COLOCATED:
      ``models/<slug>/model.json``       per-model rows / workedExamples / golden
      ``models/<slug>/rows/<anchor>.md`` per-model row bodies (resolved by anchor)

The companion UDF/tables scaffold lives in a sibling tree under
``askadia/udf/`` and is owned by the deploy ops (``model_overlay``,
``merge_shared_scaffold``, ``generate_*_config``), NOT by this engine.
"""

from __future__ import annotations

from pathlib import Path

# Stable framework anchors + their position in the assembled model row set: the
# 5 shared rows are always Ids 1..5 in this order, ahead of the per-model rows.
SHARED_ANCHORS = (
    "workflow",
    "udf-reference",
    "output-formatting",
    "examples-part-1",
    "examples-part-2",
)


def common_dir(canonical_root: Path) -> Path:
    return canonical_root / "common"


def manifest_path(canonical_root: Path) -> Path:
    return common_dir(canonical_root) / "manifest.json"


def block_path(canonical_root: Path, block: str) -> Path:
    return common_dir(canonical_root) / "blocks" / f"{block}.md"


def router_preamble_path(canonical_root: Path) -> Path:
    return common_dir(canonical_root) / "router-preamble.md"


def models_dir(canonical_root: Path) -> Path:
    return canonical_root / "models"


def model_dir(canonical_root: Path, slug: str) -> Path:
    return models_dir(canonical_root) / slug


def model_json_path(canonical_root: Path, slug: str) -> Path:
    return model_dir(canonical_root, slug) / "model.json"


def model_rows_dir(canonical_root: Path, slug: str) -> Path:
    return model_dir(canonical_root, slug) / "rows"


def model_block_path(canonical_root: Path, slug: str, anchor: str) -> Path:
    return model_rows_dir(canonical_root, slug) / f"{anchor}.md"
