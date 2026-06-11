"""
Refresh a published semantic model: XMLA via Tabular Editor 2 or REST API.

XMLA-first remains available for existing flows. REST-only mode is used for
models that carry preview metadata unsupported by the current TE2 parser.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import requests

from .auth import PBI_SCOPE, Auth

# Path (repo-root-relative) to the CSX script TE2 runs over XMLA.
_REFRESH_CSX = ".deploy/workspace/tabular_scripts/refreshModel.csx"

# Default REST poll ceilings per refresh type. Calculate refreshes a structurally-
# only deployed throwaway DirectLake model in well under a minute; Full on a
# freshly-staged DirectLake model has historically taken 6-15 min cold. The
# 1200 s ceiling on Full leaves headroom for outliers without exceeding the
# pipeline job-level timeoutInMinutes cap.
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


def _get_te_xmla_runner():
    """Import run_tabular_editor from the deploy harness (already proven in pipeline)."""
    # refresh.py is at .deploy/workspace/lib/refresh.py; operations/ is a sibling
    # of lib/ under .deploy/workspace/.
    ops_dir = str(Path(__file__).resolve().parents[1] / "operations")
    if ops_dir not in sys.path:
        sys.path.insert(0, ops_dir)
    from tabular_editor_utils import run_tabular_editor  # type: ignore[import-untyped]
    return run_tabular_editor


def _refresh_via_rest(
    *,
    dataset_id: str,
    workspace_id: str,
    auth: Auth,
    refresh_type: str,
    poll_timeout_sec: int,
    commit_mode: str = "transactional",
    retry_count: int = 0,
) -> None:
    """
    Refresh via Power BI Enhanced Refresh REST API (works with interactive auth).

    Polls the refresh-history endpoint every 2 s until the operation reaches
    a terminal status, up to `poll_timeout_sec`. Raises on terminal failure
    or on poll-timeout (callers should size the timeout for the refresh
    type; see `_REST_POLL_TIMEOUTS_SEC`).
    """
    refresh_type = _normalize_refresh_type(refresh_type)
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
    body = {"type": refresh_type, "commitMode": commit_mode, "retryCount": retry_count}
    headers = auth.headers(PBI_SCOPE)
    r = requests.post(url, headers=headers, json=body, timeout=60)
    if r.status_code == 202:
        poll_url = r.headers.get("Location")
        if not poll_url:
            request_id = r.headers.get("x-ms-request-id")
            if request_id:
                poll_url = f"{url}/{request_id}"
        if not poll_url:
            msg = "REST refresh accepted but response did not include Location or x-ms-request-id"
            raise RuntimeError(msg)
        poll_interval_sec = 2
        max_attempts = max(1, poll_timeout_sec // poll_interval_sec)
        for _ in range(max_attempts):
            time.sleep(poll_interval_sec)
            pr = requests.get(poll_url, headers=auth.headers(PBI_SCOPE), timeout=30)
            if pr.ok:
                refresh = pr.json()
                status = refresh.get("status")
                if status not in ("Unknown", "InProgress", "NotStarted", None):
                    if status == "Completed":
                        return
                    msg = (
                        f"REST refresh failed: {status} "
                        f"-- {refresh.get('serviceExceptionJson', '')[:300]}"
                    )
                    raise RuntimeError(
                        msg
                    )
        msg = (
            f"REST refresh ({refresh_type}) timed out after "
            f"{poll_timeout_sec}s ({max_attempts} polls @ {poll_interval_sec}s)"
        )
        raise RuntimeError(
            msg
        )
    r.raise_for_status()


def refresh_model(
    *,
    model_name: str,
    workspace_id: str,
    fabric_api: str,
    xmla_endpoint: str,
    auth: Auth,
    refresh_type: str = "Calculate",
    dataset_id: str | None = None,
    rest_only: bool = False,
    rest_poll_timeout_sec: int | None = None,
) -> None:
    """
    Refresh `model_name` in `workspace_id`.

    Tries XMLA first via Tabular Editor 2 (CSX runs `refreshModel.csx` with
    the requested RefreshType). If TE2 fails and `dataset_id` is provided,
    falls back to the REST Enhanced Refresh API.

    Args:
        model_name: Display name of the published semantic model.
        workspace_id: Fabric workspace ID.
        fabric_api: Fabric API root (e.g. https://api.fabric.microsoft.com).
        xmla_endpoint: XMLA endpoint URL for the workspace.
        auth: Auth instance for token acquisition.
        refresh_type: One of "Calculate", "Full", "Defragment", "ClearValues",
            "DataOnly", "Automatic". Defaults to "Calculate" (cheapest;
            recomputes calc cols/measures without re-importing data).
        dataset_id: Required for REST fallback; optional for XMLA-only callers.
        rest_only: Skip TE2/XMLA and use the REST Enhanced Refresh API.
        rest_poll_timeout_sec: Override REST fallback poll ceiling. Defaults
            to a per-refresh-type lookup (240 s for Calculate, 1200 s for Full).
            TE2 XMLA path is unaffected; TE2 enforces its own timeouts.

    """
    refresh_type = _normalize_refresh_type(refresh_type)
    if rest_only:
        if not dataset_id:
            msg = "REST-only refresh requires dataset_id"
            raise RuntimeError(msg)
        timeout_sec = (
            rest_poll_timeout_sec
            if rest_poll_timeout_sec is not None
            else _REST_POLL_TIMEOUTS_SEC.get(refresh_type, _DEFAULT_REST_POLL_TIMEOUT_SEC)
        )
        print(f"    Refreshing via REST API ({refresh_type}, poll timeout {timeout_sec}s)")
        _refresh_via_rest(
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            auth=auth,
            refresh_type=refresh_type,
            poll_timeout_sec=timeout_sec,
        )
        return

    context = SimpleNamespace(
        workspace_id=workspace_id,
        token_credential=auth.cred,
        fabric_api_url=fabric_api,
        xmla_endpoint=xmla_endpoint,
    )
    try:
        run_te = _get_te_xmla_runner()
        result = run_te(
            target="xmla",
            action="script",
            item_name=model_name,
            context=context,
            script_path=_REFRESH_CSX,
            env_vars={"RefreshType": refresh_type},
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "").strip()[:500])
    except Exception as te2_err:
        if not dataset_id:
            msg = f"TE2 refresh failed and no dataset_id for REST fallback: {te2_err}"
            raise RuntimeError(
                msg
            ) from te2_err
        timeout_sec = (
            rest_poll_timeout_sec
            if rest_poll_timeout_sec is not None
            else _REST_POLL_TIMEOUTS_SEC.get(refresh_type, _DEFAULT_REST_POLL_TIMEOUT_SEC)
        )
        print(
            f"    TE2 XMLA failed ({str(te2_err)[:120]}); "
            f"falling back to REST API refresh (poll timeout {timeout_sec}s)"
        )
        _refresh_via_rest(
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            auth=auth,
            refresh_type=refresh_type,
            poll_timeout_sec=timeout_sec,
        )
