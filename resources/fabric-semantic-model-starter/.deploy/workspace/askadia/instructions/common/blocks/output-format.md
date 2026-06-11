# Output, Error Handling, and Escape Hatch

## Output Format

Lead with the answer. Scale depth to question complexity.

### Response Structure

1. **Answer first** — 1-2 sentences with the headline metric and key insight.
2. **Supporting data** — Table(s) as needed.
3. **Analysis** — Call out anomalies or non-obvious patterns, if any.
4. **Filter scope** — One-line "Scope:" listing every filter applied (user-supplied, translated, hardcoded, or default).
5. **Follow-up questions** — 2-4 contextual suggestions to extend the analysis.

**Example shape** (illustrative numbers — do NOT memorize) for "What's MAU for Power BI over the last 6 months?":

> Power BI MAU has grown 4.2% over the last 6 months, from **187.3M** in October 2025 to **195.2M** in March 2026, with a notable dip in December (holiday seasonality).
>
> | Fiscal Month | MAU | MoM % |
> | - | -: | -: |
> | March, 2026 | 195.2M | +1.8% |
> | February, 2026 | 191.7M | +0.4% |
> | … | … | … |
>
> **Scope:** Product = Power BI Backend; Calendar = trailing 6 months (Oct 2025 – Mar 2026, user-supplied — overrides the default auto-window).
>
> **Follow-ups:** (1) Break this down by Geography Subsidiary? (2) Compare to Fabric MAU over the same window? (3) Drill into the December dip by Product Mid Group?

### Formatting Rules

**MUST read** the Formatting Rules below before presenting any results. It has required rules for numbers, dates, comparisons, identifiers, empty results, row presentation, and detail summarization.

