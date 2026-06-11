# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "environment": {
# META       "environmentId": "00000000-0000-0000-0000-000000000000",
# META       "workspaceId": "00000000-0000-0000-0000-000000000000"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Refresh + prewarm + alert pattern — Util_RefreshSemanticModel
#
# Runs after the loads to refresh the model(s), then warms the cache so the
# first user query is fast, and raises an incident if a refresh fails. Three things
# the talk keeps coming back to, in one helper:
#
# 1. **Refresh** the Direct Lake / import model via `sempy` (`fabric.refresh_dataset`).
# 2. **Prewarm** — capture the columns resident in memory *before* the refresh,
#    then touch them with a cheap DAX query *after* so the model comes back warm.
# 3. **Alert** — on failure, `helix_monitoring.create_incident(...)` files an incident
#    instead of failing silently.
#
# Refresh runs as a service principal; pull every identifier from your own key
# vault — never hard-code a tenant id or secret name in the notebook.

# CELL ********************

import time

from helixutils import global_variable, helix_monitoring
from sempy import fabric

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def get_workspace_and_datasets(environment):
    """Map an environment to its workspace and the models to refresh."""
    return {
        "dev": ("Workspace-Dev-Insights", ["Semantic Model"]),
        "test": ("Workspace-Test-Insights", ["Semantic Model"]),
        "prod": ("Workspace-Insights", ["Semantic Model"]),
    }.get(environment, (None, []))


def wait_for_refresh(refresh_id, dataset, workspace, poll_interval=10, max_wait_time=1800):
    """Poll a refresh until it reports Completed/Failed, or time out."""
    elapsed = 0
    while elapsed < max_wait_time:
        history = fabric.list_refresh_requests(dataset=dataset, workspace=workspace)
        match = history[history["Request Id"] == refresh_id]
        if not match.empty and match["Status"].iloc[0] in ("Completed", "Failed"):
            return match["Status"].iloc[0]
        time.sleep(poll_interval)
        elapsed += poll_interval
    return "Timeout"


def resident_columns(dataset, workspace):
    """Columns currently held in memory — the set worth re-warming after refresh."""
    cols = fabric.list_columns(dataset=dataset, extended=True, workspace=workspace)
    return [f"'{r['Table Name']}'[{r['Column Name']}]" for _, r in cols.iterrows() if r.get("Is Resident") is True]


def prewarm(dataset, workspace, columns):
    """Touch each column with a tiny DAX query, concurrently, so it reloads into memory."""
    from concurrent.futures import ThreadPoolExecutor

    def touch(column_ref):
        try:
            fabric.evaluate_dax(dataset=dataset, dax_string=f"EVALUATE TOPN(1, VALUES({column_ref}))", workspace=workspace)
        except Exception:
            pass

    with ThreadPoolExecutor() as executor:
        list(executor.map(touch, columns))
    print(f"    warmed {len(columns)} columns")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def refresh_semantic_model():
    env = global_variable["environment"]
    workspace, datasets = get_workspace_and_datasets(env)
    if workspace is None:
        helix_monitoring.create_incident(
            title="[AUTOMATED] Semantic model refresh — invalid environment",
            description=f"Environment '{env}' is not configured (expected dev/test/prod).",
            severity=3,
            fields="Error",
        )
        return

    for dataset in datasets:
        print(f"🔄 Refreshing {dataset} in {workspace}...")
        warm_targets = resident_columns(dataset, workspace)

        try:
            refresh_id = fabric.refresh_dataset(workspace=workspace, dataset=dataset, refresh_type="full")
            status = wait_for_refresh(refresh_id, dataset, workspace)
        except Exception as e:
            status = f"Error: {e}"

        if status == "Completed":
            print(f"  ✅ {dataset} refreshed — prewarming...")
            prewarm(dataset, workspace, warm_targets)
        else:
            print(f"  ❌ {dataset} refresh {status} — filing an incident")
            helix_monitoring.create_incident(
                title=f"[AUTOMATED] Semantic model refresh failed — {dataset}",
                description=f"Refresh of '{dataset}' in '{workspace}' ended with status: {status}.",
                severity=3,
                fields="Error",
            )

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Authenticate as a service principal. Identifiers come from your key vault via
# helixutils globals — keep tenant ids and secret names out of source control.
tenant_id = global_variable["tenant_id"]
client_id = (global_variable["vault_url"], "your-app-client-id")
client_certificate = (global_variable["vault_url"], "your-app-certificate")

with fabric.set_service_principal(tenant_id, client_id, client_certificate=client_certificate):
    refresh_semantic_model()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
