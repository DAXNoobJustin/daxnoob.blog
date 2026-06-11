"""
Recapture AskADIA semantic-model snapshots locally.

This is the canonical local path for refreshing the machine-owned snapshot
sidecars (``<catalog>/__snapshots__/<file>.yml``). It:

  1. Reads the model matrix from .pipelines/Validate_SemanticModelTests.yml
     (single source of truth -- the same matrix CI runs), so model slugs,
     source-model names and workspace folders are never duplicated here.
  2. Publishes throwaway models to the *dev* sandbox workspace you pass via
     ``--workspace-id`` (the same workspace CI uses). Snapshots are always
     captured against the dev sandbox via a throwaway model.
  3. For each selected model, runs run_tests.py with --interactive-auth
     --update-snapshots over the _shared + <slug>/unit catalogs.
     --interactive-auth is mandatory locally: it selects the REST DAX backend,
     which accepts the interactive token (the XMLA/AdomdClient backend rejects
     CLI tokens with "Authentication failed for all authenticators").
  4. Formats the touched sidecars with prettier so they pass the repo's
     `prettier --check` CI gate. (write_snapshots already emits LF.)

Usage:
  python semantic_model_tests/update_snapshots.py                 # all models
  python semantic_model_tests/update_snapshots.py --model azure_data_insights
  python semantic_model_tests/update_snapshots.py --environment dev --refresh-type Calculate

Browser SSO makes the per-model interactive auths fast (no re-entry). After it
finishes, REVIEW THE SIDECAR DIFF (`git diff semantic_model_tests`) and `git
add` the sidecars before committing -- a changed snapshot is a real behavior
change to vet.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_PIPELINE = _REPO_ROOT / ".pipelines" / "Validate_SemanticModelTests.yml"
_SHARED_CATALOG = "semantic_model_tests/_shared"
# Sidecar-only glob: recapture must never reformat hand-authored catalog YAML.
_SIDECAR_GLOB = "semantic_model_tests/**/__snapshots__/*.yml"

# run_tests.py adds .deploy/workspace to sys.path; nothing here needs it now
# that the dev workspace id is passed in explicitly via --workspace-id.
_DEPLOY_WORKSPACE_DIR = _REPO_ROOT / ".deploy" / "workspace"
if str(_DEPLOY_WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_WORKSPACE_DIR))


def load_models() -> list[dict]:
    """Parse the model matrix (parameters.models) from the CI pipeline YAML."""
    doc = yaml.safe_load(_PIPELINE.read_text(encoding="utf-8"))
    for param in doc.get("parameters", []):
        if param.get("name") == "models":
            return list(param.get("default", []))
    msg = f"{_PIPELINE}: no 'models' parameter found"
    raise SystemExit(msg)


def run_model(model: dict, workspace_id: str, environment: str, refresh_type: str) -> int:
    """Recapture snapshots for one model. Returns the run_tests.py exit code."""
    slug = model["slug"]
    unit_dir = _HERE / slug / "unit"
    catalogs = [_SHARED_CATALOG]
    if unit_dir.exists():
        catalogs.append(f"semantic_model_tests/{slug}/unit")
    else:
        print(f"  (note: no unit catalog for {slug}; only _shared snapshots will refresh)")

    # The throwaway model ALWAYS deploys to the dev sandbox workspace (matching
    # CI + debug_deploy). --environment only selects which env's parameter.yml
    # values + connections get bound, never the deployment workspace.
    workspace_dir = f"workspace/{model['workspace_dir_name']}/{model['semantic_model_name']}"

    cmd = [
        sys.executable, "semantic_model_tests/run_tests.py",
        "--workspace-id", workspace_id,
        "--workspace-dir-name", model["workspace_dir_name"],
        "--source-model", model["source_model"],
        "--workspace-dir", workspace_dir,
        "--catalog-dir", *catalogs,
        "--environment", environment,
        "--refresh-type", refresh_type,
        "--interactive-auth",
        "--update-snapshots",
    ]
    print(f"\n==> {model['source_model']} ({slug})")
    print(f"    workspace: {workspace_id} ({model['workspace_dir_name']}.Dev sandbox)")
    print(f"    binding:   {environment} connections")
    print(f"    catalogs:  {', '.join(catalogs)}")
    return subprocess.run(cmd, cwd=_REPO_ROOT, check=False).returncode


def format_snapshots() -> bool:
    """Prettier-format the sidecars so CI's check passes. Returns False on failure."""
    npx = shutil.which("npx")
    if not npx:
        print('\n(skip) npx not found -- run `npx prettier --write "'
              f'{_SIDECAR_GLOB}"` manually before committing')
        return True
    print("\n==> Formatting sidecars with prettier")
    rc = subprocess.run([npx, "prettier", "--write", _SIDECAR_GLOB], cwd=_REPO_ROOT, check=False)
    return rc.returncode == 0


def main() -> int:
    """Parse args, recapture the selected model(s), format sidecars, summarize."""
    p = argparse.ArgumentParser(description="Recapture AskADIA snapshot sidecars locally.")
    p.add_argument("--workspace-id", required=True,
                   help="Dev sandbox Fabric workspace ID to deploy throwaway models to.")
    p.add_argument("--model", default="all",
                   help="Model slug to refresh, or 'all' (default). e.g. azure_data_insights")
    p.add_argument("--environment", default="dev", choices=["dev", "test", "prod"],
                   help="Environment whose connections to bind (default dev).")
    p.add_argument("--refresh-type", default="Calculate", choices=["Calculate", "Full", "None"],
                   help="Refresh type for the throwaway model (default Calculate).")
    args = p.parse_args()

    models = load_models()
    if args.model != "all":
        models = [m for m in models if m["slug"] == args.model]
        if not models:
            slugs = ", ".join(m["slug"] for m in load_models())
            msg = f"Unknown model {args.model!r}. Known slugs: {slugs}"
            raise SystemExit(msg)

    failures = [m["slug"] for m in models if run_model(m, args.workspace_id, args.environment, args.refresh_type) != 0]

    fmt_ok = format_snapshots()

    print("\n" + "=" * 70)
    if failures:
        print(f"FAILED for: {', '.join(failures)} -- see output above.")
    if not fmt_ok:
        print("prettier formatting FAILED -- sidecars may not pass CI's format check.")
    print("Review the diff, then `git add` the sidecars before committing:")
    print("  git diff semantic_model_tests")
    print("=" * 70)
    return 1 if (failures or not fmt_ok) else 0


if __name__ == "__main__":
    raise SystemExit(main())
