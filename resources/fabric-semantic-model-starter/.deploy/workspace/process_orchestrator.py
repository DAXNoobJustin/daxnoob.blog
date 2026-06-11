"""Orchestration logic for pre/post-processing deployment operations."""

import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Ensure operations directory is importable (host-owned deploy-engine ops).
_operations_dir = str(Path(__file__).parent / "operations")
if _operations_dir not in sys.path:
    sys.path.insert(0, _operations_dir)

# The self-contained AskADIA framework package lives under askadia/deploy/.
# Its ops import each other (and the host TE runner) as flat modules, so put the
# package dir on sys.path and register only its single public entry point,
# setup_askadia_framework. The framework's sub-ops (merge_shared_scaffold,
# generate_copilot_*, generate_*_config, model_overlay) are private steps of that
# bundle and are not registered as host operations.
_askadia_deploy_dir = str(Path(__file__).parent / "askadia" / "deploy")
if _askadia_deploy_dir not in sys.path:
    sys.path.insert(0, _askadia_deploy_dir)

from generate_copilot_schema import generate_copilot_schema  # noqa: E402
from refresh_model_rest import refresh_model_rest  # noqa: E402
from run_tabular_editor import run_model_script  # noqa: E402
from setup_askadia_framework import setup_askadia_framework  # noqa: E402
from validate_item import validate_item  # noqa: E402

OPERATIONS = {
    "validate_item": validate_item,
    "refresh_model_rest": refresh_model_rest,
    "run_model_script": run_model_script,
    "generate_copilot_schema": generate_copilot_schema,
    "setup_askadia_framework": setup_askadia_framework,
}


def _get_operation(name):
    """Get an operation function by name."""
    if name not in OPERATIONS:
        available = ", ".join(sorted(OPERATIONS.keys()))
        raise KeyError(f"Operation '{name}' not found. Available: {available}")
    return OPERATIONS[name]


class DeploymentAbortError(Exception):
    """Raised when an operation fails with failure_mode='abort'."""


@dataclass
class DeploymentContext:
    """Deployment parameters passed to all operations."""

    workspace_id: str
    workspace_directory_name: str
    environment: str
    release_type: str
    item_type_in_scope: list
    token_credential: Any
    fabric_api_url: str
    xmla_endpoint: str
    repository_directory: str = None
    failed_items: list = field(default_factory=list)
    workspace: Any = None  # FabricWorkspace instance, populated after publish


def load_workspace_config(config_path):
    """Load workspace configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        return None
    with config_file.open() as f:
        return yaml.safe_load(f)


class DeploymentPipeline:
    """Orchestrates pre-process -> publish -> post-process.

    Operations receive: (item_name, item_type, context, workspace=None, **yaml_params)
    """

    def __init__(self, context: DeploymentContext, workspace_config: dict):
        self.context = context
        self.config = workspace_config or {}

    def run(self, create_workspace, publish, unpublish):
        """Execute the full pipeline: pre-process -> publish -> post-process."""
        # Phase 1: Pre-process (workspace not yet available)
        self._run_phase("pre_process")

        # Phase 2: Create workspace & publish
        exclude_pattern = self._build_exclude_pattern()
        workspace = create_workspace()
        self.context.workspace = workspace

        publish(workspace, exclude_pattern)
        unpublish(workspace)

        # Phase 3: Post-process (workspace now available to operations)
        self._run_phase("post_process")

    def _run_phase(self, phase: str):
        """Execute all operations for a given phase."""
        phase_label = phase.replace("_", "-").upper()
        print(f"\n{'=' * 100}")
        print(f"{phase_label}: {self.context.workspace_directory_name}")
        print(f"{'=' * 100}\n")

        items = self._discover_items()
        type_config = self._get_orchestration_config()
        skip_items = self.context.failed_items if phase == "post_process" else []

        for item_full_name, item_dir in items:
            if phase == "post_process" and item_full_name in skip_items:
                print(f"  [SKIP] {item_full_name} (failed pre-processing)")
                continue

            print(f"\n  {item_full_name}")

            item_type = item_full_name.split(".")[-1]
            item_name = ".".join(item_full_name.split(".")[:-1])

            operations = []
            if item_type in type_config:
                operations = type_config[item_type].get(phase, [])

            if not operations:
                continue

            self._execute_item_operations(phase, item_full_name, item_name, item_type, operations, item_dir)

        print(f"\n{'=' * 100}")
        print(f"{phase_label} COMPLETE")
        print(f"{'=' * 100}\n")

    def _execute_item_operations(self, phase, item_full_name, item_name, item_type, operations, item_dir):
        """Run each operation for a single item, respecting failure modes."""
        for op_config in operations:
            op_name = op_config["operation"]
            failure_mode = op_config.get("failure_mode", "abort")
            op_params = {k: v for k, v in op_config.items() if k not in ("operation", "failure_mode")}

            print(f"    {op_name}")

            try:
                op_func = _get_operation(op_name)
                op_func(
                    item_name=item_name,
                    item_type=item_type,
                    context=self.context,
                    workspace=self.context.workspace,
                    item_directory=str(item_dir) if item_dir else None,
                    **op_params,
                )
            except Exception as e:
                if failure_mode == "continue":
                    print(f"      [WARN] {e}")
                elif failure_mode == "skip":
                    print(f"      [ERROR] {e}")
                    if phase == "pre_process":
                        self.context.failed_items.append(item_full_name)
                    return  # Skip remaining operations for this item
                else:  # abort
                    print(f"      [FATAL] {e}")
                    traceback.print_exc()
                    raise DeploymentAbortError(f"Operation '{op_name}' failed for {item_full_name}: {e}") from e

    def _discover_items(self) -> list[tuple[str, Path | None]]:
        """Find items from config or by scanning the workspace directory."""
        config_items = self.config.get("items", [])
        if config_items:
            return [(item["name"], None) for item in config_items]

        exclude_items = set(self.config.get("exclude_items", []))
        items = []
        workspace_dir = self._get_workspace_dir()

        if workspace_dir.exists():
            for platform_file in sorted(workspace_dir.rglob(".platform")):
                item_dir = platform_file.parent
                if "." in item_dir.name:
                    item_type = item_dir.name.split(".")[-1]
                    if not self.context.item_type_in_scope or item_type in self.context.item_type_in_scope:
                        if item_dir.name in exclude_items:
                            print(f"  [EXCLUDE] {item_dir.name} (config)")
                        else:
                            items.append((item_dir.name, item_dir))

        return items

    def _get_workspace_dir(self) -> Path:
        """Resolve the workspace directory path."""
        if self.context.repository_directory:
            return Path(self.context.repository_directory)
        return Path(__file__).resolve().parent.parent.parent / "workspace" / self.context.workspace_directory_name

    def _get_orchestration_config(self) -> dict:
        """Get orchestration config for current release type, falling back to default."""
        orchestration = self.config.get("orchestration", {})
        env_key = self.context.release_type.lower() if self.context.release_type else "default"

        config = orchestration.get(env_key)
        if not config:
            config = orchestration.get("default", {})
            if self.context.release_type:
                print(f"  [INFO] No specific orchestration for '{self.context.release_type}', using defaults")

        return config

    def _build_exclude_pattern(self) -> str | None:
        """Build regex to exclude failed and config-excluded items from publishing."""
        config_excludes = self.config.get("exclude_items", [])
        config_names = [".".join(item.split(".")[:-1]) for item in config_excludes]
        failed_names = [".".join(item.split(".")[:-1]) for item in self.context.failed_items]
        all_excluded = config_names + failed_names
        if not all_excluded:
            return None
        return f"^({'|'.join(re.escape(name) for name in all_excluded)})$"
