# Semantic-model DAX tester

A small, standalone tool for **testing Power BI / Microsoft Fabric semantic models** by
running YAML-defined DAX assertions over the **XMLA endpoint**. Give it a folder of DAX
cases, get a pass/fail report.

It runs in two modes:

- **`--model`** — test a model that is already deployed and refreshed.
- **`--deploy-from`** — publish a **disposable copy** of a `*.SemanticModel/` tree, bind
  its connections, refresh it, test it, and delete it. The thing under test is then the
  model *as it exists in the branch*, not whatever is sitting in the workspace.

It is model-agnostic — it works against any semantic model you can reach over XMLA,
Import or DirectLake — and it's built to run in CI as a **service principal**, because
XMLA isn't gated by the "Dataset Execute Queries REST API" tenant setting that often
blocks the `executeQueries` REST API.

MIT licensed.

---

## What it does

- Loads DAX **test cases** from one or more YAML catalog directories.
- Optionally publishes a throwaway copy of a model to test against (see
  [Disposable model mode](#disposable-model-mode)).
- Runs each case over the Power BI **XMLA endpoint** via the AdomdClient .NET assembly,
  loaded in-process with `pythonnet`.
- Asserts results three ways:
  - **structural** — `expected_columns`, `expected_row_count` (`exact` / `min` / `max`),
    `contains_any`, `contains_all`, `contains_none`.
  - **negative** — the query must fail and the error must match `expected_error_regex`.
  - **snapshot** — exact match against a captured value stored in a generated
    `__snapshots__/` sidecar next to each catalog file (lock the exact result, fail on drift).
- Prints a pass/fail summary and exits **0** (all pass), **1** (assertion failures), or
  **2** (fatal setup/infra error — e.g. can't reach the model). The 0/1/2 split lets a CI
  gate tell "the model regressed" apart from "the harness broke".

---

## Prerequisites

- **Windows + .NET Framework.** The AdomdClient `net45` assembly runs in-process via
  `pythonnet`, so this is a Windows tool (Windows CI agents are fine). The assembly is
  downloaded from NuGet on first use and cached under your temp dir — nothing binary is
  vendored in the repo.
- **Python 3.12+.**
- **Access to the model over XMLA**, and either an Azure CLI login (`az login`) or an
  interactive browser sign-in (`--interactive-auth`).

```powershell
pip install -r requirements.txt
az login   # or pass --interactive-auth
```

---

## Quick start

[`examples/sample.yml`](examples/sample.yml) is a reference catalog with one worked
example of each assertion category. Copy it, swap the DAX for your own model, then:

```powershell
pip install -r requirements.txt
az login   # or pass --interactive-auth

# Capture the snapshot baseline (one time), then review + commit the sidecar:
python run_tests.py --workspace-id <ws-guid> --model "Your Model" `
    --catalog-dir tests --update-snapshots

# Run the suite:
python run_tests.py --workspace-id <ws-guid> --model "Your Model" `
    --catalog-dir tests
```

### Flags

| Flag | Purpose |
|---|---|
| `--workspace-id <guid>` | Target Fabric workspace GUID (required). |
| `--model <name>` | Display name of an already-deployed model to test. Mutually exclusive with `--deploy-from`. |
| `--deploy-from <dir>` | Path to a source `*.SemanticModel/` directory; publish a throwaway copy and test that. Mutually exclusive with `--model`. |
| `--catalog-dir <dir> [<dir> ...]` | One or more catalog dirs; cases merge, IDs must be globally unique (required). |
| `--update-snapshots` | Capture current results into the `__snapshots__/` sidecars instead of asserting. |
| `--interactive-auth` | Browser sign-in instead of Azure CLI (see auth note below). |
| `--filter <substr>` | Run only cases whose `id` contains the substring. |
| `--xmla-endpoint <host>` | Override the XMLA host (default `api.powerbi.com`). |
| `--api-root <url>` | Override the Fabric API root (default `https://api.fabric.microsoft.com`). |
| `--connection-id <guid>` | Connection to bind before refreshing; repeatable. `--deploy-from` only. |
| `--refresh-type <type>` | Refresh after publish: `Full` (default), `Calculate`, `DataOnly`, `Automatic`, `None`. `--deploy-from` only. |
| `--refresh-timeout <sec>` | Override the refresh poll ceiling (default 240s Calculate / 1200s Full). `--deploy-from` only. |
| `--environment <name>` | Environment passed to fabric-cicd for `parameter.yml` selection (default `dev`). `--deploy-from` only. |
| `--keep-rls` | Keep RLS roles in the staged copy (stripped by default). `--deploy-from` only. |
| `--keep-model` | Skip teardown of the throwaway, for debugging. `--deploy-from` only. |

---

## Writing test cases

A catalog file is YAML with a `cases:` list. Every case has a globally-unique `id`, a
`category`, and a `dax` string. Fields by category:

| Field | Applies to | Meaning |
|---|---|---|
| `id` | all | Unique case id (across all loaded dirs). |
| `category` | all | `structural`, `negative`, or `snapshot`. |
| `dax` | all | The DAX query to run (usually an `EVALUATE`). |
| `description` | all | Optional human note. |
| `expected_row_count` | structural | `{ exact: N }` **or** `{ min: N, max: M }` (either bound optional). |
| `expected_columns` | structural | List of column names that must be present. |
| `contains_any` | structural | At least one of these substrings must appear in the result. |
| `contains_all` | structural | All of these substrings must appear in the result. |
| `contains_none` | structural | None of these substrings may appear in the result. |
| `expected_error_regex` | negative | The query **must** error, and the message must match this regex (matched case-insensitively). |

Unknown keys are rejected at load time, and so are keys that belong to a different category
(`expected_error_regex` on a `structural` case asserts nothing, so it's an error rather than a
silent no-op). List fields must be lists — a bare `contains_none: Error` would otherwise be
iterated character by character.

`contains_*` needles match **values** by default, so a needle can't be satisfied by a column
*name*. A needle written as `Column: value` instead matches a column-labelled view, which
targets one column:

```yaml
    contains_all: ["Category: Hardware"]   # only matches the Category column
    contains_any: ["Hardware"]             # matches any value in any column
```

```yaml
cases:
  - id: measure_resolves
    category: structural
    dax: "EVALUATE { [Total Amount] }"
    expected_row_count: { exact: 1 }

  - id: categories_present
    category: structural
    dax: "EVALUATE VALUES ( Product[Category] )"
    expected_row_count: { min: 1 }
    contains_any: ["Hardware"]

  - id: bad_measure_errors
    category: negative
    dax: "EVALUATE { [No Such Measure] }"
    expected_error_regex: "cannot be determined|not a valid|no such"
```

### Snapshot cases

A snapshot case pins the exact result. It keeps its expected value in a generated
`__snapshots__/<file>.yml` sidecar next to the catalog file (you never hand-edit it):

1. Add the case (a `snapshot` category with `dax` — no expected value in the catalog).
2. Run once with `--update-snapshots` to capture the baseline into the sidecar.
3. Review the sidecar diff and commit it — a changed snapshot is a real behavior change.
4. Every later run asserts the result is byte-for-byte unchanged.

For table snapshots, use a deterministic `ORDER BY` so the captured value is stable across
runs. Until a snapshot has a captured baseline, a normal run stops up front with exit code
**2** and tells you to run `--update-snapshots`.

---

## Disposable model mode

`--deploy-from` points at a `*.SemanticModel/` directory in your repo and runs the whole
lifecycle:

1. **Stage** — copy the TMDL tree to a temp dir, rewrite `.platform` `displayName` (and issue a
   fresh `logicalId`), and strip `definition/roles/`. The display name is the load-bearing part:
   fabric-cicd resolves an already-deployed item by **type + display name**, so publishing under a
   new name is what creates a second item rather than overwriting the source.
2. **Publish** — deploy the staged copy with [fabric-cicd](https://github.com/microsoft/fabric-cicd)
   as `TEST_<Model>_<8hex>`, with `unpublish.skip: true` so orphan cleanup can't remove other
   semantic models in the workspace.
3. **Bind** — attach each `--connection-id` to the new model. A freshly-published
   DirectLake copy has no bound connections and cannot refresh until it does.

   The connection must **already exist** in Fabric — this tool binds an existing
   connection, it never creates one. Set it up once (Fabric portal → Manage
   connections and gateways, or the Connections REST API), grab its GUID, and grant
   the test identity `Use` permission on it. `Use` is all that's needed: no read
   access on the upstream workspace. Refresh then flows through the connection's own
   identity, which is why a throwaway published into a dev workspace can still
   refresh against production data.
4. **Refresh** — Enhanced Refresh REST, polled to a terminal state. Override the poll
   ceiling with `--refresh-timeout` for a large Import model.
5. **Test** — run the catalog over XMLA, exactly as in `--model` mode.
6. **Delete** — in a `finally`. If the id was never captured (publish raised late, or the
   list call was eventually consistent) the runner re-resolves by the unique name before
   giving up, and a failed teardown exits **2** rather than reporting success. A hard kill
   can't honour a `finally`, so at scale pair this with a scheduled sweep for stray `TEST_*`
   models.

```powershell
python run_tests.py --workspace-id <ws-guid> `
    --deploy-from "MODELS/Your Model.SemanticModel" `
    --connection-id <connection-guid> `
    --catalog-dir tests
```

The service principal needs **Contributor** on the workspace for this (it creates and
deletes items), where `--model` mode only needs Viewer.

### Is this practical for your model?

It depends entirely on refresh cost, which is a storage-mode question:

- **DirectLake** — the model reads live from the lakehouse, so there is no data to load.
  A `Full` refresh just frames the tables (points them at the current Delta versions) and
  lands in seconds. Don't drop to `Calculate`: it leaves a freshly published copy unframed,
  so its tables can't be queried. A throwaway per PR is cheap, so this is the mode the
  pattern is built for.
- **Import** — the copy has to actually load its data before any data assertion can run,
  and a cold `Full` refresh on a real model runs minutes to tens of minutes. Per PR, that
  gets painful fast. Prefer `--model` against a long-lived model you refresh on your own
  schedule, and keep the per-PR suite to metadata and shape assertions, which don't need
  loaded data at all.

A refresh that succeeds proves the connections bind, the credentials work, and the upstream
schema still matches. It does **not** prove the data is there — an empty table refreshes
fine. To gate on that, assert it explicitly with a row-count case.

---

## Continuous integration

Wire this into a PR gate so a model change that breaks a contract fails the build. The
[`ci/`](ci) folder has anonymized templates:

| Template | Mode |
|---|---|
| [`azure-pipelines.example.yml`](ci/azure-pipelines.example.yml) | Test an already-deployed model. |
| [`azure-pipelines.ephemeral.example.yml`](ci/azure-pipelines.ephemeral.example.yml) | Publish a throwaway from the PR branch, test it, tear it down. |
| [`github-actions.example.yml`](ci/github-actions.example.yml) | Test an already-deployed model. |

All run on a Windows agent, sign in as a service principal, `pip install -r
requirements.txt`, and run the suite — the non-zero exit fails the build. The disposable
pattern isn't ADO-specific; the GitHub Actions template ports by swapping `--model` for
`--deploy-from` and granting the service principal Contributor.

---

## Authentication

The runner needs a token for two things: a Fabric REST call to resolve the workspace name,
and the XMLA connection itself.

- **CI / service principal:** use the default `AzureCliCredential` path (no
  `--interactive-auth`). A CI task that logs in the SP — `AzureCLI@2` in Azure DevOps,
  `azure/login` in GitHub Actions — leaves a token the tool picks up.
- **Local:** `az login`, or `--interactive-auth` for a browser sign-in.

> **Gotcha — "Authentication failed for all authenticators" on XMLA.** The Power BI XMLA
> endpoint only accepts **user** tokens issued to a *Power BI-registered* client app. A
> plain `az login` (or default SDK) token can be **rejected at connect time** even though
> it works for the Fabric REST call. Fix: use `--interactive-auth`, which mints the XMLA
> token through the well-known Power BI native client (the one DAX Studio / Tabular Editor
> use). Service principals are already approved Power BI clients, so CI is unaffected.

Other common failures: not logged in (`az login`), the SP/user not added to the workspace,
XMLA read-write disabled on the capacity, or a wrong workspace GUID / model display name.
With `--deploy-from`, also check that the caller has **Contributor** on the workspace and
`Use` on every connection passed to `--connection-id`.

---

## Layout

```text
semantic-model-tests/
├── README.md
├── requirements.txt
├── run_tests.py            the XMLA runner + assertion engine
├── test_catalog.py         offline self-test of the catalog + snapshot loader
├── lib/
│   ├── auth.py             Azure CLI / interactive-browser credential wrapper
│   ├── staging.py          copy + rebrand a TMDL tree for a throwaway publish
│   ├── deploy.py           publish the staged copy via fabric-cicd
│   ├── connections.py      item lookup, connection binding, teardown
│   └── refresh.py          Enhanced Refresh REST + poll
├── ci/                     example PR-validation pipelines (ADO + GitHub Actions)
└── examples/
    └── sample.yml          reference catalog: one case per assertion category
```

## Offline self-test

The catalog / snapshot loader has unit tests that need no Fabric access:

```bash
python test_catalog.py       # no extra dependencies
# or, if you have pytest:  python -m pytest test_catalog.py -q
```
