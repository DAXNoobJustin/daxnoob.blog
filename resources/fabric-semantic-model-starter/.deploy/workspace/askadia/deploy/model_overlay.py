"""Per-model overlay path helpers for the AskADIA framework.

The shared scaffold under `.deploy/workspace/askadia/` provides canonical UDFs + canonical framework tables that get spliced into every enabled
SemanticModel. On top of canonical, individual models may carry a small
set of *per-model* UDFs (typically rankers like `_RankAccounts`) and a
curated `copilot_questions.json`. Those per-model artifacts live in a
slug-named overlay directory:

    .deploy/workspace/askadia/udf/models/<slug>/
        functions.tmdl          (optional — per-model AskADIA-namespace UDFs)
        copilot_questions.json  (optional — curated questions for this model)
        README.md               (one-pager explaining the overlay)

The slug is derived deterministically from the SemanticModel display name
via `resolve_model_slug` so there's no YAML map to keep in sync.

Consumed by:
    - merge_shared_scaffold.py    (overlay functions splice)
    - generate_copilot_questions.py (overlay JSON path resolution)
"""

from __future__ import annotations

import re
from pathlib import Path

# Canonical overlay-models root, resolved once in the package paths module so the
# whole framework tree can be relocated without editing path math here.
from paths import OVERLAY_MODELS_DIR  # noqa: F401 — re-exported for sibling ops

# Slug rule: lowercase, runs of non-alphanumeric collapse to a single '-',
# strip leading/trailing '-'. Stable across repeated calls and platform-agnostic.
_SLUG_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def resolve_model_slug(item_name: str) -> str:
    """Derive an overlay slug from a SemanticModel display name.

    Examples:
        "Azure Data Insights"            -> "azure-data-insights"
        "Azure Data Partner & Community" -> "azure-data-partner-community"
        "BizModel-2026"                  -> "bizmodel-2026"

    Raises:
        ValueError: if the input is empty or produces an empty slug.
    """
    if not item_name or not item_name.strip():
        msg = "resolve_model_slug: item_name must be a non-empty string"
        raise ValueError(msg)

    slug = _SLUG_NORMALIZE_RE.sub("-", item_name.lower()).strip("-")
    if not slug:
        msg = f"resolve_model_slug: item_name {item_name!r} produces an empty slug"
        raise ValueError(msg)
    return slug


def resolve_overlay_dir(item_name: str, *, models_root: Path | None = None) -> Path:
    """Return the overlay directory path for `item_name` (existence not checked)."""
    root = models_root if models_root is not None else OVERLAY_MODELS_DIR
    return root / resolve_model_slug(item_name)


def resolve_overlay_functions_path(item_name: str, *, models_root: Path | None = None) -> Path:
    """Return the overlay `functions.tmdl` path for `item_name` (existence not checked)."""
    return resolve_overlay_dir(item_name, models_root=models_root) / "functions.tmdl"


def resolve_overlay_questions_path(item_name: str, *, models_root: Path | None = None) -> Path:
    """Return the overlay `copilot_questions.json` path for `item_name` (existence not checked)."""
    return resolve_overlay_dir(item_name, models_root=models_root) / "copilot_questions.json"
