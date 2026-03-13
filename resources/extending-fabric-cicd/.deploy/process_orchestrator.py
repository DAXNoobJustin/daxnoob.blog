"""Pipeline engine: discovers items, runs pre/post-process operations, publishes via fabric-cicd."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Ensure operations directory is importable
_operations_dir = str(Path(__file__).parent / "operations")
if _operations_dir not in sys.path:
    sys.path.insert(0, _operations_dir)

from tabular_editor import refresh_model, run_model_script  # noqa: E402

OPERATIONS = {
    "run_model_script": run_model_script,
    "refresh_model": refresh_model,
}


@dataclass
class DeploymentContext:
    """Parameters passed to every operation."""

    workspace_id: str
    repository_directory: str
    token_credential: Any
    item_type_in_scope: list = field(default_factory=list)
    fabric_api_url: str = "https://api.fabric.microsoft.com"
    xmla_endpoint: str = "api.powerbi.com"


class DeploymentPipeline:
    """Orchestrates pre-process -> publish -> post-process."""

    def __init__(self, context: DeploymentContext, config: dict):
        self.context = context
        self.config = config or {}

    def run(self, create_workspace, publish):
        self._run_phase("pre_process")

        workspace = create_workspace()
        publish(workspace)

        self._run_phase("post_process")

    def _run_phase(self, phase):
        label = phase.replace("_", "-").upper()
        print(f"\n{'=' * 60}\n{label}\n{'=' * 60}\n")

        orchestration = self.config.get("orchestration", {})

        for item_full_name, item_dir in self._discover_items():
            item_type = item_full_name.rsplit(".", 1)[-1]
            item_name = item_full_name.rsplit(".", 1)[0]
            operations = orchestration.get(item_type, {}).get(phase, [])

            if not operations:
                continue

            print(f"  {item_full_name}")
            for op in operations:
                op_name = op["operation"]
                failure_mode = op.get("failure_mode", "abort")
                params = {k: v for k, v in op.items() if k not in ("operation", "failure_mode")}

                print(f"    {op_name}")
                try:
                    OPERATIONS[op_name](
                        item_name=item_name,
                        item_type=item_type,
                        context=self.context,
                        item_directory=str(item_dir) if item_dir else None,
                        **params,
                    )
                except Exception as e:
                    if failure_mode == "continue":
                        print(f"      [WARN] {e}")
                    elif failure_mode == "skip":
                        print(f"      [SKIP] {e}")
                        return
                    else:
                        raise

    def _discover_items(self):
        """Find deployable items by scanning for .platform files."""
        items = []
        for pf in sorted(Path(self.context.repository_directory).rglob(".platform")):
            d = pf.parent
            if "." in d.name:
                item_type = d.name.rsplit(".", 1)[-1]
                if not self.context.item_type_in_scope or item_type in self.context.item_type_in_scope:
                    items.append((d.name, d))
        return items


def load_config(path):
    p = Path(path)
    if not p.exists():
        return {}
    with p.open() as f:
        return yaml.safe_load(f) or {}
