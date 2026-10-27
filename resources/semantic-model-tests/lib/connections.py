"""
Fabric item lookup, connection binding, and teardown over the Fabric REST API.

A freshly-published copy of a DirectLake model has no bound data connections, so
a refresh against it fails until you bind them. Binding by explicit connection ID
avoids any cross-workspace read: the caller only needs 'Use' permission on each
connection object, which is a much smaller grant than workspace read on the
upstream lakehouse.
"""

from __future__ import annotations

import time

import requests

from .auth import FABRIC_SCOPE, Auth


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
        r = request_with_retry("GET", base_url, headers=auth.headers(FABRIC_SCOPE), params=params)
        r.raise_for_status()
        body = r.json()
        for item in body.get("value", []):
            if item.get("displayName") == display_name:
                return item["id"]
        token = body.get("continuationToken")
        if not token:
            return None
        params = {"continuationToken": token}


def _get_connection(*, connection_id: str, fabric_api: str, auth: Auth) -> dict:
    """GET /v1/connections/{id}. Requires only 'Use' permission on the connection."""
    url = f"{fabric_api}/v1/connections/{connection_id}"
    r = request_with_retry("GET", url, headers=auth.headers(FABRIC_SCOPE))
    r.raise_for_status()
    return r.json()


def bind_connections(
    *,
    fabric_api: str,
    workspace_id: str,
    model_id: str,
    connection_ids: list[str],
    auth: Auth,
) -> int:
    """
    Bind a known list of connection IDs to a semantic model.

    Strict by design: any failure raises. A silent skip would mask a bind
    regression and resurface later as an opaque "the model returned no data".

    Returns:
        The number of connections bound.

    Raises:
        RuntimeError: If any connection ID cannot be fetched or bound.
    """
    bind_url = f"{fabric_api}/v1/workspaces/{workspace_id}/semanticModels/{model_id}/bindConnection"
    bound = 0
    for connection_id in connection_ids:
        try:
            conn = _get_connection(connection_id=connection_id, fabric_api=fabric_api, auth=auth)
        except requests.HTTPError as exc:
            msg = (
                f"Failed to GET connection {connection_id}: {exc}. "
                f"Verify the caller has 'Use' permission on this connection."
            )
            raise RuntimeError(msg) from exc

        details = conn.get("connectionDetails") or {}
        payload = {
            "connectionBinding": {
                "id": connection_id,
                "connectivityType": conn.get("connectivityType"),
                "connectionDetails": {"type": details.get("type"), "path": details.get("path")},
            }
        }
        br = request_with_retry(
            "POST", bind_url, headers=auth.headers(FABRIC_SCOPE), json_body=payload,
        )
        if not br.ok:
            msg = (
                f"Failed to bind connection {connection_id} to model {model_id}: "
                f"HTTP {br.status_code} {br.text[:300]}"
            )
            raise RuntimeError(msg)
        bound += 1
        print(f"    bound connection {connection_id} ({details.get('type', '?')})")
    return bound


def delete_model(*, fabric_api: str, workspace_id: str, model_id: str, auth: Auth) -> bool:
    """DELETE a semantic model. Returns True on success."""
    url = f"{fabric_api}/v1/workspaces/{workspace_id}/semanticModels/{model_id}"
    r = request_with_retry("DELETE", url, headers=auth.headers(FABRIC_SCOPE))
    return r.ok
