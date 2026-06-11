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

# # STAGE pattern — Load_STAGE_Revenue_Consumption
#
# Reads a raw source, runs a freshness data-quality guard, conforms the grain
# with Spark SQL, and writes a short-retention **staged** Delta table that the
# `FACT_*` notebooks consume.
#
# Pattern beats: `helix_read` source -> `to_view` -> DQ guard -> `%%sql`
# conform -> `write_delta(retention="2d")`.
#
# The source and transform below are illustrative — swap in your own.

# CELL ********************

from datetime import datetime, timedelta

from helixutils import connection, helix_read

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Read the raw revenue source into a temp view. All reads go through helixutils
# (the linter blocks raw spark.read) so connections resolve from the variable
# library and lineage is captured consistently.
helix_read.delta(connection["source_lakehouse"] + "/raw_revenue/").to_view("vwRawRevenue")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Data-quality guard: fail fast if the source is missing the most recent period.
# A raised exception here is caught by the orchestrator, which opens an incident.
prior_period = (datetime.today().replace(day=1) - timedelta(days=1)).strftime("%Y%m")
row_count = spark.sql(f"SELECT COUNT(*) FROM vwRawRevenue WHERE PeriodKey = {prior_period}").collect()[0][0]
if row_count == 0:
    raise ValueError(f"No source rows for period {prior_period} — aborting stage load.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TEMPORARY VIEW vwStageRevenue AS
# MAGIC SELECT
# MAGIC      DIM_CalendarKey
# MAGIC     ,DIM_AccountKey
# MAGIC     ,DIM_ProductMasterId
# MAGIC     ,SUM(RevenueAmount) AS RevenueAmount
# MAGIC FROM vwRawRevenue
# MAGIC GROUP BY DIM_CalendarKey, DIM_AccountKey, DIM_ProductMasterId

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Short retention: staged tables are intermediate, rewritten every run.
spark.table("vwStageRevenue").write_delta(
    connection["staging_default"] + "/STAGE_Revenue_Consumption/",
    retention="2d",
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
