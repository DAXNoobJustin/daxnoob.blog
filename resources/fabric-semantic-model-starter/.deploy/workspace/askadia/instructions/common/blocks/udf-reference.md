# UDF Reference

## UDF Reference

All queries go through 7 public UDFs on the semantic model. This section is a lookup reference — see the Workflow row ({{ref:workflow}}) for when and how to use each UDF.

> All UDFs are namespaced under `Local.AskADIA.` — call as `Local.AskADIA.DiscoverQuestions(...)`, etc. Headers below omit the prefix for readability; code examples include it.

> **Optional parameters.** Bracketed args are optional. Prefer omitting trailing args, such as `DiscoverMeasures()`, `GenerateQuery("MAU")`, or `GenerateQuery("MAU", sliceColumns, filters, 50)`. To set a later arg, fill earlier positions explicitly (`""` for strings). Comma-skipping is valid but discouraged. Defaults: strings `""`, `rowLimit` `100`, `sortDirection` `DESC`.

> **MCP `ExecuteQuery` arguments:** `artifactId` (the artifact you are operating on — the model you discovered / are connected to for this question; use that GUID, not one quoted in any reference text) + `daxQueries` (array of DAX strings; each entry, and each `EVALUATE` block within an entry, returns its own table). **Max 4 entries per array** — to batch more, combine multiple `EVALUATE` blocks into a single string. NOT `daxQuery` (singular) or `datasourceId`.

### Discovery UDFs

#### DiscoverQuestions([searchTerm])

Find curated questions with their IDs, measures, required filters, and valid columns. Output is a `Topics in scope:` map (topic → facts) followed by per-fact sections grouped alphabetically by fact; each fact header shows its topic tag(s) inline (`; topics: a, b`). `searchTerm` substring-matches QuestionId, Topic, Question, Description, and the underlying measures' name/table/desc/alias/synonyms — pass a topic name (the model's Topic index lists them) to surface every fact carrying that topic.

```dax
EVALUATE Local.AskADIA.DiscoverQuestions("")
-- Pass "" for all questions, or a search term to filter
```

#### DiscoverMeasures([searchTerm])

Find available measures with their valid columns. Output is a `Topics in scope:` map (topic → facts) followed by per-fact sections grouped alphabetically by fact; each fact header shows its topic tag(s) inline (`; topics: a, b`). Facts can be multi-tagged (for example, a fact carrying both `usage` and `consumption`). Each column shows tags: `searchable` (has `SearchValues` support), `sliceable` (can use in `sliceColumns`), `hierarchy` (part of a curated hierarchy ladder — supports `SearchHierarchy`). All listed columns are filterable via the `filters` string. `searchTerm` matches MeasureName, MeasureTable, MeasureDescription, Alias, Synonyms, FactDescription, and Topic — pass a topic name to list every measure on facts carrying that topic.

```dax
EVALUATE Local.AskADIA.DiscoverMeasures("MAU")
```

> **MeasureName vs Alias:** `DiscoverMeasures` returns one `Value` column with formatted text — each measure entry leads with its bracketed name (`[Fabric MAU] — ...`) and may include `Alias: <short name>`. The bracketed name is the **MeasureName** — that's what `GenerateQuery` and `sortMeasure` require, NOT the alias. Example: pass `"Net Promoter Score 28d"` (MeasureName), not `"NPS_28d"` (Alias). Strip the brackets when passing — `DiscoverQuestions` shows measures bracketed too (`Measures: [Fabric MAU]`); same rule applies.

> **`DefaultFilters:` and `HardcodedFilters:` annotation lines** in each measure entry document what the framework will auto-apply for that measure. See [Filter override rules](#filter-override-rules) for the canonical override semantics; see [Reading `[AutoApplied]`](#reading-autoapplied) for the runtime audit of what fired.

#### DiscoverColumns([searchTerm])

Find available columns with descriptions, data types, synonyms, and tags (`searchable`, `sliceable`, `hierarchy` — same meaning as in `DiscoverMeasures`). Use when you need column details beyond what `DiscoverMeasures` shows — descriptions, data types, or to discover columns for a specific table or topic. Prefer `DiscoverMeasures` for metric work; use `DiscoverColumns` to inspect specific dimensions.

```dax
EVALUATE Local.AskADIA.DiscoverColumns("geographic")
```

#### SearchValues(column, searchTerm)

Search for specific values in a column. **First parameter is a column reference, not a string.**

```dax
EVALUATE Local.AskADIA.SearchValues('Account'[Account], "contoso")
```

#### SearchHierarchy(searchTerm, measureName)

Resolve a value when the filter column is **ambiguous or unknown** — the typical case when the user says **"give me \<measure> for \<X>"** and `X` is a product, workload, feature, or ability name. Scoped to tables reachable by the measure. Output: `(Ladder, Position, TableName, ColumnName, MatchedValue)` — drop `[ColumnName]=[MatchedValue]` straight into `filters`. Use `SearchValues` instead when the column is already known (a `searchable`-tagged column from `DiscoverMeasures`).

```dax
EVALUATE Local.AskADIA.SearchHierarchy("dataflow", "CU Hours (28d)")
```

> Only columns tagged `hierarchy` in `DiscoverMeasures` / `DiscoverColumns` are searched. If a measure has no hierarchy columns, `SearchHierarchy` returns nothing — use `SearchValues` on a specific column. See the Examples rows ({{ref:examples-part-1}}, {{ref:examples-part-2}}) § 4 for matching semantics (case-insensitive substring), no-match recovery, and worked disambiguation flows.

### Query Generation UDFs

#### GenerateQuery(measureName, [sliceColumns], [filters], [rowLimit], [sortMeasure], [sortDirection], [daxWrapper])

Generate DAX for a single measure with automatic time-intelligence variants (MoM%, YoY%, etc.). **ALWAYS pass the BASE measure name** — variants come back automatically as extra columns. To rank by a variant, use `sortMeasure` (see Sort behavior below).

```dax
EVALUATE Local.AskADIA.GenerateQuery(
    "MAU",                                                          -- measureName (from DiscoverMeasures)
    "'Calendar'[Fiscal Month]",                                     -- [sliceColumns] (pipe-delimited; omit for none)
    "'Product Master'[Product]=Fabric Core|'Account'[AccountKey]=1234567"  -- [filters] (pipe-delimited 'Tbl'[Col]=val; omit for none)
)
```

**Sort behavior:** Default = first measure DESC; see [UDF Argument Conventions › `sortMeasure`](#udf-argument-conventions) for variant names. Use `sortDirection="ASC"` for "smallest" / "worst" / "biggest decrease" questions.

**Hierarchy auto-injection:** When `sliceColumns` has a child level of an annotated hierarchy, parent levels that are also sliceable for the measure are auto-prepended. If the measure can't reach a parent at all, the call errors with "not sliceable". Reported via `parents:` in `[AutoApplied]`. See the model reference's **Key Dimensions › Hierarchies** subsection for the available hierarchies.

> **`"All"` rollup rows.** Auto-injected parent levels include an `"All"` row — by design for non-additive measures (distinct-count MAU/WAU): the rollup is the true cross-leaf distinct count, not a sum. Do NOT de-duplicate or sum over `"All"` rows when presenting.

**DaxWrapper (position 7, optional):** See [§UDF Argument Conventions › `daxWrapper`](#udf-argument-conventions) for full semantics. TL;DR: pass `""` for standard behavior; pass a DAX expression with `{query}` placeholder when you need bucketing, custom TOPN, or derived columns.

**Returns:** Two columns — `[GeneratedDAX]` (DAX string for `ExecuteQuery`) and `[AutoApplied]` (see [Reading `[AutoApplied]`](#reading-autoapplied) below).

#### AnswerQuestion(questionId, [sliceColumns], [filters], [rowLimit], [sortMeasure], [sortDirection])

Generate DAX for a curated question. Automatically applies hardcoded and default filters defined in the model.

> **Required filters still apply.** If a question declares required filters, you must supply them in `filters` even on the short form — otherwise the call returns a validation error naming the missing columns. Check `DiscoverQuestions` output first.

```dax
EVALUATE Local.AskADIA.AnswerQuestion(
    "revenue",                       -- questionId (from DiscoverQuestions)
    "'Calendar'[Fiscal Month]",      -- [sliceColumns] (pipe-delimited; omit for defaults)
    "'Account'[AccountKey]=1234567"         -- [filters] (pipe-delimited 'Tbl'[Col]=val; omit for none)
)
```

**Returns:** Two columns — `[GeneratedDAX]` (DAX string for `ExecuteQuery`) and `[AutoApplied]` (see [Reading `[AutoApplied]`](#reading-autoapplied) below).

**Curated question metadata** (`DefaultFilters`, `HardcodedFilters`, `HardcodedNotInFilters`, `HardcodedGroupBy`) shows up in `DiscoverQuestions` output with the same auto-apply behavior as measure-level annotations. See [Filter override rules](#filter-override-rules) for the canonical semantics; see [Reading `[AutoApplied]`](#reading-autoapplied) for the runtime audit. **Worked overrides:** the Examples rows ({{ref:examples-part-1}}, {{ref:examples-part-2}}) § 2.

**Sort behavior:** Same `sortMeasure` / `sortDirection` semantics as `GenerateQuery`; the "first measure" is the question's first listed measure (for example, `revenue` ranks by `[Consumed + Adjusted Revenue (YTD)]`). For multi-section orchestrator questions, `sortMeasure` applies only to sections where the measure is valid; others fall back to their first measure.

### Reading `[AutoApplied]`

Newline-separated `key: value` log returned by both `GenerateQuery` and `AnswerQuestion`. Read it after every call (Critical Rule 6).

| Key | What it means | Example value |
| - | - | - |
| `parents:` | Hierarchy parent levels auto-prepended to the slice | `'Fabric Capacity Units'[Workload Type]` |
| `defaults:` | Measure-level (`GenerateQuery`) or question-level (`AnswerQuestion`) `DefaultFilters` applied unless overridden. Overridden entries remain on this line tagged `(suppressed by user)` so you can see what the framework would have applied. | `'Calendar'[Azure Closed Month Flag]=True` |
| `hardcoded:` | `HardcodedFilters` applied unconditionally (`KEEPFILTERS`); orchestrator sections concatenated with `;` | `'Fabric Survey'[Survey Scope]=NPS` |
| `hardcodedNotIn:` | Question-level `Copilot_HardcodedNotInFilters` (excludes listed values) | `'Persona'[Persona]=N/A` |
| `hardcodedGroupBy:` | Question-level `Copilot_HardcodedGroupBy` appended to `sliceColumns` | `'Usage Fabric Product'[Fabric Product]` |
| `wrapper:` | `daxWrapper` argument applied around the inner query (`GenerateQuery` only) | `TOPN(5, {query}, [MAU], DESC)` |
| `pairs:` | `Copilot_PairWith` companion columns auto-added to the slice — slicing by one member of a configured pair brings the other along (for example, slicing by `Account` adds `AccountKey` so both names and IDs come back). Symmetric. | `'Account'[AccountKey]` |
| `autoFilters:` | `Copilot_AutoFilterWhenSliced` sticky-default filters auto-injected because the slice touches a trigger column. Suppressed when any user, default, or hardcoded filter touches the trigger column's table. Multi-section orchestrators concatenate with `; ` (no dedup). See your model reference's **Calendar** subsection for which autoFilters are configured (most common: the trailing-13-month window). | `'Calendar'[RelativeMonthNumber]=TREATAS({-12,...,0}, 'Calendar'[RelativeMonthNumber])` |

Empty string = nothing was auto-applied. Common surprises: a `defaults:` or `hardcoded:` line the agent didn't expect, or a `(suppressed by user)` tag on a `defaults:` entry your filter overrode.

### Filter override rules

The framework auto-applies four annotation kinds; user `filters` / `sliceColumns` interact with them as follows. **Question-level beats measure-level on shared columns** (the question's default suppresses the measure's default).

| Annotation kind | Source | When passed in `filters` (same column) | When passed in `sliceColumns` (same column) |
| - | - | - | - |
| `DefaultFilters` | Measure or question | **Overridden** by user value | **Suppressed** silently |
| `HardcodedFilters` | Measure or question | **Intersected** (`KEEPFILTERS`): user values inside the hardcoded set survive; outside values disappear | **Intersected**: group restricted to values inside the hardcoded set |
| `HardcodedNotInFilters` | Question only | **Cannot be suppressed** (ALWAYS excludes); user filter passes through | **Cannot be suppressed**; user slice passes through |
| `HardcodedGroupBy` | Question only | n/a | ALWAYS appended (as `sliceColumns`); same-column `DefaultFilters` therefore suppressed |

Net: pass user values in `filters` to override defaults; pass in `sliceColumns` to drop them. `HardcodedFilters` can NEVER be broadened — only narrowed within the hardcoded set.

### Filter vs Slice Columns

`DiscoverMeasures` output shows tags on each column:

- **No tag** — column is **filterable only** (not marked `sliceable`). Use in the `filters` string to restrict results.
- **`sliceable`** — column is **filterable AND sliceable**. Can also use in `sliceColumns` to GROUP BY.

**Rule:** Only put columns marked `sliceable` in `sliceColumns`. Any listed column can go in the `filters` string.

### UDF Argument Conventions

- **Empty string `""`** for unused optional string arguments (`sliceColumns`, `filters`, `sortMeasure`, `sortDirection`, `daxWrapper`) when you need to fill an earlier optional position to set a later one. Use exactly `""` — NEVER `" "`, `NULL`, or `BLANK()`
- **Pipe-delimited `|`** for multiple slice columns: `"'Calendar'[Fiscal Month]|'Geography'[Area]"` (up to 8 entries)
- **`filters` is a single string** with **pipe-delimited entries** in the form `'Table'[Column]=value` — for example `"'Product Master'[Product]=Fabric Core|'Account'[AccountKey]=1234567"` (up to 8 entries).
- **Multi-value (IN list)** — separate values with `;` *inside* one entry: `"'Product Master'[Product]=Power BI Premium;Power BI Embedded - A SKUs"`. The UDF converts this to `TREATAS({val1, val2, ...}, col)`.
- **NOT-IN filters** — prefix the first value with `!` or `!=`: `"'Product Master'[Product]=!Shared AI Services;Shared DI Services"`.
- **Range filters** — `>=` / `<=` operators for numeric or date ranges (cleaner than enumerating with `;`); single-bound or both-bound with `..` separator; ISO dates auto-detected. Examples: `"'Calendar'[RelativeMonthNumber]>=-5"`, `"'Calendar'[RelativeMonthNumber]>=-5..<=0"`, `"'Calendar'[Calendar Date]>=2025-01-01..<=2025-03-31"`. See the Examples rows ({{ref:examples-part-1}}, {{ref:examples-part-2}}) § 5.
- **Internal whitespace in filter values is preserved verbatim** — for example, `'Account'[Account]=Some  Vendor  Inc` keeps the double spaces. Don't trim values yourself; the UDF handles only column-name whitespace.
- **Column references** use full DAX syntax: `'Table'[Column]`
- **Filter values** are strings — even numeric account keys: `"'Account'[AccountKey]=1234567"`
- **rowLimit** is an integer controlling max rows returned
- **rowLimit** of `0` (or any value `< 1`) defaults to `100`
- **sortMeasure** (optional, position 5) — name of a measure to sort by. Valid values: any measure in the query, or its time-intelligence variants (`base`, `base MoM %`, `base YoY %`, `base WoW %`, `base PM`, `base PY`, `base PW`). Pass without brackets (for example, `"MAU MoM %"` not `"[MAU MoM %]"`). Empty string `""` = first measure.
- **sortDirection** (optional, position 6) — `"DESC"` (default) or `"ASC"`. Use ASC for "smallest", "worst", "biggest decrease" questions.
- **daxWrapper** (optional, position 7, `GenerateQuery` only) — `""` for standard behavior. Pass a DAX expression with `{query}` placeholder to wrap the generated SUMMARIZECOLUMNS. The inner query is validated first; the wrapper is applied after. Use for bucketing, custom TOPN logic, or adding derived columns. Example: `"TOPN(5, {query}, [MAU], DESC)"`. **Quote-escaping warning:** the wrapper string is itself a DAX literal, so embedded `"` MUST be doubled (`""Label""`), not backslash-escaped. Wrappers without literal strings (`FILTER`, `TOPN`, arithmetic) avoid the issue — prefer those when possible.