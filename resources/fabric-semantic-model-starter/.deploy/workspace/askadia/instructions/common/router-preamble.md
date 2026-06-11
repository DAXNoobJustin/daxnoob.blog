## Always-on rules

- Never fabricate numbers. Every metric, row, trend, and count must come from a DAX query against this model.
- Use `Local.AskADIA.*` UDFs through DAX. For metrics, first call `DiscoverQuestions` and `DiscoverMeasures`; then use `AnswerQuestion` or `GenerateQuery`; then execute the returned `GeneratedDAX`.
- Resolve user-named values at query time with `SearchValues` or `SearchHierarchy`. Do not hard-code accounts, products, dimensions, identifiers, or other named values from memory.
- Read the `AutoApplied` output after every `AnswerQuestion` or `GenerateQuery` call.

## Mandatory workflow

1. **Always fetch the core rows.** Every data question runs on the same engine, so fetch all four of `workflow`, `udf-reference`, `output-formatting`, and `model-reference` together. They carry the discovery/generate/execute contract, the UDF reference, the result-formatting + error-handling rules, and this model's account/calendar/product/geography reference. These are required, not optional — do not skip them to "be selective".
2. **Add the matching topic rows.** From the Topic index below, add the 1-2 topic keys whose signals match the question. Add `examples-part-1` / `examples-part-2` only when you need a worked pattern.
   - **Self-contained one-shot rows.** A few rows bundle a complete end-to-end workflow (their Topic and When-to-use say so — for example a "360" account/partner review or meeting prep). When the user's intent matches one, fetch **just that single row** plus the formatting row it points to, and follow it end to end. Do **not** add the core rows or other topic rows — the one-shot already contains the exact UDF calls it needs.
3. Fetch the rows in one batched query:

```dax
EVALUATE
FILTER(
    SELECTCOLUMNS(
        '_COPILOT_INSTRUCTIONS',
        "Key", [Key],
        "Topic", [Topic],
        "Instructions", [Instructions]
    ),
    [Key] IN { "workflow", "udf-reference", "output-formatting", "model-reference", "usage" }
)
```

4. Follow the returned markdown exactly. If a fetched source excerpt references a local file path, use the corresponding `_COPILOT_INSTRUCTIONS` row instead.
