# Related tools & ecosystem

This starter focuses on the engineering platform; a handful of adjacent tools
**aren't** its core. Some live right here in the repo; the rest are already
open-source in Microsoft's public repos, so this starter points to them rather
than re-shipping them.

> These are mature, open-source tools maintained in Microsoft's public repos. The
> notes below focus on what each does and when to reach for it.

---

## Lives in this repo

### Pipeline templates — `.pipelines/`

Reusable **Azure DevOps YAML** that runs the PR gates and the environment
deploys. This is the Deploy area's CI/CD made concrete.

- **Validation gates** (run on every PR): `Validate_Formatting.yml`,
  `Validate_Notebook.yml` (linter + helixutils checks), `Validate_PRName.yml`,
  `Validate_Tabular.yml`, and `Validate_SemanticModelTests.yml` (deploys a
  throwaway DirectLake model, runs DAX unit tests, tears it down).
- **Release pipeline**: `Release_FabricWorkspace.yml` (environment-based workspace deploy).
- **How the release calls `fabric_cicd`**: `Release_FabricWorkspace.yml` picks a
  release flavor from the branch, then runs `.deploy/workspace/deploy_workspace.py`,
  which builds a `fabric_cicd` `FabricWorkspace` and calls `publish_all_items` to
  deploy the workspace items for the target environment.

> These pipelines ship **flattened** so each `.pipelines/*.yml` is
> self-contained and readable on its own.

### Reliability / alerting system — `reliability/`

KQL detectors → Data Activator → cooldown SQL → Teams/incident + auto-refresh.
This is the Observe area's monitoring + auto-remediation. See
[`reliability/README.md`](reliability/README.md).

---

## Public tools (external repos)

### DAX Performance Tuner — MCP server

**[microsoft/fabric-toolbox › tools/DAXPerformanceTunerMCPServer](https://github.com/microsoft/fabric-toolbox/tree/main/tools/DAXPerformanceTunerMCPServer)**

An MCP server that turns DAX optimization into an AI-assisted loop. Connect it to
a model (Power BI Service workspace **or** a local Desktop instance), and it runs
a 2-stage workflow: capture a baseline, then iterate — each round pulls targeted
optimization guidance, analyzes a performance trace with a **Formula Engine vs
Storage Engine** breakdown, and **semantically validates** that the rewrite
returns identical results. This is the tool featured in the Optimize segment's
"AI-assisted DAX" workflow.

- **Good for:** systematically optimizing a specific slow query with evidence
  (FE/SE timings) instead of guesswork.

### Power BI Modeling MCP

**[microsoft/powerbi-modeling-mcp](https://github.com/microsoft/powerbi-modeling-mcp)**

The MCP server that gives an AI agent read/write access to a semantic model's
**TMDL** — measures, columns, tables, relationships, hierarchies — against Power
BI Desktop, a Fabric workspace, or a local PBIP folder, plus DAX execution and
performance tracing. It's the write-back engine underneath both the Dev loop (the
agent edits the raw TMDL in the repo) and the Optimize loop (it applies the tuned
measure); the DAX Performance Tuner and Skills for Fabric drive it under the hood.

- **Good for:** letting an agent author or edit a model reliably — immediate
  effect on the live model, no hand-editing TMDL and no desync.

### Semantic Model Audit

**[microsoft/fabric-toolbox › tools/SemanticModelAudit](https://github.com/microsoft/fabric-toolbox/tree/main/tools/SemanticModelAudit)**

A notebook + Power BI template that builds a long-term audit of your semantic
models. The notebook captures metadata, query logs, object dependencies, unused
columns, cold-cache performance, and per-column resident statistics into a star
schema (in a lakehouse/warehouse); the included `.pbit` turns that into an
interactive report. Runs off **Workspace Monitoring**, the same backbone the
`reliability/` detectors use. This is the "long-term observability" tool in the
Observe segment.

- **Good for:** seeing P90 trends, per-report usage, and — the killer feature —
  **which columns/measures are actually used**, so you can drop dead weight and
  improve VertiPaq compression.

### DAX Performance Testing

**[microsoft/fabric-toolbox › tools/DAXPerformanceTesting](https://github.com/microsoft/fabric-toolbox/tree/main/tools/DAXPerformanceTesting)**

A notebook that benchmarks DAX query timings under **cold / warm / hot cache**
states. You hand it a list of queries (from an Excel sheet) and a set of models;
it controls cache state (including pause/resume for true cold-cache on
Import/DirectQuery), runs each query, and logs duration/CPU to a lakehouse via an
Analysis Services trace.

- **Good for:** A/B-testing two versions of a measure, or measuring the perf
  impact of a model change — repeatably, across storage modes.

### Skills for Fabric — and the DAX optimization reference

**[microsoft/skills-for-fabric](https://github.com/microsoft/skills-for-fabric)**

Microsoft's collection of agentic **skills + MCP** for operating over Fabric from
Copilot CLI, VS Code, and Claude — authoring, consumption, and operations
plugins for Spark, Warehouse, Eventhouse, semantic models, and more. It's the
"primary" DAX optimization tooling in the Optimize segment.

Its **DAX optimization reference** lives inside the
`semantic-model-authoring` skill — the reference docs that drive the
optimization workflow:

- [`dax-guidelines.md`](https://github.com/microsoft/skills-for-fabric/blob/main/plugins/fabric-skills/skills/semantic-model-authoring/references/dax-guidelines.md)
- [`dax-perf-decision-guide.md`](https://github.com/microsoft/skills-for-fabric/blob/main/plugins/fabric-skills/skills/semantic-model-authoring/references/dax-perf-decision-guide.md)
- [`dax-perf-patterns.md`](https://github.com/microsoft/skills-for-fabric/blob/main/plugins/fabric-skills/skills/semantic-model-authoring/references/dax-perf-patterns.md)

- **Good for:** giving any agent (not just one MCP) the same expert DAX
  optimization patterns — push work into the Storage Engine, kill Formula Engine
  round-trips, avoid virtual columns in `SUMMARIZE`, watch context transitions.

### fabric_cicd

**[microsoft/fabric-cicd](https://github.com/microsoft/fabric-cicd)** ([docs](https://microsoft.github.io/fabric-cicd/))

The open-source Python library that publishes Fabric workspace items — notebooks,
environments, pipelines, semantic models, variable libraries — from source, with
environment-specific parameter substitution. It's the deploy **engine this repo's
`.deploy/` wraps** with pre/post-process operations (framework injection, refresh,
prewarm) — the backbone of the Deploy segment.

- **Good for:** scripted, environment-aware deployment of Fabric items straight
  from a git repo.

---

## Companion reading — daxnoob.blog

Deep-dives from the companion blog ([daxnoob.blog](https://daxnoob.blog)) on the patterns this repo demonstrates:

| Topic | Post |
|------|------|
| **Deploy** — `fabric_cicd` pre/post-processing ops | [Extending fabric-cicd with pre/post-processing](https://daxnoob.blog/extending-fabric-cicd-with-pre-post-processing/) |
| **Dev loop** — raising errors with data-quality tests | [Sometimes it's good to fail: raising errors with data-quality tests](https://daxnoob.blog/sometimes-its-good-to-fail-raising-errors-with-data-quality-tests/) |
| **Observe** — long-term Semantic Model Audit | [Fabric Toolbox: Semantic Model Audit](https://daxnoob.blog/fabric-toolbox-semantic-model-audit/) |
| **Observe** — capacity spikes via Workspace Monitoring | [Identifying semantic model capacity spikes using Workspace Monitoring](https://daxnoob.blog/identifying-semantic-model-capacity-spikes-using-workspace-monitoring/) |
| **Optimize** — DAX Performance Tuner MCP | [MCP server: DAX Performance Tuner](https://daxnoob.blog/mcp-server-dax-performance-tuner/) |
| **Optimize** — model size reduction | [Reducing semantic model size with creative solutions](https://daxnoob.blog/reducing-semantic-model-size-with-creative-solutions/) |
| **Optimize** — optimization theory, tips & tools | [Semantic model optimization: theory, tips, and tools](https://daxnoob.blog/semantic-model-optimization-theory-tips-and-tools/) |

---

## At a glance

| Tool | Repo | Segment | Re-shipped here? |
|------|------|---------|------------------|
| Pipeline templates | this repo › `.pipelines/` | Deploy | ✅ in-repo |
| Reliability / alerting | this repo › `reliability/` | Observe | ✅ in-repo |
| DAX Performance Tuner MCP | fabric-toolbox | Optimize | ❌ link only |
| Semantic Model Audit | fabric-toolbox | Observe | ❌ link only |
| DAX Performance Testing | fabric-toolbox | Optimize | ❌ link only |
| Skills for Fabric (+ DAX reference) | skills-for-fabric | Optimize | ❌ link only |
| Power BI Modeling MCP | powerbi-modeling-mcp | Dev / Optimize | ❌ link only |
| fabric_cicd | fabric-cicd | Deploy | ❌ link only |
