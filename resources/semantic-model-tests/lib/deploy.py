"""
Publish a staged semantic model with fabric-cicd.

Writes a self-contained `config.yml` next to the staged model and hands it to
`fabric_cicd.deploy_with_config`. Two settings matter for a throwaway:

  - `unpublish.skip: true` -- without it, fabric-cicd treats every item in the
    workspace that isn't in the staging directory as an orphan and removes it.
    The staging dir holds exactly one model, so leaving this off would delete
    the rest of the workspace.
  - no post-deploy refresh -- the caller binds connections first, then refreshes
    explicitly. A DirectLake model published with no bound connections can't
    refresh yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def publish_staged_model(
    *,
    staging_dir: str | Path,
    workspace_id: str,
    fabric_api_root: str,
    token_credential: Any,
    environment: str = "dev",
) -> None:
    """
    Publish the semantic model staged in `staging_dir` into `workspace_id`.

    Args:
        staging_dir: Directory holding the staged `*.SemanticModel/` (becomes
            fabric-cicd's `repository_directory`). If it also contains a
            `parameter.yml`, that is wired in so find/replace runs.
        workspace_id: Target workspace to publish into.
        fabric_api_root: Fabric API root.
        token_credential: An azure-identity credential.
        environment: Selects which `parameter.yml` value set applies. Only
            meaningful when the staged model carries a parameter.yml.
    """
    from fabric_cicd import deploy_with_config

    staging_dir = Path(staging_dir)
    # fabric-cicd only parameterizes when a parameter.yml is present.
    parameter_line = '  parameter: "parameter.yml"\n' if (staging_dir / "parameter.yml").exists() else ""
    config_path = staging_dir / "config.yml"
    config_path.write_text(
        "core:\n"
        f'  workspace_id: "{workspace_id}"\n'
        '  repository_directory: "."\n'
        "  item_types_in_scope:\n"
        "    - SemanticModel\n"
        f"{parameter_line}"
        "constants:\n"
        f'  DEFAULT_API_ROOT_URL: "{fabric_api_root}"\n'
        "unpublish:\n"
        "  skip: true\n",
        encoding="utf-8",
    )
    deploy_with_config(
        config_file_path=str(config_path),
        environment=environment,
        token_credential=token_credential,
    )
