# Usage

Active-user telemetry — `MAU`, `WAU`, `DAU` across Microsoft data products, plus Fabric-scoped variants that traverse the workload ladder.

## Vocabulary

Map user terms to UDF filter values:

| User Says | Measure | UDF Filter Column | UDF Filter Value |
| - | - | - | - |
| mau, fabric mau, fabric developer mau, active users *(unqualified)* | `[MAU]` | `'Product Master'[Product]` | `Fabric Core` *(measure default — leave unspecified)* |
| power bi mau, pbi mau | `[MAU]` | `'Product Master'[Product]` | `Power BI Backend` |
| mau for `<other product>` | `[MAU]` | `'Product Master'[Product]` | `<product>` *(resolve via `SearchValues`)* |
| mau by Fabric workload / feature / activity | `[Fabric MAU]` | *(slice on `'Usage Fabric Product'` ladder)* | — |

Both `[MAU]` and `[Fabric MAU]` share `Alias=MAU` — distinguish by **MeasureName**. `[Fabric MAU]` is **only** for slicing the Fabric workload ladder (`'Usage Fabric Product'[Fabric Product → Fabric Feature → Fabric Activity]`). For everything else — including unqualified **"fabric mau"** and **"fabric developer mau"** — call `GenerateQuery("MAU", ...)` directly. **`DiscoverMeasures("fabric mau")` returns both `[MAU]` and `[Fabric MAU]`; pick `[MAU]` unless the user is grouping or filtering by Fabric Product, Feature, or Activity.** Treat **"fabric developer mau"** as an alias for Fabric Core MAU unless the user explicitly asks for developer role/persona segmentation. `[MAU]` carries a measure-level `Copilot_DefaultFilter` of `'Product Master'[Product]=Fabric Core`, so the Fabric Core scope fires automatically; override via `filters` (for example, `'Product Master'[Product]=Power BI Backend`) for other products.

## Domain Notes

- **Usage Fabric Product hierarchy**: `Fabric Product` → `Fabric Feature` → `Fabric Activity` — see the Azure Data Insights Model Reference row ({{ref:model-reference}}) › Hierarchies for level-skipping rules and "All" semantics.
- **Disambiguate Feature vs Activity**: `SearchHierarchy` may return matches at both `[Fabric Feature]` and `[Fabric Activity]` for the same term. **Prefer the Feature-level match** unless the user explicitly named an activity verb ("notebook opens", "notebook runs"). Feature-level rolls up all underlying activities; Activity-level scopes to a single telemetry event.
- **WAU/DAU have no curated questions** — use `GenerateQuery` directly with the measure from `DiscoverMeasures("WAU")` or `DiscoverMeasures("DAU")`.
- **Non-additive "All" rollup row**: distinct-count measures (MAU, WAU, DAU) compute the auto-injected `"All"` row as the correct cross-leaf distinct rollup — **not** a sum and **not** a double-count.

## Gotchas

- **The `usage_mau_by_workload` curated question excludes `Shared AI Services` and `Shared DI Services`** (not directly user-facing) via a question-level `HardcodedNotInFilters` — not on the `[Fabric MAU]` measure itself. To include them, drop to `GenerateQuery("Fabric MAU", ..., sliceColumns="'Usage Fabric Product'[Fabric Product]")` directly.