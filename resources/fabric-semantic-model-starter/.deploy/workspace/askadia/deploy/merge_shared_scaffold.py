"""Merge shared AskADIA framework UDFs into per-model functions.tmdl.

Splices the canonical `askadia/udf/common/functions.tmdl` (37 framework UDFs:
internal helpers, codegen-stub helpers, and public entrypoints) into a
per-model semantic model's `definition/functions.tmdl` via name-based block
replacement. For each canonical UDF block:

- If the per-model file has a same-named `function 'NAME' = ...` block, REPLACE it.
- Otherwise, APPEND the canonical block at the end.

After the canonical splice, the per-model overlay (if any) is spliced in:

    .deploy/workspace/askadia/udf/models/<slug>/functions.tmdl

The slug is derived deterministically from `item_name`. Overlay UDF names
must NOT collide with canonical UDF names (overlay is for per-model UDFs
only — to change shared behavior, edit canonical instead). If an overlay
UDF has the same name as a UDF already present in per-model (rare —
typically only on first migration), it REPLACES it.

Per-model UDFs not in canonical and not in overlay are preserved untouched.

Designed for both:
- Pipeline use (called by `process_orchestrator.py` as a pre-process op).
- Local dev (run as a script with `--in-place <item_dir>` for TE2 editing).

See `.deploy/workspace/askadia/README.md` for the contract.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from model_overlay import OVERLAY_MODELS_DIR, resolve_model_slug
from paths import CANONICAL_FUNCTIONS_TMDL, UDF_COMMON_TABLES_DIR

# --- Constants ----------------------------------------------------------------

# Canonical scaffold paths come from the package paths module so the whole
# framework tree can be relocated without editing path math here.
DEFAULT_CANONICAL_PATH = CANONICAL_FUNCTIONS_TMDL
DEFAULT_CANONICAL_TABLES_DIR = UDF_COMMON_TABLES_DIR
DEFAULT_OVERLAY_MODELS_DIR = OVERLAY_MODELS_DIR

# Matches `function 'Local.AskADIA._Foo' =` or `function 'Local.AskADIA.Foo' =`.
# Captures the quoted name. Tolerates leading whitespace just in case (TMDL
# top-level functions are unindented in current files).
_FUNCTION_HEADER_RE = re.compile(r"^\s*function\s+'([^']+)'\s*=")

# Matches a doc-comment line (`///` followed by anything).
_DOC_COMMENT_RE = re.compile(r"^\s*///")


# --- Block parsing ------------------------------------------------------------


@dataclass(frozen=True)
class Block:
    """A logical UDF block: optional doc-comment chain + function + body + trailing properties."""

    name: str
    start: int  # 0-based line index, inclusive
    end: int    # 0-based line index, exclusive
    text: str   # full block text (lines joined, includes trailing newline if present)


def _parse_blocks(content: str, source_label: str) -> list[Block]:
    """Parse TMDL content into a list of UDF blocks.

    A block starts at the first `///` of a contiguous doc-comment chain immediately
    above a `function` line, OR at the `function` line itself if there's no chain.
    A block ends at the line just before the next block's start.

    Trailing properties (e.g. `isHidden`, `annotation TE_Group = ...`) and trailing
    blank lines belong to the block above them.

    Aborts on:
    - Duplicate function names within the same source.
    - Function header that doesn't match the expected pattern (defensive; we only
      look for `^function ` lines, so this is unreachable in practice).
    """
    lines = content.splitlines(keepends=True)

    # First pass: locate all `function` header line indexes.
    function_indexes: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _FUNCTION_HEADER_RE.match(line)
        if m:
            function_indexes.append((i, m.group(1)))

    if not function_indexes:
        return []

    # Second pass: walk back from each `function` line over the contiguous `///` chain.
    block_starts: list[tuple[int, str]] = []  # (start_idx, name)
    for func_idx, name in function_indexes:
        start = func_idx
        # Walk back over contiguous /// lines (no blank lines allowed in chain)
        j = func_idx - 1
        while j >= 0 and _DOC_COMMENT_RE.match(lines[j]):
            start = j
            j -= 1
        block_starts.append((start, name))

    # Sort by start position (should already be sorted, but defensive).
    block_starts.sort(key=lambda x: x[0])

    # Build blocks: end of block N = start of block N+1; last block ends at EOF.
    blocks: list[Block] = []
    for k, (start, name) in enumerate(block_starts):
        end = block_starts[k + 1][0] if k + 1 < len(block_starts) else len(lines)
        text = "".join(lines[start:end])
        blocks.append(Block(name=name, start=start, end=end, text=text))

    # Strict: no duplicate names within source.
    seen: dict[str, int] = {}
    for b in blocks:
        if b.name in seen:
            msg = (
                f"merge_shared_scaffold: duplicate function name '{b.name}' in {source_label} "
                f"(lines {seen[b.name] + 1} and {b.start + 1}). Aborting."
            )
            raise RuntimeError(msg)
        seen[b.name] = b.start

    return blocks


# --- Merge logic --------------------------------------------------------------


@dataclass
class MergeResult:
    """Summary of a merge operation."""

    replaced: list[str]            # names whose block was replaced (content was identical OR different)
    replaced_changed: list[str]    # subset of `replaced` where content actually differed
    appended: list[str]            # names appended (not previously in per-model)
    preserved: list[str]           # per-model names not in canonical (left untouched)
    output_text: str               # the merged content


def _merge_blocks(
    canonical_blocks: list[Block],
    per_model_blocks: list[Block],
    per_model_text: str,
) -> MergeResult:
    """Merge canonical UDFs into per-model content.

    Strategy:
    - Walk per-model blocks in order. For each block:
        - If its name is in canonical, emit the canonical block's text instead.
        - Else, emit the per-model block as-is.
    - After the loop, append any canonical blocks whose names didn't appear in
      per-model.
    - Preserve any "leading" per-model content (anything before the first block,
      including blank lines/comments). Per-model files in this repo currently
      have zero leading content above the first `function`/`///`, but we
      preserve it defensively.
    """
    canonical_by_name = {b.name: b for b in canonical_blocks}
    per_model_names = {b.name for b in per_model_blocks}

    replaced: list[str] = []
    replaced_changed: list[str] = []
    appended: list[str] = []
    preserved: list[str] = []

    out_parts: list[str] = []

    # Preserve leading content (anything before the first per-model block).
    if per_model_blocks:
        first_start = per_model_blocks[0].start
        if first_start > 0:
            leading = "".join(per_model_text.splitlines(keepends=True)[:first_start])
            out_parts.append(leading)

    # Walk per-model blocks in order.
    for b in per_model_blocks:
        if b.name in canonical_by_name:
            canon = canonical_by_name[b.name]
            out_parts.append(canon.text)
            replaced.append(b.name)
            if canon.text != b.text:
                replaced_changed.append(b.name)
        else:
            out_parts.append(b.text)
            preserved.append(b.name)

    # Append any canonical blocks not already present.
    needs_separator = bool(out_parts) and not out_parts[-1].endswith("\n\n")
    for b in canonical_blocks:
        if b.name not in per_model_names:
            if needs_separator:
                # Ensure at least one blank line separator.
                if not out_parts[-1].endswith("\n"):
                    out_parts.append("\n")
                if not out_parts[-1].endswith("\n\n"):
                    out_parts.append("\n")
                needs_separator = False
            out_parts.append(b.text)
            appended.append(b.name)

    return MergeResult(
        replaced=replaced,
        replaced_changed=replaced_changed,
        appended=appended,
        preserved=preserved,
        output_text="".join(out_parts),
    )


def _atomic_write(target: Path, content: str) -> None:
    """Write content to target atomically (temp file in same dir + os.replace)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# --- Shared tables sync -------------------------------------------------------


@dataclass
class TableSyncResult:
    """Summary of a table-sync operation (per file)."""

    name: str          # filename (e.g. "_INFO_COLUMNS.tmdl")
    action: str        # "wrote" | "noop" | "warn-overwrote-edits"
    bytes_written: int


def _sync_tables(
    canonical_tables_dir: Path,
    item_dir: Path,
) -> list[TableSyncResult]:
    """Copy each canonical .tmdl file into the per-model definition/tables/ dir.

    Each canonical file overwrites the per-model copy (single source of truth).
    If a *static-canonical* per-model copy differs from canonical, a WARN is
    logged (silently overwriting it carries the same risk as overwriting
    per-model functions.tmdl edits). Canonical ``_PLACEHOLDER`` stubs are
    exempt: those tables are regenerated downstream in the same fixed-order
    deploy chain (e.g. _INFO_HIERARCHIES via generateInfoHierarchies.csx), so a
    populated per-model copy differing from the stub is expected drift, not a
    lost edit -- warning on it would be noise that could mask a genuine
    static-table edit.
    Files that don't exist in canonical are left untouched in per-model.
    Atomic writes throughout.
    """
    results: list[TableSyncResult] = []
    if not canonical_tables_dir.exists():
        # No tables to sync — quietly return.
        return results

    target_dir = item_dir / "definition" / "tables"
    target_dir.mkdir(parents=True, exist_ok=True)

    for canonical_file in sorted(canonical_tables_dir.glob("*.tmdl")):
        canonical_text = canonical_file.read_text(encoding="utf-8")
        target_file = target_dir / canonical_file.name
        existed_before = target_file.exists()
        existing_text = target_file.read_text(encoding="utf-8") if existed_before else None

        if existing_text == canonical_text:
            results.append(TableSyncResult(name=canonical_file.name, action="noop", bytes_written=0))
            continue

        _atomic_write(target_file, canonical_text)
        # Placeholder stubs are regenerated downstream, so overwriting populated
        # per-model rows with the stub is expected — never flag it as a lost edit.
        is_placeholder = "_PLACEHOLDER" in canonical_text
        clobbered_real_edit = existed_before and existing_text != canonical_text and not is_placeholder
        action = "warn-overwrote-edits" if clobbered_real_edit else "wrote"
        results.append(TableSyncResult(
            name=canonical_file.name, action=action, bytes_written=len(canonical_text.encode("utf-8")),
        ))

    return results


# --- Operation entry point ----------------------------------------------------


def merge_shared_scaffold(
    item_name,
    item_type,
    context,  # noqa: ARG001 — required by op signature
    workspace=None,  # noqa: ARG001 — required by op signature
    item_directory=None,
    *,
    canonical_path=None,
    canonical_tables_dir=None,
    overlay_models_dir=None,
    source_model_name=None,
    **kwargs,  # noqa: ARG001 — tolerate future YAML params
):
    """Merge canonical AskADIA UDFs + tables + per-model overlay UDFs into a SemanticModel.

    Three-part sync:
    1. Block-merge canonical functions.tmdl into per-model functions.tmdl.
    2. File-copy canonical tables/*.tmdl into per-model definition/tables/.
    3. Block-merge per-model overlay functions.tmdl (if present) into the
       per-model functions.tmdl.

    Gating: this op runs unconditionally when called. Bootstrap gating (does
    this model belong on the AskADIA framework at all?) is enforced upstream
    by `setup_askadia_framework`, which checks for the per-model overlay dir
    before invoking this op. Calling this op directly via CLI (or from a
    non-bundled YAML chain) skips that gate — that's intentional for dev
    workflows but means callers should know what they're invoking.

    Args:
        item_name: Display name of the item as it appears on disk
            (e.g. "Azure Data Insights" in production, or
            "DEBUG_UnitTest_DEV_AzureDataInsights_<id>" when invoked by
            run_tests.py / debug_deploy.py against a staged copy).
        item_type: Item type (must be "SemanticModel" or this is a no-op).
        context: DeploymentContext (unused).
        workspace: FabricWorkspace (unused; pre-process runs before workspace exists).
        item_directory: Path to the per-model directory (e.g. ".../Azure Data Insights.SemanticModel").
        canonical_path: Override the canonical functions.tmdl path (defaults to
            .deploy/workspace/askadia/udf/common/functions.tmdl).
        canonical_tables_dir: Override the canonical tables dir (defaults to
            .deploy/workspace/askadia/udf/common/tables/). Set to "" to skip tables sync.
        overlay_models_dir: Override the per-model overlay root (defaults to
            .deploy/workspace/askadia/udf/models/). The slug-named subdir under
            this root provides the per-model overlay functions.tmdl. Missing dir
            or missing functions.tmdl logs a ``[OVERLAY] ... (skipped)`` line and
            continues (model has no per-model UDFs). An overlay file that exists
            but parses to zero UDF blocks raises — that's a malformed file, not
            an intentional opt-out.
        source_model_name: Source model name when ``item_name`` is a staged
            throwaway (e.g. ``DEBUG_UnitTest_*_<id>``). Used to resolve the
            overlay slug. Production deploy leaves this None and falls back
            to ``item_name``.
    """
    # Gate by item type.
    if item_type != "SemanticModel":
        return

    # Validate inputs.
    if not item_directory:
        msg = "merge_shared_scaffold: item_directory is required"
        raise ValueError(msg)

    item_dir = Path(item_directory)
    if not item_dir.exists():
        msg = f"merge_shared_scaffold: item_directory does not exist: {item_dir}"
        raise FileNotFoundError(msg)

    # Resolve canonical path.
    canonical = Path(canonical_path) if canonical_path else DEFAULT_CANONICAL_PATH
    if not canonical.exists():
        msg = f"merge_shared_scaffold: canonical file not found: {canonical}"
        raise FileNotFoundError(msg)

    canonical_text = canonical.read_text(encoding="utf-8")
    canonical_blocks = _parse_blocks(canonical_text, source_label=str(canonical))
    if not canonical_blocks:
        msg = f"merge_shared_scaffold: canonical file has no UDF blocks: {canonical}"
        raise RuntimeError(msg)

    # Resolve per-model functions.tmdl. Treat missing as empty (Phase 3 bootstrap).
    per_model_path = item_dir / "definition" / "functions.tmdl"
    if per_model_path.exists():
        per_model_text = per_model_path.read_text(encoding="utf-8")
    else:
        per_model_text = ""
    per_model_blocks = _parse_blocks(per_model_text, source_label=str(per_model_path))

    # Part 1: merge canonical into per-model (in memory).
    canonical_result = _merge_blocks(canonical_blocks, per_model_blocks, per_model_text)
    intermediate_text = canonical_result.output_text

    # Part 1b: resolve and load per-model overlay (if any).
    # Use source_model_name when set (staged contexts where item_name is a
    # throwaway DEBUG_* name); otherwise fall back to item_name (prod deploy).
    overlay_root = Path(overlay_models_dir) if overlay_models_dir else DEFAULT_OVERLAY_MODELS_DIR
    slug_source = source_model_name or item_name
    overlay_slug = resolve_model_slug(slug_source)
    overlay_path = overlay_root / overlay_slug / "functions.tmdl"
    overlay_blocks: list[Block] = []
    overlay_result = None  # Set if we actually merge an overlay; remains None if skipped.
    if overlay_path.exists():
        overlay_text = overlay_path.read_text(encoding="utf-8")
        overlay_blocks = _parse_blocks(overlay_text, source_label=str(overlay_path))

        # Reject overlay files that exist but parse to zero blocks. A user
        # who creates the file intentionally has at least one block; an empty
        # or malformed file is almost certainly a mistake we don't want to
        # silently swallow.
        if not overlay_blocks:
            msg = (
                f"merge_shared_scaffold: overlay file exists but contains no "
                f"UDF blocks: {overlay_path}. Add at least one block, or delete "
                f"the file to fall back to canonical-only."
            )
            raise RuntimeError(msg)

        # Validate: overlay UDF names must NOT collide with canonical UDF names.
        # Overlay is for per-model UDFs only; to change shared behavior, edit canonical.
        canonical_names = {b.name for b in canonical_blocks}
        collisions = sorted({b.name for b in overlay_blocks if b.name in canonical_names})
        if collisions:
            msg = (
                f"merge_shared_scaffold: overlay UDF(s) collide with canonical: {collisions} "
                f"(overlay path: {overlay_path}). Overlay is for per-model UDFs only; "
                f"to change shared behavior, edit canonical instead."
            )
            raise RuntimeError(msg)

    # Part 2: merge overlay into the post-canonical text (in memory).
    if overlay_blocks:
        intermediate_blocks = _parse_blocks(intermediate_text, source_label="<post-canonical>")
        overlay_result = _merge_blocks(overlay_blocks, intermediate_blocks, intermediate_text)
        final_text = overlay_result.output_text
    else:
        final_text = intermediate_text

    # Strict sanity: every canonical AND every overlay block must appear in final output.
    final_blocks = _parse_blocks(final_text, source_label="<merged output>")
    final_names = {b.name for b in final_blocks}
    missing_canonical = [b.name for b in canonical_blocks if b.name not in final_names]
    missing_overlay = [b.name for b in overlay_blocks if b.name not in final_names]
    if missing_canonical or missing_overlay:
        msg = (
            f"merge_shared_scaffold: post-merge sanity check failed; "
            f"missing canonical={missing_canonical}, missing overlay={missing_overlay}"
        )
        raise RuntimeError(msg)

    # Write back atomically (only if changed, to avoid noisy mtime updates).
    if final_text != per_model_text:
        _atomic_write(per_model_path, final_text)
        wrote = "WROTE"
    else:
        wrote = "NOOP"

    # Diff log — canonical line.
    n_canonical = len(canonical_blocks)
    n_per_model_in = len(per_model_blocks)
    n_final = len(final_blocks)
    print(
        f"      [{wrote}] {item_name}: canonical={n_canonical}, per-model in={n_per_model_in}, "
        f"out={n_final} | replaced={len(canonical_result.replaced)} "
        f"(changed={len(canonical_result.replaced_changed)}), "
        f"appended={len(canonical_result.appended)}, preserved={len(canonical_result.preserved)}"
    )
    if canonical_result.replaced_changed:
        # Loud warning: someone edited a shared UDF in the per-model file. Their
        # edits just got overwritten by canonical. Surface so it's visible in CI.
        print(
            f"      [WARN] Per-model edits overwritten by canonical for: "
            f"{', '.join(canonical_result.replaced_changed)}"
        )
    if canonical_result.appended:
        print(f"      [INFO] Appended canonical blocks: {', '.join(canonical_result.appended)}")

    # Diff log — overlay line (only if overlay was processed).
    if overlay_result is not None:
        print(
            f"      [OVERLAY] {item_name} (slug={overlay_slug}): overlay={len(overlay_blocks)} "
            f"| replaced={len(overlay_result.replaced)} "
            f"(changed={len(overlay_result.replaced_changed)}), "
            f"appended={len(overlay_result.appended)}"
        )
        if overlay_result.replaced_changed:
            print(
                f"      [WARN] Per-model edits overwritten by overlay for: "
                f"{', '.join(overlay_result.replaced_changed)}"
            )
        if overlay_result.appended:
            print(f"      [INFO] Appended overlay blocks: {', '.join(overlay_result.appended)}")
    elif not overlay_path.exists():
        # Quiet, but log existence-or-not so a reader can audit. No noise per-model.
        print(f"      [OVERLAY] {item_name}: no overlay at {overlay_path} (skipped)")

    # Part 2: sync canonical tables.
    if canonical_tables_dir == "":
        # Explicit opt-out
        return
    tables_dir = Path(canonical_tables_dir) if canonical_tables_dir else DEFAULT_CANONICAL_TABLES_DIR
    table_results = _sync_tables(tables_dir, item_dir)
    if table_results:
        wrote_n = sum(1 for r in table_results if r.action == "wrote")
        warn_n = sum(1 for r in table_results if r.action == "warn-overwrote-edits")
        noop_n = sum(1 for r in table_results if r.action == "noop")
        print(
            f"      [TABLES] {item_name}: {len(table_results)} canonical | "
            f"wrote={wrote_n}, overwrote-edits={warn_n}, noop={noop_n}"
        )
        for r in table_results:
            if r.action == "warn-overwrote-edits":
                print(f"      [WARN] Per-model edits overwritten in {r.name}")
            elif r.action == "wrote":
                print(f"      [INFO] Synced canonical table: {r.name}")


# --- CLI ----------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge canonical AskADIA UDFs into a per-model functions.tmdl.",
    )
    parser.add_argument(
        "--item-dir",
        required=True,
        help="Path to the per-model SemanticModel directory.",
    )
    parser.add_argument(
        "--item-name",
        default=None,
        help="Item display name (used to resolve overlay slug). Defaults to dirname.",
    )
    parser.add_argument(
        "--canonical",
        default=None,
        help=f"Override canonical path (default: {DEFAULT_CANONICAL_PATH}).",
    )
    parser.add_argument(
        "--overlay-models-dir",
        default=None,
        help=f"Override per-model overlay root (default: {DEFAULT_OVERLAY_MODELS_DIR}).",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="(No-op flag for clarity; merges always operate in-place.)",
    )
    args = parser.parse_args(argv)

    item_dir = Path(args.item_dir).resolve()
    item_name = args.item_name or item_dir.name.removesuffix(".SemanticModel")

    merge_shared_scaffold(
        item_name=item_name,
        item_type="SemanticModel",
        context=None,
        workspace=None,
        item_directory=str(item_dir),
        canonical_path=args.canonical,
        overlay_models_dir=args.overlay_models_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
