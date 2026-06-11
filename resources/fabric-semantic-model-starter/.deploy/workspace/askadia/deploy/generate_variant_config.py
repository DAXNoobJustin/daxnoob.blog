"""Generate _COPILOT_VARIANT_CONFIG rows from shared askadia_config.json."""

from pathlib import Path

from paths import ASKADIA_CONFIG_JSON, TABULAR_SCRIPTS_DIR
from run_tabular_editor import run_model_script

SHARED_ASKADIA_CONFIG_PATH = ASKADIA_CONFIG_JSON
CSX_SCRIPT_PATH = str(TABULAR_SCRIPTS_DIR / "generateVariantConfig.csx")


def generate_variant_config(
    item_name,
    item_type="SemanticModel",
    context=None,
    workspace=None,
    item_directory=None,
    *,
    source_model_name=None,  # noqa: ARG001 - accepted for setup_askadia_framework compat
    **kwargs,  # noqa: ARG001 - tolerate future YAML params
):
    """Populate _COPILOT_VARIANT_CONFIG partition rows from shared AskADIA config."""
    if item_directory is None:
        if context is None or context.repository_directory is None:
            msg = "generate_variant_config requires either item_directory or context.repository_directory"
            raise ValueError(msg)
        item_directory = Path(context.repository_directory) / f"{item_name}.{item_type}"

    item_directory = Path(item_directory)

    if not SHARED_ASKADIA_CONFIG_PATH.exists():
        print(
            f"      Skipping variant config codegen - no shared askadia_config.json "
            f"at {SHARED_ASKADIA_CONFIG_PATH}"
        )
        return

    print(f"      Generating _COPILOT_VARIANT_CONFIG rows for {item_name} from {SHARED_ASKADIA_CONFIG_PATH.name}")

    run_model_script(
        item_name=item_name,
        item_type=item_type,
        context=context,
        workspace=workspace,
        item_directory=item_directory,
        script_path=CSX_SCRIPT_PATH,
        env_vars={"ASKADIA_CONFIG_JSON": str(SHARED_ASKADIA_CONFIG_PATH.resolve())},
    )
