# `.deploy/workspace/` — Fabric workspace deploy infrastructure

Owns deployment of all items into Microsoft Fabric workspaces (notebooks,
environments, pipelines, variable libraries, semantic models). Production
deploys, developer-loop debug deploys, and CI test-model deploys all go
through the same engine and ops here — no parallel harnesses.

For the developer iteration loop, see [`DEBUG_DEPLOY.md`](./DEBUG_DEPLOY.md).
For the AskADIA UDF framework (semantic-model layer that this engine deploys),
see [`askadia/README.md`](askadia/README.md).

---

## Mental model

Three concepts compose every deploy:

| Concept | What it is | Where it lives |
|---|---|---|
| **Item** | A thing in a Fabric workspace — notebook, environment, pipeline, variable library, semantic model. | `workspace/<WS>/<Item>.<Type>/` |
| **Operation** | A Python function that mutates an item or asserts something about it. Runs **before** publish (`pre_process`) or **after** (`post_process`). | `operations/<name>.py`, registered in `process_orchestrator.OPERATIONS` |
| **Config** | YAML that wires items to operations per environment (dev/test/prod). | `configs/<workspace-name>.yml` |

The publish itself is delegated to the upstream `fabric_cicd` library —
this engine just decorates publish with the pre/post-process pipeline.

> 📖 Background: [Extending fabric-cicd with pre/post-processing](https://daxnoob.blog/extending-fabric-cicd-with-pre-post-processing/) — the pattern this engine implements.

---

## Layout

```
.deploy/workspace/
├── README.md                       you are here
├── DEBUG_DEPLOY.md                 debug-deploy iteration runbook
│
├── deploy_workspace.py             prod entry — invoked from the .pipelines/Release_FabricWorkspace pipeline
├── debug_deploy.py                 dev entry — stages DEBUG_<ENV>_<Slug>_<user>, deploys to dev Insights, binds env-mapped connection IDs, refreshes
├── process_orchestrator.py         generic pre/post-process engine + DeploymentPipeline + OPERATIONS registry
│
├── configs/                        deploy-engine configs (YAML op-chains + connection IDs)
│   ├── shared.yml                  cross-workspace defaults
│   ├── HelixFabric-Engineering.yml notebooks/env/pipelines/var libraries
│   ├── HelixFabric-Insights.yml    semantic models (AskADIA preprocess chain)
│   └── env_connection_ids.json     env -> connection-id map (bound by debug_deploy + tests)
│
├── operations/                     host deploy-engine ops registered in process_orchestrator.OPERATIONS (see registry below)
│
├── tabular_scripts/                host CSX scripts run by Tabular Editor 2 (most vs the local model definition; refreshModel over XMLA), invoked by Python ops
│   └── (generateTimeIntelMeasures, augmentMeasureDescriptions, generateCopilotSchema, refreshModel)
│
├── lib/                            dev/test plumbing — consumed by debug_deploy + run_tests
│   ├── auth.py                     Auth wrapper (token caching, AzCli + Interactive credentials)
│   ├── branch_env.py               git merge-base distance → Develop/Test/Main (local CLI only)
│   ├── connections.py              bind explicit env-mapped connection IDs (no cross-workspace lookup; needs only 'Use' perm)
│   ├── fabric_api.py               ctxmgr for fabric_cicd.DEFAULT_API_ROOT_URL
│   ├── refresh.py                  XMLA-first refresh + REST fallback (per-refresh-type poll timeout)
│   ├── staging.py                  copy TMDL tree + rebrand displayName + patch workspace config
│   └── workspace_config.py         env-key → workspace/connection ID mapping (imported by debug_deploy + connections)
│
└── askadia/                        self-contained AskADIA framework package (UDFs + instruction content + its own deploy ops)
    ├── README.md                   framework spec — concepts, lifecycle, runtime contract
    ├── MODEL_AUTHORING.md          model-owner guide — annotation reference, curated questions, ranker UDFs
    ├── RENAMING.md                 OSS adopter guide — rebrand the AskADIA namespace
    ├── rename_namespace.py         OSS adopter tool — find-and-replace the brand + re-bless goldens
    ├── config/                     model_guids.yml (per-model, per-env Copilot dataset GUIDs)
    ├── deploy/                     framework deploy ops (setup_askadia_framework + private sub-steps) + tabular_scripts/
    ├── udf/                         UDF framework
    │   ├── common/                 canonical UDFs (functions.tmdl) + framework tables (_INFO_*/_COPILOT_*) + askadia_config.json
    │   └── models/<slug>/          per-model overlays (rankers, curated questions, intent marker)
    └── instructions/               Copilot instruction content + emitters (emit_model.py, emit_router.py, _core/)
        ├── common/                 manifest.json, router-preamble.md, blocks/*.md
        └── models/<slug>/          model.json + rows/*.md
```

---

## Configs

Each config declares an `orchestration` block with a `default` op-chain per item type (and optional environment-specific overrides). The `core` block names the target workspace and repo directory.

| File | Items | Notable ops |
|---|---|---|
| `configs/shared.yml` | n/a | cross-workspace defaults (auth, item type filters) |
| `configs/HelixFabric-Engineering.yml` | Notebooks, environments, pipelines, variable libraries | `validate_item` |
| `configs/HelixFabric-Insights.yml` | Semantic models | `validate_item` → `run_model_script` (time-intel variants + measure-description notes) → `setup_askadia_framework` → `generate_copilot_schema`. |

### Config schema (excerpt)

```yaml
core:
  workspace: "HelixFabric-Insights"
  repository_directory: "."

orchestration:
  default:                               # op-chain used unless an env overrides it
    SemanticModel:
      pre_process:                       # runs before fabric_cicd publish
        - operation: validate_item
          failure_mode: abort
        - operation: setup_askadia_framework
          failure_mode: abort
        - operation: generate_copilot_schema
          failure_mode: abort
      post_process:                      # runs after publish
        - operation: refresh_model_rest
          refresh_type: calculate
          failure_mode: continue
```

Each `operation` entry maps to a function in
`process_orchestrator.OPERATIONS`. Extra keys on the entry are passed as
kwargs to the op.

---

## Operations registry

`process_orchestrator.OPERATIONS` is the code registry. For the authoritative
AskADIA setup sub-op order, see [`askadia/README.md`](askadia/README.md#framework-setup-chain).

### Adding a new operation

1. Write a function in `operations/<name>.py` accepting the dispatcher's keyword
   args (`item_name`, `item_type`, `context`, `workspace`, `item_directory`, plus
   any YAML params) — see the shipped ops for the shape. Raise an exception to fail the deploy.
2. Import it in `process_orchestrator.py` and add to the `OPERATIONS` dict.
3. Reference by name in a config's `pre_process` or `post_process` list.
4. The op should self-gate on file existence rather than relying on a
   central allowlist. (See `setup_askadia_framework` for the pattern:
   skip silently if the gating file isn't present.)

---

## Pipeline lifecycle

`DeploymentPipeline.run` executes configured `pre_process` operations, calls
`fabric_cicd.publish_all_items`, then executes configured `post_process`
operations. Operation order is declared in the workspace YAML; AskADIA's bundled
sub-op order is documented in [`askadia/README.md`](askadia/README.md#framework-setup-chain).

**`parameter.yml`** sits next to each item (`workspace/<WS>/<Item>.<Type>/parameter.yml`)
and gives `fabric_cicd` env-mapped values to swap during publish (workspace
GUIDs, lakehouse IDs, etc.).

**Failure modes** are per-op via the `failure_mode` key (`abort` halts the
pipeline; `continue` logs and proceeds). Default is `abort`.

---

## Dev/test flow

`debug_deploy.py` and `semantic_model_tests/run_tests.py` exercise the **same**
`process_orchestrator` chain as prod — they just stage the model under a
DEBUG_* name and bind connections themselves:

```
debug_deploy.py  -or-  semantic_model_tests/run_tests.py
  → lib/staging         (rebrand TMDL to DEBUG_<Slug>_<user>
                         or DEBUG_UnitTest_<ENV>_<Slug>_<8hex>;
                         copy parameter.yml so fabric_cicd can find/replace;
                         patch workspace config to inject source_model_name
                         + clear post_process so we never refresh the source)
  → lib/fabric_api      (ctxmgr scopes fabric_cicd API root)
  → process_orchestrator.DeploymentPipeline.run    (SAME chain as prod;
                         FabricWorkspace(environment=env) drives parameter.yml
                         find/replace -- staged TMDL gets env-correct storage GUIDs)
  → lib/connections     (load env-mapped IDs from
                         .deploy/workspace/configs/env_connection_ids.json;
                         bind_explicit_connections via 'Use' perm only)
  → lib/refresh         (XMLA-first, REST fallback;
                         per-refresh-type poll timeout)
  → (test runner only) DAX assertions + teardown
```

The dev/test surface (`debug_deploy.py` + `lib/`) does not duplicate prod
logic — it composes `process_orchestrator` + `operations/` + `tabular_scripts/`
and adds only what dev/test needs (staging, rebranding, connection binding,
refresh polling, teardown).

For the day-to-day iteration recipe (entry-point flags, common loops, common
errors), see [`DEBUG_DEPLOY.md`](./DEBUG_DEPLOY.md).

---

## See also

- [`DEBUG_DEPLOY.md`](./DEBUG_DEPLOY.md) — debug-deploy iteration runbook
- [`askadia/README.md`](askadia/README.md) — AskADIA framework spec
- [`askadia/MODEL_AUTHORING.md`](askadia/MODEL_AUTHORING.md) — model-owner guide
- [`semantic_model_tests/README.md`](../../semantic_model_tests/README.md) — test contributor guide
- [`../../AGENTS.md`](../../AGENTS.md) — branch / PR / promotion conventions
