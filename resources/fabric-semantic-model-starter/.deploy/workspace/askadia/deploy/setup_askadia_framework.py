"""Bundled AskADIA framework setup op.

Single yml entry point that runs the 8-step AskADIA framework chain in fixed
order against a SemanticModel that has been bootstrapped onto the framework.

Bootstrapping = create a per-model overlay directory at:

    .deploy/workspace/askadia/udf/models/<slug>/

with at minimum a README.md (the intent marker). The overlay dir is the sole
gating signal — if it doesn't exist, the entire bundle is a no-op. Slug is
derived from the SemanticModel display name via `model_overlay.resolve_model_slug`.

Steps run (each may internally skip if its specific inputs are absent):

    1. merge_shared_scaffold       — splice canonical UDFs + tables + overlay UDFs
    2. generate_copilot_instructions — render _COPILOT_INSTRUCTIONS table + instructions.md router
    3. generate_copilot_questions  — populate _COPILOT_QUESTIONS partition
    4. generate_annotation_config  — populate _COPILOT_ANNOTATIONS_REGISTRY partition
    5. generate_variant_config    — populate _COPILOT_VARIANT_CONFIG partition
    6. generateInfoAnnotations.csx — refresh _INFO_ANNOTATIONS table
    7. generateInfoHierarchies.csx — refresh _INFO_HIERARCHIES table
    8. generateSearchHelpers.csx   — regenerate _SearchAllValues + _SearchAllLadderColumns

generate_copilot_instructions writes a self-contained calculated table (pure
TMDL text rendered from the canonical instruction store) and the always-on
router; it needs no _INFO_* tables, so it runs right after the scaffold merge.

Order matters: merge syncs the _INFO_* + registry shells; csx scripts then
populate them. generate_annotation_config sits between the JSON-driven
codegen step (questions) and the runtime-info refresh steps because the
registry is static config (no dependency on _INFO_*) but DiscoverColumns
joins _COPILOT_ANNOTATIONS_REGISTRY × _INFO_ANNOTATIONS at query time and
the merge step needs to land both table shells before population.
Don't reorder.

NOT part of this bundle: `generate_copilot_schema` is PBI-native Copilot
tooling (reads `Copilot/schema.json`), not AskADIA framework. It runs as a
separate op in the workspace yml after this bundle.
"""

from __future__ import annotations

from generate_annotation_config import generate_annotation_config
from generate_copilot_instructions import generate_copilot_instructions
from generate_copilot_questions import generate_copilot_questions
from generate_variant_config import generate_variant_config
from merge_shared_scaffold import merge_shared_scaffold
from model_overlay import resolve_model_slug, resolve_overlay_dir
from paths import instruction_model_json, TABULAR_SCRIPTS_DIR
from run_tabular_editor import run_model_script

# Framework csx now live inside the self-contained package (deploy/tabular_scripts/).
_TABULAR_SCRIPTS_DIR = TABULAR_SCRIPTS_DIR

# Fixed sub-step chain. Order matters — see module docstring.
_STEPS = [
    ("merge_shared_scaffold", merge_shared_scaffold, {}),
    ("generate_copilot_instructions", generate_copilot_instructions, {}),
    ("generate_copilot_questions", generate_copilot_questions, {}),
    ("generate_annotation_config", generate_annotation_config, {}),
    ("generate_variant_config", generate_variant_config, {}),
    ("generateInfoAnnotations.csx", run_model_script, {
        "script_path": str(_TABULAR_SCRIPTS_DIR / "generateInfoAnnotations.csx"),
    }),
    ("generateInfoHierarchies.csx", run_model_script, {
        "script_path": str(_TABULAR_SCRIPTS_DIR / "generateInfoHierarchies.csx"),
    }),
    ("generateSearchHelpers.csx", run_model_script, {
        "script_path": str(_TABULAR_SCRIPTS_DIR / "generateSearchHelpers.csx"),
    }),
]


def setup_askadia_framework(
    item_name,
    item_type,
    context,
    workspace=None,
    item_directory=None,
    *,
    source_model_name=None,
    **kwargs,  # noqa: ARG001 — tolerate future YAML params
):
    """Run the AskADIA framework setup chain against `item_name`.

    Logs a ``[SKIP]`` line and returns if the model's overlay directory doesn't
    exist (the model is not bootstrapped onto the framework). Raises if the
    overlay dir exists but README.md is missing — that's a bootstrap mistake
    (someone created an empty dir without intentional sign-off) — or if the model
    is UDF-bootstrapped but has no instruction set (``models/<slug>/model.json``);
    the UDF overlay and the instruction set are a single coupled gate.

    Args:
        item_name: Display name as it appears on disk (e.g. "Azure Data
            Insights" in production, or "DEBUG_UnitTest_*_<id>" when invoked
            by run_tests.py / debug_deploy.py against a staged copy).
        item_type: Item type — must be "SemanticModel" or this is a no-op.
        context: DeploymentContext (forwarded to sub-ops).
        workspace: FabricWorkspace (forwarded to sub-ops; pre-process runs
            before workspace exists, so this is typically None).
        item_directory: Path to the per-model directory. Required.
        source_model_name: When `item_name` is a staged throwaway, this carries
            the original display name so slug resolution finds the real overlay
            dir. Production deploy leaves this None (slug derived from item_name).
    """
    if item_type != "SemanticModel":
        return

    if not item_directory:
        msg = "setup_askadia_framework: item_directory is required"
        raise ValueError(msg)

    slug_source = source_model_name or item_name
    overlay_dir = resolve_overlay_dir(slug_source)
    if not overlay_dir.exists():
        print(
            f"      [SKIP] setup_askadia_framework: no overlay dir at "
            f"{overlay_dir} ({slug_source!r} not bootstrapped)"
        )
        return

    readme = overlay_dir / "README.md"
    if not readme.exists():
        msg = (
            f"setup_askadia_framework: overlay dir exists but README.md is missing: "
            f"{readme}. Add a README to confirm intentional bootstrap, or delete the dir."
        )
        raise RuntimeError(msg)

    # Single activation gate: a UDF-bootstrapped model must also carry an
    # instruction set (instructions/models/<slug>/model.json). Couple them and
    # fail loud so a model can't deploy UDFs while silently skipping
    # _COPILOT_INSTRUCTIONS.
    slug = resolve_model_slug(slug_source)
    model_json = instruction_model_json(slug)
    if not model_json.exists():
        msg = (
            f"setup_askadia_framework: model {slug_source!r} is UDF-bootstrapped "
            f"({overlay_dir}) but has no instruction set at {model_json}. Add a "
            f"canonical model.json (instructions), or remove the UDF overlay dir."
        )
        raise RuntimeError(msg)

    for label, fn, extra in _STEPS:
        print(f"   ---- setup_askadia_framework: {label} ----")
        fn(
            item_name=item_name,
            item_type=item_type,
            context=context,
            workspace=workspace,
            item_directory=item_directory,
            source_model_name=source_model_name,
            **extra,
        )
