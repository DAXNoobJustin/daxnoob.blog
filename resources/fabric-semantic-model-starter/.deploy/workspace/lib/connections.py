"""
Bind connection IDs explicitly to a target semantic model.

Strategy: source-control connection IDs per environment in
.deploy/workspace/configs/env_connection_ids.json and bind them by ID.
No cross-workspace lookups -- the PR-validation service principal has 'Use'
permission on the connection objects (sufficient for bind + refresh through
them) but does NOT have read access on upstream Insights workspaces.

Consumed by:
  - .deploy/workspace/debug_deploy.py        (persistent DEBUG_<ENV>_*)
  - semantic_model_tests/run_tests.py        (throwaway DEBUG_UnitTest_<ENV>_*)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from .auth import FABRIC_SCOPE, Auth
from .workspace_config import ENV_TO_KEY

# Repo-root-relative path to the env -> connection-id config.
_ENV_CONNECTION_IDS_RELPATH = Path(".deploy/workspace/configs/env_connection_ids.json")


def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict,
    json_body: dict | None = None,
    params: dict | None = None,
    timeout: int = 120,
    retries: int = 3,
):
    """Retry on 429/5xx with exponential backoff. Don't retry 4xx."""
    for attempt in range(retries):
        r = requests.request(
            method, url, headers=headers, json=json_body, params=params, timeout=timeout,
        )
        if r.status_code < 500 and r.status_code != 429:
            return r
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5")))
            continue
        time.sleep(2**attempt * 2)
    return r


def resolve_item_id(
    *,
    fabric_api: str,
    workspace_id: str,
    display_name: str,
    item_type: str,
    auth: Auth,
) -> str | None:
    """Look up a Fabric item by display name + type. Returns None if missing."""
    base_url = f"{fabric_api}/v1/workspaces/{workspace_id}/items"
    params: dict[str, str] = {"type": item_type}
    while True:
        r = request_with_retry(
            "GET", base_url, headers=auth.headers(FABRIC_SCOPE), params=params,
        )
        r.raise_for_status()
        body = r.json()
        for item in body.get("value", []):
            if item.get("displayName") == display_name:
                return item["id"]
        token = body.get("continuationToken")
        if not token:
            return None
        params = {"continuationToken": token}


def load_env_connection_ids(
    *,
    repo_root: Path,
    workspace_dir_name: str,
    source_model: str,
    env: str,
) -> list[str]:
    """
    Load env-specific connection IDs from env_connection_ids.json.

    Args:
        repo_root: Path to the HelixData repo root.
        workspace_dir_name: e.g. "HelixFabric-Insights".
        source_model: Display name of the source model the throwaway
            mirrors (e.g. "Azure Data Insights").
        env: One of "dev", "test", "prod".

    Returns:
        Ordered list of connection ID strings to bind.

    Raises:
        FileNotFoundError: If the config file is missing.
        KeyError: If the workspace / model / env entry is missing.

    """
    env_key = ENV_TO_KEY.get(env)
    if not env_key:
        msg = f"Unknown env '{env}'; expected one of {sorted(ENV_TO_KEY)}"
        raise ValueError(msg)

    config_path = repo_root / _ENV_CONNECTION_IDS_RELPATH
    if not config_path.exists():
        msg = f"env_connection_ids.json not found at {config_path}"
        raise FileNotFoundError(msg)

    data = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        aliases = data[workspace_dir_name][source_model]["uses"]
    except KeyError as exc:
        available = {
            ws: list(models.keys())
            for ws, models in data.items()
            if isinstance(models, dict) and not ws.startswith("_")
        }
        msg = (
            f"env_connection_ids.json missing entry: "
            f"['{workspace_dir_name}']['{source_model}']['uses']. "
            f"Available models: {json.dumps(available, indent=2)}"
        )
        raise KeyError(msg) from exc

    if not isinstance(aliases, list) or not aliases:
        msg = (
            f"env_connection_ids.json [{workspace_dir_name}][{source_model}].uses "
            f"must be a non-empty list of alias names; got {aliases!r}"
        )
        raise ValueError(msg)

    connections_block = data.get("_connections", {})
    ids: list[str] = []
    for alias in aliases:
        try:
            cid = connections_block[alias][env_key]
        except KeyError as exc:
            msg = (
                f"env_connection_ids.json [{workspace_dir_name}][{source_model}] "
                f"references alias '{alias}' missing or with no '{env_key}' "
                f"entry under _connections. Available aliases: "
                f"{sorted(connections_block.keys())}"
            )
            raise KeyError(msg) from exc
        ids.append(cid)
    return ids


def _get_connection(
    *,
    connection_id: str,
    fabric_api: str,
    auth: Auth,
) -> dict:
    """
    GET /v1/connections/{id} -- returns the connection object.

    Requires 'Use' permission on the connection (which the PR-validation SP
    has even on prod connections it cannot otherwise read via workspace-list).
    """
    url = f"{fabric_api}/v1/connections/{connection_id}"
    r = request_with_retry("GET", url, headers=auth.headers(FABRIC_SCOPE))
    r.raise_for_status()
    return r.json()


def bind_explicit_connections(
    *,
    fabric_api: str,
    target_workspace_id: str,
    target_model_id: str,
    connection_ids: list[str],
    auth: Auth,
) -> int:
    """
    Bind a known list of connection IDs to a target semantic model.

    Sidesteps cross-workspace reads: just GET each connection by ID
    (requires 'Use' perm only, which our PR-validation SP holds for
    every env's connections) and POST bindConnection.

    Args:
        fabric_api: Fabric API root.
        target_workspace_id: Workspace containing the staged target model.
        target_model_id: SemanticModel id in `target_workspace_id`.
        connection_ids: Ordered list of connection IDs to bind, typically
            sourced from `load_env_connection_ids(...)`.
        auth: Auth instance for token acquisition.

    Returns:
        The number of connections successfully bound to the target.

    Raises:
        RuntimeError: If any connection ID cannot be fetched OR bound.
            (Strict by design -- silent skips would mask bind regressions.)

    """
    bind_url = f"{fabric_api}/v1/workspaces/{target_workspace_id}/semanticModels/{target_model_id}/bindConnection"
    bound = 0
    for connection_id in connection_ids:
        try:
            conn = _get_connection(connection_id=connection_id, fabric_api=fabric_api, auth=auth)
        except requests.HTTPError as exc:
            msg = (
                f"Failed to GET connection {connection_id}: {exc}. "
                f"Verify the SP has 'Use' permission on this connection."
            )
            raise RuntimeError(msg) from exc

        details = conn.get("connectionDetails") or {}
        payload = {
            "connectionBinding": {
                "id": connection_id,
                "connectivityType": conn.get("connectivityType"),
                "connectionDetails": {
                    "type": details.get("type"),
                    "path": details.get("path"),
                },
            }
        }
        br = request_with_retry(
            "POST", bind_url, headers=auth.headers(FABRIC_SCOPE), json_body=payload,
        )
        if not br.ok:
            msg = (
                f"Failed to bind connection {connection_id} to model "
                f"{target_model_id}: HTTP {br.status_code} {br.text[:300]}"
            )
            raise RuntimeError(msg)
        bound += 1
        print(f"    bound connection {connection_id} ({details.get('type', '?')})")
    return bound
