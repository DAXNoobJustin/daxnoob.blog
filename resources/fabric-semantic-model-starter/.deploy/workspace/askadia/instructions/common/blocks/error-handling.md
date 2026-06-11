## Error Handling

Triage for `ExecuteQuery` failures, unknown measures/questions, empty results, `Invalid filter column(s)`, and `SearchValues` timeouts — consult only when something has actually gone wrong during Discover (Step 3), filter resolution (Step 4), or query execution (Step 5), not on every turn. Most recoveries are a single retry with adjusted UDF arguments.

- **Unknown measure or question** (UDF returns empty / error DAX, or `Question '<id>' not found`): Call `DiscoverMeasures("term")` / `DiscoverQuestions("term")` to verify the name; pass `""` to dump the full catalog.
- **Execution error:** Read the error, adjust UDF arguments, retry once. `Invalid filter column(s)` → re-check `ValidColumns` in `DiscoverMeasures` and fix the table reference. If it still fails, report the error to the user.
- **Empty results:** Loosen filters or widen the time window via the model's Calendar columns (see your model reference's Calendar subsection for available columns and value formats). If still empty, tell the user no data matched and suggest checking spelling or scope.
- **Empty DiscoverColumns results:** Broaden the search term, or fall back to `DiscoverMeasures("")` and the topic rows for column details.
- **SearchValues timeout:** Retry with a shorter/more specific search term (for example, `"contoso"` instead of `"contoso AG Germany"`). Account SearchValues calculates MAU for each match — broad terms hitting 50+ accounts will timeout.

