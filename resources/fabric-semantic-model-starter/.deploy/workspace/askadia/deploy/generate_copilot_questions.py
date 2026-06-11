"""Generate _COPILOT_QUESTIONS rows from per-model overlay copilot_questions.json.

Reads `<repo>/.deploy/workspace/askadia/udf/models/<slug>/copilot_questions.json`
(per-model question registry, JSON array of question objects with PascalCase
keys matching column names) and invokes generateCopilotQuestions.csx via TE2
to populate the _COPILOT_QUESTIONS table partition.

The slug is derived from the item display name via `model_overlay.resolve_model_slug`.

The table itself (column defs + FactName calc col + DATATABLE shell with a
_PLACEHOLDER row) is provided by the shared askadia scaffold and synced into
the per-model dir by merge_shared_scaffold. This op only replaces the
*partition expression* — never touches column defs.

Skips silently with INFO log if the overlay `copilot_questions.json` doesn't
exist (model is opt-in to the Copilot question framework — bare models keep
the placeholder skeleton, which is valid but empty).

Schema (15-column TMDL table = 13 fields per JSON row + FactName + Topic, the
last two as derived calc cols): see .deploy/workspace/askadia/udf/common/tables/_COPILOT_QUESTIONS.tmdl
and .deploy/workspace/askadia/deploy/tabular_scripts/generateCopilotQuestions.csx.
"""

from pathlib import Path

from model_overlay import resolve_overlay_questions_path
from paths import TABULAR_SCRIPTS_DIR
from run_tabular_editor import run_model_script

CSX_SCRIPT_PATH = str(TABULAR_SCRIPTS_DIR / "generateCopilotQuestions.csx")


def generate_copilot_questions(
    item_name,
    item_type="SemanticModel",
    context=None,
    workspace=None,
    item_directory=None,
    *,
    source_model_name=None,
    **kwargs,  # noqa: ARG001 — tolerate future YAML params
):
    """Populate _COPILOT_QUESTIONS partition rows from per-model overlay JSON registry.

    Args:
        item_name: Display name of the item as it appears on disk.
        item_type: Item type (defaults to "SemanticModel").
        context: DeploymentContext (used to derive item_directory if absent).
        workspace: FabricWorkspace (forwarded to run_model_script).
        item_directory: Path to the per-model directory.
        source_model_name: Source model name when ``item_name`` is a staged
            throwaway (e.g. ``DEBUG_UnitTest_*_<id>``). Used to resolve the
            overlay slug. Production deploy leaves this None and falls back
            to ``item_name``.
    """
    if item_directory is None:
        if context is None or context.repository_directory is None:
            msg = "generate_copilot_questions requires either item_directory or context.repository_directory"
            raise ValueError(msg)
        item_directory = Path(context.repository_directory) / f"{item_name}.{item_type}"

    item_directory = Path(item_directory)
    slug_source = source_model_name or item_name
    json_path = resolve_overlay_questions_path(slug_source)

    if not json_path.exists():
        print(
            f"      Skipping copilot questions codegen - no overlay copilot_questions.json "
            f"at {json_path}"
        )
        return

    print(f"      Generating _COPILOT_QUESTIONS rows for {item_name} from {json_path.name}")

    # Delegate to run_model_script — it uses -D so TE2 saves the mutated TMDL
    # back to disk. The CSX reads COPILOT_QUESTIONS_JSON env var to find the
    # per-model JSON file (YAML can't compute per-model paths statically).
    run_model_script(
        item_name=item_name,
        item_type=item_type,
        context=context,
        workspace=workspace,
        item_directory=item_directory,
        script_path=CSX_SCRIPT_PATH,
        env_vars={"COPILOT_QUESTIONS_JSON": str(json_path.resolve())},
    )
