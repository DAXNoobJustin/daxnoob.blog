"""
Scoped override of `fabric_cicd`'s module-global API root.

`fabric_cicd.constants.DEFAULT_API_ROOT_URL` is read at publish time by the
fabric_cicd library. Both `.deploy/workspace/debug_deploy.py` and
`semantic_model_tests/run_tests.py`
need to point publishes at the INTERNAL API root, but mutating the global
permanently leaks into anything else running in the same process (other
tests, interactive sessions, future imports). The context manager below
scopes the mutation to the publish call site and always restores the
original value.
"""

from __future__ import annotations

from contextlib import contextmanager

import fabric_cicd.constants as fc_constants


@contextmanager
def fabric_api_root(url: str):
    """
    Temporarily override `fabric_cicd.constants.DEFAULT_API_ROOT_URL`.

    Use around any code that calls into fabric_cicd (e.g.
    `DeploymentPipeline.run`, `publish_all_items`). The original value is
    restored on exit, including on exception.

    Args:
        url: New API root URL (e.g. ``https://api.fabric.microsoft.com``).
            A trailing slash is normalized in -- callers don't need to add one.

    """
    old = fc_constants.DEFAULT_API_ROOT_URL
    fc_constants.DEFAULT_API_ROOT_URL = url.rstrip("/") + "/"
    try:
        yield
    finally:
        fc_constants.DEFAULT_API_ROOT_URL = old
