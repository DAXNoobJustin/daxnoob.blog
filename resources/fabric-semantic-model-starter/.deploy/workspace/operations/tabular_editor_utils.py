"""Shared utilities for Tabular Editor operations"""

import io
import os
import subprocess
import urllib.parse
import zipfile
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


def get_repository_root():
    """Calculate repository root from operations directory"""
    return Path(__file__).resolve().parent.parent.parent.parent


def ensure_tabular_editor():
    """Ensure Tabular Editor CLI is available, download if not present.

    Sentinel checks BOTH TabularEditor.exe AND Microsoft.AnalysisServices.Tabular.dll
    (an AMO sidecar required for any -S xmla connection). A prior incident left an
    install with the .exe present but the AMO DLLs missing — `run_tabular_editor`
    failed with the misleading "Authentication failed for all authenticators" error
    instead of a clearer "AMO assembly missing" message. Re-running this function
    after deleting the partial install (or just letting the missing-DLL branch
    re-extract) restores a working install.
    """
    root_dir = get_repository_root()
    tabular_exe = root_dir / "TabularEditor.exe"
    amo_dll = root_dir / "Microsoft.AnalysisServices.Tabular.dll"

    if tabular_exe.exists() and amo_dll.exists():
        return str(tabular_exe)

    if tabular_exe.exists() and not amo_dll.exists():
        print("      TabularEditor.exe present but AMO sidecar DLL missing — re-extracting...")
    else:
        print("      Downloading Tabular Editor...")

    if not requests:
        msg = "requests library is required to download Tabular Editor"
        raise RuntimeError(msg)

    url = "https://github.com/TabularEditor/TabularEditor/releases/download/2.27.2/TabularEditor.Portable.zip"

    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            zip_file.extractall(root_dir)

        if not tabular_exe.exists():
            msg = "Tabular Editor download failed - executable not found after extraction"
            raise RuntimeError(msg)
        if not amo_dll.exists():
            msg = (
                "Tabular Editor download incomplete - AMO sidecar "
                "Microsoft.AnalysisServices.Tabular.dll not found after extraction. "
                "Re-running this op should re-trigger the extract."
            )
            raise RuntimeError(msg)

        print(f"      Tabular Editor downloaded successfully to {tabular_exe}")

    except Exception as e:
        msg = f"Failed to download Tabular Editor: {e}"
        raise RuntimeError(msg) from e

    return str(tabular_exe)


def get_model_path(item_name, context, item_type="SemanticModel", item_directory=None):
    """Get path to model definition file"""
    if item_directory:
        return Path(item_directory) / "definition" / "database.tmdl"
    return Path(context.repository_directory) / f"{item_name}.{item_type}" / "definition" / "database.tmdl"


def run_tabular_editor(
    target,
    action,
    item_name,
    context,
    script_path=None,
    env_vars=None,
    item_type="SemanticModel",
    item_directory=None,
):
    """Core Tabular Editor execution - all operations use this"""
    tabular_exe = ensure_tabular_editor()

    # Build connection string based on target
    if target == "local":
        model_path = get_model_path(item_name, context, item_type=item_type, item_directory=item_directory)

        # Point directly to the definition folder
        connection = str(model_path.parent)
        model_name = None
    elif target == "xmla":
        # Get workspace name from API using context
        token = context.token_credential.get_token("https://api.fabric.microsoft.com/.default")
        headers = {"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}
        response = requests.get(
            f"{context.fabric_api_url}/v1/workspaces/{context.workspace_id}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        workspace_name = response.json()["displayName"]

        # Get Power BI token and construct XMLA endpoint
        pbi_token = context.token_credential.get_token("https://analysis.windows.net/powerbi/api/.default")
        encoded_workspace = urllib.parse.quote(workspace_name)
        xmla_endpoint = f"powerbi://{context.xmla_endpoint}/v1.0/myorg/{encoded_workspace}"

        connection = f"Provider=MSOLAP;Data Source={xmla_endpoint};Password={pbi_token.token}"
        model_name = item_name
    else:
        msg = f"Invalid target '{target}'. Must be 'local' or 'xmla'"
        raise ValueError(msg)

    # Build command based on action
    if action == "bpa":
        cmd = [tabular_exe, connection, "-A"]
    elif action == "script":
        if not script_path:
            msg = "script_path is required for script action"
            raise ValueError(msg)

        root_dir = get_repository_root()
        # script_path may be repo-root-relative (general csx referenced from the
        # pipeline YAML) or already absolute (the AskADIA framework resolves its
        # own csx via paths.py). Honour an absolute path as-is.
        _script = Path(script_path)
        full_script_path = _script if _script.is_absolute() else root_dir / _script

        if not full_script_path.exists():
            msg = f"Script not found: {full_script_path}"
            raise FileNotFoundError(msg)

        if target == "xmla":
            cmd = [tabular_exe, connection, model_name, "-S", str(full_script_path), "-V"]
        else:
            # For local scripts, we want to save the changes back to the source
            # Use -D to save back to the connection path (the model definition folder)
            cmd = [tabular_exe, connection, "-S", str(full_script_path), "-D"]
    else:
        msg = f"Invalid action '{action}'. Must be 'bpa' or 'script'"
        raise ValueError(msg)

    # Set up environment variables
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    # Execute command
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)

    return result
