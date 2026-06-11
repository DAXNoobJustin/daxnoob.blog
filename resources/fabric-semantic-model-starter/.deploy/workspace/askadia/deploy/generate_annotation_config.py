"""Generate _COPILOT_ANNOTATIONS_REGISTRY rows from shared askadia_config.json.

Reads the `annotationRegistry` section from
`<repo>/.deploy/workspace/askadia/udf/common/askadia_config.json` and invokes
generateAnnotationConfig.csx via TE2 to populate the
_COPILOT_ANNOTATIONS_REGISTRY table partition.

The registry drives the DiscoverColumns Tags + Behavior output columns: one
JSON row per (AnnotationKey, ObjectType, Surface) declares the literal string
to render when a column carries that annotation. Adding a new tag/behavior is
a one-row JSON edit + redeploy — no DAX changes required.

Unlike generate_copilot_questions (per-model overlay), this config is
framework-shared: every bootstrapped model gets the same registry rows. The
annotation contract is framework-wide, not a per-model decision. If a model
later needs a per-model override, this op can grow an overlay resolution
step.

The table itself (column defs + DATATABLE shell with a _PLACEHOLDER row) is
provided by the shared askadia scaffold
(.deploy/workspace/askadia/udf/common/tables/_COPILOT_ANNOTATIONS_REGISTRY.tmdl)
and synced into the per-model dir by merge_shared_scaffold. This op only
replaces the *partition expression* — never touches column defs.

Skips silently with INFO log if the shared askadia_config.json doesn't
exist (defensive — keeps the op safe to wire into setup_askadia_framework
even on branches that don't carry the JSON yet).
"""

from pathlib import Path

from paths import ASKADIA_CONFIG_JSON, TABULAR_SCRIPTS_DIR
from run_tabular_editor import run_model_script

SHARED_ASKADIA_CONFIG_PATH = ASKADIA_CONFIG_JSON
CSX_SCRIPT_PATH = str(TABULAR_SCRIPTS_DIR / "generateAnnotationConfig.csx")


def generate_annotation_config(
    item_name,
    item_type="SemanticModel",
    context=None,
    workspace=None,
    item_directory=None,
    *,
    source_model_name=None,  # noqa: ARG001 — accepted for setup_askadia_framework compat
    **kwargs,  # noqa: ARG001 — tolerate future YAML params
):
    """Populate _COPILOT_ANNOTATIONS_REGISTRY partition rows from the shared JSON config.

    Args:
        item_name: Display name of the item as it appears on disk.
        item_type: Item type (defaults to "SemanticModel").
        context: DeploymentContext (used to derive item_directory if absent).
        workspace: FabricWorkspace (forwarded to run_model_script).
        item_directory: Path to the per-model directory.
        source_model_name: Accepted for setup_askadia_framework compat; the
            shared config path is the same for every model so this is unused.
    """
    if item_directory is None:
        if context is None or context.repository_directory is None:
            msg = "generate_annotation_config requires either item_directory or context.repository_directory"
            raise ValueError(msg)
        item_directory = Path(context.repository_directory) / f"{item_name}.{item_type}"

    item_directory = Path(item_directory)

    if not SHARED_ASKADIA_CONFIG_PATH.exists():
        print(
            f"      Skipping annotation config codegen - no shared askadia_config.json "
            f"at {SHARED_ASKADIA_CONFIG_PATH}"
        )
        return

    print(
        f"      Generating _COPILOT_ANNOTATIONS_REGISTRY rows for {item_name} "
        f"from {SHARED_ASKADIA_CONFIG_PATH.name}"
    )

    # Delegate to run_model_script — it uses -D so TE2 saves the mutated TMDL
    # back to disk. The CSX reads ASKADIA_CONFIG_JSON env var to find the
    # shared JSON file (YAML can't compute repo-rooted paths statically).
    run_model_script(
        item_name=item_name,
        item_type=item_type,
        context=context,
        workspace=workspace,
        item_directory=item_directory,
        script_path=CSX_SCRIPT_PATH,
        env_vars={"ASKADIA_CONFIG_JSON": str(SHARED_ASKADIA_CONFIG_PATH.resolve())},
    )
