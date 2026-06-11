# HelixFabric-Engineering

The engineering (development) workspace: ETL + tabular-load notebooks that build the
DirectLake tables consumed by the curated semantic models in **HelixFabric-Insights**.

## Contents

- **Notebooks/** — one notebook per load pattern: `Load_DIM_*`, `Load_FACT_*` /
  `Load_Tabular_*`, `Load_BRIDGE_*`, `Load_STAGE_*`, plus `Util_*` helpers
  (e.g. refresh + adaptive-prewarm). Every notebook builds on the shared `helixutils`
  library (`helix_read` / `write_delta` / `CheckConfig`).
- **Environments/** — Spark environments (`Env_Default`, `Env_Custom`, `Env_Tabular`)
  that distribute `helixutils` to the notebooks via `Libraries/CustomLibraries/`.
- **Pipelines/** — an example worker pipeline (`05_WorkerNotebook`) showing how loads are
  orchestrated: a retry/until loop that conditionally invokes load notebooks + sub-pipelines
  (`dependsOn` DAG edges), failing loudly on error.
- **Variables/** — connection variable libraries (`connection[...]`, `linked_services`).

See the repo-root [`AGENTS.md`](../../AGENTS.md) for notebook conventions and the
[`linter/`](../../linter) that enforces them.