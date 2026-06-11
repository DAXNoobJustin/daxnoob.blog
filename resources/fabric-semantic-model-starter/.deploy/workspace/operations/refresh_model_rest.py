"""Refresh semantic models through the Power BI Enhanced Refresh REST API."""

from __future__ import annotations

from lib.auth import Auth
from lib.connections import resolve_item_id
from lib.refresh import refresh_model


def refresh_model_rest(
    item_name,
    item_type="SemanticModel",
    context=None,
    workspace=None,  # noqa: ARG001
    refresh_type=None,
    rest_poll_timeout_sec=None,
    **kwargs,  # noqa: ARG001
):
    """Refresh a published semantic model without loading it through TE2/XMLA."""
    if item_type != "SemanticModel":
        return
    if context is None:
        msg = "refresh_model_rest requires a deployment context"
        raise ValueError(msg)

    auth = Auth(credential=context.token_credential)
    dataset_id = resolve_item_id(
        fabric_api=context.fabric_api_url,
        workspace_id=context.workspace_id,
        display_name=item_name,
        item_type="SemanticModel",
        auth=auth,
    )
    if not dataset_id:
        msg = f"Semantic model '{item_name}' not found in workspace {context.workspace_id}"
        raise RuntimeError(msg)

    refresh_model(
        model_name=item_name,
        workspace_id=context.workspace_id,
        fabric_api=context.fabric_api_url,
        xmla_endpoint=context.xmla_endpoint,
        auth=auth,
        refresh_type=refresh_type or "Calculate",
        dataset_id=dataset_id,
        rest_only=True,
        rest_poll_timeout_sec=rest_poll_timeout_sec,
    )
