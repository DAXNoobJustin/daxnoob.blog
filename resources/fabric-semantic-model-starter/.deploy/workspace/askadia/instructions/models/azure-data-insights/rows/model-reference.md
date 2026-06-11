# Azure Data Insights — Model Reference

> Read the matching topic row first — topic rows own measure-level routing rules. This row covers cross-topic model context (key dimensions, hierarchies, disambiguation). UDF signatures live in the UDF Reference row ({{ref:udf-reference}}).

## Key Dimensions

> **Model-wide default:** the model has Environment and Capacity dimensions, and measures related to them include **all environments (incl. INTERNAL) and all capacity types (incl. Fabric Trial)** by default. Apply these filters where relevant — and only where the columns are available for the measure (visible when you run `DiscoverMeasures` / `DiscoverQuestions`) — for example, `'Environment'[Environment]=PROD` for customer-facing reporting, or `'Capacity'[Capacity Grouping]=!Fabric Trial` to drop trial capacity.

### Calendar

`'Calendar'` carries filterable columns. `[RelativeMonthNumber]` is filter-only — pass it via `filters=`, NEVER `sliceColumns=`. Slicing by `[Fiscal Month]` or `[Calendar Date]` triggers a trailing-13-month auto-window (current month plus the 12 prior; `0` = current, `-12` = 12 months ago). Year-grain and quarter-grain slices do NOT trigger it. Any explicit filter on any `'Calendar'` column — user-passed, measure default, or hardcoded — suppresses the auto-injection.

| Column | Grain | Value format | Example (single `filters` entry) |
| - | - | - | - |
| `'Calendar'[RelativeMonthNumber]` | Month | Integer, `0` = current month | `'Calendar'[RelativeMonthNumber]=-5;-4;-3;-2;-1;0` or range `'Calendar'[RelativeMonthNumber]>=-5` |
| `'Calendar'[Fiscal Year]` | Year | `FYxx` | `'Calendar'[Fiscal Year]=FY25` or `FY24;FY25` |
| `'Calendar'[Fiscal Quarter]` | Quarter | `FYxx-Qn` (dash) | `'Calendar'[Fiscal Quarter]=FY25-Q3` |
| `'Calendar'[Fiscal Month]` | Month | `"Month, YYYY"` (comma + space) | `'Calendar'[Fiscal Month]=March, 2025` |
| `'Calendar'[Calendar Date]` | Day | ISO date | `'Calendar'[Calendar Date]=2025-03-15` or range `>=2025-01-01..<=2025-03-31` |

### Account (AccountKey)

ALWAYS use `'Account'[AccountKey]` with the digits-only AccountKey value (no inner quotes around the number) in filter strings — for example `filters="'Account'[AccountKey]=1234567"`. When a user names a company, use `SearchValues('Account'[Account], "name")` to resolve to AccountKey — NEVER hard-code account keys from memory. If multiple matches, present options.

`SearchValues('Account'[Account], "<term>")` returns `[SearchResult]` + `[Rank]`. The `[SearchResult]` string has the account name plus **AccountKey, MAU, Area, Segment, Industry** — quote those fields directly from the result instead of issuing a follow-up query. When multiple candidates surface, present `Area` / `Segment` / `Industry` alongside Account / AccountKey / MAU so the user can pick unambiguously (especially for ambiguous terms like "Apple", "Target", multinational subsidiaries).

> **"Microsoft" is a customer account, not a corporate rollup.** The dataset measures per-customer telemetry for thousands of tenants — Microsoft is one of them. Resolve via `SearchValues` like any other customer. Treat as cross-account ONLY if the user explicitly says "across all customers" or similar.

### Product Disambiguation

The word "product" appears in multiple tables with different meanings. ALWAYS verify the correct column via `DiscoverMeasures` for the measure in question — a column valid for one measure may not exist for another.

| Column | Used For | Example Values |
| - | - | - |
| `'Product Master'[Product]` | Usage | `Fabric Core`, `Power BI Backend` |
| `'Product Master'[Product Mid Group]` | Revenue (coarse rollup only — see the Revenue topic row ({{ref:revenue}}) grain rule) | `Fabric`, `Power BI` |
| `'Usage Fabric Product'[Fabric Product]` | Usage workload breakdowns | `Data Engineering`, `Real Time Intelligence` |
| `'Fabric Capacity Units'[Product Flag]` | Consumption | `Fabric`, `Power BI` |
| `'Capacity'[Capacity Grouping]` | Consumption SKU type | `Fabric`, `Fabric Trial`, `Power BI Premium` |
| `'Fabric Capacity Units'[Workload Type]` | Consumption workload detail | `DE and DS`, `Data Warehousing Core` |

### Geography

Hierarchy: **Big Area → Area → Region → Sub Region → Subsidiary**. No `[Country]` column exists — when the user asks about a country, filter on `'Geography'[Subsidiary]`. Use `SearchValues` on the right column to discover exact values.

### Hierarchies

**Usage Fabric Product** — broad → narrow: Fabric Product → Fabric Feature → Fabric Activity. All three levels have an `"All"` rollup row. The same Feature or Activity name can exist under multiple parents — ALWAYS filter on every level above the grain you query (skipping a level produces duplicates). `"All"` is the rollup row at each level (NOT a wildcard) — when filtering to a specific lower-grain value, higher levels MUST hold the specific parent value, NEVER `"All"`.

**Product Master** — Product Group → Product Mid Group → Product.

**Fabric Capacity Units** — broad → narrow: `[Workload Type]` → `[Workload Kind]` → `[Artifact Kind]` → `[Operation Name]`. When slicing, child levels auto-inject all parents — for example, slicing by `[Operation Name]` adds `[Workload Type]`, `[Workload Kind]`, `[Artifact Kind]` (visible via the `parents:` line of `[AutoApplied]`).

## Gotchas

_None at the model level._