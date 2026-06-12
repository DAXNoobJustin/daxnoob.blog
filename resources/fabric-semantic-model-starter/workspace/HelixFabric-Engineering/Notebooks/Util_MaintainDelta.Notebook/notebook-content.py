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

# # Maintenance pattern — Util_MaintainDelta (vacuum + time-travel rollback)
#
# Housekeeping for the data product's Delta tables. Two operations that keep
# Direct Lake fast and make a bad load recoverable:
#
# 1. **Vacuum** — `helix_delta.vacuum(path, retention=...)` removes old data
#    files so storage and the file count per table stay bounded (a smaller,
#    tidier table reframes and scans faster under Direct Lake).
# 2. **Rollback** — `helix_delta.rollback(path, commit=False)` uses Delta
#    time-travel to find the last good version. It is a **dry-run by default**;
#    inspect the version it reports, then re-run with `commit=True` to restore.
#
# The table list and paths are illustrative -- point them at your own tables.

# CELL ********************

from helixutils import connection, helix_delta

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Tables to keep tidy. Vacuum removes data files older than the retention
# window; keep the window comfortably longer than your longest-running reader.
tableList = [
    "FACT_RevenueAndLicense",
    "DIM_Account",
    "DIM_Calendar",
    "DIM_ProductMaster",
]

for table in tableList:
    helix_delta.vacuum(connection["core_default"] + f"/{table}/", retention="7d")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Recovery: roll a table back to its last good version using Delta time-travel.
# commit=False only logs the version it WOULD restore -- inspect that first,
# then re-run with commit=True to actually restore. max_date is optional and
# lets you roll back to the last good version on or before a point in time.
helix_delta.rollback(
    connection["core_default"] + "/FACT_RevenueAndLicense/",
    commit=False,
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
