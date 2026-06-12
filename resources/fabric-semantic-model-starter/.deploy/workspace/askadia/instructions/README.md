# ADIA Canonical Instructions

Single source of truth for ADIA copilot instruction content. Every block is
authored **once** in the neutral content store (`common/` + `models/<slug>/`)
and **emitted** to its targets so they never drift.

| Target | Artifact | Emitter |
| ------ | -------- | ------- |
| HelixData semantic models (ADI / PC) | `_COPILOT_INSTRUCTIONS.tmdl` calculated table + `Copilot/Instructions/instructions.md` always-on router | `emit_model.py` (deploy-only) |
| Router preview | `generated/adia-router.SKILL.md` | `emit_router.py` |

## Architecture (the pivot)

The full instructions live **only** in each model's `_COPILOT_INSTRUCTIONS` table.
A model queried directly (M365 Copilot, FabricIQ) self-guides: it fetches the
rows it needs and, when a question really belongs to a sibling model, reroutes
there. The **skill is a thin router** — it owns no query workflow, just a
high-level "which model + which topic" map generated from each model's
`model.json` (title + per-topic routes). Both
emitters are pure renderers over the content store; abstract tokens resolve per
target and per environment.

Per-model topic ownership (title + topic routes) lives in each
`models/<slug>/model.json`; `routing.json` keeps only the cross-model
`modelOrder` + the shared description config. There is **one** GUID source
(`config/model_guids.yml`). No content is duplicated between targets, and the few
self-contained "360" workflows are authored once as one-shot rows.

## Layout

```
askadia/
├── instructions/              # the instruction engine + single source content store
│   ├── routing.json           # cross-model `modelOrder` + shared description config
│   ├── common/                # SINGLE SOURCE: content identical across every model
│   │   ├── manifest.json      # structural config: shared-row grouping + row metadata
│   │   ├── router-preamble.md # generic always-on rules + mandatory workflow (shared by every router)
│   │   └── blocks/            # shared row bodies (workflow, udf-reference, output-formatting, examples-*)
│   ├── models/<slug>/         # everything specific to one model, COLOCATED
│   │   ├── model.json         # title + per-model rows (anchor/topic/whenToUse/routerHint + route) + workedExamples + golden
│   │   └── rows/              # per-model authored row bodies (model-reference, topics, the 360 one-shot); the slim out-of-scope row is GENERATED, not authored
│   ├── _core/                 # pure library
│   │   ├── tokens.py          # {{model-guid:<slug>}} + {{ref:<anchor>}} resolution
│   │   ├── guids.py           # the ONLY GUID-source reader (resolve_guids / load_guids)
│   │   ├── paths.py           # single owner of the on-disk layout
│   │   ├── routing.py         # model.json routing view + cross-model "reroute" section builder
│   │   ├── model_table.py     # calc-table boilerplate codec
│   │   ├── model_description.py # .platform model description (from model.json topics)
│   │   └── tmdl.py            # ROW(...) row codec
│   ├── emit_model.py          # emit: store -> model TMDL table + router (deploy-only)
│   ├── emit_router.py         # emit: model.json + modelOrder -> thin consumer router skill
│   ├── generated/             # committed preview + drift golden of the router artifact
│   │   └── adia-router.SKILL.md
│   └── test_roundtrip.py      # invariants (self-contained, no external checkout)
├── config/                    # framework config
│   └── model_guids.yml        # the ONE per-env dataset GUID source (copilot_model_guids)
├── deploy/                    # self-contained deploy ops (host registers setup_askadia_framework)
│   ├── setup_askadia_framework.py   # the single public op (runs the sub-op chain)
│   ├── merge_shared_scaffold.py     # UDF splice
│   ├── generate_copilot_instructions.py
│   ├── generate_copilot_questions.py
│   ├── generate_annotation_config.py
│   ├── generate_variant_config.py
│   ├── model_overlay.py             # slug + overlay path helpers
│   ├── paths.py                     # framework filesystem anchors
│   └── tabular_scripts/             # framework TE2 csx codegen scripts
└── udf/                       # the companion UDF/tables scaffold (owned by the deploy ops)
    ├── common/                # canonical framework UDFs + table shells + annotation config
    │   ├── functions.tmdl
    │   ├── askadia_config.json
    │   └── tables/
    └── models/<slug>/         # per-model overlay: README (the deploy GATE), ranker UDFs, curated questions

# GUIDs live in exactly one place, inside the framework package:
#   askadia/config/model_guids.yml  (copilot_model_guids: env-keyed dataset GUIDs)
```

Per-model **row bodies** live under `models/<slug>/rows/`, colocated with that
model's `model.json` (which keeps the model `title`, per-row metadata, a per-row
`route:{name,triggers}` on each user-facing topic row — the routing view consumed
by the reroute section, the model description, and the thin router —
`workedExamples`, and the golden snapshot). The shared rows are authored once
under `common/blocks/` and grouped by `common/manifest.json`. The emitter prepends
the shared rows ahead of the per-model rows and assigns every `Id` by
**position** — Ids are never authored. The always-on router is **fully generated**
(no authored `router.md`).

## Tokens

Bodies never hard-code target- or environment-specific values. Two token kinds:

- `{{model-guid:<slug>}}` — a model's dataset GUID. Resolved from
  `config/model_guids.yml` `copilot_model_guids` for the **target environment**
  (explicit per-env GUID, **no prod fallback** — a missing env GUID fails the
  deploy loudly) and **injected** into the renderer as a `slug -> guid` map;
  the renderer reads no config (portability boundary).
- `{{ref:<anchor>}}` — a cross-reference to another instruction row. Resolves to
  the referenced row's `` `key` `` (its anchor, the stable handle the LLM fetches
  by), so reordering rows can never drift a reference.

The rendered routers carry GUIDs only as `{{model-guid:<slug>}}` tokens — never
literal values. A stray unresolved token fails the emit loudly.

## GUIDs (single source)

`config/model_guids.yml`:

```yaml
copilot_model_guids:
  azure-data-insights:            { dev: "...", test: "...", prod: "aaaaaaaa-..." }
  azure-data-partner-community:   { dev: "...", test: "...", prod: "..." }
```

Every environment a model deploys to must have an **explicit** GUID — there is
**no prod fallback**. `prod` is required as the baseline; a missing env key fails
the deploy loudly.

`_core/guids.py` is the only reader: `resolve_guids(raw_map, env)` is pure and
validating (requires a `prod` baseline + well-formed, non-empty GUIDs);
`load_guids(config_path, env)` lazily loads the YAML. The deploy op resolves
`env` from `context.environment`; `emit_model` validates that the injected map
contains this model **and every active sibling** it reroutes to before rendering.

## One-shot "360" rows

`Customer 360` (ADI) and `Partner 360` (PC) are **self-contained one-shot**
rows: they bundle the full entity-resolution -> curated-DAX -> report workflow in
a single row and reference only the shared formatting row (`{{ref:output-formatting}}`).
The router-preamble teaches that, on a 360 intent, the model fetches **just that
one row + formatting** (the worked examples demonstrate it).

Their optional M365 pieces (Mode A meeting prep, the enrichment follow-up) are
**capability-gated**: used only when the current turn actually exposes
calendar/email/Teams retrieval (natively or via a tool such as `copilot_chat`)
**and** the host supports a follow-up turn; otherwise they are skipped silently
(no prompt, no mention). Single-turn hosts (one-shot FabricIQ) end after Key
Insights.

## Model side (`_COPILOT_INSTRUCTIONS`)

Each model's rows are the shared rows (grouped from `common/blocks/` by
`common/manifest.json`) followed by that model's own rows
(`models/<slug>/rows/`). The shared rows are byte-identical across models
(DRY); per-model rows are bespoke prose with `{{ref:anchor}}` cross-references.

```sh
# Regenerate a model's TMDL table + instructions.md router (writes into --model-dir).
python emit_model.py --slug azure-data-insights \
    --model-dir "<...>/Azure Data Insights.SemanticModel"

# GUIDs resolve from config/model_guids.yml for --env (default prod); override one model with --guid.
python emit_model.py --slug azure-data-insights --model-dir <...> --env prod
python emit_model.py --slug azure-data-insights --model-dir <...> --guid aaaaaaaa-...

# Golden / CI drift gate.
python emit_model.py --slug azure-data-insights --model-dir <...> --check
```

The table is a **calculated** `UNION(ROW(...))` partition (NOT an M `#table` —
calculated rows keep DirectLake validation + refresh working). `_core/tmdl.py` is
the row codec; `_core/model_table.py` adds the static table/column/annotation
boilerplate.

## Deploy-only generation + cross-model routing

The model `_COPILOT_INSTRUCTIONS.tmdl` + `instructions.md` are **not** source-
controlled on the models. They are generated into the *staged* model at deploy
(`generate_copilot_instructions`, pre_process, gated on a canonical
`models/<slug>/model.json`), env-aware via `context.release_type`.
Authoring a model's canonical dir is the only opt-in; nothing is written to the
model's source tree.

The same step sets the model's **metadata description** (capped at 500 chars,
generated from the model's `model.json` topics, so it can't drift from the
model's routes) onto the staged model's `.platform` (`metadata.description`, what
Copilot/M365 grounding reads); a hand-authored description is preserved as the
lead-in with a generated "Trained topics: …" suffix appended.
`_core/model_description.py` builds it (fails loudly > 500 chars, and if the
shared template/suffix/scope config is missing) and applies it idempotently.

Cross-model routing derives from each model's `model.json` routes + the
`modelOrder` in `routing.json`. `_core/routing.py`
appends an "Other Ask ADIA models — reroute" section to each model's router,
listing only *active* siblings (those with a `model.json`) with their env-
resolved GUID tokens. Two models are active: `azure-data-insights` (ADI),
`azure-data-partner-community` (PC).

Goldens are **emitter snapshots** (self-generated, deploy-only models have no
committed table to anchor against) — they pin drift, not correctness; the
invariant tests cover correctness. Re-bless after intentional content changes:

```sh
python emit_model.py --slug <slug> --update-golden
```

The emitted table carries
`annotation BestPracticeAnalyzer_IgnoreRules = {"RuleIDs":["ROLE_ALL_USERS_MISSING_TABLE_PERMISSION"]}`,
matching every other AskADIA framework calc table; the table is role-readable by
default (no `tablePermission` entry needed).

## Thin router (consumer skill)

`emit_router.py` turns each model's `model.json` (title + topic routes) + the
`modelOrder` in `routing.json` into the thin `adia-router` skill — a
high-level model+topic map with GUID **tokens** left unresolved (the consumer's own
deploy resolves them per environment). Only active models are emitted.

```sh
python emit_router.py                  # print the rendered router
python emit_router.py --update-golden  # rewrite the committed preview artifact
python emit_router.py --check          # CI drift gate
```

The rendered artifact is committed at `generated/adia-router.SKILL.md` purely as
a reviewable preview + drift golden. Nothing here writes outside this source
store.

## Tests

```sh
python -m pytest test_roundtrip.py      # or: python test_roundtrip.py
```

Asserts: the emitter consumes only the `common/` + `models/<slug>/` store; no
unresolved tokens after emit; no literal GUID/Id leaks into bodies; shared-row
grouping well-formed; per-model rows never reuse a shared anchor; TMDL codec
round-trips quotes/newlines/unicode; GUID resolution is env-aware + validating
and fails loud on a missing GUID; worked-example anchors all resolve; model
description is within cap + lists topics idempotently;
cross-model routing is correct + deterministic; the committed router artifact
matches the generator and lists every active model + topic; the framework is
split into `udf/` + `instructions/` with no legacy layout, every
instruction-active model is UDF-bootstrapped, and the deploy ops' canonical paths
all resolve.
