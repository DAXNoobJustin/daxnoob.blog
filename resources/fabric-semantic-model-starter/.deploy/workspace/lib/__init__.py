"""
Shared building blocks for AskADIA semantic-model dev workflows.

Modules:
  auth         -- AzureCli/InteractiveBrowser credential wrapper + scopes
  branch_env   -- detect upstream long-lived branch (Develop/Test/Main) -> env
  fabric_api   -- scoped override of fabric_cicd's module-global API root
  staging      -- copy TMDL tree + rewrite displayName/logicalId
  connections  -- bind connections from a source model to a target model
  refresh      -- model refresh (XMLA-first with REST fallback)

Consumed by:
  - .deploy/workspace/debug_deploy.py        (developer-facing test deploys)
  - semantic_model_tests/run_tests.py        (CI semantic-model tests)

NOT consumed by .deploy/workspace/deploy_workspace.py (production deploy
backbone). That stays self-contained and unchanged.
"""
