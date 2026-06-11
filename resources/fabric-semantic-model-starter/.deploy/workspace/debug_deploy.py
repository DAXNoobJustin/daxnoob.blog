r"""
Developer-facing entry point: stage <Model> as DEBUG_<ENV>_<Model>_<user>,
deploy to HelixFabric-Insights[Dev] with the full prod preprocess chain, bind
the env-matching connections, and refresh.

Always publishes to the dev workspace you pass via ``--workspace-id`` regardless
of --environment (sandboxed: we never write to test/prod Insights).

The --environment flag controls TWO things:
  1. parameter.yml find/replace values applied to the staged model's TMDL
     (so test/prod storage IDs get rewritten on the way in).
  2. Which environment's connection IDs are bound to the staged model. IDs are
     read from .deploy/workspace/configs/env_connection_ids.json and bound by
     ID -- no cross-workspace reads, the publishing identity only needs 'Use'
     permission on the connection objects. So a Main-feature / unit-test run can
     deploy to dev Insights but bind prod connections to read real prod data.
     (See lib/connections.py.)

Branch detection (when --environment is omitted) uses git merge-base distance
against origin/Develop|Test|Main; see lib/branch_env.py.

Published model name is `DEBUG_<ENV>_<SluggedModelName>_<username>`. The
env + username suffixes prevent collision when multiple developers (or per-env
runs) test the same source model concurrently, while staying stable across
re-runs by the same user (so a single developer's iterate-deploy-query loop is
idempotent).

Usage:
  python .deploy/workspace/debug_deploy.py \\
      --model-name "Azure Data Insights" \\       # required
      --workspace-id <dev_insights_ws_id>         # required

Optional:
  --environment dev|test|prod  (default: branch-detected)
  --refresh-type Calculate|Full|None  (default: Calculate)
  --interactive                (browser auth instead of AzureCli)
  --keep-staged                (skip cleanup of staged temp dir)

Exit codes: 0 = success, 1 = pipeline/bind/refresh failure, 2 = bad input.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from fabric_cicd import FabricWorkspace, publish_all_items

_DEPLOY_WORKSPACE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _DEPLOY_WORKSPACE_DIR.parent.parent
# debug_deploy.py lives at .deploy/workspace/debug_deploy.py. process_orchestrator
# is a sibling and lib/ is a sibling package; both resolve once .deploy/workspace/
# is on sys.path (Python adds the script dir automatically when invoked as a
# script, but we add it explicitly so `python -m` invocations work too).
if str(_DEPLOY_WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_WORKSPACE_DIR))

from lib import branch_env, connections, fabric_api, refresh, staging, workspace_config
from lib.auth import DEFAULT_FABRIC_API, Auth
from process_orchestrator import (
    DeploymentAbortError,
    DeploymentContext,
    DeploymentPipeline,
    load_workspace_config,
)

# --- Hardcoded targets --------------------------------------------------------

# debug_deploy ALWAYS publishes to the dev workspace passed via --workspace-id;
# the --environment flag only swaps which env's parameter.yml replace_values are
# applied during fabric_cicd publish.
_INSIGHTS_WORKSPACE_KEY = "HelixFabric-Insights"
# Cosmetic label used in pipeline header prints. Doesn't affect any path
# resolution because we always pass repository_directory=<temp dir>.
_DEV_INSIGHTS_DIRECTORY_NAME = "HelixFabric-Insights"

# Source TMDL + config locations (Insights workload, the only one currently
# bootstrapped for the AskADIA UDF framework).
_SOURCE_WORKSPACE_DIR = _REPO_ROOT / "workspace" / "HelixFabric-Insights"
_PARAMETER_YML = _SOURCE_WORKSPACE_DIR / "parameter.yml"
_WORKSPACE_CONFIG = _DEPLOY_WORKSPACE_DIR / "configs" / "HelixFabric-Insights.yml"
_SHARED_CONFIG = _DEPLOY_WORKSPACE_DIR / "configs" / "shared.yml"

# Endpoints. Public Fabric/Power BI API hosts (see auth.py defaults).
# The TE2 wrapper builds the full XMLA URI from the bare host below.
_FABRIC_API_URL = DEFAULT_FABRIC_API
_XMLA_ENDPOINT_HOST = "api.powerbi.com"

_MODEL_PREFIX = "DEBUG_"

# Same regex `slug_model_name` uses, applied here so we can distinguish
# "user provided no usable identifier" from "slug had real content".
_USER_TAG_STRIP = re.compile(r"[^A-Za-z0-9]")


def _resolve_user_tag() -> str:
    """
    Derive a per-user suffix so concurrent developers don't collide.

    Reads USERNAME (Windows) or USER (POSIX) and strips it to alphanumerics
    so the suffix is XMLA-safe. Falls back to "user" if the env var is unset
    OR yields no alphanumeric chars (e.g. some CI contexts -- though
    debug_deploy is intended for local developer use, not CI).
    """
    raw = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    cleaned = _USER_TAG_STRIP.sub("", raw)
    return cleaned or "user"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model-name",
        required=True,
        help='Source semantic model display name (e.g. "Azure Data Insights").',
    )
    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Dev sandbox Fabric workspace ID to publish the DEBUG_* model to.",
    )
    parser.add_argument(
        "--environment",
        choices=tuple(workspace_config.ENV_TO_KEY),
        default=None,
        help=(
            "Override branch-detected environment. Controls (a) which env's "
            "parameter.yml replace_values are applied to the staged TMDL and "
            "(b) which Insights workspace we bind connections from. "
            "Always publishes to HelixFabric-Insights[Dev]; for env=test/prod "
            "you need read access to the upstream Insights workspace and "
            "storage for bind+refresh to succeed."
        ),
    )
    parser.add_argument(
        "--refresh-type",
        choices=("Calculate", "Full", "None"),
        default="Calculate",
        help="Refresh type after publish (default: Calculate). Use None to skip.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Use InteractiveBrowserCredential instead of AzureCliCredential.",
    )
    parser.add_argument(
        "--keep-staged",
        action="store_true",
        help="Skip cleanup of the staged temp directory (debugging).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Stage source TMDL → publish DEBUG_<ENV>_<Slug>_<user> → bind → refresh.

    Returns 0 on success, 1 on pipeline / bind / refresh failure, 2 on
    bad input (missing source model directory).
    """
    args = _parse_args(argv)

    # 1. Resolve environment
    env = args.environment or branch_env.resolve_environment(branch_env.get_upstream_branch())
    print(f"==> Environment: {env}  (drives parameter.yml find/replace + connection IDs to bind)")

    # Always publish to the dev sandbox workspace regardless of env.
    # parameter.yml handles per-env storage-ID rewriting at fabric_cicd publish.
    target_workspace_id = args.workspace_id
    print(f"==> Publish target: dev sandbox -> {target_workspace_id}")

    # 2. Auth
    auth = Auth(interactive=args.interactive)
    auth.warm()

    # 3. Compute staged name + locate source TMDL.
    # Name shape: DEBUG_<ENV>_<Slug>_<user>. Env in the name lets per-env
    # debug models coexist (DEBUG_DEV_AzureDataInsights_alice and
    # DEBUG_PROD_AzureDataInsights_alice are distinct items), avoiding the
    # state-pollution issue where switching --environment for the same
    # staged model leaves stale connections that don't match new TMDL.
    user_tag = _resolve_user_tag()
    staged_name = (
        f"{_MODEL_PREFIX}{env.upper()}_{staging.slug_model_name(args.model_name)}_{user_tag}"
    )
    source_model_dir = _SOURCE_WORKSPACE_DIR / f"{args.model_name}.SemanticModel"
    if not source_model_dir.exists():
        print(f"[ERROR] Source model not found: {source_model_dir}", file=sys.stderr)
        return 2
    print(f"==> Staged name: {staged_name}  (user tag: {user_tag})")

    # 4. Stage TMDL into temp repo
    tmp = Path(tempfile.mkdtemp(prefix="debug_deploy_"))
    print(f"==> Temp repo: {tmp}")

    try:
        staging.stage_model(
            source_dir=source_model_dir,
            model_name=staged_name,
            output_dir=tmp,
            strip_rls=False,
        )

        # 5. Copy parameter.yml so FabricWorkspace's find/replace fires for env
        shutil.copy2(_PARAMETER_YML, tmp / "parameter.yml")

        # 6. Load + merge YAML config; patch in-memory
        shared_cfg = load_workspace_config(_SHARED_CONFIG) or {}
        ws_cfg = load_workspace_config(_WORKSPACE_CONFIG) or {}
        config = {**shared_cfg, **ws_cfg}
        staging.patch_workspace_config_for_staged_model(
            config,
            source_model_name=args.model_name,
        )

        # 7. Build DeploymentContext targeting Dev Insights with our temp repo.
        # fabric_api_root scopes the fabric_cicd DEFAULT_API_ROOT_URL mutation
        # to the publish call (vs. permanently mutating the module global).
        ctx = DeploymentContext(
            workspace_id=target_workspace_id,
            workspace_directory_name=_DEV_INSIGHTS_DIRECTORY_NAME,
            environment=env,
            release_type="default",
            item_type_in_scope=["SemanticModel"],
            token_credential=auth.cred,
            fabric_api_url=_FABRIC_API_URL,
            xmla_endpoint=_XMLA_ENDPOINT_HOST,
            repository_directory=str(tmp),
        )

        # 8. Run pipeline. unpublish is a no-op: orphan cleanup against
        # Dev Insights would wipe the source "Azure Data Insights" model
        # and every other unmanaged item. The ^DEBUG.* exclude regex in
        # deploy_workspace.py protects FUTURE prod deploys from removing OUR
        # debug models -- it doesn't help us in the other direction.
        pipeline = DeploymentPipeline(ctx, config)
        try:
            with fabric_api.fabric_api_root(_FABRIC_API_URL):
                pipeline.run(
                    create_workspace=lambda: FabricWorkspace(
                        workspace_id=target_workspace_id,
                        environment=env,
                        repository_directory=str(tmp),
                        item_type_in_scope=["SemanticModel"],
                        token_credential=auth.cred,
                    ),
                    publish=lambda ws, ex: publish_all_items(ws, item_name_exclude_regex=ex),
                    unpublish=lambda ws: None,  # noqa: ARG005
                )
        except DeploymentAbortError as e:
            print(f"\n[ABORT] {e}", file=sys.stderr)
            return 1

        # 9. Resolve target ID + bind explicit env-mapped connections.
        # We bind connection IDs that we source-control in
        # .deploy/workspace/configs/env_connection_ids.json (env-keyed).
        # Sidesteps cross-workspace read perms: the SP only needs 'Use' on
        # the connection objects (which it has for every env's connections),
        # not read access on the upstream Insights workspace.
        target_id = connections.resolve_item_id(
            fabric_api=_FABRIC_API_URL,
            workspace_id=target_workspace_id,
            display_name=staged_name,
            item_type="SemanticModel",
            auth=auth,
        )
        if not target_id:
            print(
                f"[ERROR] Published model '{staged_name}' not found in target workspace",
                file=sys.stderr,
            )
            return 1

        connection_ids = connections.load_env_connection_ids(
            repo_root=_REPO_ROOT,
            workspace_dir_name=_INSIGHTS_WORKSPACE_KEY,
            source_model=args.model_name,
            env=env,
        )
        bound = connections.bind_explicit_connections(
            fabric_api=_FABRIC_API_URL,
            target_workspace_id=target_workspace_id,
            target_model_id=target_id,
            connection_ids=connection_ids,
            auth=auth,
        )
        print(f"==> Bound {bound} connection(s) ({env})")

        # 10. Refresh (skip if None). Use REST so preview-only TMDL metadata
        # does not require the current TE2 parser to understand the live model.
        if args.refresh_type != "None":
            print(f"==> Refreshing ({args.refresh_type})")
            refresh.refresh_model(
                model_name=staged_name,
                workspace_id=target_workspace_id,
                fabric_api=_FABRIC_API_URL,
                xmla_endpoint=_XMLA_ENDPOINT_HOST,
                auth=auth,
                refresh_type=args.refresh_type,
                dataset_id=target_id,
                rest_only=True,
            )

        url = (
            f"https://app.powerbi.com/groups/{target_workspace_id}"
            f"/datasets/{target_id}"
        )
        print(f"\n==> Deployed: {url}")
        return 0

    finally:
        if args.keep_staged:
            print(f"==> Staged dir kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
