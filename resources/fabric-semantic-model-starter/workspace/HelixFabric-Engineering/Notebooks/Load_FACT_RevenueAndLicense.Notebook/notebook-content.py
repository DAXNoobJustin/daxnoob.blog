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

# # FACT pattern — Load_FACT_RevenueAndLicense
#
# Reads one or more **staged** sources, conforms them to a single fact grain
# with Spark SQL, validates the foreign keys against the dimensions, and writes
# the curated fact Delta table the semantic model reads.
#
# Pattern beats: read `STAGE_*` (+ dims for FK validation) -> `%%sql` union /
# conform -> `write_delta(retention="2d")`.
#
# A real fact often unions several staged feeds (billed, consumed, budget,
# target). One staged source is shown here to keep the pattern legible.

# CELL ********************

from helixutils import connection, helix_read

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Staged feed(s) produced by the STAGE notebooks.
helix_read.delta(connection["staging_default"] + "/STAGE_Revenue_Consumption/").to_view("vwStageRevenueConsumption")

# Dimensions used to validate foreign keys before publish.
helix_read.delta(connection["core_default"] + "/DIM_Account/").to_view("vwAccount")
helix_read.delta(connection["core_default"] + "/DIM_Calendar/").to_view("vwCalendar")
helix_read.delta(connection["core_default"] + "/DIM_ProductMaster/").to_view("vwProductMaster")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TEMPORARY VIEW vwFactRevenue AS
# MAGIC SELECT
# MAGIC      s.DIM_CalendarKey
# MAGIC     ,s.DIM_AccountKey
# MAGIC     ,s.DIM_ProductMasterId
# MAGIC     ,s.RevenueAmount
# MAGIC FROM vwStageRevenueConsumption s
# MAGIC -- inner joins drop any rows whose keys are missing from the dimensions
# MAGIC INNER JOIN vwCalendar      c ON s.DIM_CalendarKey    = c.DIM_CalendarKey
# MAGIC INNER JOIN vwAccount       a ON s.DIM_AccountKey           = a.DIM_AccountKey
# MAGIC INNER JOIN vwProductMaster p ON s.DIM_ProductMasterId = p.DIM_ProductMasterId

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

spark.table("vwFactRevenue").write_delta(
    connection["core_default"] + "/FACT_RevenueAndLicense/",
    retention="2d",
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
