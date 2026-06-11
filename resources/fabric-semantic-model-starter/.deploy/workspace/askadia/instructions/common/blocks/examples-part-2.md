
## Part 2 — End-to-end scenarios

The scenarios below string Part 1 techniques together. Each shows the **full flow** — topic load → discovery → resolution → query → recovery — for a realistic ask. Use these as templates when an ask spans multiple techniques.

---

## 9. Combining same-column include filter + cross-column slice (with optional `!N/A` exclusion)

**Why this is non-trivial (technique focus):** This example shows how to combine a **same-column include filter** with an optional **`!N/A` exclusion** on a pivot column — and when each pattern applies. (For *which* column is the pivot vs. the slice for any given measure, read the topic overview.)

**Step 1 — Discovery (read the matching topic row first):**

```dax
EVALUATE Local.AskADIA.DiscoverMeasures("<measure family>")
EVALUATE Local.AskADIA.DiscoverQuestions("<topic>")
```

`DiscoverMeasures` returns the `MeasureName` and the columns it can be sliced by.

**Step 2 — Generate DAX. Pivot column gets the include filter; slice column goes in `sliceColumns`:**

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "<MeasureName>",
    "'<Pivot Table>'[<Pivot Col>]",                  -- the dimension you want to break the result down by
    "'<Filter Table>'[<Filter Col>]=<value>"         -- include filter on a different column
)
```

**Step 3 — `ExecuteQuery`** the returned `[GeneratedDAX]`.

> **Same-column include + `!N/A` exclude is redundant.** Picking a specific value on a column already excludes `N/A` on that column. Only add `'<Table>'[<Column>]=!N/A` when you intentionally want **all named values together** (omit the include filter, keep the exclude). This is a generic pattern — applies to any column.

---

## 10. Combining a same-column equality filter with a NOT-IN exclusion

**Why this is non-trivial (technique focus):** Two filters on different columns joint in one `filters` arg, where one filter is a **NOT-IN list** (prefix the first excluded value with `!`, semicolon-separate the rest). Pipe-separates filter clauses across columns. (For *whether* a given measure auto-applies a state filter for you, read the topic overview.)

**Step 1 — Discovery (read the matching topic row first):**

```dax
EVALUATE Local.AskADIA.DiscoverMeasures("<measure family>")
```

`DiscoverMeasures` returns the measure and the columns it can be sliced by.

**Step 2 — Generate DAX. Pipe-separate filter clauses across columns; use NOT-IN syntax for the exclusion list:**

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "<MeasureName>",
    "'<Slice Table>'[<Slice Col>]",
    "'<State Table>'[<State Col>]=<state>|'<Slice Table>'[<Slice Col>]=!<excluded 1>;<excluded 2>"
)
```

**Step 3 — `ExecuteQuery`** and present results.

> **NOT-IN syntax recap.** Prefix the first value with `!` (or `!=`); later values use `;` as the separator inside the same filter entry. The UDF generates `NOT IN { ... }` semantics. `=!A;B;C` excludes A, B, AND C.

> **Filter clause separator.** Use `|` to combine clauses across **different** columns in one `filters` arg. Within one column's clause, `;` separates IN-list values.

---

## 11. Recovery from common errors (not sliceable, invalid question, empty results)

The framework returns specific, actionable errors. Recover by re-querying the discovery UDFs once — NEVER guess. See the Error Handling section in the Output, Formatting, Error Handling row ({{ref:output-formatting}}) for the full tactic catalog.

- **`not sliceable` error** → wrong measure for the column. Re-run `DiscoverMeasures("<topic>")` and pick a measure whose `ValidColumns` includes the target column. If no measure on the topic can slice it, the dimension isn't reachable from this topic — rephrase the question.
- **`Unknown questionId` error** → curated ID typo or stale ID. Run `DiscoverQuestions("<fragment>")` and use the returned ID. NEVER guess curated question IDs.
- **0 rows on a query that ought to have data** → triage in order: (1) value typo — `SearchValues` / `SearchHierarchy` is case-insensitive substring, NOT stem-aware (`"warehouse"` ≠ `"Warehousing"`; use `"warehous"`); (2) window too narrow — widen with `'Calendar'[RelativeMonthNumber]>=-N`; (3) wrong column — retry with `SearchHierarchy(term, measure)` to get the correct `[ColumnName]`.

> **Empty ≠ "no data".** A blank result almost ALWAYS means the wrong filter, wrong column, or wrong window — not that the underlying data doesn't exist. Recover with a discovery call before reporting "no data" to the user.

---

## 12. Cross-workload substitution (batching multiple `GenerateQuery` calls)

**Use when:** The user wants the **same shape** of metric across two or more values that don't combine cleanly into a single sliced query — typically two specific workloads, two specific accounts, or two specific time windows you want to make side-by-side.

**User question:** *"Show me CU Hours over the last 6 months for `copilot` vs `warehousing` — I want to compare their trends."*

**Why batch instead of slice:** A single `GenerateQuery` sliced by `[Workload Type]` returns both workloads in one long table — the user wanted two **side-by-side trend tables**. Two separate `GenerateQuery` calls produce two parallel tables you can present under their own headings.

**Step 1 — Resolve workload values via `SearchHierarchy`** (NEVER hard-code workload names from memory — the canonical values may differ from how the user phrased them):

```dax
EVALUATE Local.AskADIA.SearchHierarchy("copilot", "CU Hours (28d)")
EVALUATE Local.AskADIA.SearchHierarchy("warehousing", "CU Hours (28d)")
```

→ Each call returns canonical values for the filter strings below — for example `Copilot` and `Data Warehousing Core` at `[Workload Type]`. Pull the resolved value from `[MatchedValue]`; NEVER type the canonical name from memory.

**Step 2 — Batch both `GenerateQuery` calls in one `ExecuteQuery`** (pass each as a separate `daxQueries` array entry — keeps each result table cleanly mapped to its workload):

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "CU Hours (28d)", "'Calendar'[Fiscal Month]",
    "'Fabric Capacity Units'[Workload Type]=Copilot|'Calendar'[RelativeMonthNumber]>=-5",
    20
)
```

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "CU Hours (28d)", "'Calendar'[Fiscal Month]",
    "'Fabric Capacity Units'[Workload Type]=Data Warehousing Core|'Calendar'[RelativeMonthNumber]>=-5",
    20
)
```

Each call returns its own `[GeneratedDAX]` string. Pass both as separate entries in the next `ExecuteQuery` call's `daxQueries` array — both data tables come back in one round-trip.

**Step 3 — Present:**

> **Copilot:**
>
> \| Fiscal Month | CU Hours | MoM % |
> \| … |
>
> **Data Warehousing Core:**
>
> \| Fiscal Month | CU Hours | MoM % |
> \| … |

> **Caps:** `ExecuteQuery.daxQueries` accepts up to 4 array entries. To compare more than 4 values side-by-side, slice by the dimension column instead and let `SUMMARIZECOLUMNS` group naturally.