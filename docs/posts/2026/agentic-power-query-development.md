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
slug: agentic-power-query-development
image: assets/images/posts/agentic-power-query-development/hero.png
---

## The problem

A teammate recently sent me a PBIX with four source tables full of overlapping data that needed to be reshaped into a clean star schema. There were no clean keys to join on, so identifying the same entity across sources meant trying a sequence of matches: first columns A and B, then a fuzzy match on C if that didn't hit, and so on.

I hadn't used Power Query in a while, and I have been leaning on GitHub Copilot for most of my day-to-day dev work, so I wanted to see if I could just hand this off and have the LLM figure out the M for me.

## What I tried first

I knew I could use the [Power BI modeling MCP](https://github.com/microsoft/fabric-pbi-modeling-mcp) since it can read and write a model's partitions and M expressions, but it requires you to apply the change and refresh the model, possibly breaking the report sitting on top.

So I spun up a sandbox Fabric Dataflow Gen2 and let the LLM use the [public APIs](https://learn.microsoft.com/fabric/data-factory/dataflow-gen2-public-apis) to push new M definitions and trigger refreshes. It worked really well - the LLM did the full build of the consolidated queries inside the dataflow, and once everything looked right I copied the final M back into the PBIX.

I asked Copilot if there was something lighter weight that I could use in the future for similar projects that didn't require me to spin up a dataflow and this is what it found.

## PQTest

The [Power Query SDK extension](https://marketplace.visualstudio.com/items?itemName=PowerQuery.vscode-powerquery-sdk) for VS Code ships with a CLI called `PQTest.exe`. Point it at a `.pq` file and it evaluates the M against your real data sources and prints the result as JSON. No PBIX, no Desktop, no dataflow, no model.

The [official docs](https://learn.microsoft.com/power-query/sdk-tools/pqtest-overview) are mostly written for custom-connector authors, but we can repurpose `PQTest.exe` to enable Copilot to test all PQ changes before we even need to write it back to the target artifact. It can iterate over changes and have the exe evaluate the expression and give you back the rows.

Install the extension:

```bash
code --install-extension PowerQuery.vscode-powerquery-sdk
```

The binary lands at a path like:

```text
%USERPROFILE%\.vscode\extensions\powerquery.vscode-powerquery-sdk-0.7.1-win32-x64\.nuget\Microsoft.PowerQuery.SdkTools.2.154.1\tools\PQTest.exe
```

(Versions change; the pattern is stable.)

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

The important part is that `Output` is the materialized result of evaluating the query. PQTest ran it against the source and returned the rows. About a second on this example.

## Connecting to real data

For anything that hits a remote source, you have to register a credential first. For a Fabric warehouse with Entra auth, I grab a token with Az PowerShell and pass it in as an `OAuth2` credential:

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

PQTest stores the credential in `%LOCALAPPDATA%\Microsoft\PQTest\credentials.bin`, encrypted with Windows DPAPI tied to your user account. Same security model as Windows Credential Manager.

After that, `run-test` hits the warehouse and returns rows. Same JSON shape as the hello-world example, just with real data inside `Output`.

## What makes this useful for an LLM

When the query fails, PQTest returns a structured error the LLM can parse and self-correct against.

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

The LLM can fix and retry without another round trip to ask you what went wrong.

For the user-group consolidation work, the LLM landed the final transformation in about 20 iterations over ten minutes. Each loop was a few seconds, and the source PBIX was never touched.

## Wrapping Up

Code samples are in the [resources folder for this post on GitHub](https://github.com/DAXNoobJustin/daxnoob.blog/tree/main/resources/agentic-power-query-development): the `.pq` files (including the failing examples above), a wrapper that pretty-prints results, and a bootstrap script that installs the SDK extension and drops an `AGENTS.md` so any agent that follows the convention picks up the loop on its own.

If your team is doing anything serious with Power Query, definitely check out PQTest. Even without an LLM, being able to evaluate an M expression and see real rows back without a model/dataflow is awesome.

Like always, if you have any questions or feedback, please reach out. I'd love to hear from you!
