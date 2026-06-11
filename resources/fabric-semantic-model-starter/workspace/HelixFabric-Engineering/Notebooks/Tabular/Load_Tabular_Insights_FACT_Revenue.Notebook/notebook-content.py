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

# # Standalone tabular FACT pattern — Load_Tabular_Insights_FACT_Revenue
#
# When a model table needs a transform that copy-straight can't express, it gets
# its own notebook. This reads the curated fact (and any dimensions it needs),
# shapes it to exactly what the model should hold, and writes the Direct Lake
# table.
#
# Pattern beats: `%%configure` V-Order -> read curated -> `%%sql` shape /
# trim to the grain the model needs -> `write_delta(tabular=True)`.

# CELL ********************

# MAGIC %%configure
# MAGIC {
# MAGIC     "conf": {
# MAGIC         "spark.sql.parquet.vorder.enabled": "true",
# MAGIC         "spark.databricks.delta.optimizeWrite.enabled": "true"
# MAGIC     }
# MAGIC }

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from helixutils import connection, helix_read

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

helix_read.delta(connection["core_default"] + "/FACT_RevenueAndLicense/").to_view("vwFact")
helix_read.delta(connection["core_default"] + "/DIM_Calendar/").to_view("vwCalendar")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TEMPORARY VIEW vwRevenue AS
# MAGIC SELECT
# MAGIC      f.DIM_CalendarKey
# MAGIC     ,f.DIM_AccountKey
# MAGIC     ,f.DIM_ProductMasterId
# MAGIC     ,f.RevenueAmount
# MAGIC FROM vwFact f
# MAGIC INNER JOIN vwCalendar c ON f.DIM_CalendarKey = c.DIM_CalendarKey
# MAGIC -- trim history the model doesn't need so Direct Lake stays lean
# MAGIC WHERE c.FiscalYear >= year(current_date()) - 3

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

spark.table("vwRevenue").write_delta(
    connection["tabular_default"] + "/FACT_Revenue/",
    tabular=True,
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
