---
title: "Agentic Power Query Development"
description: "An experiment in letting an LLM write, run, and self-correct Power Query M on its own with PQTest - including the licensing caveats and the supported alternative."
draft: false
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

!!! danger "UPDATE: read this before you try it"

    **Update (May 2026):** after I first published this, I went back and dug into the licensing and the supported alternatives.

    This post uses `PQTest.exe` from the **Power Query SDK Tools** to evaluate arbitrary Power Query M. The license that ships with that tool (the `Microsoft.PowerQuery.SdkTools` package) scopes it to **developing custom connectors** with the Power Query SDK, and to build or automated-test processes *for developing connectors*. Using it as a general-purpose M evaluator - which is exactly what I do in this post - appears to fall outside that licensed purpose (though using it to test custom connectors, as intended, would be fine).

    I'm not a lawyer so you should read the license yourself and make your own call. Treat everything here as a **fun experiment** and not something to lean on for production.

    If you want a path that's actually supported: spin up a Fabric **Dataflow Gen2** and use its [public APIs](https://learn.microsoft.com/fabric/data-factory/dataflow-gen2-public-apis) to push and edit your M programmatically. Two caveats from my own testing - to refresh against real sources you'll likely need to go into the service and **authorize the connections yourself**, and API-triggered refresh of CI/CD dataflows is documented as unreliable - the API accepts the request and starts a job, but the job doesn't actually refresh your data. If someone figures out how to use dataflows to fully work end to end, please let me know!

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

For anything that hits a remote source, you have to register a credential first.

Which command depends on the source kind:

| Source | `-ak` | Extra flags |
|---|---|---|
| Excel from disk, public web data | `Anonymous` | — |
| On-prem SQL, file shares | `Windows` | — |
| Snowflake password, REST API keys, many SaaS connectors | `Key` | `-cp Key=<secret>` |
| Excel-with-password, legacy DBs | `UsernamePassword` | `-cp Username=... -cp Password=...` |
| Anything OAuth — Power BI XMLA, Fabric warehouse, Dataverse, Graph, SharePoint | `OAuth2` | `--interactive --useMsal --useSystemBrowser` |

For OAuth sources the `--interactive` flow pops a system browser, you sign in, PQTest caches the token.

One gotcha worth knowing about: `set-credential` does static analysis on your `.pq` to find the data source, so if your query builds the source path or SQL dynamically it can't see it. The fix is a stub `.pq` with a literal connector call - creds are keyed by host + database, so the real query picks it up:

```powershell
'Sql.Database("yourhost.datawarehouse.fabric.microsoft.com", "yourdb")' |
    Set-Content .\_stub-warehouse.pq

& $pqtest set-credential -q .\_stub-warehouse.pq -ak OAuth2 `
    --interactive --useMsal --useSystemBrowser
```

## Composing a real project

PQTest evaluates one M expression per file, but real projects often have parameters, functions, and a bunch of queries that reference each other.

`Invoke-PQTest.ps1` in the resources folder handles this with three input modes (raw pq files, pbip, and dataflow) that all produce the same thing: read every named expression out of the source, wrap them in one `let` block, run the target you asked for. The source of truth stays in the original artifact until you are ready to write the changes back.

```powershell
# PBIP: parses expressions.tmdl + tables/*.tmdl
.\Invoke-PQTest.ps1 -PbipPath '.\Model.SemanticModel' -Target Users

# Dataflow Gen2: parses mashup.pq (a section doc)
.\Invoke-PQTest.ps1 -DataflowPath '.\Dataflow1.Dataflow' -Target DimUserGroup

# Folder of .pq files: each file is one named binding, filename = name
.\Invoke-PQTest.ps1 -PqFolder .\example-project -Target Issues
```

If you pass `-ShowComposed`, the wrapper will write the unfolded `let` block next to the source so you can see exactly what PQTest received. This can help with debugging.

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
