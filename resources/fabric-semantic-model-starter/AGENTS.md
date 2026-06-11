# Agents Guide — Fabric Semantic Model Starter

> This document provides AI coding agents with the context needed to assist with development in this repository. It describes architecture, conventions, workflows, and rules that **must** be followed.

---

## Repository Overview

HelixData is a **Microsoft Fabric data engineering** repository. It manages notebooks, semantic models, pipelines, and environments across Fabric workspaces. The shared Python library `helixutils` powers all notebook operations.

### Technology Stack

| Layer           | Technology                                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------------------------- |
| Compute         | Microsoft Fabric Spark (PySpark)                                                                                    |
| Storage         | Delta Lake on OneLake                                                                                               |
| Orchestration   | Fabric Data Pipelines                                                                          |
| Semantic Models | Power BI DirectLake (TMDL)                                                                                          |
| Library         | `helixutils` (Python, distributed as `.whl`)                                                                        |
| CI/CD           | Azure DevOps Pipelines + `fabric_cicd`                                                                              |
| Linting         | Custom notebook linter (`linter/`) + `ruff`                                                                         |
| Build Tool      | `uv` (for helixutils wheel builds)                                                                                  |
| Agent Skills    | [Skills for Fabric](https://github.com/microsoft/skills-for-fabric) (**required** — Copilot CLI plugin for Fabric development) |

---

## Architecture — Domain Model

```
┌─────────────────────────────────────────────────────────────┐
│                  HelixFabric-Engineering                     │
│      (ETL + tabular-load notebooks, powered by helixutils)   │
│                            ↓                                 │
│                   HelixFabric-Insights                       │
│         (curated DirectLake semantic models for BI)          │
└─────────────────────────────────────────────────────────────┘
```

### Workspace Purposes

| Workspace                   | Role                                                                                                        |
| --------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **HelixFabric-Engineering** | Development workspace. DIM/FACT/BRIDGE/STAGE + tabular-load notebooks. Hard dependency on `helixutils`.      |
| **HelixFabric-Insights**    | Curated semantic models (DirectLake TMDL). Where engineering outputs converge for BI consumption.           |

> The full internal estate spans additional domain workspaces and a separate orchestration workspace. This starter includes two representative workspaces.

---

## Directory Structure

```
fabric-semantic-model-starter/
├── workspace/                     # Fabric workspace definitions (1 dir = 1 workspace)
│   ├── HelixFabric-Engineering/   # ETL + tabular-load notebooks
│   │   ├── Notebooks/             # DIM / FACT / BRIDGE / STAGE / Tabular notebooks
│   │   ├── Environments/          # Env_Default, Env_Custom, Env_Tabular
│   │   ├── Pipelines/             # One example worker pipeline (orchestration DAG)
│   │   └── Variables/             # Connection variable libraries
│   └── HelixFabric-Insights/      # Curated semantic models (DirectLake TMDL)
│       ├── Azure Data Insights.SemanticModel/            # Primary (hero) model
│       └── Azure Data Partner & Community.SemanticModel/ # Secondary model
├── helixutils/                    # Shared Python library
│   ├── src/helixutils/            # Package source
│   ├── scripts/                   # Build & distribution scripts
│   ├── VERSION                    # Current version (bump here)
│   └── pyproject.toml             # Package config
├── linter/                        # Custom notebook AST linter
├── semantic_model_tests/          # Semantic-model unit-test harness
├── reliability/                   # OneLake-security detector → Activator → cooldown → Teams
├── .deploy/                       # Deployment engine (fabric_cicd) + AskADIA framework
├── .pipelines/                    # Azure DevOps CI/CD pipelines (Validate + Release)
├── .vscode/                       # Workspace editor settings
├── AGENTS.md                      # Agent playbook (this file)
├── README.md                      # Repository overview
├── RELATED-TOOLS.md               # Companion tools + daxnoob.blog deep-dives
└── ruff.toml                      # Python lint config
```

---

## The helixutils Library

`helixutils` is the **foundational library** used by notebooks. Every data operation (reads, writes, quality checks, monitoring) should go through helixutils APIs.

### Key Modules

| Module                        | Purpose                              | Common Usage                                   |
| ----------------------------- | ------------------------------------ | ---------------------------------------------- |
| `helix_read`                  | Read Delta, Parquet, CSV, SQL, Kusto | `helix_read.delta(path).to_view("vw")`         |
| `helix_check` / `CheckConfig` | PyDeequ-based data quality           | `checks.error.isUnique("id").isComplete("id")` |
| `helix_monitoring`            | Incident webhook + alerting         | `helix_monitoring.create_incident(...)`        |
| `helix_vault`                 | Azure Key Vault secrets              | `helix_vault.get_helix_secret(name)`                 |
| `helix_tabular`               | Semantic model processing            | `df.write_delta(path, tabular=True)`           |
| `helix_delta`                 | Delta table management               | `helix_delta.vacuum(path)`                     |
| `connection`                  | Variable library accessor            | `connection["core_default"]`          |
| `global_variable`             | Global variable accessor             | `global_variable["key"]`                       |

### DataFrame Extensions (monkeypatched)

helixutils extends Spark DataFrames with these methods:

- `.to_view("name")` — Create temp view (replaces `createOrReplaceTempView`)
- `.write_delta(path, retention, checks, tabular)` — Write with retention + quality checks. When `tabular=True`, calls `process_tabular()` (derives `DIM_CalendarKey` from `DIM_DateId`) and auto-partitions by `DIM_CalendarKey` for large tables. `process_tabular` is the extension point for model-specific prep — alt-key replacement via `replace_dim_alt_key` against a bridge table, dimension filtering, etc.
- `.write_parquet(path)` — Write parquet
- `.select_except("col1", "col2", ...)` — Select all columns except specified
- `.check(config)` — Run inline data quality checks

### Version & Distribution

- **Version file**: `helixutils/VERSION` (plain text, e.g., `1.0.14`)
- **Build**: `uv build` from `helixutils/` directory
- **Distribution**: `scripts/update_helixutils.py` copies the built wheel to the workspace environment `Libraries/CustomLibraries/` directories — Engineering's Env_Default, Env_Custom, and Env_Tabular.
- **Bump workflow**: Edit `VERSION` → build → run update script. (Built wheels are gitignored environment artifacts — not committed in this public starter.)

### When Modifying helixutils

1. Make changes in `helixutils/src/helixutils/`
2. Bump version in `helixutils/VERSION`
3. Run `python helixutils/scripts/update_helixutils.py` to build and distribute
4. Verify the new `.whl` files appear in workspace `Environments/*/Libraries/CustomLibraries/`
5. The `Validate_Notebook` PR gate checks that `VERSION` is bumped whenever `helixutils/src` changes

---

## Notebook Patterns & Conventions

### Notebook File Structure

Fabric notebooks are stored as `notebook-content.py` files with cell boundaries:

```python
# Fabric notebook source

# METADATA ********************
# META { "kernel_info": { "name": "synapse_pyspark" },
# META   "dependencies": { "environment": { "environmentId": "<LOGICAL_ID>" } } }
# METADATA ********************

# CELL ********************
# Code cell content here
# CELL ********************
```

### Environment Binding

Each notebook declares its environment via a **logical ID** in the metadata block. Logical IDs are **scoped to a workspace** — the same environment name will have different logical IDs in different workspaces. To find the correct logical ID, look at the `.platform` file inside the target environment's directory within the same workspace.

**Environment selection rules:**

| Environment   | When to Use                                                                   |
| ------------- | ----------------------------------------------------------------------------- |
| `Env_Tabular` | All notebooks in the `Tabular/` subdirectory                                  |
| `Env_Custom`  | Any notebook that has a `%%configure` cell (custom Spark resource allocation) |
| `Env_Default` | Everything else                                                               |

To determine which environment a notebook currently uses, check the `environmentId` in its metadata block and cross-reference it with the `.platform` files in the workspace's `Environments/` directory.

### Standard Notebook Template (DIM/FACT)

```python
# %%configure cell (if needed for heavy workloads)
%%configure -f
{"driverMemory":"112g", "driverCores":16, "executorMemory":"112g", "executorCores":16, "numExecutors":16}

# Imports
from helixutils import CheckConfig, connection, helix_read

# Read source data into views
helix_read.delta(connection["source_lakehouse"] + "/path/").to_view("vwSource")

# SQL transformations (in SQL cells)
CREATE OR REPLACE TEMPORARY VIEW vwResult AS
SELECT ... FROM vwSource ...

# Data quality checks (DIM tables MUST have these)
checks = CheckConfig()
checks.error.isUnique("PrimaryKeyCol").isComplete("PrimaryKeyCol")

# Write output
spark.table("vwResult").write_delta(
    connection["core_default"] + "/TABLE_NAME/",
    retention="2d",
    checks=checks
)
```

### Notebook Naming Conventions

| Prefix          | Category                | Example                                |
| --------------- | ----------------------- | -------------------------------------- |
| `Load_DIM_`     | Dimension tables        | `Load_DIM_Account`                     |
| `Load_FACT_`    | Fact tables             | `Load_FACT_RevenueAndLicense`          |
| `Load_BRIDGE_`  | Bridge/hierarchy tables | `Load_BRIDGE_SellerAccount`            |
| `Load_STAGE_`   | Staging tables          | `Load_STAGE_Revenue_Consumption`       |
| `Load_Tabular_` | Tabular model copies    | `Load_Tabular_Insights_CopyStraight`   |
| `Util_`         | Utility notebooks       | `Util_RefreshSemanticModel`            |

### Tabular Notebook Pattern

Tabular notebooks read from dataprod (output of DIM/FACT notebooks) and copy to the tabular lakehouse for semantic model consumption:

```python
from helixutils import connection, helix_read

# Simple read → write (most common)
helix_read.delta(connection["core_default"] + "/FACT_Consumption/").write_delta(
    connection["tabular_default"] + "/FACT_Consumption/", tabular=True
)
```

For DIM tables in tabular, include `CheckConfig` just like dataprod DIM notebooks:

```python
from helixutils import CheckConfig, connection, helix_read

checks = CheckConfig()
checks.error.isUnique("DIM_AccountId").isComplete("DIM_AccountId")

# Note: if process_tabular() replaces the key (e.g., DIM_CapacityId → DIM_CapacityId_Alt),
# the CheckConfig key must use the _Alt version since checks run after the replacement.

spark.table("vwDIM_Account").write_delta(
    connection["tabular_default"] + "/DIM_Account/", tabular=True, checks=checks
)
```

Notebooks can use `%run OtherNotebook` to reference shared utility notebooks. When deleting or renaming a utility notebook, check for `%run` references in other notebooks first.

---

## Data Flow Pipeline

```
External Sources (upstream teams)
        ↓
  helix_read.delta/csv/sql/kusto
        ↓
  STAGE notebooks (staging transforms)
        ↓
  DIM / FACT / BRIDGE notebooks (dataprod)
        ↓  write_delta → connection["core_default"]
        ↓
  Tabular notebooks (copy to tabular lakehouse)
        ↓  write_delta(tabular=True) → connection["tabular_*_default"]
        ↓
  Semantic Models (HelixFabric-Insights)
        ↓  DirectLake mode
        ↓
  Power BI Reports
```

### Connection Names

Notebooks reference OneLake paths and upstream sources through **variable libraries** (`connection["name"]`). The Engineering workspace ships three:

| Library           | Purpose                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------ |
| `fs_connections`  | Lakehouse/storage paths for our own data products plus connections to upstream source lakehouses |
| `global`          | Shared config — key vault URL, tenant/app identity, current environment, Insights workspace name |
| `linked_services` | Linked-service connections to external SQL / Kusto sources (read via `helix_read.sql_endpoint` / `kusto_endpoint`) |

**Naming convention for connections:**

- **`_default` suffix** — Resolves **relative to the current environment**. `core_default` in dev points to the dev lakehouse; in prod it points to the prod lakehouse. Use this for standard development.
- **Per-environment values** — Each `_default` connection resolves to a different path per environment through the variable library's `dev` / `test` / `prod` **value sets**. The notebook code stays the same; only the value set changes on deployment.

Illustrative connection names (our own data-product outputs):

| Connection                         | Library          | Purpose                                  |
| ---------------------------------- | ---------------- | ---------------------------------------- |
| `core_default`            | `fs_connections` | Standard data product output             |
| `restricted_core_default` | `fs_connections` | Restricted/sensitive data product output |
| `tabular_default`       | `fs_connections` | Tabular lakehouse destination            |

> Upstream source connections (owned by other teams) are environment-specific and named per source; the values shipped here are placeholders.

---

## Linting Rules

All notebooks are validated by the custom linter (`linter/`). The CI pipeline runs this on every PR.

### How to Run

```bash
python -m linter lint ./workspace/HelixFabric-Engineering/
python -m linter lint ./workspace/HelixFabric-Engineering/ --json  # JSON output
```

### Rules That Must Be Followed

| Rule                           | Requirement                                                        | ❌ Violation                             | ✅ Correct                                     |
| ------------------------------ | ------------------------------------------------------------------ | ---------------------------------------- | ---------------------------------------------- |
| No wildcard helixutils imports | Import specific modules                                            | `from helixutils import *`               | `from helixutils import helix_read`            |
| No private module access       | Don't import `_`-prefixed modules                                  | `from helixutils._var import ...`        | `from helixutils import connection`            |
| Use helix_read for reads       | Don't use raw `spark.read`                                         | `spark.read.parquet(path)`               | `helix_read.parquet(path)`                     |
| Use write_delta for writes     | Don't use raw `write.format('delta')`                              | `df.write.format('delta').save(p)`       | `df.write_delta(p)`                            |
| Use .to_view()                 | Don't use createOrReplaceTempView                                  | `df.createOrReplaceTempView("v")`        | `df.to_view("v")`                              |
| No sqlContext                  | Use `spark` instead                                                | `sqlContext.sql(...)`                    | `spark.sql(...)`                               |
| No wildcard paths              | Explicit paths only                                                | `connection["x"] + "/*/data"`            | `connection["x"] + "/table/"`                  |
| Standard connection names      | Use known connection prefixes                                      | Custom path strings                      | `connection["core_default"]`          |
| DIM quality checks             | DIM notebooks must use CheckConfig with `isUnique` + `isComplete`  | Missing checks                           | `checks.error.isUnique("id").isComplete("id")` |
| Use to_staged_view()           | For staging writes                                                 | Write to `temp_default`                  | `df.to_staged_view("name")`                    |
| No redundant `read.table`      | Use `spark.table()` on registered views; `.read.table()` is redundant | `spark.read.table("v")`              | `spark.table("v")`                             |
| No unused variables            | Assigned variables must be read (or prefixed `_`)                  | `tmp = load()  # never used`             | `_tmp = load()` or remove the line             |

> **`DIM quality checks` scope:** the linter recognizes a DIM write by a literal `/DIM_` path in the `write_delta` call. Loop-driven tabular copies that build the path from a variable (e.g. copy-straight's `write_delta(... + f"/{table}/")`) aren't auto-detected — those trust the dataprod DIM load's `CheckConfig` upstream, so re-validation isn't required.

### Inline Suppression

To suppress a specific rule on a line:

```python
spark.read.parquet(path)  # helix-lint: ignore no-spark-read-parquet
```

---

## Semantic Models (HelixFabric-Insights)

The Insights workspace contains curated semantic models in **TMDL format**:

- `Azure Data Insights.SemanticModel`
- `Azure Data Partner & Community.SemanticModel`

These models use **DirectLake** mode — they read directly from Delta tables in the tabular lakehouses. The `parameter.yml` files map workspace and lakehouse IDs across environments (dev/test/prod).

**Cross-layer awareness**: Adding a new column to a dataprod notebook that flows through a tabular notebook to a semantic model requires coordinated changes: the dataprod notebook (add column), the tabular notebook (column flows through `write_delta(tabular=True)`), and the semantic model TMDL (add column definition, wire up relationships if it's a foreign key). Similarly, renaming a Delta table means updating the `entityName` in the TMDL partition definition.

> **⚠️ Split cross-layer work into separate PRs.** When a change touches **both** the engineering side (notebooks / dataprod / tabular lakehouse loads under `workspace/HelixFabric-Engineering/Notebooks/`) **and** the tabular side (semantic model TMDL under `workspace/HelixFabric-Insights/*.SemanticModel/`), ship them as **two separate PRs**, not one combined PR:
>
> 1. **Engineering PR first** — land the notebook/lakehouse change so the new column or table actually exists in the tabular lakehouse and has been refreshed.
> 2. **Tabular/model PR second** — once the column is materialized upstream, wire it into the semantic model (column definition, relationship, annotations).
>
> Why: the two layers have different validation pipelines (`Validate_Notebook` vs `Validate_Tabular`), different reviewers, and different blast radius. A DirectLake model PR that references a `sourceColumn` not yet present in the lakehouse will fail validation or break the model on refresh. Keeping them separate also keeps cherry-picks during environment promotion clean. If a change is **model-only** (the field already exists in the lakehouse) or **engineering-only**, a single PR is fine.

### Semantic Model Development Workflow

Semantic model changes use a **two-tool workflow**:

1. **`semantic-model-authoring` skill** (from [Skills for Fabric](https://github.com/microsoft/skills-for-fabric)) — Use this skill for any semantic model development task: creating/editing measures, tables, relationships, columns, or working with TMDL files. Invoke it first — it provides structured guidance for semantic-model work across Power BI Desktop, PBIP projects, and the Fabric service.

2. **`powerbi-modeling-mcp` tools** — The underlying MCP server that connects to semantic models. Supports:
   - **Connect to Desktop or Fabric**: `connection_operations` (Connect, ConnectFabric, ListLocalInstances)
   - **Read model structure**: `table_operations` (List, Get, ExportTMDL), `measure_operations`, `column_operations`, `relationship_operations`
   - **Modify model**: `measure_operations` (Create, Update, Delete), `table_operations` (Create, Update), `column_operations` (Create, Update)
   - **Test DAX**: `dax_query_operations` (Execute, Validate)
   - **Performance tracing**: `trace_operations` (Start, Stop, Fetch)
   - **Deploy**: `database_operations` (DeployToFabric, ImportFromTmdlFolder, ExportToTmdlFolder)

**Workflow for making semantic model changes:**

1. Invoke the `semantic-model-authoring` skill
2. Connect to the model (local via Tabular Editor/Desktop, or Fabric service via ConnectFabric)
3. Make changes using MCP tools (measures, columns, tables, relationships)
4. Export to TMDL folder: `ExportToTmdlFolder` → writes to the workspace TMDL directory in this repo
5. **Cleanup** (see "MCP CRLF behavior" below): `git add --renormalize <path>` to strip line-ending noise
6. Review the diff (`git diff --cached`), run linter, commit

**Choose your tool by edit size:**

| Edit size | Tool |
|---|---|
| Single annotation, single description, single small DAX tweak | Edit the `.tmdl` file directly — faster, no MCP noise to clean up |
| Multiple related changes, structural changes (new table, new relationship, refactor) | `powerbi-modeling-mcp` — gets you validation + integrity checks |
| Anything that touches the AskADIA shared scaffold (`askadia/*`) | See [`askadia/MODEL_AUTHORING.md`](.deploy/workspace/askadia/MODEL_AUTHORING.md) — those files have their own merge-on-deploy semantics |

For direct TMDL edits: write valid TMDL, no schema validation will catch typos until deploy. Test with `Validate_SemanticModelTests.yml` before merging.

**⚠️ MCP CRLF behavior on Windows.** The `powerbi-modeling-mcp` TMDL serializer writes `\r\n` line endings on Windows, while this repo enforces `\n` via `.gitattributes` (`* text=auto eol=lf`). After any MCP `ExportToTmdlFolder` or save:

- `git status` will flag almost every touched file as `M` (modified) — visually noisy
- `git diff` shows nothing (git normalizes on read), and `git add` silently converts CRLF→LF on stage, so commits are clean
- BUT the noise makes "what did I actually change" hard to read

**Cleanup recipe:** Run `git add --renormalize <path>` (or `git add --renormalize .` to scope to the whole repo) immediately after any MCP save. This rewrites files to LF in both index and working tree so `git status` goes back to clean. Then `git diff --cached` shows only your intentional changes.

**Never commit MCP-touched files without first inspecting `git diff --cached`** — the file-modtime change alone can confuse diff viewers and PR reviewers even when no content changed.

### AskADIA UDF framework

A subset of HelixFabric-Insights models are "bootstrapped onto the AskADIA UDF
framework" — a shared scaffold of `Local.AskADIA.*` DAX UDFs and `_INFO_*` /
`_COPILOT_*` framework tables that the Azure Data Insights Agent
(the AskADIA runtime skills) queries at runtime. Bootstrapped today: Azure Data Insights,
Azure Data Partner & Community.

**Before touching one of these models, check whether it's bootstrapped:**
look for `.deploy/workspace/askadia/udf/models/<slug>/README.md`. If it
exists, the model has shared canonical UDFs/tables that get spliced in at
deploy from `askadia/`. **Do not hand-edit those UDFs/tables in the
per-model TMDL** — your edits will be silently overwritten on next deploy.

**Routing — where to look depending on what you're doing:**

| You need to | Read |
|---|---|
| Understand the framework end-to-end (concepts, annotations, lifecycle) | [`.deploy/workspace/askadia/README.md`](.deploy/workspace/askadia/README.md) |
| Iterate locally on framework or model code (debug-deploy) | [`.deploy/workspace/DEBUG_DEPLOY.md`](.deploy/workspace/DEBUG_DEPLOY.md) |
| Add a model test or bootstrap a new model on the framework | [`semantic_model_tests/README.md`](semantic_model_tests/README.md) + the framework README's "Bootstrapping" section |
| Understand the deploy engine (operations, configs, fabric_cicd wiring) | [`.deploy/workspace/README.md`](.deploy/workspace/README.md) |

**Key contracts** (full detail in the framework README):

- The 7 public entrypoint UDFs (`GenerateQuery`, `AnswerQuestion`,
  `Discover{Measures,Questions,Columns}`, `SearchValues`, `SearchHierarchy`)
  are the **runtime API to the AskADIA skills package**. Don't change their signatures
  without coordinating cross-repo.
- `Copilot_*` annotations on tables/columns/measures/hierarchies are the
  authoring contract — set them via `powerbi-modeling-mcp`, not by hand-
  editing TMDL.
- Eligibility for the framework is inferred from the existence of
  `askadia/udf/models/<slug>/README.md` — there's no allowlist to maintain.

---

## CI/CD & Deployment

### Branch model

This sample assumes an environment-per-branch model — a `Develop` → `Test` →
`Main` progression mapping to dev / test / production workspaces, with changes
promoted up the chain. That's just the convention these examples are written
against; **adapt the branch names and promotion flow to your own team's
process.** PRs are gated by the validation pipelines below.

### Validation pipelines (run on PR)

- **Validate_Notebook** — Runs `python -m linter lint` and validates the helixutils version bump when source changes
- **Validate_Formatting** — Prettier check for JSON/YML/YAML
- **Validate_PRName** — PR naming convention enforcement
- **Validate_Tabular** — Tabular model validation
- **Validate_SemanticModelTests** — deploys a throwaway DirectLake model, runs the DAX unit-test suite, and tears it down

### Deployment

Deployment uses the `fabric_cicd` library via `.deploy/workspace/deploy_workspace.py`:

- Deploys workspace items by type: Notebooks, Environments, Pipelines, VariableLibraries
- Environment-specific parameter substitution via `parameter.yml`
- Pre/post deployment operations defined in `.deploy/workspace/configs/`

### Environment promotion (parameter.yml)

Each workspace has a `parameter.yml` defining find/replace rules applied at
deploy time so the same source deploys to any environment:

- OneLake domain URLs (per environment: dev/test/prod)
- Workspace IDs per environment
- Lakehouse IDs per environment
- Spark capacity pool configurations

---

## Required Plugins & Skill Routing

This repository requires **two Copilot CLI plugins**. Agents **must** invoke the appropriate skill rather than manually crafting API calls or queries.

**Skill routing for this repo:**

| Task | Skill | Plugin Source |
| ---- | ----- | ------------- |
| Semantic model development (measures, tables, DAX, TMDL) | `semantic-model-authoring` | [Skills for Fabric](https://github.com/microsoft/skills-for-fabric) |
| Notebook / PySpark / lakehouse development | `spark-authoring-cli` | [Skills for Fabric](https://github.com/microsoft/skills-for-fabric) |
| Query lakehouse data (SQL) | `sqldw-consumption-cli` | [Skills for Fabric](https://github.com/microsoft/skills-for-fabric) |
| Query lakehouse data (PySpark) | `spark-consumption-cli` | [Skills for Fabric](https://github.com/microsoft/skills-for-fabric) |
| Pipeline design | `spark-authoring-cli` | [Skills for Fabric](https://github.com/microsoft/skills-for-fabric) |

### Installation

**Skills for Fabric plugin** (semantic models, notebooks, lakehouse, pipelines):

```bash
/plugin marketplace add microsoft/skills-for-fabric
/plugin install fabric-skills@fabric-skills-marketplace
```

**Power BI Modeling MCP** (the semantic-model execution layer the `semantic-model-authoring` skill drives) — register the [`microsoft/powerbi-modeling-mcp`](https://github.com/microsoft/powerbi-modeling-mcp) server in your Copilot CLI MCP config; see [RELATED-TOOLS.md](RELATED-TOOLS.md).

---

## Common Development Tasks

### Creating a New DIM/FACT Notebook

1. Create the notebook file at `workspace/HelixFabric-Engineering/Notebooks/Load_{TYPE}_{Name}.Notebook/`
2. Follow the standard template (see [Notebook Patterns](#notebook-patterns--conventions))
3. Set the environment per the [Environment Binding](#environment-binding) rules: `Env_Custom` if using `%%configure`, `Env_Default` otherwise. Look up the logical ID from the workspace's `.platform` file.
4. DIM notebooks **must** include `CheckConfig` with `isUnique` and `isComplete`
5. Write output to `connection["core_default"]` (or `restricted_core_default` for sensitive data)
6. Run the linter: `python -m linter lint ./workspace/HelixFabric-Engineering/`

### Creating a New Tabular Notebook

1. Create at `workspace/HelixFabric-Engineering/Notebooks/Tabular/Load_Tabular_{Name}.Notebook/`
2. Use `Env_Tabular` environment (look up the logical ID from the workspace's `Environments/Env_Tabular.Environment/.platform` file)
3. Use `write_delta(tabular=True)` for writes to the tabular lakehouse
4. DIM tabular notebooks must include `CheckConfig` with `isUnique` and `isComplete` on the primary key

### Renaming or Replacing a Notebook

When replacing one notebook with another (e.g., renaming `Load_STAGE_X` to `Load_FACT_X`):

1. Delete the old notebook directory (`.platform`, `notebook-content.py`, `notebook-settings.json`)
2. Create the new notebook directory with all three files
3. Check for `%run` references to the old notebook in other notebooks and update them
4. If the table name changed, update the TMDL semantic model (table definition, relationships, roles) via Tabular Editor

### Modifying helixutils

See **[When Modifying helixutils](#when-modifying-helixutils)** in the helixutils Library section for the full edit → bump → build → distribute workflow (the `Validate_Notebook` gate enforces the `VERSION` bump).

---

## Important Rules for Agents

1. **Use Skills for Fabric** — This repository has [Skills for Fabric](https://github.com/microsoft/skills-for-fabric) installed. Agents **must** use the appropriate skill for all Fabric development tasks. See the [Required Plugins & Skill Routing](#required-plugins--skill-routing) section for details.
2. **Always use helixutils APIs** — never raw `spark.read`/`spark.write`. The linter enforces this.
3. **Always run the linter** after modifying notebooks: `python -m linter lint ./workspace/HelixFabric-Engineering/`
4. **DIM tables require data quality checks** — `CheckConfig` with `isUnique` + `isComplete` on the primary key.
5. **Environment selection** — Use `Env_Tabular` for Tabular notebooks, `Env_Custom` when a `%%configure` cell is present, `Env_Default` otherwise. Look up logical IDs from the workspace's `.platform` files.
6. **Version bumps are enforced** — when modifying helixutils source, always bump `VERSION` and update wheels. The CI pipeline will reject PRs that change helixutils source without a version bump.
7. **Follow your PR naming convention** — the `Validate_PRName` gate enforces an `Environment_Description_Iteration` format in this sample; adapt it to your own convention.
8. **Retention policy** — data product writes should use `retention="2d"` unless specified otherwise.
9. **Separate PRs for cross-layer changes** — when work touches **both** the engineering side (notebooks/lakehouse) and the tabular side (semantic model TMDL), split it into two PRs (engineering first, then model). See [Cross-layer awareness](#semantic-models-helixfabric-insights). Model-only or engineering-only changes stay in one PR.

---

## Known Gaps

| Gap                            | Status                  | Notes                                                                   |
| ------------------------------ | ----------------------- | ----------------------------------------------------------------------- |
| No test suite for `helixutils` | Known — to be addressed | Many notebooks depend on this library with no automated tests           |
| Lakehouse provisioning         | Undocumented            | Lakehouses are .gitignored; provisioning happens outside source control |
