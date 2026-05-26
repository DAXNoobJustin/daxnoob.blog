# Iterating on Power Query with an LLM

Supporting code and examples for the [blog post of the same name](https://daxnoob.blog/agentic-power-query-development/).

## Files

| File | What it is |
|---|---|
| `Initialize-PQTestWorkspace.ps1` | One-time setup. Installs the SDK extension if needed, resolves the PQTest binary, and drops an `AGENTS.md` so any agent picks up the loop instructions automatically. |
| `hello.pq` | Trivial M expression that needs no data source. Use this to confirm PQTest works. |
| `warehouse-query.pq` | Template for a query against a Fabric warehouse. Fill in your server/database/schema/table. |
| `bad-syntax.pq` | Intentional syntax error. Use to see PQTest's exact line/column reporting. |
| `bad-runtime.pq` | Intentional runtime error (missing table). PQTest returns the failing key and available alternatives. |
| `bad-types.pq` | Intentional type error (text + number). PQTest returns the operator, both types, and values. |
| `set-credential.ps1` | Helper that registers an OAuth2 credential with PQTest using your Az PowerShell session token. |
| `Invoke-PQTest.ps1` | Wrapper that finds PQTest, runs a query, and pretty-prints the result. |

## Quick start

```powershell
# 1. One-time setup: installs the SDK extension, writes AGENTS.md
.\Initialize-PQTestWorkspace.ps1

# 2. Trivial test, no auth needed
.\Invoke-PQTest.ps1 -QueryFile .\hello.pq

# 3. For real data sources: edit warehouse-query.pq with your details, then
.\set-credential.ps1 -QueryFile .\warehouse-query.pq
.\Invoke-PQTest.ps1 -QueryFile .\warehouse-query.pq
```

Once `AGENTS.md` is in the folder, point Copilot CLI, Claude Code, Cursor, or any agent that follows the AGENTS.md convention at this directory and ask it to write or change an M expression. It will pick up the loop automatically.
