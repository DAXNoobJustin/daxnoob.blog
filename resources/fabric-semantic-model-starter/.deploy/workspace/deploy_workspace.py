"""Deploy workspace to Fabric."""

import argparse
import os
import sys
from pathlib import Path

import fabric_cicd.constants as constants
from azure.identity import AzureCliCredential, InteractiveBrowserCredential
from fabric_cicd import (
    FabricWorkspace,
    change_log_level,
    publish_all_items,
    unpublish_all_orphan_items,
)
from process_orchestrator import DeploymentAbortError, DeploymentContext, DeploymentPipeline, load_workspace_config

# Set up argument parser
parser = argparse.ArgumentParser(description="Deploy workspace to Fabric")
parser.add_argument("--workspace_id", type=str, required=True, help="Workspace ID")
parser.add_argument("--workspace_directory_name", type=str, required=True, help="Workspace Directory Name")
parser.add_argument("--item_type_in_scope", nargs="+", required=True, help="Item types in scope (list)")
parser.add_argument("--environment", type=str, required=True, help="Environment")
parser.add_argument("--release_type", type=str, required=True, help="Release Type (e.g., test/prod)")
parser.add_argument("--interactive", action="store_true", help="Use browser auth instead of Azure CLI")

args = parser.parse_args()

workspace_id = args.workspace_id
workspace_directory_name = args.workspace_directory_name
item_type_in_scope = args.item_type_in_scope
environment = args.environment.lower()
release_type = args.release_type

root_directory = Path(__file__).resolve().parent.parent.parent

repository_directory = str(root_directory / "workspace" / workspace_directory_name)

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True, write_through=True)
sys.stderr.reconfigure(line_buffering=True, write_through=True)

# Enable debugging if defined in Azure DevOps pipeline
if os.getenv("SYSTEM_DEBUG", "false").lower() == "true":
    change_log_level("DEBUG")

# Authenticate: browser for local dev, Azure CLI for pipelines
if args.interactive:
    token_credential = InteractiveBrowserCredential()
else:
    token_credential = AzureCliCredential()

constants.DEFAULT_API_ROOT_URL = "https://api.fabric.microsoft.com/"
xmla_endpoint = "api.powerbi.com"

configs_dir = Path(__file__).parent / "configs"
shared_config = load_workspace_config(configs_dir / "shared.yml") or {}
workspace_config = load_workspace_config(configs_dir / f"{workspace_directory_name}.yml") or {}

# Merge: shared provides defaults, workspace-specific overrides
config = {**shared_config, **workspace_config}

if "environment_configuration" in config:
    env_key = release_type.lower()
    env_config = config["environment_configuration"]

    def resolve_env_val(val):
        """Resolve value based on environment key."""
        return val.get(env_key, val.get("prod")) if isinstance(val, dict) else val

    if "DEFAULT_API_ROOT_URL" in env_config:
        constants.DEFAULT_API_ROOT_URL = resolve_env_val(env_config["DEFAULT_API_ROOT_URL"])

    if "XMLA_ENDPOINT" in env_config:
        xmla_endpoint = resolve_env_val(env_config["XMLA_ENDPOINT"])

context = DeploymentContext(
    workspace_id=workspace_id,
    workspace_directory_name=workspace_directory_name,
    environment=environment,
    release_type=release_type,
    item_type_in_scope=item_type_in_scope,
    token_credential=token_credential,
    fabric_api_url=constants.DEFAULT_API_ROOT_URL.rstrip("/"),
    xmla_endpoint=xmla_endpoint,
    repository_directory=repository_directory,
)

pipeline = DeploymentPipeline(context, config)

try:
    pipeline.run(
        create_workspace=lambda: FabricWorkspace(
            workspace_id=workspace_id,
            environment=environment,
            repository_directory=repository_directory,
            item_type_in_scope=item_type_in_scope,
            token_credential=token_credential,
        ),
        publish=lambda ws, ex: publish_all_items(ws, item_name_exclude_regex=ex),
        unpublish=lambda ws: unpublish_all_orphan_items(ws, item_name_exclude_regex=r"^DEBUG.*"),
    )
except DeploymentAbortError as e:
    print(f"\n[ABORT] {e}")
    sys.exit(1)
