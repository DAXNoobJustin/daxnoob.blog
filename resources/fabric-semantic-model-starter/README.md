# Fabric Semantic Model Starter

> **Open source:** [daxnoob.blog/starter](https://daxnoob.blog/starter) · companion deep-dive posts on [daxnoob.blog](https://daxnoob.blog).

How a Microsoft analytics team runs **production semantic models on Fabric** —
the workspace layout, the dev loop, the CI/CD, the monitoring, and the agentic
layer — cleaned up and anonymized so you can lift the parts that fit.

The Azure Data Insights & Analytics team is the internal analytics arm for
Microsoft's Azure Data org; we run a small fleet of large DirectLake models and
treat them like the production systems they are — version-controlled, tested,
deployed, observed, and optimized. This repo distills those patterns into a
readable reference.

> **It's a reference, not a framework.** Nothing here is a drop-in package. GUIDs,
> endpoints, and identifiers are placeholders, and some content is illustrative.
> Read it, take the patterns, adapt them to your estate.

---

## How this repo is organized — three roots

| Root | What it is | Where |
|------|------------|-------|
| **1 · HelixData** | The engineering platform — how we build, deploy, test, and serve models. | code in this repo |
| **2 · Reliability** | Model monitoring, alerting, and auto-remediation. | [`reliability/`](reliability/) |
| **3 · Related tools** | Public tools the platform leans on (not re-shipped here). | [`RELATED-TOOLS.md`](RELATED-TOOLS.md) |

Roots 1 and 2 are code you can read and adapt. Root 3 is a curated set of
already-open-source tools, documented and linked rather than copied.

---

## Root 1 · HelixData — the engineering platform

The bulk of the repo: the loop that takes a model change from your editor to a
refreshed, tested model in production.

| Area | Path | What it is |
|------|------|------------|
| **Workspace items** | [`workspace/`](workspace/) | Fabric notebooks (one per load pattern — DIM / FACT / BRIDGE / STAGE / Tabular), DirectLake semantic models in TMDL, and an example orchestration pipeline. The repo *is* the source of truth — edited locally, shipped through PRs. |
| **Shared notebook library** | [`helixutils/`](helixutils/) | The Python library every notebook builds on: Delta reads/writes with retention + data-quality checks, and monitoring/incident helpers. (The refresh + adaptive-prewarm pattern itself lives in the `Util_RefreshSemanticModel` notebook.) |
| **Deploy engine + AskADIA framework** | [`.deploy/`](.deploy/workspace/README.md) | A `fabric_cicd`-based deploy engine with pre/post-process operations, plus the **AskADIA UDF framework** that turns a semantic model into a typed, deterministic API an LLM can query. |
| **CI/CD pipelines** | [`.pipelines/`](.pipelines/) | Azure DevOps YAML — PR validation gates plus a per-environment release pipeline (`Release_FabricWorkspace.yml`) that runs the `fabric_cicd`-based deploy engine (`deploy_workspace.py` → `publish_all_items`). |
| **Semantic-model unit tests** | [`semantic_model_tests/`](semantic_model_tests/README.md) | A DAX test harness that deploys a throwaway DirectLake model, asserts against it, and tears it down — fast enough to run as a PR gate. |
| **Notebook linter** | [`linter/`](linter/) | A custom AST linter (on top of Ruff) that enforces the notebook conventions so the platform stays consistent. |

**Go deeper:**
[`.deploy/workspace/README.md`](.deploy/workspace/README.md) (deploy engine) ·
[`.deploy/workspace/askadia/README.md`](.deploy/workspace/askadia/README.md) (AskADIA framework) ·
[`semantic_model_tests/README.md`](semantic_model_tests/README.md) (test harness) ·
[`AGENTS.md`](AGENTS.md) (conventions, branch/PR/promotion).

---

## Root 2 · Reliability — monitoring & auto-remediation

A self-contained system that watches the models in production and acts when
something's wrong: **KQL detectors → Data Activator (1-min) → cooldown SQL →
Teams / incident + auto-refresh.** Its hero is OneLake security-version drift,
which it detects and **auto-remediates** with a refresh before anyone is paged.

Everything runs on first-party Fabric surfaces (Workspace Monitoring, Eventhouse,
Data Activator, Pipelines, SQL Database, Notebooks) — no external infrastructure.

**Go deeper:** [`reliability/README.md`](reliability/README.md).

---

## Root 3 · Related tools — the wider ecosystem

The wider ecosystem leans on several tools that are already open-source, so this
repo points to them instead of copying them:

- **DAX Performance Tuner (MCP server)** — optimizes a slow DAX query with a
  Formula-Engine-vs-Storage-Engine trace breakdown and semantic-equivalence
  validation.
- **Semantic Model Audit** — builds a long-term audit (usage, unused columns,
  P90 trends) off Workspace Monitoring into a star-schema report.
- **DAX Performance Testing** — benchmarks query timings across cold / warm / hot
  cache states.
- **Skills for Fabric** — Microsoft's agentic skills + MCP for Fabric, including
  a DAX optimization reference used by the modeling workflow.
- **Power BI Modeling MCP** — gives an agent read/write access to a model's TMDL;
  the write-back engine behind the dev and optimize loops.
- **fabric_cicd** — open-source library that deploys Fabric workspace items from
  source; the engine this repo's `.deploy/` wraps.

**Full descriptions + repo links:** [`RELATED-TOOLS.md`](RELATED-TOOLS.md).

---

## How the pieces fit

| Capability | Where in this repo |
|---------|--------------------|
| Architecture | `workspace/` layout · this README |
| Dev loop | `workspace/` (notebooks + TMDL) · `helixutils/` · `linter/` |
| Deploy | `.deploy/` · `.pipelines/` · `semantic_model_tests/` |
| Observe | `reliability/` |
| Optimize | `workspace/` (`Util_RefreshSemanticModel` adaptive-prewarm) · `RELATED-TOOLS.md` (DAX Tuner MCP, Skills for Fabric) |
| AskADIA (beyond reports) | `.deploy/workspace/askadia/` |

---

## Where to start

- **Want the CI/CD + PR-gate tests?** → [`.pipelines/`](.pipelines/) + [`semantic_model_tests/`](semantic_model_tests/README.md)
- **Want monitoring / auto-remediation?** → [`reliability/`](reliability/README.md)
- **Want the agentic "model-as-typed-API" framework?** → [`.deploy/workspace/askadia/`](.deploy/workspace/askadia/README.md)
- **Want the notebook + library patterns?** → [`workspace/`](workspace/) + [`helixutils/`](helixutils/README.md)

---

## A note on scope

Distilled and anonymized from an internal repo. The Helix / Fabric workspace
names are kept for realism; GUIDs, endpoints, and identifiers are placeholders;
some models and content are illustrative. Treat it as a worked example to adapt —
not a supported product.
