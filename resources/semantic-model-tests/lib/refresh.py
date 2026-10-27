"""
Refresh a published semantic model via the Power BI Enhanced Refresh REST API.

Enhanced Refresh (rather than the plain refresh endpoint) because it returns an
operation to poll, so the caller can block until the refresh actually reaches a
terminal state instead of guessing.
"""

from __future__ import annotations

import contextlib
import time

import requests

from .auth import PBI_SCOPE, Auth

# Poll ceilings per refresh type. A Calculate on a freshly-published DirectLake
# model finishes in well under a minute -- there is no data load, the model reads
# from the lakehouse. A cold Full on an Import model is a different animal
# (minutes to tens of minutes), so it gets far more headroom.
_REST_POLL_TIMEOUTS_SEC = {
    "Calculate": 240,
    "ClearValues": 240,
    "Defragment": 240,
    "Full": 1200,
    "DataOnly": 1200,
    "Automatic": 1200,
}
_DEFAULT_REST_POLL_TIMEOUT_SEC = 600
_REFRESH_TYPES = {
    "automatic": "Automatic",
    "calculate": "Calculate",
    "clearvalues": "ClearValues",
    "dataonly": "DataOnly",
    "defragment": "Defragment",
    "full": "Full",
}


def _normalize_refresh_type(refresh_type: str) -> str:
    try:
        return _REFRESH_TYPES[refresh_type.lower()]
    except KeyError as exc:
        msg = (
            f"Invalid refresh_type '{refresh_type}'. "
            f"Must be one of: {', '.join(sorted(_REFRESH_TYPES.values()))}"
        )
        raise ValueError(msg) from exc


def _refresh_via_rest(
    *,
    dataset_id: str,
    workspace_id: str,
    fabric_api: str,
    auth: Auth,
    refresh_type: str,
    poll_timeout_sec: int,
    commit_mode: str = "transactional",
    retry_count: int = 0,
) -> None:
    """
    POST a refresh, then poll refresh history until it reaches a terminal status.

    Raises on terminal failure or on poll timeout. Callers should size the
    timeout for the refresh type; see `_REST_POLL_TIMEOUTS_SEC`.
    """
    refresh_type = _normalize_refresh_type(refresh_type)
    base = fabric_api.rstrip("/")
    url = f"{base}/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
    body = {"type": refresh_type, "commitMode": commit_mode, "retryCount": retry_count}
    r = requests.post(url, headers=auth.headers(PBI_SCOPE), json=body, timeout=60)
    if r.status_code != 202:
        r.raise_for_status()
        msg = f"Refresh POST returned unexpected status {r.status_code}"
        raise RuntimeError(msg)

    poll_url = r.headers.get("Location")
    if not poll_url:
        request_id = r.headers.get("x-ms-request-id")
        if request_id:
            poll_url = f"{url}/{request_id}"
    if not poll_url:
        msg = "Refresh accepted but response carried no Location or x-ms-request-id to poll"
        raise RuntimeError(msg)

    poll_interval_sec = 2
    max_attempts = max(1, poll_timeout_sec // poll_interval_sec)
    for _ in range(max_attempts):
        time.sleep(poll_interval_sec)
        pr = requests.get(poll_url, headers=auth.headers(PBI_SCOPE), timeout=30)
        if not pr.ok:
            continue
        status = pr.json().get("status")
        if status in ("Unknown", "InProgress", "NotStarted", None):
            continue
        if status == "Completed":
            return
        detail = (pr.json().get("serviceExceptionJson") or "")[:300]
        msg = f"Refresh failed: {status} -- {detail}"
        raise RuntimeError(msg)

    # Abandoning the poll does not stop the refresh server-side, so cancel it.
    with contextlib.suppress(requests.RequestException):
        requests.delete(poll_url, headers=auth.headers(PBI_SCOPE), timeout=30)
    msg = (
        f"Refresh ({refresh_type}) timed out after {poll_timeout_sec}s "
        f"({max_attempts} polls @ {poll_interval_sec}s)"
    )
    raise RuntimeError(msg)


def refresh_model(
    *,
    workspace_id: str,
    fabric_api: str,
    auth: Auth,
    dataset_id: str,
    refresh_type: str = "Calculate",
    poll_timeout_sec: int | None = None,
    commit_mode: str = "transactional",
    retry_count: int = 0,
) -> None:
    """
    Refresh the published semantic model `dataset_id` in `workspace_id`.

    Args:
        workspace_id: Fabric workspace ID.
        fabric_api: Fabric API root; it also serves the /v1.0/myorg Power BI surface.
        auth: Auth instance for token acquisition.
        dataset_id: The published semantic model's dataset ID.
        refresh_type: "Calculate", "Full", "Defragment", "ClearValues", "DataOnly"
            or "Automatic". Defaults to "Calculate" -- the cheapest, and all a
            DirectLake model needs to recompute calculated columns and measures.
        poll_timeout_sec: Override the poll ceiling. Defaults to a per-type lookup.
        commit_mode: "transactional" (all-or-nothing) or "partialBatch" (each
            command commits individually, so one failing table doesn't roll back
            the tables that succeeded).
        retry_count: Times the service retries the operation before failing.
    """
    refresh_type = _normalize_refresh_type(refresh_type)
    if not dataset_id:
        msg = "refresh requires dataset_id"
        raise RuntimeError(msg)
    timeout_sec = (
        poll_timeout_sec
        if poll_timeout_sec is not None
        else _REST_POLL_TIMEOUTS_SEC.get(refresh_type, _DEFAULT_REST_POLL_TIMEOUT_SEC)
    )
    print(f"    Refreshing ({refresh_type}/{commit_mode}, poll timeout {timeout_sec}s)")
    _refresh_via_rest(
        dataset_id=dataset_id,
        workspace_id=workspace_id,
        fabric_api=fabric_api,
        auth=auth,
        refresh_type=refresh_type,
        poll_timeout_sec=timeout_sec,
        commit_mode=commit_mode,
        retry_count=retry_count,
    )
