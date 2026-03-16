"""Run Tabular Editor scripts on local models (pre-process) and refresh published models (post-process)."""

import io
import os
import subprocess
import urllib.parse
import zipfile
from pathlib import Path

import requests

TE_URL = "https://github.com/TabularEditor/TabularEditor/releases/download/2.27.2/TabularEditor.Portable.zip"


def _repo_root():
    return Path(__file__).resolve().parent.parent.parent


def _ensure_te():
    exe = _repo_root() / "TabularEditor.exe"
    if not exe.exists():
        print("      Downloading Tabular Editor...")
        resp = requests.get(TE_URL, timeout=60)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(_repo_root())
    return str(exe)


def _run_te(connection, script_path, model_name=None, save_local=False, env_vars=None):
    exe = _ensure_te()
    script = str(_repo_root() / script_path)

    if model_name:
        cmd = [exe, connection, model_name, "-S", script, "-V"]
    else:
        cmd = [exe, connection, "-S", script] + (["-D"] if save_local else [])

    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result


def _xmla_connection(context):
    token = context.token_credential.get_token("https://api.fabric.microsoft.com/.default")
    resp = requests.get(
        f"{context.fabric_api_url}/v1/workspaces/{context.workspace_id}",
        headers={"Authorization": f"Bearer {token.token}"},
        timeout=30,
    )
    resp.raise_for_status()
    ws_name = urllib.parse.quote(resp.json()["displayName"])

    pbi_token = context.token_credential.get_token("https://analysis.windows.net/powerbi/api/.default")
    return f"Provider=MSOLAP;Data Source=powerbi://{context.xmla_endpoint}/v1.0/myorg/{ws_name};Password={pbi_token.token}"


# --- Operations (called by the orchestrator) ---


def run_model_script(item_name, item_type="SemanticModel", context=None,
                     script_path=None, env_vars=None, item_directory=None, **kwargs):
    """Run a C# script against the local model definition."""
    if item_directory:
        model_dir = str(Path(item_directory) / "definition")
    else:
        model_dir = str(Path(context.repository_directory) / f"{item_name}.{item_type}" / "definition")

    result = _run_te(model_dir, script_path, save_local=True, env_vars=env_vars)
    if result.returncode != 0:
        raise RuntimeError(f"Script failed (exit code {result.returncode})")


def refresh_model(item_name, context=None, refresh_type="calculate", **kwargs):
    """Refresh a published semantic model via XMLA."""
    connection = _xmla_connection(context)
    result = _run_te(
        connection, ".deploy/scripts/refreshModel.csx",
        model_name=item_name, env_vars={"RefreshType": refresh_type.capitalize()},
    )
    if result.returncode != 0:
        raise RuntimeError(f"Refresh failed ({refresh_type})")
