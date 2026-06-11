# Debug deploy runbook

End-to-end recipe for deploying a debug copy of a HelixFabric-Insights
semantic model into the dev Insights workspace and exercising the full
prod preprocess chain against it. Use this loop when iterating on:

- Semantic model TMDL (measures, columns, tables, relationships, annotations)
- AskADIA framework artifacts (canonical UDFs in `askadia/udf/common/functions.tmdl`,
  per-model overlay UDFs, `Copilot_*` annotations, `copilot_questions.json`)
- Framework operations themselves (`merge_shared_scaffold`, csx scripts,
  `setup_askadia_framework`, etc.)

For the deploy engine itself (concepts, configs, operations registry, prod
flow), see [`README.md`](./README.md). For the AskADIA framework deep-dive,
see [`askadia/README.md`](./askadia/README.md).

There are two debug-deploy entry points; choose based on what you're iterating on.

## Loop A — `debug_deploy.py` (long-lived debug model)

For ad-hoc DAX queries against a deployed model that should persist across runs.

```pwsh
python .deploy\workspace\debug_deploy.py --model-name "Azure Data Insights" --workspace-id <dev_insights_ws_id>
```

What happens (in order):

1. **Stage** — copies `workspace/HelixFabric-Insights/<Model>.SemanticModel/`
   into a temp dir; rewrites `.platform` to give it a debug display name
   (`DEBUG_<ENV>_<Slug>_<username>`); keeps RLS roles intact.
2. **Patch config** — calls `staging.patch_workspace_config_for_staged_model`
   to inject `source_model_name="<Model>"` into every preprocess op (so
   framework ops like `setup_askadia_framework` resolve the real overlay
   slug from the source name, not the throwaway debug name) and clear
   `post_process` (so we never accidentally refresh the source).
3. **Run prod preprocess chain** — same chain as `deploy_workspace.py`,
   driven by `configs/HelixFabric-Insights.yml`. See
   [`askadia/README.md`](askadia/README.md#framework-setup-chain)
   for the authoritative AskADIA sub-op order.
4. **Bind connections** — copies the source model's connection bindings to
   the staged copy (DirectLake bindings don't survive publish; they're re-bound
   afterward).
5. **Refresh** — `Calculate` by default (fast). Pass `--refresh-type Full`
   if you need data populated.

The published model lives in the dev Insights workspace under the debug name,
visible in Power BI service. Connect via DAX Studio, Power BI Desktop's "Connect
to dataset", or XMLA endpoint.

**Idempotent** — re-running for the same user re-uses the same debug name,
overwriting the previous deploy. Prevents collision when multiple devs are
iterating concurrently (each gets `DEBUG_<ENV>_AzureDataInsights_<their_alias>`).

## Loop B — `run_tests.py` (unit-test loop)

For running the YAML test fixtures under `semantic_model_tests/<slug>/` against
a freshly-staged model. Used by the `Validate_SemanticModelTests` PR pipeline
and by devs iterating on framework UDFs.

```pwsh
python semantic_model_tests\run_tests.py `
    --workspace-dir workspace\HelixFabric-Insights\"Azure Data Insights.SemanticModel" `
    --source-model "Azure Data Insights" `
    --workspace-id <dev_insights_ws_id> `
    --xmla-endpoint <dev_insights_xmla> `
    --catalog-dir semantic_model_tests\_shared semantic_model_tests\azure_data_insights\unit
```

What happens (in order):

1. **Stage with random suffix** — copies the source TMDL into a temp dir under a
   throwaway name like `DEBUG_UnitTest_DEV_AzureDataInsights_a1b2c3d4`. Each
   test run gets a fresh GUID-suffixed copy so concurrent runs don't collide.
2. **Patch config** — same `staging.patch_workspace_config_for_staged_model`
   call as Loop A.
3. **Run prod preprocess + publish** — full chain via `DeploymentPipeline`.
4. **Run test fixtures** — walks every `--catalog-dir` you pass (e.g. `_shared`
   plus a model's `unit/`; add the model's `smoke/` dir to run smoke cases too),
   executes each `dax` query against the staged model, and asserts against the
   `__snapshots__/` sidecars / `expected_columns` / etc. See
   [`semantic_model_tests/README.md`](../../semantic_model_tests/README.md) for the YAML schema.
5. **Tear down** — deletes the staged model from the workspace (unless
   `--keep-model` is set).

## Common iteration loops

Model-owner iteration loops (changing annotations, authoring a curated
question, editing a per-model ranker UDF, editing `copilot_questions.json`)
live with the authoring guidance in
[`askadia/MODEL_AUTHORING.md`](askadia/MODEL_AUTHORING.md) ›
**Validating your change locally**.

Framework-maintainer loops:

### "I changed a canonical UDF in `askadia/udf/common/functions.tmdl`"

1. `python .deploy/workspace/askadia/deploy/merge_shared_scaffold.py --in-place
   "workspace/HelixFabric-Insights/Azure Data Insights.SemanticModel"
   --item-name "Azure Data Insights"` — splice changes into per-model TMDL.
2. Open the per-model TMDL in Tabular Editor 2 → verify the UDF body looks right.
3. **`git restore` the per-model files** — don't commit the merged copies.
4. `python semantic_model_tests/run_tests.py ...` to run the unit tests.

### "I changed an overlay UDF (e.g. `_RankAccounts`)"

Same as above, but edit `askadia/udf/models/<slug>/functions.tmdl` instead of
`askadia/udf/common/functions.tmdl`.

### "I changed a framework operation (e.g. `merge_shared_scaffold.py`)"

1. `python semantic_model_tests/run_tests.py ...` — exercises every framework op
   end-to-end against a freshly-staged model.
2. If the op-level behavior changes are intentional and snapshot tests fail,
   re-run with `--update-snapshots` to capture the new outputs, review the
   diff carefully, and commit.

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `setup_askadia_framework: overlay dir exists but README.md is missing` | Created a `udf/models/<slug>/` dir without committing the README intent marker. | Add `README.md` to the overlay dir, or delete the dir if it was a mistake. |
| `setup_askadia_framework: no overlay dir at .../models/<slug>` (logged as `[SKIP]`) | Model isn't bootstrapped onto the AskADIA framework. | If intentional (model isn't an AskADIA target), nothing to do. If unintentional, follow the bootstrap checklist in `askadia/README.md`. |
| `merge_shared_scaffold: overlay UDF(s) collide with canonical: [...]` | A per-model overlay defines a UDF with the same name as a canonical one. | Either rename the overlay UDF, or move the change to canonical (`askadia/udf/common/functions.tmdl`). |
| `generateInfoAnnotations.csx: zero Copilot_* annotations on model` | Overlay dir exists + bootstrap is partial — `_INFO_ANNOTATIONS` table got synced but the model itself has no annotations yet. | Add `Copilot_*` annotations to the model TMDL (typically via `powerbi-modeling-mcp`). |
| `BindConnectionDetailNotFound` during refresh | The staged DirectLake bindings didn't resolve. | Verify the source model has bound connections in its env-matching workspace; verify your auth has read access to the bind source workspace. |

## See also

- [`README.md`](./README.md) — deploy engine concepts (Items / Operations / Configs / pre+post-process / fabric_cicd / parameter.yml)
- [`askadia/README.md`](./askadia/README.md) — AskADIA framework spec (annotation registry mechanics, lifecycle, runtime contract)
- [`askadia/MODEL_AUTHORING.md`](./askadia/MODEL_AUTHORING.md) — **model-owner guide** (annotation reference, curated question authoring, ranker UDFs, cross-repo updates, validating-your-change checklist)
- [`debug_deploy.py`](./debug_deploy.py) — Loop A entry point.
- [`../../semantic_model_tests/run_tests.py`](../../semantic_model_tests/run_tests.py) — Loop B entry point.
- [`semantic_model_tests/README.md`](../../semantic_model_tests/README.md) — test fixture YAML schema + pipeline reference.
- [`lib/staging.py`](./lib/staging.py) — staging + config patch helpers.
