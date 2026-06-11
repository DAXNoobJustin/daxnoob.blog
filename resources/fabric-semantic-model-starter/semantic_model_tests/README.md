# Semantic Model Tests — How-To Guide

A deterministic **DAX test harness for Fabric semantic models** — assert
anything you can express in an `EVALUATE`: table/column structure, business
and data-quality invariants (row-count thresholds, value relationships),
refresh sanity, regression snapshots, and negative (error-path) cases. In this
repo it *also* covers the AskADIA UDF contract, but that's just one use — most
cases are plain DAX with no framework dependency, so the harness works against
any semantic model.

An **ADO pipeline** (`Validate_SemanticModelTests.yml`) runs the tests
automatically as a PR gate on Develop, Test, and Main branches. The pipeline
deploys a throwaway model to the dev workspace, refreshes it, executes DAX,
asserts results, and tears down.

> **Illustrative — not runnable as-is.** This documents _how_ we gate
> semantic-model PRs with DAX tests; it isn't a drop-in suite. It needs a live
> Fabric dev workspace plus the AskADIA-bootstrapped models, and the
> machine-owned `__snapshots__/` baselines are intentionally not shipped — so the
> `snapshot` cases below are worked examples, not green tests. Take the patterns.

## Layout

```
semantic_model_tests/
├── README.md                  this guide
├── __init__.py
├── DaxQueryRunner.cs          AdomdClient out-of-proc DAX runner (Windows; .NET Framework 4.x)
├── requirements.txt           pip dependencies (used by both local + CI)
├── run_tests.py               CI test runner (deploy throwaway → refresh → assert → tear down)
├── _shared/                   framework UDF contract — runs against EVERY registered model
│   ├── discover_columns_shape.yml
│   ├── discover_measures_shape.yml
│   └── discover_questions_shape.yml
└── <model_slug>/              per-model surface
    ├── unit/                  model-specific structurals/snapshots — every PR
    └── smoke/                 Main-PR-only data freshness — needs Full refresh
```

## How it relates to the rest of the repo

| Tree                                 | Role                                                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `semantic_model_tests/`              | **What you assert** — DAX cases + the runner that deploys/queries                                                   |
| `.deploy/workspace/lib/`             | Shared dev-loop plumbing (auth, staging, connections, refresh, fabric_api, branch_env) — imported by `run_tests.py` |
| `.deploy/workspace/operations/`      | Pre/post-deploy ops invoked via `process_orchestrator.DeploymentPipeline` (same chain prod uses)                    |
| `.deploy/workspace/tabular_scripts/` | TE2 CSX scripts run during the preprocess chain                                                                     |
| `.deploy/workspace/askadia/`         | Canonical AskADIA scaffold merged into models at deploy time                                                        |
| `.deploy/workspace/debug_deploy.py`  | Developer-facing entry point — same pipeline, persistent `DEBUG_<ENV>_<Slug>_<user>` model for iterating            |

The runner does not maintain a parallel deploy harness — it composes the
production `process_orchestrator` with dev-loop additions (staging, binding,
REST refresh fallback) so what we test matches what we ship.

## How it works

When you open a PR that touches semantic model files, the AskADIA framework,
or test catalogs, the `Validate_SemanticModelTests` pipeline fires. It:

1. Copies the model definition to a temp directory with a `DEBUG_UnitTest_<ENV>_` prefix
2. Strips RLS roles (so the service principal can query via XMLA)
3. Runs CSX pre-deploy scripts (generates `_INFO_*` calculated tables)
4. Publishes to the workspace via `fabric_cicd` with env-correct parameter.yml find/replace
5. Binds env-mapped connection IDs from `.deploy/workspace/configs/env_connection_ids.json`
   (no cross-workspace lookup — the SP only needs `Use` permission on the connection objects)
6. Refreshes (Calculate on Develop/Test PRs; Full on Main against real prod data),
   runs all YAML-cataloged DAX test cases, asserts results
7. Deletes the throwaway model (always — even on failure)

## Running locally (optional)

```bash
# Install dependencies (single source of truth — pipeline uses the same file)
pip install -r semantic_model_tests/requirements.txt

# Log into Azure CLI
az login

# Run the full suite against the Develop workspace
python semantic_model_tests/run_tests.py \
    --workspace-id aaaaaaaa-aaaa-aaaa-aaaa-000000000047 \
    --source-model "Azure Data Insights" \
    --workspace-dir "workspace/HelixFabric-Insights/Azure Data Insights.SemanticModel" \
    --catalog-dir semantic_model_tests/_shared semantic_model_tests/azure_data_insights/unit
```

Prerequisites: `az login` (your Microsoft identity), Python 3.11+.

## How to add a test case

1. Open (or create) a YAML file in `semantic_model_tests/<model_slug>/unit/`.
   Each file is one logical test group (e.g. `generate_query.yml`, `discover_measures.yml`).

2. Add a case entry under `cases:`:

    ```yaml
    cases:
        - id: "build_query_with_topn"
          description: "GenerateQuery with topN parameter"
          category: snapshot # or structural, negative
          dax: 'EVALUATE Local.AskADIA.GenerateQuery("MAU", BLANK(), BLANK(), 10, BLANK(), BLANK(), BLANK())'
    ```

3. Capture the baseline with the snapshot wrapper:

    ```bash
    python semantic_model_tests/update_snapshots.py --workspace-id <dev_ws_id> --model azure_data_insights
    ```

    This deploys a throwaway model to the dev sandbox, runs the cases, and
    writes the captured values into the catalog's `__snapshots__/` sidecar
    (e.g. `azure_data_insights/unit/__snapshots__/generate_query.yml`). The
    wrapper also prettier-formats the sidecars so they pass CI. Review the
    captured values in your PR diff.

4. Commit the source YAML **and** its `__snapshots__/` sidecar. The pipeline
   will assert against the snapshot on your next PR.

## Test categories

| Category       | When to use                                                    | Assertion                                                 |
| -------------- | -------------------------------------------------------------- | --------------------------------------------------------- |
| **snapshot**   | UDF returns a deterministic string (GenerateQuery, etc.)       | Exact string match on the captured `__snapshots__/` value |
| **structural** | UDF output changes as model content changes (DiscoverMeasures) | Column set, row count bands, `contains_all/any`           |
| **negative**   | UDF should raise an error on bad input                         | Query must fail; error matches `expected_error_regex`     |

## When do tests run?

The `Validate_SemanticModelTests` pipeline runs as a PR gate. It triggers on
PRs to Develop, Test, and Main that modify files matching these path filters:

- `semantic_model_tests/**` — test runner + catalogs
- `.deploy/workspace/debug_deploy.py` + `lib/**` + `askadia/**` — dev-loop deploy entry + plumbing + AskADIA scaffold
- `.deploy/workspace/process_orchestrator.py` + `operations/**` + `tabular_scripts/**` — the pre/post engine + Python ops + CSX scripts the runner exercises
- `.deploy/workspace/configs/{shared,HelixFabric-Insights}.yml` — orchestration config (op chain)
- `workspace/**/*.SemanticModel/**` + `workspace/**/parameter.yml` — any semantic model TMDL or env replacements
- `.pipelines/Validate_SemanticModelTests.yml` — the pipeline itself

The runner is branch-aware:

- **Develop / Test PRs**: refresh = `Calculate` (fast, structure-only); runs
  `semantic_model_tests/_shared/` (framework contract, model-agnostic) +
  `semantic_model_tests/<model>/unit/` (model-specific snapshots/structurals).
- **Main PRs**: refresh = `Full` (populates partitions); also runs
  `semantic_model_tests/<model>/smoke/` (data-freshness smoke — table counts, joins,
  end-to-end UDF data).

### Pre-deploy scripts

The test runner automatically executes `generateInfoAnnotations.csx` and
`generateInfoHierarchies.csx` against the staged model via Tabular Editor
**before** publishing. This ensures the test model's `_INFO_ANNOTATIONS` and
`_INFO_HIERARCHIES` tables reflect the current state of annotations and
hierarchies in the repo — not stale baked-in data from a previous deploy.

## YAML schema reference

```yaml
source_model: "Azure Data Insights" # optional, informational
cases:
    - id: unique_case_id # required, kebab-case
      description: "Human-readable" # optional
      category: snapshot # snapshot | structural | negative
      dax: "EVALUATE ..." # the DAX to execute
      refresh_type: Calculate # Calculate (default) or Full

      # --- snapshot fields ---
      # No inline value. The captured string lives in the machine-owned
      # sidecar __snapshots__/<this-file>.yml, keyed by case id, and is
      # (re)generated with update_snapshots.py. Inline expected_snapshot is
      # rejected by the loader.

      # --- structural fields ---
      expected_columns: ["Col1", "Col2"]
      expected_row_count: { min: 1, max: 100 } # or { exact: 5 }
      contains_any: ["Contoso"]
      contains_all: ["Usage", "Revenue"]

      # --- negative fields ---
      expected_error_regex: "(?i)not found"
```

## Regenerating snapshots

When you intentionally change a UDF's output, re-run the wrapper:

```bash
python semantic_model_tests/update_snapshots.py --workspace-id <dev_ws_id> --model azure_data_insights
# or, for every model:
python semantic_model_tests/update_snapshots.py --workspace-id <dev_ws_id>
```

This recaptures the values into each catalog's `__snapshots__/` sidecar (the
hand-authored `.yml` case definitions and comments are never touched), then
prettier-formats them. The PR diff shows exactly which snapshot values changed
— reviewers can verify the new output is correct.

> **Why a sidecar?** Snapshots are machine-owned. Keeping them in a separate
> `__snapshots__/<file>.yml` (Jest-style) means recapturing never rewrites your
> hand-authored cases or strips your `#` comments. Don't edit sidecars by hand;
> regenerate them with the wrapper.

## Debugging a failing test

1. **Run locally** with `--filter` to isolate:

    ```bash
    python .../run_tests.py ... --filter build_query_minimal
    ```

2. **Keep the model alive** for manual inspection:

    ```bash
    python .../run_tests.py ... --keep-model
    ```

    The model name is printed at the start. Connect via DAX Studio or XMLA
    endpoint to run the DAX interactively.

3. **Check the runner output** — each failed case prints the actual vs expected
   diff and the assertion details.

## Adding a new model (e.g. Partner Insights)

End-to-end recipe. The framework is designed so each step is mechanical and
the framework UDF contract tests under `semantic_model_tests/_shared/` automatically apply to
the new model with no copying.

### 1. Bootstrap the AskADIA scaffold into the source model

Follow [`.deploy/workspace/askadia/README.md`](../.deploy/workspace/askadia/README.md)
to wire the new model into `merge_shared_scaffold` (Copilot annotations,
per-model ranker UDF, `copilot_questions.json`, etc.). Without this, the
framework UDFs (`Local.AskADIA.*`) won't resolve and the `_shared/` tests
will fail.

### 2. Bootstrap is automatic

The deploy pipeline detects the new model the moment its overlay dir
(`.deploy/workspace/askadia/udf/models/<slug>/README.md`) lands in the repo
— `setup_askadia_framework` infers eligibility from that file. No YAML edits
required to enable the framework.

### 3. Create the test catalog directory tree

```
semantic_model_tests/<model_slug>/
├── unit/      # snapshots + structurals — runs on every PR (Develop, Test, Main)
└── smoke/     # data-freshness checks — runs only on Main PRs (Full refresh)
```

`unit/` is required (even if empty initially); `smoke/` is optional but
recommended for any model with non-trivial fact tables.

### 4. Append the model to the pipeline matrix

In `.pipelines/Validate_SemanticModelTests.yml`, add an entry to
`parameters.models`:

```yaml
- slug: azure_data_partner_community
  source_model: "Azure Data Partner & Community"
  workspace_dir_name: "HelixFabric-Insights"
  semantic_model_name: "Azure Data Partner & Community.SemanticModel"
```

The pipeline resolves the sandbox `workspace_id` from a single inline
`dev_workspace_id` variable defined at the top of
`Validate_SemanticModelTests.yml`, so you don't duplicate IDs per model. Point
it at the dev workspace that holds the models under test.

### 5. (Usually no-op) Verify pipeline triggers

`paths.include` already covers:

- `semantic_model_tests/**` (the test framework + your new catalog)
- `workspace/**/*.SemanticModel/**` (any model's TMDL)
- `workspace/**/parameter.yml` (env replacements)
- `.deploy/workspace/configs/env_connection_ids.json` (env-mapped connection IDs)
- `.deploy/workspace/configs/HelixFabric-Insights.yml` (the existing model
  config — if your new model lives in a different workspace config file,
  add that file to `paths.include`)

For a model in `HelixFabric-Insights/`, no `paths.include` change is needed.
For a model in a different workspace, add that workspace's config `.yml` to
the trigger.

Also remember to add an entry to `env_connection_ids.json` for the new
model. If it shares an existing source (e.g. another AskADIA model on
the same DirectLake), add a `uses` entry referencing existing aliases:

```json
"HelixFabric-Insights": {
  "Partner Insights": {
    "uses": ["DirectLakeInsights", "DirectLakeInsightsRestricted"]
  }
}
```

For a brand-new shared source, register a new alias under
`_connections` first, then reference it from the model's `uses` list.

### 6. Add a few cases and capture snapshots

Start with one or two structural tests in `unit/discover_columns.yml` using
a model-relevant search term (the framework `_shared/` contract tests will
already cover the empty / no-match cases). Run `update_snapshots.py`
locally to seed any snapshot tests, commit the captured sidecars, open the PR,
and watch the matrix job succeed.

## Test catalog organization

> **Snapshots are machine-owned sidecars.** Captured values live in
> `__snapshots__/<file>.yml` next to each catalog file and are regenerated with
> `update_snapshots.py`. The hand-authored `.yml` holds the case definitions and
> any `#` comments — recapturing never touches it. Document file scope and design
> intent in the source `.yml`, not the sidecar.

### Shared shape contracts (`_shared/`)

These files assert the **framework UDF contract** and run against every
registered model. They guard the runtime shape that downstream consumers
(Copilot, AnswerQuestion, etc.) depend on:

| File                           | Owns                                                   |
| ------------------------------ | ------------------------------------------------------ |
| `discover_columns_shape.yml`   | `DiscoverColumns` row/column shape + no-match behavior |
| `discover_measures_shape.yml`  | `DiscoverMeasures` format + no-match contract          |
| `discover_questions_shape.yml` | `DiscoverQuestions` format + no-match contract         |

### Model-specific unit tests (`<model_slug>/unit/`)

Per-model assertions that depend on the model's curated content (specific
measure names, question catalog, etc.). Generic format/no-match contract
lives in `_shared/` — the per-model files only cover what's unique to that
model. For example:

- `azure_data_insights/unit/discover_measures.yml` — Insights-specific
  search-term tests (revenue, MAU, etc.); generic format / no-match in
  `_shared/discover_measures_shape.yml`.
- `azure_data_insights/unit/discover_questions.yml` — Insights-specific
  curated catalog presence; generic format / no-match in
  `_shared/discover_questions_shape.yml`.

## Architecture notes

- **Throwaway model**: each run creates `DEBUG_UnitTest_<ENV>_<slug>_<hex>`
  (env in the name lets concurrent test runs against different envs coexist),
  always deleted in a `finally` block. The `^DEBUG.*` regex in
  `deploy_workspace.py` excludes these from production deploy sweeps.
- **Env-mapped connection binding**: the throwaway binds explicit connection
  IDs from `.deploy/workspace/configs/env_connection_ids.json`. Models
  reference named aliases (defined under `_connections`) via
  `<workspace>.<model>.uses: [aliasName, ...]`, so multiple models that share
  a DirectLake source don't duplicate IDs. The pipeline SP only needs
  `Use` permission on the connection objects (which it has for every env);
  no cross-workspace read is needed. Refresh then flows through each
  connection's own identity, so Full refresh against prod data works on
  Main PRs even though the throwaway lives in the dev workspace.
- **Calculate refresh**: default on Develop/Test PRs. Populates
  `_COPILOT_QUESTIONS`, `_COPILOT_TOPICS` (DATATABLEs) and calculated
  tables. Does NOT load lakehouse data — search UDFs need
  `--refresh-type Full` for that.
- **RLS stripping**: the throwaway model has RLS roles removed so the service
  principal can query via XMLA without RLS filtering affecting results.
  UDF tests only touch `_COPILOT_*` / `_INFO_*` tables which are not role-filtered.
- **Auth**: uses `AzureCliCredential` — in the pipeline this comes from the
  `AzureCLI@2` task's service principal; locally from your `az login` session.
