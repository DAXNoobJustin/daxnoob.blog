"""Model emitter: render the canonical instruction store into a model's
``_COPILOT_INSTRUCTIONS.tmdl`` + ``Copilot/Instructions/instructions.md`` router.

This is a pure renderer over the store (no second authored copy). It
assembles the shared rows (``common/manifest.json`` › ``model.sharedRows``,
Ids 1..N — each row a concatenation of one or more shared blocks) ahead of the
model's own rows (``models/<slug>/rows/``, ordered by
``models/<slug>/model.json``), assigns position-derived Ids,
resolves visible ``{{ref:anchor}}`` cross-references to the row's stable key
(its anchor, the handle the LLM fetches by),
resolves model GUID tokens to the target environment's dataset GUID (an injected
``slug -> guid`` map resolved from ``config/model_guids.yml`` ``copilot_model_guids``;
production by default, per-environment overrides at deploy), and emits
the calculated-table TMDL via the proven codec. The always-on router is fully
generated (no authored router file).

``--check`` is a dry diff used by CI: regenerating a model reproduces the
deploy-staged artifacts byte-for-byte.

Usage:
    python emit_model.py --slug azure-data-insights \
        --model-dir "<...>/Azure Data Insights.SemanticModel"
    python emit_model.py --slug azure-data-insights --model-dir <...> --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from _core.model_table import render_table
from _core.paths import (
    block_path,
    manifest_path,
    model_block_path,
    model_json_path,
    router_preamble_path,
)
from _core.routing import (
    active_siblings,
    render_cross_model_section,
    render_out_of_scope,
)
from _core.tmdl import InstructionRow
from _core.anchors import find_dangling_anchors
from _core.tokens import (
    TokenMap,
    detokenize,
    find_tokens,
    find_residual_tokens,
    find_unresolved_directives,
)

HERE = Path(__file__).resolve().parent

TABLE_REL = "definition/tables/_COPILOT_INSTRUCTIONS.tmdl"
ROUTER_REL = "Copilot/Instructions/instructions.md"

# Model rows whose body the emitter generates from the routing registry instead
# of reading a per-model file (the row still declares its metadata in model.json;
# only the body is generated). Keyed anchor -> renderer(canonical_root, slug).
_GENERATED_ROW_RENDERERS = {
    "out-of-scope": render_out_of_scope,
}

# Router intro paragraph. The only model-specific part of the always-on header;
# everything below it (rules + workflow) is the shared router-preamble.md.
_INTRO = (
    "You answer questions about the {title} semantic model. The detailed Ask "
    "ADIA skill instructions have been split into the `_COPILOT_INSTRUCTIONS` "
    "table so this always-on file can stay small. Fetch only the rows needed "
    "for the user's question, then follow the returned markdown as the source "
    "of truth."
)


def _load_manifest(canonical_root: Path) -> dict:
    return json.loads(manifest_path(canonical_root).read_text(encoding="utf-8"))


def _model_token_map(slug: str, guids: dict[str, str]) -> TokenMap:
    return TokenMap(guids=dict(guids), refs={})


def _assemble(canonical_root: Path, slug: str) -> tuple[list[dict], dict]:
    """Assemble the full ordered row set for a model: the shared rows (Ids
    1..N, each one a list of content blocks per the manifest) followed by the
    model's own rows. Each row dict carries anchor / topic / whenToUse /
    routerHint / the content block path(s) and a 1-based, position-derived
    ``id`` (never authored — that is what keeps cross-references drift-free)."""
    manifest = _load_manifest(canonical_root)
    model = json.loads(model_json_path(canonical_root, slug).read_text(encoding="utf-8"))

    assembled: list[dict] = []
    for row in manifest["model"]["sharedRows"]:
        assembled.append(
            {
                "anchor": row["anchor"],
                "topic": row["topic"],
                "whenToUse": row["whenToUse"],
                "routerHint": row["routerHint"],
                "paths": [block_path(canonical_root, b) for b in row["blocks"]],
            }
        )
    for r in model["rows"]:
        anchor = r["anchor"]
        generated = anchor in _GENERATED_ROW_RENDERERS
        assembled.append(
            {
                "anchor": anchor,
                "topic": r["topic"],
                "whenToUse": r["whenToUse"],
                "routerHint": r["routerHint"],
                "paths": [] if generated else [model_block_path(canonical_root, slug, anchor)],
                "generated": anchor if generated else None,
            }
        )
    for i, row in enumerate(assembled, start=1):
        row["id"] = i
    return assembled, model


def _render_body(paths: list[Path], tmap: TokenMap) -> str:
    return "".join(
        detokenize(p.read_text(encoding="utf-8"), tmap) for p in paths
    )


def render(canonical_root: Path, slug: str, guids: dict[str, str]) -> dict[str, str]:
    """Render a model's _COPILOT_INSTRUCTIONS table + always-on router.

    ``guids`` is an injected ``slug -> dataset GUID`` map (already resolved to the
    target environment by the caller, e.g. via ``_core.guids.load_guids``). It
    must contain this model AND every active sibling it reroutes to — the renderer
    itself reads no config, which keeps it portable.
    """
    required = {slug, *active_siblings(canonical_root, slug)}
    missing = sorted(required - set(guids))
    if missing:
        raise KeyError(
            f"Missing dataset GUID(s) for {slug} render: {missing}. "
            f"Add them to copilot_model_guids (config/model_guids.yml)."
        )
    assembled, model = _assemble(canonical_root, slug)
    # anchor -> `anchor` (backtick'd key) so visible {{ref:anchor}} tokens in
    # bodies render to the row's stable fetch handle, matching the always-on
    # Topic index and the [Key] IN {...} fetch DAX.
    refs = {row["anchor"]: f"`{row['anchor']}`" for row in assembled}
    tmap = _model_token_map(slug, guids)
    tmap.refs = refs

    rows = []
    for row in assembled:
        if row.get("generated"):
            body = detokenize(
                _GENERATED_ROW_RENDERERS[row["generated"]](canonical_root, slug), tmap
            )
        else:
            body = _render_body(row["paths"], tmap)
        dangling = find_dangling_anchors(body)
        if dangling:
            raise ValueError(
                f"Dangling intra-row anchor(s) in {slug} row '{row['anchor']}': "
                f"{dangling}. A '](#x)' link must target a heading in the SAME row; "
                f"use a {{{{ref:<anchor>}}}} token for a cross-row pointer."
            )
        rows.append(
            InstructionRow(
                id=row["id"],
                key=row["anchor"],
                topic=row["topic"],
                when_to_use=row["whenToUse"],
                instructions=body,
            )
        )

    out = {
        TABLE_REL: render_table(rows),
        ROUTER_REL: _render_router(canonical_root, slug, assembled, model, tmap),
    }
    for rel, content in out.items():
        leftover = find_tokens(content)
        if leftover:
            raise ValueError(f"Unresolved tokens in {slug}:{rel}: {leftover}")
        stray = find_unresolved_directives(content)
        if stray:
            raise ValueError(
                f"Unresolved {{{{only}}}} directive in {slug}:{rel}: {stray}"
            )
        residual = find_residual_tokens(content)
        if residual:
            raise ValueError(
                f"Malformed/unresolved token in {slug}:{rel}: {residual} "
                "(a {{...}} fragment survived detokenization)"
            )
    return out


def _render_router(
    canonical_root: Path, slug: str, assembled: list[dict], model: dict, tmap: TokenMap
) -> str:
    """Fully generate the always-on router: H1 + intro (from the model.json
    title) + shared preamble + a generated topic index (keyed by the row's
    fetch handle) + generated worked routing examples (anchors -> key sets) +
    the cross-model section."""
    title = model["title"]
    preamble = router_preamble_path(canonical_root).read_text(encoding="utf-8").rstrip("\n")

    lines = [f"# {title} - Copilot guidance", "", _INTRO.format(title=title), "", preamble, ""]
    lines += ["## Topic index", "", "| Key | Topic | When to use |", "|---|---|---|"]
    for row in assembled:
        lines.append(f"| `{row['anchor']}` | {row['topic']} | {row['routerHint']} |")
    lines += ["", "## Worked routing examples", ""]
    for ex in model.get("workedExamples", []):
        keystr = ", ".join(f'"{a}"' for a in ex["rows"])
        lines.append(f'- "{ex["ask"]}" -> `{{ {keystr} }}`')
    router = "\n".join(lines) + "\n"

    section = render_cross_model_section(canonical_root, slug)
    if section:
        router = router.rstrip("\n") + "\n\n" + section
    return detokenize(router, tmap)


def update_golden(canonical_root: Path, slug: str, guids: dict[str, str]) -> dict[str, str]:
    """Capture sha256 of the current emit output into the model's ``golden``
    block (a drift snapshot), using the production GUID baseline.

    These models are deploy-only (no committed _COPILOT_INSTRUCTIONS to anchor
    against), so the golden is *self-generated*: it pins future drift, not
    current correctness. Run this only after the canonical content and
    ``routing.json`` are final (cross-model routing must already be active for
    every sibling), since the router bytes — and therefore the hash — depend on
    which siblings are active. Correctness is enforced separately by the
    semantic-invariant tests in ``test_roundtrip.py``.
    """
    mj = model_json_path(canonical_root, slug)
    model = json.loads(mj.read_text(encoding="utf-8"))
    rendered = render(canonical_root, slug, guids)
    golden = {
        rel: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for rel, content in rendered.items()
    }
    model["golden"] = golden
    mj.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    return golden


def _cli_guids(args) -> dict[str, str]:
    """Resolve the GUID map for the CLI from the workspace config, honoring an
    optional single-model ``--guid`` override for ``--slug``."""
    from _core.guids import load_guids  # noqa: PLC0415

    config = args.config or (args.canonical_root.resolve().parent / "config" / "model_guids.yml")
    guids = load_guids(config, args.env)
    if args.guid:
        guids[args.slug] = args.guid
    return guids


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--model-dir", type=Path)
    ap.add_argument("--canonical-root", type=Path, default=HERE)
    ap.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Config holding copilot_model_guids. Defaults to "
        "askadia/config/model_guids.yml relative to --canonical-root.",
    )
    ap.add_argument(
        "--env",
        default="prod",
        help="Target environment (release_type) for GUID resolution. Default: prod.",
    )
    ap.add_argument(
        "--guid",
        default=None,
        help="Override this model's dataset GUID for the emit (overlays the "
        "resolved map for --slug). Siblings still resolve from --config.",
    )
    ap.add_argument("--check", action="store_true")
    ap.add_argument(
        "--update-golden",
        action="store_true",
        help="Recompute the golden drift snapshot from the current emit output "
        "and write it into model.json. Use after intentional content changes.",
    )
    args = ap.parse_args()

    if args.update_golden and (args.env != "prod" or args.guid):
        ap.error(
            "--update-golden blesses the production-GUID baseline; do not combine "
            "it with --env/--guid (that would pin a non-prod hash)."
        )

    guids = _cli_guids(args)

    if args.update_golden:
        golden = update_golden(args.canonical_root, args.slug, guids)
        print(f"Updated golden for {args.slug}: {len(golden)} file(s)")
        for rel, sha in golden.items():
            print(f"  {sha[:12]}  {rel}")
        return 0

    rendered = render(args.canonical_root, args.slug, guids)
    if args.model_dir is None:
        ap.error("--model-dir is required unless --update-golden is used")
    if args.check:
        drift = []
        for rel, content in rendered.items():
            dest = args.model_dir / rel
            if not dest.exists():
                drift.append(f"missing in target: {rel}")
            elif dest.read_bytes().decode("utf-8") != content:
                drift.append(f"differs: {rel}")
        if drift:
            print(f"Model {args.slug} output is stale:", file=sys.stderr)
            for d in drift:
                print(f"  - {d}", file=sys.stderr)
            return 1
        print(f"OK: {args.slug} output matches canonical source.")
        return 0

    for rel, content in rendered.items():
        dest = args.model_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="\n")
    print(f"Emitted {len(rendered)} files for {args.slug} into {args.model_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
