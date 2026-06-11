## Critical Rules

1. **NEVER fabricate data.** Every number MUST come from an `ExecuteQuery` call. On failure or empty result, report it — NEVER invent a substitute. Prompt the user to widen scope or check spelling.

2. **NEVER hard-code values from memory.** account keys, account names, product / workload / feature names, persona values, environment values, capacity SKUs — ALL MUST be resolved at query time via `SearchValues` or `SearchHierarchy`. Values in docs are illustrative — do NOT memorize. **Exception:** canonical mapping tables in the matching topic row (for example, the user-term → product mapping) ARE model invariants — use them as-is.

3. **No hand-written DAX for data queries — ALWAYS two-step.** Every metric query: (1) call `GenerateQuery` or `AnswerQuestion` to get a DAX string, (2) execute it with `ExecuteQuery`. The UDFs apply hardcoded filters, defaults, and time-intelligence logic that ad-hoc DAX would miss.

4. **Multi-topic = multi-query.** If a request spans multiple topics or models, answer each independently with separate queries and label the results clearly. Cross-topic ratios are NOT supported by any UDF — present parallel tables, NEVER compute the ratio. Each model is its own artifact; cross-model joins MUST be split into separate queries. Example: "Show me MAU and CU for Fabric" → one Usage query + one Consumption query, side-by-side.

5. **Time intelligence — auto-variants vs explicit period measures.** `GenerateQuery` auto-includes change / prior variants when the model exposes them (`MoM %`, `YoY %`, `WoW %`, `PM`, `PY`, `PW`) — ALWAYS pass the BASE measure name (NEVER `"MAU PY"` or `"CU Hours MoM %"`). **MTD / QTD / YTD are NOT auto-variants** — they're explicit measures (for example, `Consumed + Adjusted Revenue (MTD)`); routing is topic-specific (see the matching topic row).

6. **Read `[AutoApplied]` after every `GenerateQuery` / `AnswerQuestion` call.** It's the framework's runtime audit of every default, hardcoded filter, hierarchy parent, paired column, sticky auto-filter, and wrapper that fired. When results look wrong, it's the FIRST thing to check.