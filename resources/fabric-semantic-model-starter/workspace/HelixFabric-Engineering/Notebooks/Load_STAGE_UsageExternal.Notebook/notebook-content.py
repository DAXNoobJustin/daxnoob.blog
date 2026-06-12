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

# # STAGE pattern — Load_STAGE_UsageExternal (SQL source)
#
# Reads an external **SQL** source through a linked service, stages it to the
# temp area, conforms the grain with Spark SQL, and writes a short-retention
# staged Delta table for a downstream `FACT_*` notebook.
#
# Pattern beats: `helix_read.sql_endpoint` -> `to_staged_view` (land raw) ->
# `%%sql` conform -> `write_delta(retention="2d")`.
#
# `to_staged_view` lands the source to parquet first, then exposes a view over
# the staged copy — so the (often slow / rate-limited) source is read once and
# every later cell reads the stable staged copy. The SQL connection resolves
# from the `linked_services` variable library; the query is illustrative.

# CELL ********************

from helixutils import connection, helix_read

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Read from the external SQL source via the named linked service. The linter
# blocks raw spark.read / JDBC, so reads go through helix_read — the connection
# string (server + database) resolves from the linked_services variable library.
query = """
    SELECT
         CapacityId
        ,EventDateKey
        ,EnvironmentId
        ,OperationCount
    FROM dbo.CapacityOperations
    WHERE EventDateKey >= 20240101
"""
helix_read.sql_endpoint(connection["example_sql_source"], query).to_staged_view("vwRawUsageExternal")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Data-quality guard: fail fast if the source returned no rows. A raised
# exception is caught by the orchestrator, which opens an incident.
row_count = spark.sql("SELECT COUNT(*) FROM vwRawUsageExternal").collect()[0][0]
if row_count == 0:
    raise ValueError("External SQL source returned no rows — aborting stage load.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TEMPORARY VIEW vwStageUsageExternal AS
# MAGIC SELECT
# MAGIC      CapacityId      AS DIM_CapacityId_Alt
# MAGIC     ,EnvironmentId   AS DIM_EnvironmentId
# MAGIC     ,EventDateKey    AS DIM_CalendarKey
# MAGIC     ,SUM(OperationCount) AS OperationCount
# MAGIC FROM vwRawUsageExternal
# MAGIC GROUP BY CapacityId, EnvironmentId, EventDateKey

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Short retention: staged tables are intermediate, rewritten every run.
spark.table("vwStageUsageExternal").write_delta(
    connection["staging_default"] + "/STAGE_UsageExternal/",
    retention="2d",
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
