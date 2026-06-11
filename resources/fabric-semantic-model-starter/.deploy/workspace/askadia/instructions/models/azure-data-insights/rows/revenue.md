# Revenue

Azure consumed + adjusted revenue — period scoping (MTD / YTD), product-grain breakdowns, and the dedicated P-vs-F-SKU comparison shape.

## Vocabulary

Map user terms to UDF filter values:

| User Says | UDF Filter Column | UDF Filter Value |
| - | - | - |
| fabric revenue, all-up fabric revenue, p+f sku revenue, premium + fabric revenue | `'Product Master'[Product Mid Group]` | `Fabric` (rolls up Premium + other Fabric-billed products) |
| power bi revenue, pbi revenue | `'Product Master'[Product Mid Group]` | `Power BI` (excludes Premium — see Domain Notes) |
| power bi premium revenue, p sku alone | `'Product Master'[Product]` | `Power BI Premium` |
| f sku revenue | `'Product Master'[Product]` | `Fabric` |

## Total Revenue vs ARR vs Allocated ARR — pick the right measure

| User says | Measure family |
| - | - |
| "revenue", "Consumption" | `[Consumed + Adjusted Revenue (MTD/YTD)]` |
| "ARR", "annualized", "Fabric ARR" | `[Allocated ARR (MTD)]` / `[Allocated ARR (YTD)]` — Fabric workload-attributable, with Compute Pool / Capacity Overage redistributed. The headline "Fabric ARR" in executive briefings. |
| "Azure ARR", "org-wide ARR" | `[ARR (MTD)]` / `[ARR (YTD)]` — all Azure scope; much larger than Fabric ARR |
| "NRR", "retention" | `[NRR (MoM)]` / `[NRR (YoY)]` — **all-up Azure only** (see Gotchas) |

**ALWAYS use a period-suffixed variant** — no unsuffixed `[ARR]` or `[Allocated ARR]` is exposed. Default plain "ARR" asks to the `[Allocated ARR (MTD/YTD)]` family. Use the `[ARR (MTD/YTD)]` family only when the user explicitly signals all-up Azure scope. For workload breakdowns, slice the Allocated family by `'Revenue'[Workload Type]`.

## Domain Notes

> **CRITICAL — "By product" means `[Product]`, NEVER `[Product Mid Group]`.** When the user asks for a breakdown **"by product"** (for example, *"FY25 Contoso revenue by product"*, *"break down Power BI revenue by product"*), slice AND filter at `'Product Master'[Product]`. **What breaks if you compress to `[Product Mid Group]`:** individual products like `Power BI E5`, `Power BI Pro`, `Fabric`, `Power BI Premium` collapse into 2-3 rows and the user silently loses the intended granularity. Reserve `[Product Mid Group]` for asks phrased as "by mid group", "Power BI vs Fabric", or coarse rollups. The pattern: `sliceColumns="'Product Master'[Product]"` and either no Product filter (full landscape) or `filters="'Product Master'[Product Mid Group]=Power BI"` to scope within a mid-group while still grouping at `[Product]`.

- **Default period**: ALWAYS show MTD and YTD.
- **Trend presentation**: Lead with YTD + YTD YoY% (smooths monthly volatility, more business-relevant than MTD YoY%). Include MTD + MTD MoM% for recent movement.
- **Default revenue**: Use Total Revenue (`Consumed + Adjusted Revenue`) — exposed as MTD/YTD only (no standalone Consumed/Adjusted measures).
- **"Power BI" Mid Group excludes Premium**: If the user says "Power BI revenue" generically, `Product Mid Group = Power BI` covers `Power BI`, `Power BI E5`, `Power BI Pro`, `Power BI Embedded`, `Power BI PPU` — but **not** `Power BI Premium` (which lives under Mid Group=Fabric). If they want Premium included, filter at the `[Product]` level with explicit Premium added.

## Gotchas

- **Closed-month default — overridable on most questions, locked on the P-vs-F-SKU comparison.** Revenue measures default to `'Calendar'[Azure Closed Month Flag]=True` (fully-closed months only). For most questions, override with `'Calendar'[Azure Closed Month Flag]=True;False` to include the current open month. The P-vs-F-SKU comparison question hardcodes closed-only and cannot be overridden — to compare P-vs-F-SKU including the open month, route to the generic revenue question with explicit `'Product Master'[Product]` filters.
- **The P-vs-F-SKU comparison is a 2-row shape, not a rollup.** That curated question returns exactly two products at `'Product Master'[Product]` grain: **P SKU** = `Power BI Premium` (the SKU is named "P", short for Premium) and **F SKU** = `Fabric`. The `HardcodedFilters` on `'Product Master'[Product]` cannot be expanded — for "all-up Fabric revenue" use the generic revenue question with `filters="'Product Master'[Product Mid Group]=Fabric"` instead.
- **Slicing the `[ARR (MTD)]` / `[ARR (YTD)]` family by `'Revenue'[Workload Type]` includes `Compute Pool` / `Capacity Overage` catch-all rows with significant value.** Use the `[Allocated ARR (MTD)]` / `[Allocated ARR (YTD)]` family for clean per-workload reporting — it redistributes those catch-alls into the real workloads.
- **NRR is all-up Azure only — do NOT slice `[NRR (MoM)]` or `[NRR (YoY)]` by `'Revenue'[Workload Type]`.** Workload-scoped NRR is intentionally not exposed (per-workload allocations would mislead retention analysis). For workload-level retention questions, fall back to comparing `[Allocated ARR (YTD)]` across periods.