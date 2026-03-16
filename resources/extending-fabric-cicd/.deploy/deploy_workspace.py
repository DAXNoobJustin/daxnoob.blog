"""Deploy a Fabric workspace with pre/post-processing operations."""

import argparse
from pathlib import Path

from azure.identity import AzureCliCredential, InteractiveBrowserCredential
from fabric_cicd import FabricWorkspace, publish_all_items
from process_orchestrator import DeploymentContext, DeploymentPipeline, load_config

parser = argparse.ArgumentParser()
parser.add_argument("--workspace_id", required=True)
parser.add_argument("--workspace_directory_name", required=True)
parser.add_argument("--item_type_in_scope", nargs="+", required=True)
parser.add_argument("--interactive", action="store_true", help="Use browser auth instead of Azure CLI")
args = parser.parse_args()

root = Path(__file__).resolve().parent.parent
repository_directory = str(root / args.workspace_directory_name)

token_credential = InteractiveBrowserCredential() if args.interactive else AzureCliCredential()

config = load_config(Path(__file__).parent / "configs" / f"{args.workspace_directory_name}.yml")

context = DeploymentContext(
    workspace_id=args.workspace_id,
    repository_directory=repository_directory,
    token_credential=token_credential,
    item_type_in_scope=args.item_type_in_scope,
)

pipeline = DeploymentPipeline(context, config)
pipeline.run(
    create_workspace=lambda: FabricWorkspace(
        workspace_id=args.workspace_id,
        repository_directory=repository_directory,
        item_type_in_scope=args.item_type_in_scope,
        token_credential=token_credential,
    ),
    publish=lambda ws: publish_all_items(ws),
)
