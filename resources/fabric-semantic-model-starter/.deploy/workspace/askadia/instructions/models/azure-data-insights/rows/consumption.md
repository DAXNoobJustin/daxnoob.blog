# Consumption

Capacity Unit (CU Hours) consumption — Fabric vs Power BI workloads, SKU-type splits, and the workload-ladder breakdown via the `Fabric Capacity Units` hierarchy.

## Vocabulary

Map user terms to UDF filter values:

| User Says | UDF Filter Column | UDF Filter Value |
| - | - | - |
| fabric cu, fabric consumption | `'Fabric Capacity Units'[Product Flag]` | `Fabric` |
| power bi cu, power bi consumption | `'Fabric Capacity Units'[Product Flag]` | `Power BI` |
| total cu, all cu | *(no filter)* | — |
| f sku, fabric capacity | `'Capacity'[Capacity Grouping]` | `Fabric` |
| ft sku, trial capacity, fabric trial | `'Capacity'[Capacity Grouping]` | `Fabric Trial` |
| p sku, power bi capacity, premium sku | `'Capacity'[Capacity Grouping]` | *semicolon-separated multi-value — see below* |
| embedded em sku | `'Capacity'[Capacity Grouping]` | `Power BI Embedded - EM SKUs` |
| embedded a sku | `'Capacity'[Capacity Grouping]` | `Power BI Embedded -  A SKUs` *(note: two spaces between `-` and `A`)* |

> `'Fabric Capacity Units'[Workload Type]` and `[Workload Kind]` carry `Copilot_ValueSynonyms` — resolve user terms via `SearchHierarchy("<term>", "<measure>")` or `SearchValues('Fabric Capacity Units'[Workload Type], "<term>")`. The framework handles the mapping.

For `p sku` / `power bi capacity` / `premium sku`, pass the exact UDF filter value:

```text
'Capacity'[Capacity Grouping]=Power BI Premium;Power BI Embedded -  A SKUs;Power BI Embedded - EM SKUs
```

## Domain Notes

- **Product Flag vs Capacity Grouping are different axes — don't conflate.** Product Flag (`Fabric` / `Power BI`) filters by workload meter category. Capacity Grouping (`Fabric`, `Fabric Trial`, `Power BI Premium`) filters by the capacity SKU. A query that filters Product Flag=`Power BI` AND Capacity Grouping=`Fabric` is almost ALWAYS wrong (zero rows / unintended intersection). Pick one based on user intent.
- **CU disambiguation**: When a user asks "CU for Power BI" — they almost ALWAYS mean `Product Flag = Power BI`, not `Capacity Grouping = Power BI Premium`. Only use Capacity Grouping when the user explicitly mentions SKU types (P SKU, F SKU, FT SKU, EM SKU). When multiple workloads match a search, **rank by CU Hours descending** to surface the most significant first.
- **Pick the workload ladder by measure.** CU measures (`CU Hours (28d)` etc.) breakdown by workload via the `Fabric Capacity Units` hierarchy (`[Workload Type]` → `[Workload Kind]` → `[Artifact Kind]` → `[Operation Name]`). MAU / Fabric MAU breakdown by workload via the `Usage Fabric Product` hierarchy (`[Fabric Product]` → `[Fabric Feature]` → `[Fabric Activity]`). The two ladders aren't cross-reachable — see the Azure Data Insights Model Reference row ({{ref:model-reference}}) › Hierarchies for full details.
- **Workload term disambiguation**: For ambiguous workload terms ("Dataflow Gen2", "SparkCore", "Data Warehouse") the term may match in any of the 4 Workload Hierarchy columns — call `SearchHierarchy("term", "CU Hours (28d)")` to scan all four at once.

## Gotchas

- **The "top trial customers" question is pinned to `Capacity Grouping = Fabric Trial`** — the one Capacity-pinned exception in this topic. Honor the pin; don't override.