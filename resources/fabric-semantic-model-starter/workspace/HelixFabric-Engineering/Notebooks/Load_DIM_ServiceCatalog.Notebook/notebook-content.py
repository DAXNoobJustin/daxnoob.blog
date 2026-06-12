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

# # DIM pattern — Load_DIM_ServiceCatalog (Kusto source)
#
# Reads a **Kusto / Eventhouse** source through a linked service, applies the
# required DIM data-quality checks, and writes the dimension to the data
# product lakehouse.
#
# Pattern beats: `helix_read.kusto_endpoint` -> shape -> `CheckConfig`
# (`isUnique` + `isComplete` on the key) -> `write_delta(checks=...)`.
#
# DIM notebooks must declare `isUnique` + `isComplete` on the primary key (the
# linter enforces it). The KQL and column shape below are illustrative.

# CELL ********************

from helixutils import CheckConfig, connection, helix_read

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Read from the Kusto source via the named linked service (cluster + database
# resolve from the linked_services variable library). helix_read handles the
# Kusto connector + auth; the linter blocks raw spark.read of the connector.
kql = """
    ServiceCatalog
    | project ServiceId = tostring(ServiceId),
              ServiceName = tostring(ServiceName),
              ServiceTier = tostring(ServiceTier)
    | distinct ServiceId, ServiceName, ServiceTier
"""
helix_read.kusto_endpoint(connection["example_kusto_source"], kql).to_view("vwServiceCatalog")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TEMPORARY VIEW vwDIM_ServiceCatalog AS
# MAGIC SELECT
# MAGIC      ServiceId      AS DIM_ServiceId
# MAGIC     ,ServiceName
# MAGIC     ,ServiceTier
# MAGIC FROM vwServiceCatalog

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# DIM data-quality contract: the surrogate key must be unique and complete.
# checks.error raises (and opens an incident) on violation, failing the load.
checks = CheckConfig("DIM_ServiceCatalog validation")
checks.error.isUnique("DIM_ServiceId").isComplete("DIM_ServiceId")

spark.table("vwDIM_ServiceCatalog").write_delta(
    connection["core_default"] + "/DIM_ServiceCatalog/",
    retention="2d",
    checks=checks,
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
