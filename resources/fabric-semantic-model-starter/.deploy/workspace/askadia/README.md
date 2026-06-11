# AskADIA UDF framework

A shared scaffold of DAX UDFs and metadata tables that lets Copilot
consumers (for example, an Azure Data Insights agent/skill)
discover and query Power BI semantic models through a uniform interface —
instead of every consumer hand-rolling DAX against each model's quirks.

This document is for **framework maintainers** — canonical UDFs, deploy
pipeline, annotation registry mechanics, runtime contract. For the
**model-owner** workflow (adding annotations, authoring curated
questions, writing per-model ranker UDFs, keeping the consumer-side docs
in sync), see [`MODEL_AUTHORING.md`](MODEL_AUTHORING.md).

For the debug-deploy loop, see [`../DEBUG_DEPLOY.md`](../DEBUG_DEPLOY.md).
For the test pipeline, see [`semantic_model_tests/README.md`](../../../semantic_model_tests/README.md).

---

## Big picture

```
           ┌─────────────────────────────────────────┐
           │   askadia/  (this directory)     │
authoring  │  • udf/common/functions.tmdl  canonical │
           │  • udf/common/tables/*.tmdl   fw tables  │
           │  • udf/models/<slug>/  per-model overlays│
           └──────────────────┬──────────────────────┘
                              │  setup_askadia_framework
                              │  (pre_process bundle)
                              ▼
           ┌─────────────────────────────────────────┐
deploy     │   <Model>.SemanticModel/definition/     │
           │   • merged functions.tmdl               │
           │     (canonical + overlay)               │
           │   • _INFO_*, _COPILOT_* tables          │
           │     (placeholders filled by csx scripts │
           │     from live Copilot_* annotations)    │
           └──────────────────┬──────────────────────┘
                              │  publish via fabric_cicd
                              ▼
           ┌─────────────────────────────────────────┐
runtime    │   Power BI service (Insights workspace) │
           │   a consumer calls Local.AskADIA.*      │
           │   UDFs via ExecuteQuery                 │
           └─────────────────────────────────────────┘
```

The framework's job is to make the **runtime** layer uniform across
models without forcing the **authoring** layer to copy-paste UDFs and
framework tables into each model's TMDL.

---

## Key concepts

| Term | Meaning |
|---|---|
| **Canonical** | UDFs and tables in `askadia/udf/common/` — identical across all bootstrapped models, spliced into each model's TMDL at deploy. |
| **Overlay** | Per-model artifacts in `askadia/udf/models/<slug>/`. Model-specific ranker UDFs, curated questions, the README intent marker. |
| **Framework table** | `_INFO_*` / `_COPILOT_*` tables that expose model metadata (columns, measures, annotations, hierarchies, curated questions, value-synonym registry, annotation-rendering registry, measure-variant registry) as queryable DAX tables. |
| **Public entrypoint UDF** | One of `GenerateQuery`, `AnswerQuestion`, `DiscoverMeasures`, `DiscoverQuestions`, `DiscoverColumns`, `SearchValues`, `SearchHierarchy` — runtime API to consumers. Everything else (`_LeadingUnderscore` + `INTERNAL` in its doc comment) is an internal helper. |
| **`Copilot_*` annotation** | Model-author-controlled hints on tables, columns, measures, hierarchies that drive runtime behavior. Captured into `_INFO_ANNOTATIONS` at deploy. |
| **AskADIA config** | The `askadia_config.json` file that declares framework-level annotation rendering and measure variant suffixes. |
| **Slug** | Auto-derived directory name for a model overlay (`"Azure Data Insights"` → `azure-data-insights`). Computed by `resolve_model_slug` in `model_overlay.py`. |
| **Bootstrapped** | A model with `askadia/udf/models/<slug>/README.md` is "on the framework." The deploy pipeline auto-detects this and runs the framework setup chain. Models without the marker are skipped. |

---

## `Copilot_*` annotations

Annotations are the contract between **model authors** and the framework.
The full annotation reference (when to set/skip each, format rules,
gotchas) is in [`MODEL_AUTHORING.md`](MODEL_AUTHORING.md). This section
covers framework-internal mechanics only.

`generateInfoAnnotations.csx` captures every `Copilot_*` annotation it
finds on the model and writes them into `_INFO_ANNOTATIONS`. Adding a
new annotation **type** therefore requires no codegen change — but it
needs a UDF that consumes it, otherwise nothing happens at runtime.

### AskADIA config

A subset of annotations (currently `Copilot_Enumerable`,
`Copilot_Sliceable`, `Copilot_AutoIncludeParents`, `Copilot_PairWith`,
`Copilot_AutoFilterWhenSliced`) project a literal string into the
`DiscoverColumns` `Tags` / `Behavior` output columns. The projection is
declarative — driven by the `annotationRegistry` section in
[`askadia_config.json`](./udf/common/askadia_config.json), not hand-coded DAX branches.

Each entry: `AnnotationKey`, `ObjectType`, `Surface`, `EmitOrder`,
`RenderedValue`, `Description`. The pipeline is:

```
askadia_config.json.annotationRegistry
    → generate_annotation_config (Python op)
    → generateAnnotationConfig.csx (TE2)
    → rewrites _COPILOT_ANNOTATIONS_REGISTRY partition
    → _GetAnnotationsForSurface iterates registry at query time
    → DiscoverColumns joins Tags + Behavior into output
```

Validation (fails the deploy loud): `Surface` must be
`DiscoverColumnsTags` or `DiscoverColumnsBehavior`; `RenderedValue` must
be non-empty; malformed JSON is rejected by the CSX script.

The registry is intentionally narrow — only "annotation-key → display-
string" projections for `DiscoverColumns` metadata columns. Complex
emit functions (`_FormatAutoApplied`, `_FormatFactBody`,
`_FormatTopicFactBody`) are not registry-driven. To add a new tag /
behavior: one-row JSON edit + redeploy.

The same config file's `measureVariants` section declares suffixes for
existing measure variants that AskADIA can auto-include and accept as
sort aliases. The framework does not create those measures; it only
discovers variants that already exist in the semantic model.

---

## Framework setup chain

`setup_askadia_framework` is a bundled pre_process op (dispatched from
`HelixFabric-Insights.yml`). It runs these sub-ops in order; later
sub-ops depend on earlier ones syncing the table shells.

| # | Sub-op | Reads | Writes | When body matters |
|---|---|---|---|---|
| 1 | `merge_shared_scaffold` | `udf/common/functions.tmdl`, `udf/common/tables/*.tmdl`, `udf/models/<slug>/functions.tmdl` | per-model `definition/functions.tmdl`, `definition/tables/_*.tmdl` | Edit any canonical UDF / table or any overlay UDF |
| 2 | `generate_copilot_instructions` | `instructions/models/<slug>/model.json` + `rows/`, `instructions/common/{manifest.json,blocks/,router-preamble.md}`, `config/model_guids.yml` | `_COPILOT_INSTRUCTIONS` table, `Copilot/Instructions/instructions.md` router, staged `.platform` description | Add/edit an instruction row body, a model's `title` / `route`, or a shared block / manifest |
| 3 | `generate_copilot_questions` | `udf/models/<slug>/copilot_questions.json` | `_COPILOT_QUESTIONS` partition | Edit curated questions |
| 4 | `generate_annotation_config` | `askadia_config.json.annotationRegistry` | `_COPILOT_ANNOTATIONS_REGISTRY` partition | Change which `Copilot_*` annotations render as Tags / Behavior |
| 5 | `generate_variant_config` | `askadia_config.json.measureVariants` | `_COPILOT_VARIANT_CONFIG` partition | Change which existing measure suffixes AskADIA auto-includes / accepts as sort aliases |
| 6 | `generateInfoAnnotations.csx` | live `Copilot_*` annotations | `_INFO_ANNOTATIONS` DATATABLE | Add / change any `Copilot_*` annotation on a model object |
| 7 | `generateInfoHierarchies.csx` | live hierarchy definitions | `_INFO_HIERARCHIES` DATATABLE | Add / restructure hierarchies |
| 8 | `generateSearchHelpers.csx` | `Copilot_SearchRanker` + `Copilot_SearchLadder` + `Copilot_ValueSynonyms` annotations, ranker UDF presence | `_SearchAllValues` + `_SearchAllLadderColumns` UDF bodies (between `BEGIN/END GENERATED` markers) + `_COPILOT_VALUE_SYNONYMS` partition expression | Add / remove search annotations, change value-synonym mappings, or rename ranker UDFs |

`generate_copilot_schema` runs as a separate op after this bundle. It's
PBI-native Copilot tooling (emits `Copilot/schema.json`) and self-gates
on `Copilot/schema.json` presence — not part of the AskADIA framework.

### Common change types

| You change | What gets re-run automatically | What you should also do |
|---|---|---|
| Canonical UDF body | Step 1 splices new body into all bootstrapped models | Verify the signature didn't change (runtime contract). Run the test pipeline. |
| Canonical UDF **signature** | Step 1 splices new signature | **Coordinate with the consumer skill** — public-entrypoint signatures are runtime contract. |
| New canonical UDF | Step 1 picks it up automatically | Add unit test cases under `_shared/`. |
| Overlay ranker UDF | Step 1 splices into target model only | If new, also add the `Copilot_SearchRanker` annotation to a column. |
| `Copilot_*` annotation on a model object | Step 6 captures into `_INFO_ANNOTATIONS`. Step 8 re-runs if `SearchRanker` / `SearchLadder` / `ValueSynonyms` changed. | Annotate via `powerbi-modeling-mcp` — don't hand-edit TMDL. |
| Instruction row body, model `title` / `route`, or a shared block / manifest | Step 2 re-emits the `_COPILOT_INSTRUCTIONS` table + `instructions.md` router | Run `test_roundtrip.py`; re-bless goldens with `emit_model.py --slug <slug> --update-golden`. |
| `copilot_questions.json` | Step 3 rewrites `_COPILOT_QUESTIONS` partition | Verify each question references measures that exist on the model. |
| `askadia_config.json.annotationRegistry` | Step 4 rewrites `_COPILOT_ANNOTATIONS_REGISTRY` partition | Add an `_shared/annotation_registry_shape.yml` test case for the new row. |
| `askadia_config.json.measureVariants` | Step 5 rewrites `_COPILOT_VARIANT_CONFIG` partition | Verify variant ordering in generated DAX snapshots. |
| Hierarchy structure | Step 7 captures into `_INFO_HIERARCHIES` | If hierarchy carries `Copilot_SearchLadder=true`, step 8 also re-runs. |
| New canonical framework table in `udf/common/tables/` | Step 1 picks it up automatically | If the table requires per-deploy population, add a csx script and wire it into the bundle. |

---

## Runtime contract

The public entrypoint UDFs are queried at runtime by external consumers.
Treat them as a stable API.

| UDF | Used for |
|---|---|
| `GenerateQuery` | Synthesize a `SUMMARIZECOLUMNS` query from a measure + slice + filters spec. |
| `AnswerQuestion` | Run a curated question from `_COPILOT_QUESTIONS` with parameter overrides. |
| `DiscoverMeasures` | List Copilot-visible measures grouped by fact table. |
| `DiscoverQuestions` | List curated questions grouped by Topic > Fact. |
| `DiscoverColumns` | List Copilot-visible columns. |
| `SearchValues` | Generic value-search dispatcher (ranked / ladder / generic). |
| `SearchHierarchy` | Hierarchy-aware ladder search returning `(Ladder, Position, Table, Column, MatchedValue)`. |

Stability rules:

- **Parameter signatures are contract.** Renaming, reordering, or
  changing parameter types is a breaking change. Coordinate with
  the consumer skill (PR-cross-link the change).
- **Return shapes are contract.** Adding a column to a returned table is
  generally safe; removing or renaming columns is breaking.
- **Internal helpers are NOT contract.** Refactor freely. Identify them
  by the `INTERNAL` prefix in the doc comment and the `_LeadingUnderscore`
  naming convention.

---

## Deploy-time invariants

1. **Single source of truth.** Canonical UDFs in `udf/common/functions.tmdl` and
   tables in `udf/common/tables/` are the only authoritative copies. Per-model
   files do not contain these in their committed form — they're added
   back at deploy time. The placeholder framework tables
   (`_INFO_ANNOTATIONS`, `_INFO_HIERARCHIES`, `_COPILOT_QUESTIONS`,
   `_COPILOT_VALUE_SYNONYMS`, `_COPILOT_ANNOTATIONS_REGISTRY`) and the
   codegen-stub UDFs (`_SearchAllValues`, `_SearchAllLadderColumns`)
   are rewritten in-place by the matching csx scripts.
2. **Block format (functions).** Each UDF is a contiguous `///`
   doc-comment chain (optional) followed immediately by
   `function 'Local.AskADIA.NAME' = ...` and any trailing properties
   (`isHidden`, `annotation TE_Group = ...`). Blocks are separated by
   blank lines.
3. **File format (tables).** Each `tables/*.tmdl` is a complete TMDL
   table file. The merge op overwrites the per-model copy with the
   canonical content verbatim.
4. **Overlay-vs-canonical names are disjoint.** Overlay UDF names must
   not collide with canonical UDF names. The merge op enforces this at
   deploy time with a clear error message.
5. **No source-side editing in per-model files.** Edits to a shared UDF
   or table directly in `<Model>.SemanticModel/definition/` are silently
   overwritten on next deploy (the op logs WARN when it does). Edit in
   `askadia/` (canonical) or `askadia/udf/models/<slug>/`
   (overlay) instead.
6. **Bootstrapped models only.** The framework bundle gates on
   `udf/models/<slug>/README.md` presence. Models without the marker are
   silently skipped.

---

## Overlay layout

Each `udf/models/<slug>/`:

- `README.md` — required. Its presence is the framework's intent marker
  (`setup_askadia_framework` raises if the dir exists without the README).
  Content is per-model state — see existing overlays for the shape.
- `functions.tmdl` — optional. Per-model UDFs only (rankers, deprecated
  legacy UDFs). Must not collide with canonical UDF names.
- `copilot_questions.json` — optional. Curated question registry.

---

## Bootstrapping a new model

Model-owner workflow, not framework-maintainer workflow. Full recipe
(compute slug, create overlay dir, add `Copilot_*` annotations, author
the first curated questions, debug-deploy + test) in
[`MODEL_AUTHORING.md`](MODEL_AUTHORING.md).

Framework-side: no allowlist edit, no YAML map. `resolve_model_slug`
derives the slug from the display name; `setup_askadia_framework` infers
eligibility from `models/<slug>/README.md` presence; the next deploy
picks up the new model automatically.

---

## Porting to another repo or team

The framework is self-contained **within `.deploy/workspace/`** — it depends on
the pre/post-processing framework that ships alongside it (`process_orchestrator.py`,
`operations/run_tabular_editor.py`), so the unit of handoff is `.deploy/workspace`
(or at least: `askadia/`, `operations/`, `process_orchestrator.py`, and a
deploy YAML), **not** `askadia/` alone.

A receiving team needs:

- **Python deps:** `fabric-cicd`, `azure-identity`, `PyYAML`, `requests`
  (`run_tabular_editor` auto-downloads Tabular Editor 2 — pinned to 2.27.2 — on
  first use; no manual install).
- **A host deploy YAML.** `../../configs/HelixFabric-Insights.yml` is the working
  Helix reference: copy it, drop the non-AskADIA ops, and keep the
  `setup_askadia_framework` (pre_process) + `generate_copilot_schema` entries.
  `process_orchestrator.py` discovers and dispatches the op from there.
- **Their own model content.** Replace, per adopted model: the instruction store
  (`instructions/models/<slug>/` + add the slug to `instructions/routing.json`
  `modelOrder`), the UDF overlay (`udf/models/<slug>/` with a `README.md`), and the
  per-env dataset GUIDs in `config/model_guids.yml` (every environment — no
  fallback). See [`MODEL_AUTHORING.md`](MODEL_AUTHORING.md) for the per-model steps.

The shipped ADIA models (`azure-data-*`) are working examples — delete or replace
them. Everything else (the engine, deploy ops, tests) is model-agnostic.

---

## See also

- [`MODEL_AUTHORING.md`](MODEL_AUTHORING.md) — model-owner authoring guide
- [`../DEBUG_DEPLOY.md`](../DEBUG_DEPLOY.md) — debug-deploy runbook
- [`semantic_model_tests/README.md`](../../../semantic_model_tests/README.md) — test contributor guide
- [`../README.md`](../README.md) — deploy infrastructure overview
- `./deploy/setup_askadia_framework.py` — bundled framework setup op
- `./deploy/merge_shared_scaffold.py` — splice logic
- `./deploy/model_overlay.py` — slug + overlay path helpers
- `./deploy/tabular_scripts/generate*.csx` — framework codegen scripts
- `../../configs/HelixFabric-Insights.yml` — pipeline wiring
