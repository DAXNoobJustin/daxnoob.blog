# AskADIA Model Authoring Guide

A practical guide for **model owners** — the people who own a specific
AskADIA-bootstrapped semantic model (Azure Data Insights, Azure Data Partner
& Community, or any future model) and who
keep it useful as the underlying data evolves.

You're in the right place if you need to:

- Decide which `Copilot_*` annotations to put on a new column, measure,
  hierarchy, or table.
- Add or refine a curated question in your model's `copilot_questions.json`.
- Add or refine model instruction rows under `instructions/models/<slug>/`.
- Decide whether your model needs a per-model ranker UDF, and write one if so.
- Sanity-check a change end-to-end before opening a PR.

You're in the **wrong** place (those are framework-maintainer territory) if
you want to:

- Add or change a `Copilot_*` annotation **type** itself (the UDFs that
  read annotations are part of the framework contract).
- Change the canonical UDFs in `askadia/udf/common/functions.tmdl`.
- Modify the deploy pipeline (`process_orchestrator.py`, host `operations/`, or the
  framework's own `askadia/deploy/` ops).
- Add a new framework table.

Those topics live in [`README.md`](README.md) (the framework spec) and
[`../README.md`](../README.md) (the deploy infra). Come back here when
you're ready to author your model's content again.

---

## Contents

- [Authoring workflow](#authoring-workflow)
- [The four things you can change](#the-four-things-you-can-change)
- [TMDL object descriptions (`///`)](#tmdl-object-descriptions-)
- [`Copilot_*` annotation reference](#copilot_-annotation-reference)
- [Authoring a curated question](#authoring-a-curated-question)
- [Per-model ranker UDFs](#per-model-ranker-udfs)
- [Validating your change locally](#validating-your-change-locally)
- [Ship checklist](#ship-checklist)

---

## Authoring workflow

Instruction content is single-source in this repo under
`instructions/models/<slug>/model.json` plus `instructions/models/<slug>/rows/*.md`.
Shared wording lives in `instructions/common/blocks/*.md`, and `routing.json`
declares model order for cross-model routing. Do not edit generated instruction
artifacts directly.

At deploy, `setup_askadia_framework` renders that store into the model's
`_COPILOT_INSTRUCTIONS` table and the model description. Separately,
`instructions/emit_router.py` renders the thin router preview at
`instructions/generated/adia-router.SKILL.md` for review/drift checks.

The UDF overlay remains the source for runtime query helpers:

| Runtime surface | Source you edit |
|---|---|
| Model/topic guidance and routes | `instructions/models/<slug>/model.json` + `rows/*.md` |
| Shared instruction blocks | `instructions/common/blocks/*.md` |
| Curated questions returned by `DiscoverQuestions` / `AnswerQuestion` | `udf/models/<slug>/copilot_questions.json` |
| Ranked/enriched value search | `udf/models/<slug>/functions.tmdl` plus `Copilot_SearchRanker` annotations |
| Discover/search eligibility | `Copilot_*` annotations in the model TMDL |

For 360-style orchestrators, keep the multi-section curated question in
`copilot_questions.json` and describe when to use it in the matching instruction
row. The deployed agent consumes the generated instruction table/router and the
AskADIA UDFs; there is no manual topic or `SKILL.md` sync step.

---

## The four things you can change

| Change | Owned in | When |
|---|---|---|
| Apply or update a `Copilot_*` annotation on a column / measure / hierarchy / table | HelixData — model TMDL via `powerbi-modeling-mcp` | Adding a new table or column to the model; changing what the agent can search / slice / discover |
| Add or edit an instruction row or route | HelixData — `askadia/instructions/models/<slug>/model.json` + `rows/*.md` | The agent needs new or clearer model/topic guidance, routing triggers, or worked examples |
| Add or edit a curated question | HelixData — `askadia/udf/models/<slug>/copilot_questions.json` | New canonical question pattern emerges from real usage; existing question shape needs tightening |
| Add or change a per-model ranker UDF | HelixData — `askadia/udf/models/<slug>/functions.tmdl` | Adding a multi-attribute searchable entity (account, partner, capacity) where bare-string matching isn't enough |

What you **cannot** do as a model owner:

- Add a new `Copilot_*` annotation **type** (e.g. invent `Copilot_RequireApproval`).
  The UDFs that read annotations are framework code — extending the
  annotation surface requires a UDF change. File an ask with the framework
  maintainer.
- Change a canonical UDF body or signature. Framework territory.
- Change which annotations render as Tags / Behavior in `DiscoverColumns`
  output — that's the annotation registry (`askadia_config.json.annotationRegistry`),
  framework territory.

---

## Editing the instruction store (topics, routes, new models)

The per-model **instruction store** — `instructions/models/<slug>/model.json`
plus `instructions/models/<slug>/rows/<anchor>.md` — is the single source of
truth for what the model teaches the agent and how it routes. `model.json` is a
small registry: a top-level `title`, an ordered `rows[]` list, and
`workedExamples`. Each row carries an `anchor`, the model's own topic-index
metadata (`topic` / `whenToUse` / `routerHint`), and a `route` — the clean
cross-model routing name + triggers. `route.name` ("Usage") is intentionally
distinct from the row `topic` ("Usage Topic") and `routerHint`; never derive one
from another.

The trailing **`out-of-scope` row has no `rows/out-of-scope.md`** — its body is
generated at emit time (`_core/routing.py` › `render_out_of_scope`). It is a slim,
model-agnostic deny/reroute **decision rule** that points back at the always-on
guidance for the actual lists: this model's supported topics live in the generated
**Topic index**, and the siblings (title + GUID + their topics) live in the
**Other Ask ADIA models — reroute** section. The row no longer restates either
list (that would duplicate two always-on sections that can drift), so there is
nothing to hand-author here.

**Add a topic to an existing model**
1. Add a row to `model.json` `rows[]` (before the trailing `out-of-scope` row),
   with `anchor`, `topic`, `whenToUse`, `routerHint`, and a
   `route: {name, triggers}`. Use `"route": null` only for a structural row that
   should never be routed to. *(A row that omits `route` entirely fails the
   deploy loudly — deliberate, so a forgotten route can't silently drop a topic.)*
2. Write the row body at `rows/<anchor>.md`.
3. If a worked example should reference it, add the anchor under `workedExamples`.
4. Regenerate goldens (below).

**Change a route's `name` / `triggers`, or a model's `title`**
Edit the field in `model.json`, then regenerate goldens. Nothing else to touch —
descriptions and the cross-model reroute section are derived from these.

**Add a new model**
1. Create `instructions/models/<new-slug>/model.json` (+ `rows/`) and the UDF
   overlay `udf/models/<new-slug>/` (with `README.md` — its presence is what
   bootstraps the model onto the framework).
2. Add `<new-slug>` to `routing.json` `modelOrder` (deploy fails loud if a model
   exists on disk but is missing from `modelOrder`).
3. Add the model's per-env dataset GUIDs to `config/model_guids.yml` (every
   environment — there is no fallback).
4. Regenerate goldens.

**Regenerate goldens after any of the above**

```sh
cd .deploy/workspace/askadia/instructions
python emit_router.py --update-golden     # refresh generated/adia-router.SKILL.md
python -m pytest test_roundtrip.py -q      # invariants incl. emit/router goldens
```

The model TMDL + `instructions.md` router are emitted fresh at deploy, and are
not source-controlled on the model. Drift is pinned by a `golden` sha256 map in
each model's `model.json` (one hash per emitted file), refreshed with
`emit_model.py --slug <slug> --update-golden` after an intentional content
change; `test_roundtrip.py` re-emits and asserts the bytes match those hashes.
The thin cross-model router preview (`generated/adia-router.SKILL.md`) is the
only committed emitted artifact; CI/tests run `emit_router.py --check` and fail
if it drifts.

---

## TMDL object descriptions (`///`)

Every annotated object (table, column, measure, hierarchy with `Copilot_Visibility = Visible`) should also carry a TMDL description — the `/// <text>` line directly above the object declaration. **`Description` is the single highest-leverage authoring artifact you have.**

**Why descriptions matter (more than annotations):**

The agent reads descriptions verbatim when it calls `DiscoverMeasures`, `DiscoverColumns`, `DiscoverQuestions`. A column named `Operating Unit` with no description tells the agent nothing; the same column with `/// Microsoft operating unit (geographic or organizational subdivision) attributed to the account (e.g., United States, France, ANZ)` tells the agent exactly when to use it. Bad / missing descriptions are the #1 cause of mis-routing.

**TMDL syntax:**

```tmdl
/// Monthly active users of Fabric, self-scoped to the most recent month available. Default: 'Product Master'[Product]=Power BI Backend (no Product filter falls back to this product). Cross-leaf distinct rollup — the 'All' row is the correct distinct cardinality, not a sum.
measure 'Fabric MAU' =
		VAR _MaxDate = ...

/// Top-level grouping in the segment hierarchy (e.g., Enterprise, SME&C Corporate, SME&C - SMB Commercial, Consumer).
column 'Segment Group'
	dataType: string
	sourceColumn: SegmentGroup
```

Rules:

- The `///` line must be **directly** above the object declaration (no blank lines between).
- Single-line is the canonical pattern. Multi-line is allowed (consecutive `///` lines) but agents render them concatenated.
- Tables get their `///` line above `table 'X'`. Tables auto-promote to Visible if any child is Visible, so they need descriptions too.
- Plain text only — no markdown, no backticks for code. The agent reads them as prose.

> **The `model` object's own `///` description is deploy-managed.** At deploy,
> `generate_copilot_instructions` sets the semantic model's metadata description
> (used by Copilot / M365 for grounding + model selection, ≤500 chars). It
> **preserves** any hand-authored `///` above `model 'X'` as the lead-in and
> **appends** a generated "Trained topics: …" sentence (the topics come from the
> model's own `model.json` routes). So
> you may still curate the model-level description — it won't be lost — but you
> don't need to list topics yourself, and the topic clause you see in production
> is generated. This applies only to the top-level `model` object; table / column
> / measure descriptions below are yours alone.

**What a good description includes:**

| For… | Include |
|---|---|
| **Measures** | What it computes (algorithm, not implementation), default filters applied via `Copilot_DefaultFilter`, scoping (self-scoping to max date, cross-leaf rollup behavior, closed-month gating), known gotchas (requires X slicer to resolve, doesn't compose with measure Y) |
| **Columns** | Business meaning + real example values for enum columns (e.g., "Values: Active, Qualified, PendingQualification, Denied, Unknown"), grain, format if non-obvious |
| **Tables** | What grain (one row per …), what the table represents in business terms, key relationships, what topics consume it |
| **Hierarchies** | Roll-up direction (broad → narrow), level cardinality if surprising |

**Process for authoring at scale (e.g., onboarding a new model):**

1. Run `DiscoverColumns("")` and `DiscoverMeasures("")` against the model — see what's currently surfaced.
2. Bucket every Visible object into one of three tiers:
   - **Tier 1 — copy parity**: a sister model already has a description for an identical (table, kind, name). Copy it. Safe, mechanical.
   - **Tier 2 — author from DAX + topic file + live values**: pull the measure's DAX expression for ground truth on what it computes; pull the topic file (e.g., `topics/usage.md`) for business framing; query the live model for sample values on enum columns (`EVALUATE CONCATENATEX(TOPN(10, VALUES(...)), [Col], ", ")`). Write descriptions that anchor on those three sources.
   - **Tier 3 — needs SME input**: rare measures where the DAX is opaque and topic file is silent. List them and ask the model owner before guessing.
3. Verify by running the same `Discover*` UDFs again — the new descriptions should appear in the `Description` column.

**Anti-patterns to avoid:**

- Placeholder descriptions that just restate the name (`/// Fiscal Month` on the column `Fiscal Month`). Worse than no description because it costs tokens without adding signal.
- Fabricated business framing where you couldn't confirm the semantics (e.g., describing `Operating Unit` as "Microsoft sales seller name" when it's actually a geographic subdivision). When in doubt, query the model or escalate.
- Marketing prose ("flexible, powerful measure that …"). The agent doesn't need persuasion; it needs accurate scoping rules.
- Repeating what's already in `Copilot_DefaultFilter` annotations — call out the default once in the description so the agent surfaces it in chat, but don't restate the annotation syntax.

---

## `Copilot_*` annotation reference

Annotations live on TMDL objects (tables, columns, measures, hierarchies). The next deploy captures them into `_INFO_ANNOTATIONS` automatically and the UDFs read them at query time.

**How to apply:**

| Number of annotations to add/change | Tool |
|---|---|
| One or a handful, on existing objects you can name | Edit the `.tmdl` file directly — faster than spinning up the MCP, no serializer noise to clean up |
| Many annotations across many objects, or applied as part of a structural change (new table / new measure) | `powerbi-modeling-mcp` operations on the live model — gets you validation |

For direct TMDL edits, follow the exact syntax shown in each annotation's section below — TMDL parsers are strict about indentation (tabs only) and key spacing.

**If you use the MCP**, expect line-ending noise across most touched files (the serializer writes CRLF on Windows, this repo is LF). See the repo-root [`AGENTS.md`](../../../AGENTS.md) > "MCP CRLF behavior on Windows" for cleanup recipe (`git add --renormalize`).

### `Copilot_Visibility`

| Applies to | Tables, columns, measures, hierarchies |
|---|---|
| Values | `"Visible"` or `"Hidden"` |
| What it does | Gates whether the object appears in `DiscoverMeasures` / `DiscoverColumns` / `DiscoverQuestions` output. Tables auto-promote to `Visible` if any child object is `Visible`. |
| When to set `"Visible"` | Any column, measure, or hierarchy you want the agent to see. Default for fact measures, dimension grouping columns, calendar fiscal columns. |
| When to set `"Hidden"` | Internal keys (`DIM_*Id`), staging columns, scratch measures, deprecated objects you can't yet delete. |
| Gotcha | A measure won't appear in `DiscoverMeasures` even if it's a great measure — if you forget to mark it Visible. New tables default to Hidden in most TMDL workflows. |

### `Copilot_Synonyms`

| Applies to | Tables, columns, measures, hierarchies |
|---|---|
| Values | Pipe-separated string, e.g. `"Consumption\|consumed revenue\|azure consumed revenue"` |
| What it does | Adds alternate names that the Discover* UDFs substring-match against. The agent searches `Name + Description + Synonyms` together. |
| When to set | When the user-facing terminology differs from the canonical TMDL name. Common pattern: marketing names ("Consumption") vs. measure name ("Consumed + Adjusted Revenue (YTD)"). |
| Format rule | Pipe is the delimiter, so synonyms can't contain `\|`. Whitespace is preserved. |
| Tip | Use the same canonical naming pattern across your model. If "FY26" and "FY2026" are both common, add both as synonyms on `'Calendar'[Fiscal Year]`. |

### `Copilot_Enumerable`

| Applies to | Columns |
|---|---|
| Values | `"true"` (omit otherwise) |
| What it does | Marks the column as searchable via `SearchValues`. Renders the `searchable` tag in `DiscoverColumns` output. |
| When to set | Any column whose distinct values the agent should be able to look up by substring (account name, partner name, product name, persona, geography, calendar values). |
| When to skip | Free-text columns (case titles, survey comments), high-cardinality timestamps, internal IDs the user wouldn't type. |
| Pair with | `Copilot_SearchRanker` if values need ranked + enriched matches (see below). |

### `Copilot_Sliceable`

| Applies to | Columns |
|---|---|
| Values | `"true"` (omit otherwise) |
| What it does | Marks the column as valid in `sliceColumns` (GROUP BY). Renders the `sliceable` tag in `DiscoverColumns` output. |
| When to set | Any dimension column the agent should be able to group by (fiscal month, product, geography, segment, profit center). |
| When to skip | Free-text, high-cardinality keys, or columns whose grouping would produce a meaningless cross-tab. |
| Independent of `Enumerable` | A column can be sliceable but not enumerable (rarely the reverse). |

### `Copilot_SearchRanker`

| Applies to | Columns |
|---|---|
| Values | A UDF fully-qualified name: `"Local.AskADIA._RankAccounts"` |
| What it does | Wires the column to a per-model ranker UDF (which lives in your overlay's `functions.tmdl`). When `SearchValues` is called on this column, the dispatcher routes to your ranker instead of generic substring search. |
| When to set | Multi-attribute entities where users need disambiguation context (an "Apple" search needs to show industry / area / segment alongside the bare name). |
| Required: the named UDF must exist in your overlay | Deploy fails loud (`generateSearchHelpers.csx`) if the UDF is missing. See [Per-model ranker UDFs](#per-model-ranker-udfs) below. |
| Pair with | `Copilot_PairWith` on a sibling column if the ranker should apply when searching either side of a name/ID pair. |

### `Copilot_SearchLadder`

| Applies to | Hierarchies |
|---|---|
| Values | `"true"` |
| What it does | Marks the hierarchy as a ladder for `SearchHierarchy`. A search across a ladder returns `(Ladder, Position, Table, Column, MatchedValue)` rows — one row per match at any level. |
| When to set | Hierarchies where the user might mention any level by name ("Power BI" could be a Product Group, a Mid Group, or a Product). Lets the agent resolve ambiguous terms automatically. |
| When to skip | Hierarchies where the user always knows the exact level (e.g. a flat `Calendar` hierarchy). |
| Convention | BPA recommends at most one ladder per table to keep `SearchHierarchy` outputs interpretable. |

### `Copilot_AutoIncludeParents`

| Applies to | Hierarchies |
|---|---|
| Values | `"true"` |
| What it does | When the agent slices by a non-leaf level of the hierarchy, the framework auto-injects every parent level above it (and skips silently if the measure can't reach a parent). Surfaces in `[AutoApplied]` › `parents:`. |
| When to set | Almost always — when you have a hierarchy worth slicing, you almost always want the parent context too. |
| When to skip | Genuinely flat "hierarchies" (single-level groupings) where parent injection would be a no-op. |
| Renders in `DiscoverColumns` Behavior column as | `AutoIncludeParents` |

### `Copilot_PairWith`

| Applies to | Columns |
|---|---|
| Values | Sibling column reference, e.g. `"'Partner'[Partner Id]"` |
| What it does | Pairs two columns so that (a) `SearchValues` on one automatically uses the other's ranker if the queried column lacks its own, and (b) slicing by one auto-includes the other so the result carries both name + id together. |
| When to set | Any name/id pair (Account/AccountKey, Partner Name/Id, Tenant Name/Tenant Id). Asymmetric setup is fine — only one side needs the annotation. |
| Renders in `DiscoverColumns` Behavior column as | `PairWith` |

### `Copilot_ValueSynonyms`

| Applies to | Columns |
|---|---|
| Values | Canonical-to-synonyms map, e.g. `"DE and DS=Data Engineering;Data Science\|RTI=Real Time Intelligence"` |
| What it does | Maps cryptic / abbreviated canonical column **values** to user-friendly aliases. At deploy, all annotated columns are pre-parsed into `_COPILOT_VALUE_SYNONYMS` and the `_GetColumnSynonymMatches` helper handles substitution at query time. Surfaces in `DiscoverColumns` › `ValueSynonyms` output column. |
| When to set | When canonical column values are abbreviations or insider terminology and users will type the long form. |
| When to skip | Columns whose values are already plain English (`'Geography'[Subsidiary]` = `Japan` doesn't need a synonym for `Japan`). |
| Format rules | `\|` separates canonical entries; `=` separates canonical from synonyms; `;` separates multiple synonyms for one canonical. None of these three characters can appear in canonical or synonym text. Malformed entries fail the deploy loud. |
| **Restriction** | NOT supported on `Copilot_SearchRanker` columns (deploy fails loud). Rankers already do fuzzy multi-column scoring with rich enrichment; layering value synonyms would either lose enrichment or require per-ranker plumbing. |

### `Copilot_AutoFilterWhenSliced`

| Applies to | Measures (with trigger config) **or** columns (registry-driven Behavior tag) |
|---|---|
| Values on measures | `"trigger:col1,col2\|<filterDAX>"` — e.g. `"trigger:Fiscal Month,Calendar Date\|'Calendar'[RelativeMonthNumber]=TREATAS({-12,...,0}, 'Calendar'[RelativeMonthNumber])"` |
| Values on columns | `"true"` (registry-driven; renders as `AutoFilterWhenSliced` in Behavior) |
| What it does | On **measures**: sticky default filter — if any trigger column appears in `sliceColumns` AND no user / default / hardcoded filter touches that filter's table, inject the filter automatically. Surfaces in `[AutoApplied]` › `autoFilters:`. On **columns**: visibility tag only. |
| When to set on measures | Time-windowed reporting patterns — the trailing-13-month auto-window pattern (ADIA + BizMgmt). Anywhere the "default sensible scope" should kick in when the user provides a slice but not a filter. |
| When to skip | If the model never needs implicit scoping (P&C deliberately omits this — partner queries are usually unbounded by intent). |
| Suppression rule | Any explicit filter on the same table suppresses the auto-injection — user always wins. |

---

## Authoring a curated question

A curated question lives in your overlay's `copilot_questions.json`. It
gives the agent a one-call shortcut for a common ask: instead of composing
`GenerateQuery` with the right measure + filters + group-by, the agent
calls `AnswerQuestion("<id>", filters, sliceColumns, …)` and the framework
applies all the curated defaults.

### When should I add a curated question?

| Add one when | Skip and let the agent use `GenerateQuery` when |
|---|---|
| The same question pattern recurs across users ("what's MAU?", "what's revenue?") | The question is one-off or exploratory |
| The right answer requires non-obvious filter / group-by defaults (closed-month flag, excluded persona values, "do not include trial capacity") | The question is well-served by passing the user's own filters straight through |
| There's a multi-measure answer shape (NPS + Promoter + Detractor + Passive counts in one row) | A single measure suffices |
| The agent has been mis-routing the question and a curated answer would lock the shape in | The agent's freeform composition is producing correct results |
| The question is the entry point to a 360 orchestrator | (N/A — orchestrators are always curated) |

### Schema

Each entry in `copilot_questions.json` is a JSON object. Fields:

| Field | Type | Purpose |
|---|---|---|
| `QuestionId` | `string` | Stable kebab_snake_case identifier the agent calls. `usage_mau_by_workload`, `revenue_pf_sku`. Convention: `<topic>_<intent>`. |
| `Question` | `string` | One-sentence display title shown in `DiscoverQuestions`. Phrase it the way a user would. |
| `Description` | `string` | The "when to use this" + "how it differs from siblings" guidance. The agent reads this verbatim — be precise. Document default filters, common variants, and known traps. |
| `Measures` | pipe-delimited bracketed list | `[MAU]` or `[NPS Score]\|[Promoter Responses]\|[Detractor Responses]`. Multi-measure returns side-by-side columns. |
| `HardcodedGroupBy` | pipe-delimited `'Table'[Column]` | ALWAYS appended to `sliceColumns`. Use for required grouping (Profit Center for budget questions, Product Master[Product] for MAU). |
| `DefaultFilters` | pipe-delimited `'Table'[Column]=value` | Applied unless the agent passes an overlapping filter or sliceColumn. User filter wins. |
| `HardcodedFilters` | pipe-delimited `'Table'[Column]=value` | Intersected via `KEEPFILTERS` — user values inside the set survive, outside values disappear. Cannot be widened. |
| `HardcodedNotInFilters` | pipe-delimited `'Table'[Column]=val1;val2` | NOT-IN exclusion. ALWAYS applied. |
| `RequiredFilters` | pipe-delimited `'Table'[Column]` (column refs only, no values) | The agent MUST pass these filters or the call fails. Use for account-specific / partner-specific questions. |
| `DaxWrapper` | DAX expression with `{query}` placeholder | Wraps the generated DAX. Common use: `"EVALUATE {query} ORDER BY [Measure] DESC"`. The `{query}` token is substituted with the validated inner DAX. |
| `IsOrchestrator` | `bool` | `true` for multi-section composed answers (Customer 360, Partner 360). |
| `SectionIndex` | `int` | For orchestrators: 1..N. For single-section questions: `1`. |
| `SectionLabel` | `string` | For orchestrators: human-readable label printed above the section's DAX (e.g. `"Power BI MAU"`). For single-section: empty string. |

### Worked example — single-section question

```json
{
  "QuestionId": "usage_mau_by_workload",
  "Question": "Show MAU by Fabric workload",
  "Description": "Show MAU by Fabric workload (can also slice by feature or activity)",
  "Measures": "[Fabric MAU]",
  "HardcodedGroupBy": "'Usage Fabric Product'[Fabric Product]",
  "DefaultFilters": "",
  "HardcodedFilters": "",
  "HardcodedNotInFilters": "'Usage Fabric Product'[Fabric Product]=Shared AI Services;Shared DI Services",
  "RequiredFilters": "",
  "DaxWrapper": "EVALUATE {query} ORDER BY [Fabric MAU] DESC",
  "IsOrchestrator": false,
  "SectionIndex": 1,
  "SectionLabel": ""
}
```

The agent calls `AnswerQuestion("usage_mau_by_workload", "", "", 100, "", "")`
and gets back DAX that:

- Groups by `'Usage Fabric Product'[Fabric Product]` (from `HardcodedGroupBy`)
- Excludes `Shared AI Services` and `Shared DI Services` from the result
  set (from `HardcodedNotInFilters`)
- Wraps the inner `SUMMARIZECOLUMNS` with `ORDER BY [Fabric MAU] DESC`
  (from `DaxWrapper`) so the agent gets workloads ranked by MAU
- Returns the `[Fabric MAU]` measure plus its time-intelligence variants
  (MoM%, YoY%, etc., per the framework's auto-variant rule)

> **Authoring trap — dead defaults.** Don't set a `DefaultFilters` entry
> on the same column as a `HardcodedGroupBy` (or `sliceColumns` you know
> the agent will always pass). The framework suppresses the default at
> emit time, so the filter never fires — it's pure noise in the question
> definition. Same column = pick one or the other. Use `DefaultFilters`
> only for columns the agent typically won't slice / filter (e.g., a
> default state for support tickets, or a default product pin).

### Worked example — orchestrator

The Customer 360 orchestrator is the same JSON shape but with N rows
sharing the same `QuestionId`, distinguished by `SectionIndex` and
`SectionLabel`. See
[`udf/models/azure-data-insights/copilot_questions.json`](udf/models/azure-data-insights/copilot_questions.json)
for the live `customer_360_overview` definition.

### Common authoring traps

- **Filter syntax.** Values are not quoted: `'Product Master'[Product]=Fabric Core`
  (no quotes around `Fabric Core`). Multi-value uses `;`: `=Fabric Core;Power BI Backend`.
  NOT-IN uses `!` prefix on the first value: `=!Shared AI Services;Shared DI Services`.
- **`HardcodedGroupBy` always fires.** Even with `sliceColumns=""`, the
  group-by columns get appended. If your question is a single-row
  summary (no group-by intended), leave `HardcodedGroupBy` empty.
- **`HardcodedFilters` cannot be widened.** If you set
  `'Product Master'[Product]=Power BI Premium;Fabric` (P-vs-F SKU
  comparison), the user cannot ask for all products — they can only
  narrow to one of the two. Document this in `Description`.
- **`RequiredFilters` rejects calls without them.** Don't add a
  required filter unless the question is meaningless without scope (e.g.
  account-level case detail, per-partner revenue).
- **DAX validation.** Every measure name in `Measures` must exist on the
  model. The deploy doesn't validate this (because the framework tables
  are populated at query time), but the test suite under
  `semantic_model_tests/<slug>/unit/` should cover question presence and
  shape.

---

## Per-model ranker UDFs

A ranker UDF turns `SearchValues('Account'[Account], "contoso")` from a
flat list of substring matches into a ranked, enriched result the agent
can present for disambiguation. Without one, `SearchValues` just returns
distinct values that contain the search term — no ordering, no context.

### When do I need a ranker?

| Add one when | Skip when |
|---|---|
| The column represents a real-world entity users care about (account, partner, tenant, capacity) | The column is a low-cardinality enum (persona, segment, area) where the bare value is enough |
| Multiple matches are common and the user needs context to pick the right one (`Apple` could be Apple Inc. or Apple Bank) | Matches are usually unique or the order doesn't matter |
| There's a meaningful ranking signal you can compute (MAU, revenue, recency) | No signal beats alphabetical |
| You can pull useful enrichment fields (industry, area, segment) onto the result rows | Enrichment would require fact-table joins too expensive at search time |

### Anatomy of a ranker

Every ranker:

1. Lives in `askadia/udf/models/<slug>/functions.tmdl` (your overlay).
2. Is named `_Rank<Something>` (leading underscore — internal helper convention).
3. Takes one parameter: `searchTerm: SCALAR STRING VAL`.
4. Returns a table with exactly two columns: `[SearchResult]` (formatted
   display string) and `[Rank]` (integer, 1 = best).
5. Has `isHidden` + `annotation TE_Group = Local.AskADIA.Admin` so it
   doesn't leak into Tabular Editor's function picker.
6. Is wired in via `Copilot_SearchRanker = "Local.AskADIA._Rank<Something>"`
   on the column you want ranked.

### Template

See [`udf/models/azure-data-partner-community/functions.tmdl`](udf/models/azure-data-partner-community/functions.tmdl)
for a reference shape. The recipe at the high level:

1. **Numeric-term short-circuit.** Detect once outside the FILTER whether
   the search term is numeric; use direct equality on the int64 ID column
   for storage-engine pushdown (avoid per-row `CONTAINSSTRING(FORMAT(...))`
   callbacks).
2. **Match.** Filter the dim to rows where the name column contains the
   term or the ID equals the numeric term.
3. **Score.** `ADDCOLUMNS` the matches with the ranking signal via
   `CALCULATE` (and any filters that scope the signal — e.g. a product
   pin for MAU rankers).
4. **Filter to scored rows + take TOPN.** Cap before enrichment so
   fact-table joins are bounded.
5. **Enrich.** `ADDCOLUMNS` the TOPN with disambiguation context
   (industry, area, segment).
6. **Rank.** `ADDCOLUMNS` with `_Rank` via the standard
   `COUNTROWS(FILTER(_Enriched, [_Score] > EARLIER([_Score]))) + 1`
   pattern.
7. **Format.** `SELECTCOLUMNS` to `[SearchResult]` + `[Rank]` with the
   display string assembled inline.

### Conventions for the `SearchResult` string

Pack everything the agent needs to disambiguate into the result string
itself — the agent quotes it verbatim. Convention:

```
<DisplayName> (Key1: <val1>, Key2: <val2>, ...)
```

The Account and Partner rankers in the existing overlays are good
references for the level of enrichment.

---

## Validating your change locally

The full debug-deploy loop is in [`../DEBUG_DEPLOY.md`](../DEBUG_DEPLOY.md).
Model owner happy path:

### 1. Debug-deploy your model

```pwsh
python .deploy\workspace\debug_deploy.py --model-name "<Your Model Name>"
```

This stages a `DEBUG_PROD_<Slug>_<your-alias>` copy of your model into
the dev Insights workspace, runs the full preprocess chain (merges the
canonical scaffold, populates `_INFO_ANNOTATIONS` and
`_COPILOT_QUESTIONS` from your overlay, runs the codegen csx scripts),
publishes it, and refreshes. Idempotent — re-running overwrites.

### 2. Smoke-test your change against the deployed copy

Connect to the deployed `DEBUG_*` model via DAX Studio or
`powerbi-modeling-mcp` and run the relevant Discover / Search / Answer
calls. Examples:

- New annotation on a column → `EVALUATE Local.AskADIA.DiscoverColumns("<your search term>")`
  and confirm the column appears with the right Tags / Behavior values.
- New curated question → `EVALUATE Local.AskADIA.DiscoverQuestions("<topic>")`
  to confirm it's in the catalog, then `EVALUATE Local.AskADIA.AnswerQuestion("<id>", "", "", 5, "", "")`
  to inspect the generated DAX.
- New ranker → `EVALUATE Local.AskADIA._Rank<Yours>("contoso")` and
  inspect the result + rank ordering.

### 3. Add or update a test case

YAML cases under `semantic_model_tests/<slug>/unit/` lock the shape in.
See [`semantic_model_tests/README.md`](../../../semantic_model_tests/README.md)
for the schema. At minimum, add a structural test for each new curated
question (assert it's in the `DiscoverQuestions` catalog with the right
measures).

## Ship checklist

- [ ] PR opened against your working branch following your repo's naming convention
- [ ] Instruction changes are authored under `instructions/models/<slug>/` or `instructions/common/` (not generated output)
- [ ] `semantic_model_tests/<slug>/unit/` updated for new questions / annotations
- [ ] Debug-deploy succeeds locally; smoke queries return expected shapes
- [ ] Promoted through your environments (dev → test → prod) as needed
- [ ] If the change touches the runtime contract (a public UDF's behavior or output shape), coordinate the rollout with the framework maintainer

---

## See also

- [`README.md`](README.md) — framework spec (concepts, lifecycle, runtime contract)
- [`../README.md`](../README.md) — deploy infrastructure
- [`../DEBUG_DEPLOY.md`](../DEBUG_DEPLOY.md) — debug-deploy iteration runbook
- [`semantic_model_tests/README.md`](../../../semantic_model_tests/README.md) — test contributor guide
- `udf/models/*/` — per-model overlays (existing examples of rankers, curated questions, annotations)
