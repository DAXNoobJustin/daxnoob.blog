## Escape Hatch — Custom DAX (last resort)

For trained topics only — for shape gaps within a matched topic, not for missing topics or raw fact-table exploration (those route per the Out-of-scope Routing row ({{ref:out-of-scope}})).

Walk these phases in order. Each layer is the input to the next — do not skip ahead.

### Phase 1 — Verify you completed Workflow Step 3

Did you batch BOTH `DiscoverQuestions` AND `DiscoverMeasures`? Did you READ both returns before picking a call? Most "the standard call doesn't fit" moments are actually "I picked the wrong call because I matched on a topic-row example without confirming the live catalog." If you cannot cite the `QuestionId` you tried and the measure list you saw, go back.

### Phase 2 — Verify the standard call doesn't fit

Run `AnswerQuestion` (curated match) or `GenerateQuery` (no match) and read `[GeneratedDAX]` + `[AutoApplied]`. Most "the result is wrong" moments are a misread of `defaults:` / `hardcoded:` suppression — not a framework limitation.

### Phase 3 — `daxWrapper`

`GenerateQuery`'s `daxWrapper` parameter wraps the validated inner `SUMMARIZECOLUMNS` and lets you reshape the output (top-N, `GROUPBY` re-aggregation, `ADDCOLUMNS` bucketing, derived columns) while keeping every framework safeguard live — `DefaultFilters`, `HardcodedFilters`, `PairWith`, `AutoFilterWhenSliced`, hierarchy parent injection. See the Examples rows ({{ref:examples-part-1}}, {{ref:examples-part-2}}) § 8 for the technique catalog.

### Phase 4 — Custom DAX

Only after phases 1–3. If you cannot cite a specific `[GeneratedDAX]` line you tried AND a specific `daxWrapper` you tried, you are not at this phase yet.

Tag the call `/* ask-adia custom */` (block comment, exact text — do not vary). Lead the response with: *"Custom DAX — results are not framework-validated."* Critical Rule #2 still applies — every value resolved via `SearchValues` / `SearchHierarchy`, NEVER hard-coded.
