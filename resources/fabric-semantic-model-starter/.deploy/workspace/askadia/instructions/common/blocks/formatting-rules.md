## Formatting Rules

### Numbers

- Round large numbers in summaries: "$4.7M" not "$4,712,345"
- Keep exact values in detailed tables
- ALWAYS include the period the data covers
- **Identifiers (AccountKey, IDs) are not quantities** - NEVER apply thousand separators. Display as `1234567`, not `1,234,567`

### Dates

- ALWAYS include calendar year: "Feb 2026", NEVER just "February"
- Growth metrics MUST show MoM % and YoY % - NEVER vague labels like "Growing"
- If YoY unavailable, state "N/A" - don't omit the column

### Comparisons

- Use MoM, MoM%, and similar measures from UDF output - do not create your own
- State comparison explicitly: "vs. February 2025" not "vs. prior period"

### Metadata

- Tags from `DiscoverMeasures` and `DiscoverColumns` (`searchable`, `sliceable`) — display as-is, do not rename or reinterpret
- Synonyms — display as comma-separated list when presenting column details

### Empty Results

- Not errors - explain why: "No data matched because..."
- Suggest loosening filters, adjusting time range, or checking a different dimension

### Row Presentation

- **≤50 rows**: Show ALL rows in the table. Do not truncate or summarize.
- **>50 rows**: Show the top 10-20 rows and summarize the rest (total count, range, notable outliers).
- When using `ORDER BY` with `DESC`, the top rows are the most important — ALWAYS show those.

### Summarize, Don't Dump

When presenting detail data (NPS comments, support case details, or any row-level data), **summarize by theme** — group by sentiment, severity, product, or other natural categories. Highlight recurring patterns, outliers, and actionable items. Only show raw rows when the user explicitly asks for them or when fewer than 10 rows exist.

