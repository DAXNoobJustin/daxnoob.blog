# Iterating on Power Query with an LLM

Supporting code and examples for the [blog post of the same name](https://daxnoob.blog/iterating-on-power-query-with-an-llm/).

## Files

| File | What it is |
|---|---|
| `hello.pq` | Trivial M expression that needs no data source. Use this to confirm PQTest works. |
| `warehouse-query.pq` | Template for a query against a Fabric warehouse. Fill in your server/database/schema/table. |
| `bad-syntax.pq` | Intentional syntax error. Use to see PQTest's exact line/column reporting. |
| `bad-runtime.pq` | Intentional runtime error (missing table). PQTest returns the failing key and available alternatives. |
| `bad-types.pq` | Intentional type error (text + number). PQTest returns the operator, both types, and values. |
| `set-credential.ps1` | Helper that registers an OAuth2 credential with PQTest using your Az PowerShell session token. |
| `Invoke-PQTest.ps1` | Wrapper that finds PQTest, runs a query, and pretty-prints the result. |
| `prompt-template.md` | The prompt I use to drive an LLM through the iteration loop. |

## Quick start

```powershell
# 1. Install the Power Query SDK extension (one time)
code --install-extension PowerQuery.vscode-powerquery-sdk

# 2. Trivial test, no auth needed
.\Invoke-PQTest.ps1 -QueryFile .\hello.pq

# 3. For real data sources: edit warehouse-query.pq with your details, then
.\set-credential.ps1 -QueryFile .\warehouse-query.pq
.\Invoke-PQTest.ps1 -QueryFile .\warehouse-query.pq
```
