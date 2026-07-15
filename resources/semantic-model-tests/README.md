# Semantic-model DAX tester

A small, standalone tool for **testing Power BI / Microsoft Fabric semantic models** by
running YAML-defined DAX assertions against an already-deployed model over the **XMLA
endpoint**. Point it at a model, give it a folder of DAX cases, get a pass/fail report.

It is model-agnostic — it works against any semantic model you can reach over XMLA,
Import or DirectLake — and it's built to run in CI as a **service principal**, because
XMLA isn't gated by the "Dataset Execute Queries REST API" tenant setting that often
blocks the `executeQueries` REST API.

MIT licensed.

---

## What it does

- Loads DAX **test cases** from one or more YAML catalog directories.
- Runs each case over the Power BI **XMLA endpoint** via the AdomdClient .NET assembly,
  loaded in-process with `pythonnet`.
- Asserts results three ways:
  - **structural** — `expected_columns`, `expected_row_count` (`exact` / `min` / `max`),
    `contains_any`, `contains_all`.
  - **negative** — the query must fail and the error must match `expected_error_regex`.
  - **snapshot** — exact match against a captured value stored in a generated
    `__snapshots__/` sidecar next to each catalog file (lock the exact result, fail on drift).
- Prints a pass/fail summary and exits **0** (all pass), **1** (assertion failures), or
  **2** (fatal setup/infra error — e.g. can't reach the model). The 0/1/2 split lets a CI
  gate tell "the model regressed" apart from "the harness broke".

It only runs queries and assertions: the target model must already be deployed, and any
data your tests read must already be loaded (refreshed) in it.

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

## Quick start (bundled sample)

The repo ships a tiny, self-contained sample model so you can see it work end to end.
See [`examples/sample-model/README.md`](examples/sample-model/README.md) for the full
walkthrough; the short version:

```powershell
# 1. Deploy examples/sample-model/"Sales Sample.SemanticModel" to a workspace
#    (Power BI Desktop, Tabular Editor, or fabric-cicd) and refresh it once.

# 2. Capture the snapshot baseline (one time), review + commit the sidecar:
python run_tests.py --workspace-id <ws-guid> --model "Sales Sample" `
    --catalog-dir examples/sample-model/tests --update-snapshots

# 3. Run the suite:
python run_tests.py --workspace-id <ws-guid> --model "Sales Sample" `
    --catalog-dir examples/sample-model/tests
```

Point it at your own model by passing your workspace GUID + model display name and a
folder of your own catalog files.

### Flags

| Flag | Purpose |
|---|---|
| `--workspace-id <guid>` | Target Fabric workspace GUID (required). |
| `--model <name>` | Target semantic model display name (required). |
| `--catalog-dir <dir> [<dir> ...]` | One or more catalog dirs; cases merge, IDs must be globally unique (required). |
| `--update-snapshots` | Capture current results into the `__snapshots__/` sidecars instead of asserting. |
| `--interactive-auth` | Browser sign-in instead of Azure CLI (see auth note below). |
| `--filter <substr>` | Run only cases whose `id` contains the substring. |
| `--xmla-endpoint <host>` | Override the XMLA host (default `api.powerbi.com`). |

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
| `expected_error_regex` | negative | The query **must** error, and the message must match this regex (matched case-insensitively). |

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

## Continuous integration

Wire this into a PR gate so a model change that breaks a contract fails the build. The
[`ci/`](ci) folder has anonymized templates for **Azure DevOps**
([`azure-pipelines.example.yml`](ci/azure-pipelines.example.yml)) and **GitHub Actions**
([`github-actions.example.yml`](ci/github-actions.example.yml)). Both run on a Windows
agent, sign in as a service principal, `pip install -r requirements.txt`, and run the
suite — the non-zero exit fails the build.

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

---

## Layout

```text
semantic-model-tests/
├── README.md
├── requirements.txt
├── run_tests.py            the XMLA runner + assertion engine (one file)
├── test_catalog.py         offline self-test of the catalog + snapshot loader
├── lib/
│   └── auth.py             Azure CLI / interactive-browser credential wrapper
├── ci/                     example PR-validation pipelines (ADO + GitHub Actions)
└── examples/
    └── sample-model/       a runnable, self-contained model + its test catalog
```

## Offline self-test

The catalog / snapshot loader has unit tests that need no Fabric access:

```bash
python test_catalog.py       # no extra dependencies
# or, if you have pytest:  python -m pytest test_catalog.py -q
```
