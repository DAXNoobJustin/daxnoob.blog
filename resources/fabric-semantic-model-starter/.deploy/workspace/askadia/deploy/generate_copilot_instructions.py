"""Generate a model's _COPILOT_INSTRUCTIONS table + instructions.md router from
the canonical instruction store, at deploy time (pre_process).

Sibling to `generate_copilot_questions`, but simpler: the `_COPILOT_INSTRUCTIONS`
table is a *calculated* `UNION(ROW())` partition, so its whole TMDL file is pure
text rendered from canonical — no TabularEditor pass is needed.

These two artifacts are NOT source-controlled on the model. Exactly like the
shared `_COPILOT_*` / `_INFO_*` tables (injected by `merge_shared_scaffold`),
they are generated into the staged model during pre_process, before publish.
Like those siblings, `_COPILOT_INSTRUCTIONS` is not listed in any role (readable
under `modelPermission: read`); the emitted table carries the
`ROLE_ALL_USERS_MISSING_TABLE_PERMISSION` BPA ignore annotation.
Canonical (`askadia/instructions/`) is the single source of truth.

Canonical source of truth:

    .deploy/workspace/askadia/instructions/
        routing.json + common/manifest.json + common/router-preamble.md
        common/blocks/<shared block bodies>.md
        models/<slug>/model.json      (per-model row order / worked examples / golden)
        models/<slug>/rows/<per-model block bodies>.md

If the model has no canonical instruction set (`model.json` absent), the op
skips silently — bare models opt in by adding a canonical model dir, exactly
like the questions/overlay framework.

This op resolves the per-model dataset GUIDs from the central
``askadia/config/model_guids.yml`` ``copilot_model_guids`` map for the
target environment and injects them into the emitter. The target env is
``context.environment`` — the actual workspace being written (one of
dev/test/prod), resolved per-branch by the release pipeline and by the
debug/unit-test harness. Every environment requires an explicit GUID
(no prod fallback). GUIDs live in exactly one place; there is no per-model
GUID in the instruction store itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

from model_overlay import resolve_model_slug
from paths import INSTRUCTIONS_DIR as _INSTRUCTIONS_DIR
from paths import MODEL_GUIDS_YML

# The instruction toolkit (emitter + _core) is a sibling tree under the framework
# package; put it on sys.path so we can import its emitter without duplicating
# logic.
if str(_INSTRUCTIONS_DIR) not in sys.path:
    sys.path.insert(0, str(_INSTRUCTIONS_DIR))


def generate_copilot_instructions(
    item_name,
    item_type="SemanticModel",
    context=None,
    workspace=None,  # noqa: ARG001 — accepted for op signature symmetry
    item_directory=None,
    *,
    source_model_name=None,
    **kwargs,  # noqa: ARG001 — tolerate future YAML params
):
    """Render canonical instruction rows into the model's _COPILOT_INSTRUCTIONS
    table + always-on router.

    Args:
        item_name: Display name of the item as it appears on disk.
        item_type: Item type (defaults to "SemanticModel"); no-op otherwise.
        context: DeploymentContext (used to derive item_directory if absent).
        item_directory: Path to the per-model SemanticModel directory.
        source_model_name: Source model name when ``item_name`` is a staged
            throwaway; used to resolve the canonical slug.
    """
    if item_type != "SemanticModel":
        return

    if item_directory is None:
        if context is None or getattr(context, "repository_directory", None) is None:
            msg = (
                "generate_copilot_instructions requires either item_directory or "
                "context.repository_directory"
            )
            raise ValueError(msg)
        item_directory = Path(context.repository_directory) / f"{item_name}.{item_type}"
    item_directory = Path(item_directory)

    slug = resolve_model_slug(source_model_name or item_name)
    from _core.paths import model_json_path  # noqa: PLC0415

    model_json = model_json_path(_INSTRUCTIONS_DIR, slug)
    if not model_json.exists():
        print(
            f"      Skipping copilot instructions codegen - no canonical model.json "
            f"at {model_json}"
        )
        return

    # Imported lazily so the sys.path insert above is in effect and so models
    # that skip never pay the import cost.
    import emit_model  # noqa: PLC0415
    from _core.guids import load_guids  # noqa: PLC0415

    # Resolve the *target environment* whose dataset GUIDs the cross-model
    # routing should reference. ``context.environment`` is the actual workspace
    # being written (one of dev/test/prod), resolved per-branch by the release
    # pipeline (Variables_*.yml `environments` map) and by the debug/unit-test
    # harness. The release *flavor* is deliberately NOT used as the GUID key —
    # the same flavor can target different environments per branch, so keying off
    # it would point a release at the wrong datasets.
    # No prod fallback: the resolved env must have its own GUID (enforced downstream).
    env = getattr(context, "environment", None)
    if not env:
        raise ValueError(
            "generate_copilot_instructions: cannot resolve target environment "
            "(context.environment is unset)"
        )
    guids = load_guids(MODEL_GUIDS_YML, env)
    rendered = emit_model.render(_INSTRUCTIONS_DIR, slug, guids)
    print(f"      Generating _COPILOT_INSTRUCTIONS for {item_name} (slug={slug})")
    for rel, content in rendered.items():
        dest = item_directory / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="\n")
        print(f"        wrote {rel}")

    # Set the Fabric item's metadata description on its .platform (Copilot/M365
    # grounding + catalog; <=500 chars), combining any hand-authored description
    # with the routing-derived topic list.
    from _core.model_description import (  # noqa: PLC0415
        apply_platform_description,
        build_description,
        read_platform_description,
        read_platform_display_name,
    )

    platform = item_directory / ".platform"
    if platform.exists():
        existing = read_platform_description(platform)
        display = read_platform_display_name(platform)
        apply_platform_description(
            platform,
            build_description(_INSTRUCTIONS_DIR, slug, existing=existing, display_name=display),
        )
        print("        set .platform description")
