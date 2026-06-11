"""Tabular Editor operations for semantic models."""

from tabular_editor_utils import run_tabular_editor


def run_model_script(
    item_name,
    item_type="SemanticModel",
    context=None,
    workspace=None,  # noqa: ARG001
    script_path=None,
    env_vars=None,
    item_directory=None,
    **kwargs,  # noqa: ARG001
):
    """Execute C# script against local model definition"""
    result = run_tabular_editor(
        target="local",
        action="script",
        item_name=item_name,
        context=context,
        script_path=script_path,
        env_vars=env_vars,
        item_type=item_type,
        item_directory=item_directory,
    )

    if result.returncode != 0:
        msg = f"Script '{script_path}' failed with exit code {result.returncode}"
        raise RuntimeError(msg)
