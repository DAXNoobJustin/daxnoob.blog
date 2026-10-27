"""
Copy a semantic-model TMDL tree to a working dir and rebrand it.

Rewrites .platform `displayName` + `logicalId` so the staged copy publishes as a
distinct item alongside the source rather than overwriting it. Optionally strips
RLS roles, which a service principal usually can't satisfy (it isn't listed in
any role's member set, so the publish or the query fails).
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

    Fabric display names are loose (spaces and ampersands welcome), but the slug
    is appended into a generated test-model name and should round-trip cleanly.
    Falls back to "Model" if the name has zero alphanumerics.
    """
    return re.sub(r"[^A-Za-z0-9]", "", name) or "Model"


def make_test_model_name(prefix: str, source: str) -> str:
    """Build a unique-per-run model name like '<prefix>_<Source>_<8hex>'."""
    return f"{prefix}_{slug_model_name(source)}_{uuid.uuid4().hex[:8]}"


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
        output_dir: Working directory the staged copy is written under. The
            caller owns this directory and is responsible for cleanup.
        strip_rls: When True, remove `definition/roles/` from the staged copy.
            Set this when publishing as a service principal that isn't a member
            of any role; leave False to preserve RLS.

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
