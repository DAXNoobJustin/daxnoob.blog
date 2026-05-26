---
title: "Agentic Power Query Development"
description: "Let an LLM write, run, and self-correct Power Query M on its own using PQTest, without ever touching your PBIX, dataflow, or semantic model."
draft: true
date:
  created: 2026-05-26
categories:
  - Power Query
tags:
  - Power Query
  - Microsoft Fabric
  - Power BI
  - LLM
  - Copilot
authors:
  - justinmartin
slug: agentic-power-query-development
image: assets/images/posts/agentic-power-query-development/hero.png
---

## The problem

A teammate recently sent me a PBIX with four source tables full of overlapping data that needed to be reshaped into a clean star schema. There were no clean keys to join on, so identifying the same entity across sources meant trying a sequence of matches: first columns A and B, then a fuzzy match on C if that didn't hit, and so on.

I hadn't used Power Query in a while, and I have been leaning on GitHub Copilot for most of my day-to-day dev work, so I wanted to see if I could just hand this off and have the LLM figure out the M for me.

## What I tried first

I knew I could use the [Power BI modeling MCP](https://github.com/microsoft/fabric-pbi-modeling-mcp) since it can read and write a model's partitions and M expressions, but it requires you to apply the change and refresh the model, possibly breaking the report sitting on top.

So I spun up a sandbox Fabric Dataflow Gen2 and let the LLM use the [public APIs](https://learn.microsoft.com/fabric/data-factory/dataflow-gen2-public-apis) to push new M definitions and trigger refreshes. It worked really well - the LLM did the full build of the queries inside the dataflow, and once everything looked right I copied the final M back into the PBIX.

I asked Copilot if there was something lighter weight that I could use in the future for similar projects that didn't require me to spin up a dataflow and this is what it found.

## PQTest

The [Power Query SDK extension](https://marketplace.visualstudio.com/items?itemName=PowerQuery.vscode-powerquery-sdk) for VS Code ships with a CLI called `PQTest.exe`. Point it at a `.pq` file and it evaluates the M against your real data sources and prints the result as JSON.

The [official docs](https://learn.microsoft.com/power-query/sdk-tools/pqtest-overview) are mostly written for custom-connector authors, but we can repurpose `PQTest.exe` to enable Copilot to test all PQ changes before we even need to write it back to the target artifact. It can iterate over changes and have the exe evaluate the expression and give you back the rows.

Install the extension:

```bash
code --install-extension PowerQuery.vscode-powerquery-sdk
```

The binary lands at a path like:

```text
%USERPROFILE%\.vscode\extensions\powerquery.vscode-powerquery-sdk-0.7.1-win32-x64\.nuget\Microsoft.PowerQuery.SdkTools.2.154.1\tools\PQTest.exe
```

Grab it into a variable so the rest of the snippets in this post work as-is:

```powershell
$pqtest = Get-ChildItem "$env:USERPROFILE\.vscode\extensions\powerquery.vscode-powerquery-sdk-*\.nuget\Microsoft.PowerQuery.SdkTools.*\tools\PQTest.exe" |
          Sort-Object FullName -Descending |
          Select-Object -First 1 -ExpandProperty FullName
```

## Hello world

```text title="hello.pq"
let
    Source = #table({"id", "name", "score"}, {
        {1, "Alice",   95},
        {2, "Bob",     82},
        {3, "Charlie", 77}
    }),
    Filtered = Table.SelectRows(Source, each [score] > 80)
in
    Filtered
```

```powershell
& $pqtest run-test -q .\hello.pq -p
```

Returns:

```json
[{
  "Status": "Passed",
  "RowCount": 2,
  "Output": [
    {"id": 1, "name": "Alice", "score": 95},
    {"id": 2, "name": "Bob",   "score": 82}
  ]
}]
```

The important part is that `Output` is the materialized result of evaluating the query. PQTest ran it against the source and returned the rows.

## Connecting to real data

For anything that hits a remote source, you have to register a credential first. PQTest stores creds per data source kind + path in `%LOCALAPPDATA%\Microsoft\PQTest\credentials.bin`, encrypted with Windows DPAPI tied to your user account. Same security model as Windows Credential Manager. You only register once per machine.

Which command depends on the source. `-ak` (authentication kind) is the switch:

| Source | `-ak` | Extra flags |
|---|---|---|
| Excel from disk, public web data | `Anonymous` | — |
| On-prem SQL, file shares | `Windows` | — |
| Snowflake password, REST API keys, many SaaS connectors | `Key` | `-cp Key=<secret>` |
| Excel-with-password, legacy DBs | `UsernamePassword` | `-cp Username=... -cp Password=...` |
| Anything OAuth — Power BI XMLA, Fabric warehouse, Dataverse, Graph, SharePoint | `OAuth2` | `--interactive --useMsal --useSystemBrowser` |

For OAuth-based sources the `--interactive` flow pops a system browser, you sign in for real, PQTest caches the token (including a refresh token). For Power BI XMLA in particular this is the only flow that works — pre-fetched bearer tokens get rejected by the XMLA endpoint.

One gotcha: `set-credential` does static analysis on your `.pq` file to find the data source. If your query builds the source path or SQL dynamically (very common — parameterised queries, dynamic schemas), it can't see it and you get `Unable to determine data source from expression`. Workaround is to write a tiny stub `.pq` that just calls the connector with literal arguments and register the credential against that. Credentials are keyed by host + database, so all your real queries pick them up.

```powershell
# Stub: just enough M for set-credential to identify the source
'Sql.Database("yourhost.datawarehouse.fabric.microsoft.com", "yourdb")' |
    Set-Content .\_stub-warehouse.pq

& $pqtest set-credential -q .\_stub-warehouse.pq -ak OAuth2 `
    --interactive --useMsal --useSystemBrowser
```

After that, `run-test` against any query that hits the same warehouse returns data in the same JSON shape as the hello-world example.

## Composing a real project

PQTest evaluates one M expression per file. Real Power Query projects are bigger than one expression — they have parameters, functions, and many queries that reference each other by bare name. You need a way to take that whole graph and present it to PQTest as a single `let` block.

The `Invoke-PQTestComposed.ps1` wrapper in the resources folder does exactly this. It treats `// #include <file>` comments as a preprocessor instruction — before PQTest runs, every include line is replaced with the contents of the referenced file. Includes nest, so you can layer them.

Mapping a real PBIX or dataflow into this layout is mechanical:

1. **Open Advanced Editor** for each parameter, function, and query in your project. Copy the M.
2. **Drop each one into `_project.pq`** as a `name = expression,` binding. Order does not matter — `let` is lexically scoped, so a query can call a UDF defined below it, a UDF can call a query defined above it, anything goes. This file is a *fragment* — it ends in a comma and is not valid standalone M. Don't try to run it directly.
3. **Per query you want to test**, create a small `.pq` file like this:

```text title="query-most-recent.pq"
let
    // #include _project.pq

    MostRecent5 = Table.FirstN(
        Table.Sort(IssuesTyped, {{"CreatedAt", Order.Descending}}),
        5
    )
in
    MostRecent5
```

Run it with:

```powershell
.\Invoke-PQTestComposed.ps1 -QueryFile .\query-most-recent.pq
```

Pass `-ShowComposed` and the wrapper also writes a `query-most-recent.composed.pq` next to the source — that's the fully unfolded file PQTest actually evaluated, useful when something behaves unexpectedly and you want to see exactly what the engine saw.

For larger projects you can split `_project.pq` further (`_params.pq`, `_udfs.pq`, `_queries.pq`, ...) and include them all from a parent fragment. The wrapper resolves recursively and detects cycles.

## What makes this useful for an LLM

The main benefit: the LLM can keep editing and testing M without touching your target artifact and without a human in the loop. Once the M looks right, it can write the changes back to the target dataflow, PBIX, or model using the modeling MCP or dataflow APIs.

The other main benefit is error handling. When a query fails, PQTest returns a structured error the LLM can parse and self-correct against.

**Syntax error**, with exact line and column:

```json
{"Status": "Failed", "Error": { "Message": "Token Literal expected. Start position: (2, 134)..." }}
```

**Runtime error**, with the failing key *and* the available alternatives:

```json
{
  "Status": "Failed",
  "Error": {
    "Message": "The key didn't match any rows in the table.",
    "Details": {
      "Key": "[Schema = \"X\", Item = \"DOES_NOT_EXIST\"]",
      "Table": "#table({\"Name\",\"Schema\",\"Item\",\"Kind\"}, {...})"
    }
  }
}
```

**Type error**, with the operator, both types, and both values:

```json
{
  "Status": "Failed",
  "Error": {
    "Message": "We cannot apply operator + to types Text and Number.",
    "Details": {"Operator":"+","Left":"hello","Right":5}
  }
}
```

The LLM can fix and retry without another round trip to ask you what went wrong after you published the changes.

## Wrapping Up

Code samples are in the [resources folder for this post on GitHub](https://github.com/DAXNoobJustin/daxnoob.blog/tree/main/resources/agentic-power-query-development): the `.pq` files (including the failing examples above), a wrapper that pretty-prints results, and a bootstrap script that installs the SDK extension and creates an `AGENTS.md`.

If your team is using Power Query as any part of your data architecture, definitely check out PQTest. Even without an LLM, being able to evaluate an M expression and see real rows back without needing to go through a model/dataflow is pretty cool. I'm sure there are many other creative use cases for PQTest. 

Like always, if you have any questions or feedback, please reach out. I'd love to hear from you!
