# Azure Data Partner & Community — AskADIA framework overlay

Per-model overlay for the **Azure Data Partner & Community** SemanticModel.
Slug `azure-data-partner-community` (auto-derived).

For the model-owner authoring workflow (annotations, instruction rows,
curated questions, and ranker UDFs), see
[`../../../MODEL_AUTHORING.md`](../../../MODEL_AUTHORING.md).

## Contents

- `functions.tmdl`
  - `_RankPartners` — ranker for `'Partner'[Partner Name]`, ranked
    by `[Partner Influenced Consumed Revenue (MTD)]`.
- `copilot_questions.json` — curated question catalog for the
  specialization topic (illustrative — assumes a richer Partner model than the
  trimmed sample; see the `specialization.md` row's caveat).
