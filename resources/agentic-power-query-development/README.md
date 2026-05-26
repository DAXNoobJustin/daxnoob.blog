# Iterating on Power Query with an LLM

Supporting code and examples for the [blog post of the same name](https://daxnoob.blog/agentic-power-query-development/).

## Files

| File | What it is |
|---|---|
| `Initialize-PQTestWorkspace.ps1` | One-time setup. Installs the SDK extension if needed, resolves the PQTest binary, and drops an `AGENTS.md` so any agent picks up the loop instructions automatically. |
| `Invoke-PQTest.ps1` | Wrapper that finds PQTest, runs a single `.pq` file, and pretty-prints the result. |
| `Invoke-PQTestComposed.ps1` | Same idea, but resolves `// #include <file>` comments first so you can split a real project across many fragments. |
| `hello.pq` | Trivial M expression that needs no data source. Use this to confirm PQTest works. |
| `bad-syntax.pq` | Intentional syntax error. Use to see PQTest's exact line/column reporting. |
| `bad-runtime.pq` | Intentional runtime error (missing table). PQTest returns the failing key and available alternatives. |
| `bad-types.pq` | Intentional type error (text + number). PQTest returns the operator, both types, and values. |
| `warehouse-query.pq` | Template for a query against a Fabric warehouse. Fill in your server/database/schema/table. |
| `_project.pq` | Example shared-definitions fragment (parameters + a UDF + two queries) showing how to capture a real project's M graph in one file. Not a valid standalone M expression. |
| `query-most-recent.pq` | Example consumer of `_project.pq` via `// #include`. Runs against live GitHub data, no credentials needed beyond an Anonymous web cred. |

## Quick start

```powershell
# 1. One-time setup: installs the SDK extension, writes AGENTS.md
.\Initialize-PQTestWorkspace.ps1

# 2. Trivial test, no auth needed
.\Invoke-PQTest.ps1 -QueryFile .\hello.pq
```

## Connecting to a real data source

PQTest stores credentials per data source kind + path. You only register them once per machine; they persist (DPAPI-encrypted) in `%LOCALAPPDATA%\Microsoft\PQTest\credentials.bin`.

Pick the `-ak` (authentication kind) that matches your source:

| Source | `-ak` | Extra flags |
|---|---|---|
| Excel from disk, public web data | `Anonymous` | — |
| On-prem SQL, file shares | `Windows` | — |
| Snowflake password, REST API keys, many SaaS connectors | `Key` | `-cp Key=<secret>` |
| Excel-with-password, legacy DBs | `UsernamePassword` | `-cp Username=... -cp Password=...` |
| Anything OAuth — Power BI XMLA, Fabric warehouse, Dataverse, Graph, SharePoint | `OAuth2` | `--interactive --useMsal --useSystemBrowser` |

For OAuth-based sources the `--interactive` flow pops a system browser and signs you in for real. For Power BI XMLA in particular this is the only flow that works — handing PQTest a pre-fetched bearer token will be rejected by the XMLA endpoint.

One gotcha: `set-credential` does static analysis on your `.pq` file to find the data source. If your query builds the source path or SQL dynamically (very common for parameterised queries), it can't see it. Workaround: write a tiny stub `.pq` that just calls the connector with literal arguments and register against that. Credentials are keyed by host + database, so all your real queries will pick them up.

```powershell
# Example: register an OAuth credential for a Fabric warehouse
'Sql.Database("yourhost.datawarehouse.fabric.microsoft.com", "yourdb")' |
    Set-Content .\_stub-warehouse.pq
& $pqtest set-credential -q .\_stub-warehouse.pq -ak OAuth2 `
    --interactive --useMsal --useSystemBrowser
```

## Composing a real project

PQTest evaluates one M expression per file. Real Power Query projects have parameters, UDFs, and many cross-referencing queries. `Invoke-PQTestComposed.ps1` handles this by resolving `// #include <file>` comments before evaluation:

```powershell
.\Invoke-PQTestComposed.ps1 -QueryFile .\query-most-recent.pq
.\Invoke-PQTestComposed.ps1 -QueryFile .\query-most-recent.pq -ShowComposed   # writes the unfolded file alongside
```

How to map a PBIX/dataflow into this layout:

1. Open Advanced Editor for each parameter, function, and query in your project.
2. Drop them all into a single `_project.pq` as `name = expression,` bindings (see the example file). Order does not matter — `let` is lexically scoped, bindings can reference each other in any direction.
3. Per query you want to test, create a small `.pq` file whose body is `let // #include _project.pq <maybe-some-extra-steps> in <name>`.

The wrapper splices `_project.pq` into the `let` block at evaluation time, so `name` and friends are in scope. Includes nest, so you can split `_project.pq` further (e.g. `_params.pq`, `_udfs.pq`, `_queries.pq`) and include each from a shared parent.

## Agents

Once `AGENTS.md` is in the folder, point Copilot CLI, Claude Code, Cursor, or any agent that follows the AGENTS.md convention at this directory and ask it to write or change an M expression. It will pick up the loop automatically.
