"""
Copy a semantic-model TMDL tree to a working dir and rebrand it.

Rewrites .platform `displayName` + `logicalId` so the staged copy publishes
as a distinct item alongside the source. Optionally strips RLS roles
(needed when the publishing identity is a service principal that isn't
listed in any role's member set, e.g. UDF unit tests).

Used by both:
  - semantic_model_tests/run_tests.py  (throwaway DEBUG_UnitTest_<slug>_<id> models)
  - .deploy/workspace/debug_deploy.py  (persistent DEBUG_<Model> models)
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path


def slug_model_name(name: str) -> str:
    """
    Strip non-alphanumerics from a model display name.

    Fabric display names are loose (spaces + ampersands welcome), but the
    slug is used in test/debug model names where a clean identifier is
    preferable (e.g. "Azure Data Insights" -> "AzureDataInsights").
    Falls back to "Model" if the name has zero alphanumerics.
    """
    return re.sub(r"[^A-Za-z0-9]", "", name) or "Model"


def make_test_model_name(prefix: str, env: str, source: str) -> str:
    """
    Build a unique-per-run model name like '<prefix>_<ENV>_<source>_<8hex>'.

    Strips non-alphanumerics from `source` (Fabric display names are loose
    but the slug is appended after the prefix and must round-trip cleanly).
    `env` is upper-cased for visibility in workspace listings.
    """
    return f"{prefix}_{env.upper()}_{slug_model_name(source)}_{uuid.uuid4().hex[:8]}"


def patch_workspace_config_for_staged_model(
    config: dict,
    *,
    source_model_name: str,
) -> None:
    """
    In-memory patch so a staged model picks up the prod preprocess chain.

    Used by callers that publish a renamed copy of a source model (e.g.
    ``DEBUG_<Model>_<user>`` or ``DEBUG_UnitTest_<Model>_<id>``) but still want
    to run the production pipeline config (``HelixFabric-Insights.yml`` etc.)
    against the staged copy. Two mutations:

    1. ``source_model_name=<source_model_name>`` injected into every
       pre_process op so slug-aware ops (overlay resolvers in
       ``setup_askadia_framework``, ``merge_shared_scaffold``, etc.) find the
       per-model overlay dir from the source name instead of the staged
       throwaway name. All ops accept ``**kwargs`` so unrelated ops absorb
       it harmlessly.
    2. ``post_process`` cleared so a debug session never refreshes the
       source model the staged copy was cloned from.

    Mutates ``config`` in place.

    Args:
        config: Loaded orchestration config (merge of ``shared.yml`` +
            workload-specific ``HelixFabric-*.yml``).
        source_model_name: Display name of the original model.

    """
    orchestration = config.get("orchestration", {})

    for env_block in orchestration.values():
        if not isinstance(env_block, dict):
            continue
        for type_block in env_block.values():
            if not isinstance(type_block, dict):
                continue
            for op in type_block.get("pre_process") or []:
                op["source_model_name"] = source_model_name
            type_block["post_process"] = []


def stage_model(
    source_dir: Path,
    model_name: str,
    output_dir: Path,
    *,
    strip_rls: bool = False,
) -> Path:
    """
    Copy a `.SemanticModel` tree into `output_dir` and rebrand it.

    Args:
        source_dir: Path to the source `*.SemanticModel/` directory.
        model_name: New display name; also used as the staged folder name.
        output_dir: Working directory the staged copy is written under.
            Caller owns this directory and is responsible for cleanup.
        strip_rls: When True, remove `definition/roles/` from the staged copy.
            Set this for runs that publish via a service principal not
            listed in any role's member set; leave False to preserve RLS.

    Returns:
        Path to the staged `*.SemanticModel/` directory inside `output_dir`.

    """
    if not source_dir.exists():
        msg = f"Source model not found: {source_dir}"
        raise FileNotFoundError(msg)
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / f"{model_name}.SemanticModel"
    shutil.copytree(source_dir, dest)

    pf = dest / ".platform"
    platform = json.loads(pf.read_text(encoding="utf-8"))
    platform["metadata"]["displayName"] = model_name
    platform["config"]["logicalId"] = str(uuid.uuid4())
    pf.write_text(json.dumps(platform, indent=2), encoding="utf-8")

    if strip_rls:
        roles_dir = dest / "definition" / "roles"
        if roles_dir.exists():
            shutil.rmtree(roles_dir)
            print(f"    Stripped RLS roles from {roles_dir}")

    return dest
