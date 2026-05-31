# Iterating on Power Query with an LLM

Supporting code and examples for the [blog post of the same name](https://daxnoob.blog/agentic-power-query-development/).

> **⚠️ UPDATE - read first (licensing).** These scripts use `PQTest.exe` from the Power Query SDK Tools. The license that ships with the `Microsoft.PowerQuery.SdkTools` package scopes that tool to **developing custom connectors** (and build/test automation for connectors). Using it as a general-purpose M evaluator - what this repo demonstrates - appears to fall outside that licensed purpose. I'm not a lawyer; read the license and decide for yourself. Treat this as an experiment, not a production pattern. For a supported path, use a Fabric Dataflow Gen2 and its [public APIs](https://learn.microsoft.com/fabric/data-factory/dataflow-gen2-public-apis) to edit M programmatically - though refreshing against real sources will likely require you to authorize the connections in the service.

## Files

| File | What it is |
|---|---|
| `Initialize-PQTestWorkspace.ps1` | One-time setup. Installs the SDK extension if needed, resolves the PQTest binary, and drops an `AGENTS.md` so any agent picks up the loop instructions automatically. |
| `Invoke-PQTest.ps1` | Single wrapper for all four input modes: single `.pq` file, PBIP folder, dataflow folder, or a folder of `.pq` files. Composed modes wrap every named expression into one `let` block and run the chosen target. |
| `hello.pq` | Trivial M expression that needs no data source. Use to confirm PQTest works. |
| `bad-syntax.pq` / `bad-runtime.pq` / `bad-types.pq` | Intentional failures. Use to see PQTest's structured error output. |
| `warehouse-query.pq` | Template for a query against a Fabric warehouse. Fill in your server/database/schema/table. |
| `example-project/` | A small `.pq` folder showing the project-compose pattern: `SourceUrl` parameter, `fnAgeBucket` UDF, `Issues` query, `BracketedOnly` filtered view. Hits the public GitHub API, runs anonymously. |

## Quick start

```powershell
.\Initialize-PQTestWorkspace.ps1
.\Invoke-PQTest.ps1 -QueryFile .\hello.pq
.\Invoke-PQTest.ps1 -PqFolder .\example-project -Target Issues
```

## The four modes

```powershell
# 1. Single file - run an expression as-is
.\Invoke-PQTest.ps1 -QueryFile .\hello.pq

# 2. PBIP - compose every expression and partition into one let, run the named target
.\Invoke-PQTest.ps1 -PbipPath '.\Model.SemanticModel' -Target Users

# 3. Dataflow - compose every shared binding from mashup.pq, run the named target
.\Invoke-PQTest.ps1 -DataflowPath '.\Dataflow1.Dataflow' -Target DimUserGroup

# 4. .pq folder - each file becomes one binding (filename = name), run the named target
.\Invoke-PQTest.ps1 -PqFolder .\example-project -Target Issues
```

Pass `-ShowComposed` in any composed mode to dump the unfolded `let` block next to the source (`<source>.<target>.composed.pq`). Useful for debugging.

## Credentials

PQTest caches credentials per source (DPAPI-encrypted), so you register once per machine. Pick the `-ak` (authentication kind) that matches your source:

| Source | `-ak` | Extra flags |
|---|---|---|
| Excel from disk, public web data | `Anonymous` | — |
| On-prem SQL, file shares | `Windows` | — |
| Snowflake password, REST API keys, many SaaS connectors | `Key` | `-cp Key=<secret>` |
| Excel-with-password, legacy DBs | `UsernamePassword` | `-cp Username=... -cp Password=...` |
| Anything OAuth — Power BI XMLA, Fabric warehouse, Dataverse, Graph, SharePoint | `OAuth2` | `--interactive --useMsal --useSystemBrowser` |

One gotcha: `set-credential` does static analysis on your `.pq` to find the data source. If the query builds the source dynamically (parameterised SQL, etc.), write a stub `.pq` with a literal connector call and register against that - creds are keyed by host + database, so the real query picks them up.

```powershell
'Sql.Database("yourhost.datawarehouse.fabric.microsoft.com", "yourdb")' |
    Set-Content .\_stub-warehouse.pq

& $pqtest set-credential -q .\_stub-warehouse.pq -ak OAuth2 `
    --interactive --useMsal --useSystemBrowser
```

## Agents

Once `AGENTS.md` is in the folder, point Copilot CLI, Claude Code, Cursor, or any agent that follows the AGENTS.md convention at this directory and ask it to write or change an M expression. It picks up the loop automatically.
