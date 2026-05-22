# LLM prompt template

Use a variation of this when driving the loop from a coding agent (Copilot CLI, Claude Code, etc.).

---

I have a Power Query M expression I want to iterate on. Use the PQTest CLI to evaluate it headlessly so my model and report are never touched.

**Setup (one-time, if not already done):**

1. Confirm PQTest is available at `~/.vscode/extensions/powerquery.vscode-powerquery-sdk-*/.nuget/Microsoft.PowerQuery.SdkTools.*/tools/PQTest.exe`. If not, install with `code --install-extension PowerQuery.vscode-powerquery-sdk`.
2. If the query hits a SQL/warehouse source, register an OAuth2 credential first using the token from `Get-AzAccessToken -ResourceUrl "https://database.windows.net"`.

**The loop:**

1. Write the proposed M to `.\test.pq`.
2. Run `PQTest.exe run-test -q .\test.pq -p` and capture the JSON output.
3. Parse the JSON:
   - If `Status == "Passed"`, summarize the first 5 rows of `Output` and the column names/types. Confirm the shape matches the intent. If it does, stop. If not, revise and re-run.
   - If `Status == "Failed"`, read `Error.Message` and `Error.Details`. Propose a fix, explain why the previous attempt failed, write the corrected M, and re-run.
4. Between iterations, show me the diff of what changed.

**Specific guidance:**

- Power Query returns `null` silently for missing column references. If my expected output has unexpected nulls, treat that as a failure even if `Status == "Passed"`.
- Cap at 10 iterations. If you haven't passed by then, stop and ask for guidance.
- If the error mentions a missing key/table and the response includes the available alternatives, use those to inform the next attempt instead of guessing.

**My goal for this M:**

<describe the transformation here — input shape, output shape, business rules, edge cases>
