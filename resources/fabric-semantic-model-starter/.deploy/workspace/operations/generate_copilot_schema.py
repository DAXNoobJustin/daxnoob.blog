"""Generate Copilot schema.json from Tabular Model annotations"""

import json
import subprocess
from pathlib import Path

from tabular_editor_utils import ensure_tabular_editor, get_repository_root


def generate_copilot_schema(
    item_name,
    item_type="SemanticModel",
    context=None,
    workspace=None,  # noqa: ARG001
    item_directory=None,
    **kwargs,  # noqa: ARG001
):
    """Generate Copilot schema.json from model annotations"""
    print(f"      Generating Copilot schema.json for {item_name}")

    item_dir = Path(item_directory) if item_directory else Path(context.repository_directory) / f"{item_name}.{item_type}"
    model_path = item_dir / "definition"
    copilot_dir = item_dir / "Copilot"
    settings_path = copilot_dir / "settings.json"
    schema_path = copilot_dir / "schema.json"

    # Gate on the Copilot opt-in marker (settings.json), NOT on the generated
    # schema.json. schema.json is .gitignored (it is regenerated here from the
    # model's Copilot_* annotations), so it is absent on every clean CI
    # checkout — gating on it made this op always skip and never (re)generate,
    # leaving a stale/empty `{"tables": []}` schema deployed in the service.
    if not settings_path.exists():
        print(f"      Skipping - no Copilot/settings.json (model not opted into Copilot indexing) for {item_name}")
        return

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        msg = f"Failed to read Copilot/settings.json for {item_name}: {e}"
        raise RuntimeError(msg) from e

    if not settings.get("indexingEnabled"):
        print(f"      Skipping - Copilot indexing disabled (indexingEnabled is not true) for {item_name}")
        return

    root_dir = get_repository_root()
    script_path = root_dir / ".deploy" / "workspace" / "tabular_scripts" / "generateCopilotSchema.csx"

    if not script_path.exists():
        msg = f"Script not found: {script_path}"
        raise FileNotFoundError(msg)

    tabular_exe = ensure_tabular_editor()

    result = subprocess.run(
        [str(tabular_exe), str(model_path), "-S", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print(f"      stdout: {result.stdout}")
        print(f"      stderr: {result.stderr}")
        msg = "Failed to generate Copilot schema"
        raise RuntimeError(msg)

    # Extract JSON object from stdout (Tabular Editor Output() writes here)
    full_output = result.stdout
    schema_start = full_output.find("{")

    if schema_start == -1:
        print(f"      stdout: {full_output}")
        msg = "No JSON found in Tabular Editor output"
        raise RuntimeError(msg)

    # Find matching closing brace
    brace_count = 0
    for i, char in enumerate(full_output[schema_start:], start=schema_start):
        if char == "{":
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                schema_json = full_output[schema_start : i + 1]
                break
    else:
        msg = "Incomplete JSON in Tabular Editor output"
        raise RuntimeError(msg)

    schema_data = json.loads(schema_json)

    with open(schema_path, "w") as f:
        json.dump(schema_data, f, indent=2)

    print(f"      Successfully generated {schema_path}")
    print(f"      Tables: {len(schema_data.get('tables', []))}")
