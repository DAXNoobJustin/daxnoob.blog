# Examples by Technique

**Consult on demand.** The UDF Reference row ({{ref:udf-reference}}) is the rules + UDF reference; the matching topic row carries the topic's routing rules. These Examples rows show how the UDFs combine into real query flows when you're unsure how to wire them together. **Part 1** is organized by **technique** — find the technique that matches the user's intent, then adapt the example to the specific topic / measure / filter. **Part 2** strings techniques together into end-to-end scenarios for common multi-step questions.

Every example follows the same two-step contract: (1) call the UDF to get a DAX string, (2) execute that string with `ExecuteQuery`. Step 2 is shown only where the rendered result matters; assume it for every example. Examples omit trailing optional args and fill earlier positions explicitly when setting a later arg.

## Contents

- [**Part 1 — UDF mechanics by technique**](#part-1--udf-mechanics-by-technique)

1. [Discover and pick (batched discovery)](#1-discover-and-pick-batched-discovery)
2. [Curated question lookup (`AnswerQuestion`)](#2-curated-question-lookup-answerquestion)
3. [Custom slice with `GenerateQuery`](#3-custom-slice-with-generatequery)
   - [3b. Cross-tab (multi-column slice)](#3b-cross-tab-multi-column-slice)
   - [3c. Picking the level within a hierarchy](#3c-picking-the-level-within-a-hierarchy)
4. [Resolve filter values (`SearchValues` vs `SearchHierarchy`)](#4-resolve-filter-values-searchvalues-vs-searchhierarchy)
   - [4a. `SearchValues` — known column](#4a-searchvalues--known-column)
   - [4b. `SearchHierarchy` — ambiguous term](#4b-searchhierarchy--ambiguous-term)
   - [4c. Disambiguate with data](#4c-disambiguate-with-data)
5. [Time-window override (Calendar columns + range predicates)](#5-time-window-override-calendar-columns--range-predicates)
6. [Sort by change (`sortMeasure` + time-intel variants + ASC)](#6-sort-by-change-sortmeasure--time-intel-variants--asc)
7. [Hierarchy walk](#7-hierarchy-walk-auto-injected-parents)
8. [DaxWrapper](#8-daxwrapper-bucketing--distribution)
   - [8b. Rank by an entity via `GROUPBY` collapse](#8b-rank-by-an-entity-via-groupby-collapse)

- **Part 2 — End-to-end scenarios** (separate row — {{ref:examples-part-2}}):

9. Combining same-column include filter + cross-column slice (with optional `!N/A` exclusion)
10. Combining a same-column equality filter with a NOT-IN exclusion
11. Recovery from common errors (not sliceable, invalid question, empty results)
12. Cross-workload substitution (batching multiple `GenerateQuery` calls)

---

## Part 1 — UDF mechanics by technique

## 1. Discover and pick (batched discovery)

**Use when:** Any new question. ALWAYS start here — one round-trip to find the right question, measure, account, and (if ambiguous) hierarchy column.

**User question:** *"Show CU consumption by workload for Contoso, last 3 months."*

**Step 1 — One `ExecuteQuery` with multiple `EVALUATE` blocks** (each returns a separate result table):

```dax
EVALUATE Local.AskADIA.DiscoverQuestions("consumption")
EVALUATE Local.AskADIA.DiscoverMeasures("CU Hours")
EVALUATE Local.AskADIA.SearchValues('Account'[Account], "contoso")
EVALUATE Local.AskADIA.SearchHierarchy("copilot", "CU Hours (28d)")  -- only when the user's term could live in multiple hierarchy levels
```

From the results: pick the curated question, confirm the AccountKey from `SearchValues`, and (if the user mentioned an ambiguous term like `"copilot"` or `"dataflow"`) use `SearchHierarchy` to resolve which column + value to filter on. `SearchHierarchy` resolves user-mentioned **values** like `"copilot"` or `"dataflow"` against multiple hierarchy levels — it does NOT resolve generic dimension labels like `"workload"` (that's what `DiscoverMeasures.ValidColumns` is for).

> **Read the matching topic row first.** Topic-specific routing rules (which measure for which intent, which column to filter on, which curated question's defaults already apply) live in the matching topic row, not here. This example shows the *batching technique*; the matching topic row tells you which measure and slice column to pick.

**Step 2 — Generate DAX:**

```dax
EVALUATE Local.AskADIA.AnswerQuestion(
    "consumption_workload_breakout", "",
    "'Account'[AccountKey]=1234567|'Calendar'[RelativeMonthNumber]>=-2",
    20
)
```

**Step 3 — `ExecuteQuery` the returned `[GeneratedDAX]`** and present results.

> **Why batch?** A single `ExecuteQuery` call accepts a `daxQueries` array (up to 4 entries), and each entry can contain multiple `EVALUATE` blocks; each block returns its own table. Batching `DiscoverQuestions + DiscoverMeasures + SearchValues + SearchHierarchy` cuts 3-4 round-trips down to one.

---

## 2. Curated question lookup (`AnswerQuestion`)

**Use when:** A curated question matches the user's intent. The framework auto-applies hardcoded filters, default filters, and the question's `HardcodedGroupBy` — so you get a correct, multi-measure answer with one call.

**User question:** *"Show me MAU by Fabric workload."*

**Step 1 — Discovery batch confirms `usage_mau_by_workload` is the right route:**

```dax
EVALUATE Local.AskADIA.DiscoverQuestions("MAU")
EVALUATE Local.AskADIA.DiscoverMeasures("MAU")
```

**Step 2 — Call the curated question, then `ExecuteQuery` the returned `[GeneratedDAX]`:**

```dax
EVALUATE Local.AskADIA.AnswerQuestion("usage_mau_by_workload")
```

> **`HardcodedGroupBy` ALWAYS appends.** The example above appends `'Usage Fabric Product'[Fabric Product]` even with empty `sliceColumns` — so the question returns one row per Fabric Product. To scope to one product, pass it in `filters`.

> **Both `DefaultFilters` and `HardcodedFilters` auto-apply.** A curated question may carry `DefaultFilters` (suppressed when you pass an overlapping value in `filters`) and `HardcodedFilters` (intersected via `KEEPFILTERS` — user values narrow within the hardcoded set; values outside it disappear). Both are visible in `DiscoverQuestions` output — NEVER re-add them in your `filters` arg.

> **Routing rule:** If `DiscoverQuestions` returns a question whose name + measures match the intent, use it. Otherwise drop to [Technique 3 (`GenerateQuery`)](#3-custom-slice-with-generatequery).

> **Multi-measure questions return all measures as columns in one row.** When a question's `Measures` list has more than one entry (for example, NPS = score + Promoter / Detractor / Passive counts), all come back side-by-side in the result.

---

## 3. Custom slice with `GenerateQuery`

**Use when:** No curated question fits — the user wants a metric you have, sliced by a dimension that no curated question groups by.

**Step 1 — Confirm the measure + sliceable column** (batch into one `ExecuteQuery`):

<!-- dax-validate: skip reason="placeholder template (angle-bracket schema not resolvable at parse time)" -->
```dax
EVALUATE Local.AskADIA.DiscoverMeasures("<measure family>")
EVALUATE Local.AskADIA.SearchValues('<Hierarchy Table>'[<Parent Level>], "<term>")
```

Confirm: the measure of interest is returned, both the parent and child columns carry the `sliceable` tag, and the exact filter value is resolved.

**Step 2 — Generate DAX:**

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "<MeasureName>",                              -- the MeasureName, NOT Alias
    "'<Hierarchy Table>'[<Child Level>]",         -- slice within the parent
    "'<Hierarchy Table>'[<Parent Level>]=<value>"
)
```

**Result:**

| `<Child Level>` | `<Measure>` |
| - | - |
| `<value 1>` | `<n1>` |
| `<value 2>` | `<n2>` |

> See the Workflow and Critical Rules row ({{ref:workflow}}) › Critical Rules for `MeasureName` vs `Alias`, bracket-stripping, and the `sliceable` tag rule.

### 3b. Cross-tab (multi-column slice)

**User question:** *"Show CU Hours by workload kind AND by capacity SKU for the last 3 months."*

Pipe-separate slice columns to get a cross-tab grain. The result is one row per combination.

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "CU Hours (28d)",
    "'Fabric Capacity Units'[Workload Kind]|'Capacity'[Capacity SKU]",
    "'Calendar'[RelativeMonthNumber]>=-2",
    100, "CU Hours (28d)"
)
```

> **Watch the row count.** Slicing by 2 columns multiplies cardinality (`Workload Kind × SKU` is easily 100+ rows). Add `rowLimit` and a `sortMeasure` so the user sees the top combinations first.

### 3c. Picking the level within a hierarchy

When a hierarchy exposes multiple sliceable levels (Group → Mid Group → Product, etc.), pick the level that matches the granularity in the user's question. Filtering at one level slices the level below by default; passing all levels in `sliceColumns` walks the full hierarchy in one shot (auto-injected parent rollups are covered in [§7](#7-hierarchy-walk-auto-injected-parents)).

> **Hierarchy levels and the right grain per ask are model + topic facts.** See the Model Reference row ({{ref:model-reference}}) › Hierarchies for the Product Master ladder, and the matching topic row for the "by product" grain rule.

---

## 4. Resolve filter values (`SearchValues` vs `SearchHierarchy`)

**Use when:** The user mentions a value that needs exact matching (account, geography) or whose hierarchy column is ambiguous (product, workload, feature).

**Decision rule:**

- **`SearchValues(column, term)`** — when you already know the column. Best for stable identifier columns (account, AccountKey, geography, fiscal month) and bounded category columns flagged `searchable` in `DiscoverMeasures` output.
- **`SearchHierarchy(term, measureName)`** — when the user's term could live in multiple hierarchy levels. Returns one row per match with `[ColumnName]` and `[MatchedValue]` already scoped to columns valid for the measure. **When in doubt, use this — it's strictly more permissive for ambiguous terms.**

### 4a. `SearchValues` — known column

**User question:** *"What's Fabric MAU for Contoso?"*

```dax
EVALUATE Local.AskADIA.SearchValues('Account'[Account], "contoso")
```

Result: a single match returning the matched account name with its `AccountKey` (and any other identifier columns the UDF surfaces). Use that AccountKey in the filter:

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "MAU", "", "'Account'[AccountKey]=1234567"
)
```

### 4b. `SearchHierarchy` — ambiguous term

**User question:** *"How much CU is Copilot using?"* — "Copilot" could live in Workload Type, Workload Kind, Artifact Kind, or Operation Name.

```dax
EVALUATE Local.AskADIA.SearchHierarchy("copilot", "CU Hours (28d)")
```

Result includes `(Workload Hierarchy, 0, Fabric Capacity Units, Workload Type, Copilot)`. Drop `[ColumnName]=[MatchedValue]` straight into `filters`:

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "CU Hours (28d)", "",
    "'Fabric Capacity Units'[Workload Type]=Copilot"
)
```

### 4c. Disambiguate with data

When `SearchHierarchy` returns matches across multiple levels (for example, "dataflow" matches `Workload Kind`, 3 `Artifact Kind` values, and many `Operation Name` values), don't just list the names — slice by the candidate column(s) and rank by the metric so the user can pick:

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "CU Hours (28d)",
    "'Fabric Capacity Units'[Workload Kind]|'Fabric Capacity Units'[Artifact Kind]",
    "'Fabric Capacity Units'[Workload Kind]=Dataflows",
    50
)
```

> **Matching is case-insensitive substring (`CONTAINSSTRING`) plus `Copilot_ValueSynonyms`** — not prefix, not stem-aware, not fuzzy. Synonyms cover common Fabric workload aliases (for example, `"warehouse"` resolves to `Data Warehousing Core`); for values without a synonym, watch trailing characters and use a shorter stem (`"warehous"` to match values ending in `-ing`). Inspect what is wired via `DiscoverColumns` › `[ValueSynonyms]`.

> **Empty result = retry with a shorter stem.** If `SearchHierarchy("term", measure)` returns only diagnostic `(no match for ...)` rows, narrow the term to a shorter substring and retry. **NEVER call `SearchHierarchy("", measure)`** — empty `searchTerm` returns no rows by design (avoids enumerating thousands of values). For broad enumeration of a single column, use `SearchValues(<column>, "")` instead.

---

## 5. Time-window override (Calendar columns + range predicates)

**Use when:** The user wants a non-default time window. Any `'Calendar'` filter suppresses the auto-window — see your model reference for the column inventory, per-column value formats, and which slices trigger an auto-window in the first place.

### 5a. Range predicate (preferred for "last N months")

```dax
-- Last 6 months MAU trend
EVALUATE Local.AskADIA.GenerateQuery(
    "MAU", "'Calendar'[Fiscal Month]",
    "'Calendar'[RelativeMonthNumber]>=-5|'Product Master'[Product]=Fabric Core"
)
```

> **Range predicate syntax** — `>=X`, `<=Y`, or `>=X..<=Y` for both bounds. The UDF auto-detects date vs. numeric and generates the right DAX (`DATE()` for dates, raw for numbers). Date variant: `'Calendar'[Calendar Date]>=2025-01-01..<=2025-03-31`.

> **One filter slot per Calendar column.** Range predicates count as one entry — much cleaner than enumerating values when you have more than 3-4 months / dates. Prefer the range predicate over an explicit value list (`-5;-4;-3;-2;-1;0`).

> **Time filter consumes one of the 8 `filters` entries.** If you need many non-time filters plus a custom window, move a dimension to `sliceColumns` and filter the result in your presentation.

---

## 6. Sort by change (`sortMeasure` + time-intel variants + ASC)

**Use when:** The user asks for "biggest", "smallest", "biggest decrease", "fastest growing", or any ranking by change rather than absolute value.

**Key insight:** `GenerateQuery` auto-returns change/prior variants for every base measure (when the model exposes them): `[<measure> MoM %]`, `[<measure> YoY %]`, `[<measure> WoW %]`, `[<measure> PM]`, `[<measure> PY]`, `[<measure> PW]`. Set `sortMeasure` to the variant column name and `sortDirection` to `"ASC"` for "smallest / worst / biggest decrease". (MTD / YTD / QTD are NOT auto-variants — they only exist as explicit measures on specific topics; use `DiscoverMeasures` to confirm and call those measures by their full name.)

### 6a. Biggest MoM decrease

**User question:** *"Which accounts have the biggest MoM drop in CU?"*

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "CU Hours (28d)",                -- BASE measure name
    "'Account'[Account]",
    "",
    10,
    "CU Hours (28d) MoM %",          -- sort by MoM % variant
    "ASC"                            -- ascending = biggest decrease first
)
```

> **ALWAYS pass the BASE measure name** to `GenerateQuery` — variants come back automatically as extra columns. NEVER pass `"MAU PY"` or `"CU Hours MoM %"` as `measureName`. The variant name only goes in `sortMeasure`.

> **Direction = intent.** `ASC` ranks smallest / biggest drop; `DESC` ranks largest / fastest growth. Same recipe as §6a with `sortMeasure="MAU YoY %"` + `sortDirection="DESC"` returns top YoY growers.

> **Pass `sortMeasure` without brackets** — `"MAU MoM %"`, NOT `"[MAU MoM %]"`.

> **Empty `sortMeasure` = first measure DESC.** Default sort works for "top N" — only override for "smallest", "biggest decrease", or to rank by a variant.

---

## 7. Hierarchy walk (auto-injected parents)

**Use when:** Slicing by a child level of an annotated hierarchy. The framework auto-prepends parent levels — but only the parents that are themselves valid sliceable columns for the measure.

**Pattern:** Pass just the child level in `sliceColumns`. The framework auto-prepends the parent levels that the chosen `<measure>` can reach. See the Model Reference row ({{ref:model-reference}}) › Hierarchies for the inventory of annotated hierarchies and their levels.

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "<measure>",                -- must list the child level (and its parents) in ValidColumns
    "<table>[<child level>]"    -- pass just the child; parents auto-inject
)
```

Both `GenerateQuery` and `AnswerQuestion` return `[AutoApplied]` — the `parents:` line lists exactly which parent columns were prepended. Surface this to the user so they understand the grouping. See the UDF Reference row ({{ref:udf-reference}}) › Reading `[AutoApplied]`.

> **Auto-injected parents include `"All"` rollup rows** — present as-is. See the UDF Reference row ({{ref:udf-reference}}) › GenerateQuery and the model reference for handling.

> **Auto-injection requires `ValidColumns` reach.** Parents auto-prepended by the helper are intersected with the measure's `ValidColumns` — parents the measure can't slice are silently skipped (no error). If you manually pass a non-sliceable parent in `sliceColumns`, validation rejects it with a `not sliceable` error. ALWAYS check `DiscoverMeasures`' `ValidColumns` before slicing.

---

## 8. DaxWrapper (bucketing / distribution)

**Use when:** The user explicitly asks for bucketing, distribution, or derived calculations that `rowLimit` / `sortMeasure` cannot achieve. Pass a DAX expression to `GenerateQuery`'s `daxWrapper` parameter (position 7) — the UDF substitutes the literal `{query}` placeholder with the validated `SUMMARIZECOLUMNS` expression. The inner query is still validated; only the outer wrapper is caller-controlled.

### 8a. MAU distribution by bucket

**User question:** *"How many accounts fall in each MAU bucket (1, 2-10, 11-100, 100+)?"*

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "MAU",
    "'Account'[Account]",
    "'Product Master'[Product]=Fabric Core",
    1000000,            -- rowLimit MUST be a real cap; 0/blank silently defaults to 100 and truncates the inner result before bucketing
    "", "",
    "VAR _Inner = {query} VAR _B = ADDCOLUMNS(_Inner, ""Bucket"", SWITCH(TRUE(), [MAU]<=1, ""1"", [MAU]<=10, ""2-10"", [MAU]<=100, ""11-100"", "">100"")) RETURN SUMMARIZE(_B, [Bucket], ""Account Count"", CALCULATE(COUNTROWS(_B)))"
)
```

The wrapper takes the per-account MAU result, classifies into buckets, and aggregates count of accounts per bucket.

> **DAX uses double-quoted strings** — when embedding a `daxWrapper` in a string literal, escape inner quotes. In DAX (which is what you pass to `ExecuteQuery`), that means doubled quotes (`""…""`).

> **The `{query}` placeholder is literal.** The UDF substitutes it with the validated `SUMMARIZECOLUMNS` expression. The inner query is still validated (measure names, columns, filters); only the wrapper is caller-controlled.

> **Use sparingly.** Only when the user explicitly asks for bucketing, distribution, or derived calculations. For ranking and limiting, prefer `sortMeasure` + `rowLimit`.

> **Malformed wrapper = error, not wrong data.** If the wrapper DAX is bad, the query fails — no silent wrong results. Read the error, fix the wrapper, retry.

### 8b. Rank by an entity via `GROUPBY` collapse

**Use when:** The user wants entity B as rows ranked by a measure, but B isn't a single sliceColumn — for example, you need to slice by `[Product]` AND `[Partner]` so the inner query resolves, then collapse to `[Partner]` for the final ranking. Pattern: keep both dims in `sliceColumns`, then collapse + rank in the wrapper.

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "<MeasureName>",
    "'<TableA>'[<DimA>]|'<TableB>'[<EntityB>]",
    "",
    1000, "", "DESC",
    "TOPN(<N>, GROUPBY({query}, '<TableB>'[<EntityB>], ""<OutColName>"", SUMX(CURRENTGROUP(), [<MeasureName>])), [<OutColName>], DESC)"
)
```

The wrapper keeps every framework safeguard live on the inner query (`DefaultFilters`, `HardcodedFilters`, `PairWith`, `AutoFilterWhenSliced`, hierarchy parent injection) while letting you reshape the output.

---