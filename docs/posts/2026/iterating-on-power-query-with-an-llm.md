---
title: "Agentic Power Query Development"
description: "Let an LLM write, run, and self-correct Power Query M on its own using PQTest, without ever touching your PBIX, dataflow, or semantic model."
draft: true
date:
  created: 2026-05-22
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
slug: iterating-on-power-query-with-an-llm
image: assets/images/posts/iterating-on-power-query-with-an-llm/hero.png
---

<!-- TODO: hero image — diagram of M file -> PQTest -> JSON -> LLM loop, or terminal screenshot of a passing PQTest run -->

## The problem

A teammate recently sent me a PBIX with four source tables full of overlapping data that needed to be reshaped into a clean star schema. The catch was that there were no clean keys to join on. Identifying the same entity across sources meant trying a sequence of matches: first columns A and B, then a fuzzy match on C if that didn't hit, and so on.

I hadn't written serious Power Query in a while, and I have been leaning on GitHub Copilot for most of my day-to-day dev work, so I wanted to see if I could just hand this off and have the LLM iterate on the M for me.

## What I tried first

My first thought was the [Power BI modeling MCP](https://github.com/microsoft/fabric-pbi-modeling-mcp). It can read and write a model's partitions and named expressions over the wire, so in theory I could just point an agent at it and let it iterate. The problem is that to actually *see* what the M produces, you have to apply the change and refresh the model. Every iteration would either break the report sitting on top, or force me into a throwaway PBIX. Not great.

So I spun up a sandbox Fabric Dataflow Gen2 and let the LLM use the [public APIs](https://learn.microsoft.com/fabric/data-factory/dataflow-gen2-public-apis) to push new M definitions and trigger refreshes. This actually worked really well. The LLM did the full build of the consolidated queries inside the dataflow, and once everything looked right I copied the final M back into the PBIX. For that specific project it was the right call anyway, because the transformations were going to live in a dataflow long term.

But the loop is slow (30 to 60 seconds per refresh), and there is no dry-run mode. `updateDefinition` always commits, so you really do need a sandbox workspace if you don't want to nuke a real artifact mid-iteration. After shipping the dataflow I went looking for something lighter weight that didn't require a service round-trip at all.

## PQTest

If you have the [Power Query SDK extension](https://marketplace.visualstudio.com/items?itemName=PowerQuery.vscode-powerquery-sdk) installed in VS Code, you already have a CLI called `PQTest.exe` bundled inside it. Point it at a `.pq` file and it evaluates the M against your real data sources and prints the result as JSON. No PBIX, no Desktop, no dataflow, no model.

The [official docs](https://learn.microsoft.com/power-query/sdk-tools/pqtest-overview) are mostly written for custom-connector authors, but the CLI doesn't care where the M is eventually going to live. PBIX, semantic model, dataflow, notebook, custom connector — it just evaluates the expression and gives you back the rows. You can iterate on the transformation first and pick the destination later.

Install it:

```bash
code --install-extension PowerQuery.vscode-powerquery-sdk
```

The binary lands at a path like:

```text
%USERPROFILE%\.vscode\extensions\powerquery.vscode-powerquery-sdk-0.7.1-win32-x64\.nuget\Microsoft.PowerQuery.SdkTools.2.154.1\tools\PQTest.exe
```

(Versions change; the pattern is stable.)

## Hello world

```powershell title="hello.pq"
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

The important part is that `Output` is the actual evaluated result. PQTest ran the query and materialized the rows. About a second on this trivial example, and nothing downstream was touched.

## Talking to real data

For anything that hits a remote source, you have to register a credential first. For a Fabric warehouse with Entra auth, I grab a token from Az PowerShell and inject it as an `OAuth2` credential:

<!-- TODO: screenshot — terminal output of PQTest running against a warehouse, showing real rows in the Output array -->

```powershell
Import-Module Az.Accounts
$token = (Get-AzAccessToken -ResourceUrl "https://database.windows.net").Token

$cred = @{
  AuthenticationKind = "OAuth2"
  AuthenticationProperties = @{
    AccessToken = $token
    Expires     = (Get-Date).AddHours(1).ToString("r")
    RefreshToken = ""
  }
  PrivacySetting = "None"
  Permissions    = @()
} | ConvertTo-Json -Depth 5

$cred | & $pqtest set-credential -q .\warehouse-query.pq
```

PQTest stores the credential in `%LOCALAPPDATA%\Microsoft\PQTest\credentials.bin`, encrypted with Windows DPAPI tied to your user account. Same security model as Windows Credential Manager, fine to leave on disk between runs, only readable by you.

After that, `run-test` actually hits the warehouse and returns rows. Same JSON shape as the hello-world example, just with real data inside `Output`. About four seconds end-to-end for a small query.

## What makes this useful for an LLM

When the query fails, PQTest gives back a structured error the LLM can parse and self-correct on.

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

The LLM can fix and retry without another round trip to ask you what went wrong. That is what actually makes the loop work.

## The loop

```mermaid
flowchart LR
    A[LLM writes M] --> B[Save .pq file]
    B --> C[PQTest run-test]
    C --> D{Status?}
    D -- Passed --> E[Inspect Output]
    D -- Failed --> F[Read Error.Details]
    F --> A
    E --> G{Looks right?}
    G -- No --> A
    G -- Yes --> H[Ship it]
```

A typical inner loop is a few seconds. For the user-group consolidation work, the LLM landed the final transformation in around 20 iterations over maybe ten minutes of wall time. The source PBIX was never touched.

## Where the result lives

PQTest is the iteration tool. When the M is good, you still need to put it somewhere it actually runs. A few sensible options:

- **Push it into a PBIX or semantic model** via the modeling MCP's named-expression and partition operations.
- **Publish it as a Fabric Dataflow Gen2** if it needs to be shareable, scheduled, or queried by multiple consumers.
- **Have your PBIX connect to a published dataflow** if you want one canonical source feeding several reports.

The point is that iteration is decoupled from the destination. Test fast and locally, decide where it lives last.

## Bonus: PQTest in CI

The same CLI runs in build pipelines. Pre-deploy validation, regression tests using `PQTest compare` against an expected `.pqout` file, schema contracts — all worth wiring up if your team is treating Power Query like real code.

## What I'm shipping with this post

Code samples are in the [resources folder for this post on GitHub](https://github.com/DAXNoobJustin/daxnoob.blog/tree/main/resources/iterating-on-power-query-with-an-llm): the `.pq` files (including the failing examples above), a credential bootstrap script, a wrapper that pretty-prints results, and the prompt I use to drive the loop with an agent.

## Wrapping Up

The friction of "I need to refresh the model to see what my Power Query produces" has been baked into how we work with Power Query for so long that it took an LLM use case to push me to look for something better. PQTest was the answer the whole time, bundled inside a VS Code extension most of us only ever crack open when writing a custom connector.

If your team is doing anything serious with Power Query, give it a try. Even without an LLM in the loop, being able to evaluate an M expression and see real rows back without a model attached is a nice quality-of-life upgrade.

Like always, if you have any questions or feedback, please reach out. I'd love to hear from you!
