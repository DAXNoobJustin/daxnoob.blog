"""
Environment-name -> config-key mapping for Fabric deploys.

CLI ``--environment`` values ("dev"/"test"/"prod") map to the capitalized env
keys used across the deploy configs (parameter.yml replace_values,
env_connection_ids.json). Kept explicit so a typo or a new env (e.g. "PreProd")
blows up at the call site rather than silently no-op'ing.

Workspace IDs are NOT resolved here -- each entry point takes an explicit
``--workspace-id`` (deploy_workspace.py, run_tests.py, debug_deploy.py,
update_snapshots.py), so the target workspace is named in exactly one place.
"""

from __future__ import annotations

# CLI --environment values map to the capitalized env keys used in deploy configs.
ENV_TO_KEY = {"dev": "Dev", "test": "Test", "prod": "Prod"}
