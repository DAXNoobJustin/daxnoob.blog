# Azure Data Insights — AskADIA framework overlay

Per-model overlay for the **Azure Data Insights** SemanticModel. Slug
`azure-data-insights` (auto-derived).

For the model-owner authoring workflow (annotations, instruction rows,
curated questions, and ranker UDFs), see
[`../../../MODEL_AUTHORING.md`](../../../MODEL_AUTHORING.md).

## Contents

- `functions.tmdl` — `_RankAccounts` (per-model ranker for `'Account'[Account]`,
  ranked by `[MAU]`).
- `copilot_questions.json` — curated question catalog (usage / revenue /
  consumption, plus the `customer_360_overview` orchestrator).
