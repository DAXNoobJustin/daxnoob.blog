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

# # DIM pattern — Load_DIM_Account
#
# Builds a conformed dimension (the account hub many facts join to). Reads the
# source, shapes attributes with Spark SQL, then runs **CheckConfig** assertions
# so a bad key (non-unique or null) fails the load instead of silently
# corrupting every downstream join.
#
# Pattern beats: `helix_read` source -> `%%sql` shape -> `CheckConfig` on the
# key -> `write_delta(retention="2d", checks=...)`.
#
# Attributes below are generic placeholders; a real dimension carries far more.

# CELL ********************

from helixutils import CheckConfig, connection, helix_read

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

helix_read.delta(connection["source_lakehouse"] + "/raw_account/").to_view("vwRawAccount")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TEMPORARY VIEW vwAccount AS
# MAGIC SELECT
# MAGIC      DIM_AccountKey
# MAGIC     ,AccountName
# MAGIC     ,SegmentName
# MAGIC     ,CountryName
# MAGIC FROM vwRawAccount

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Assertions run as part of write_delta. error-level checks abort the write,
# so DIM_AccountKey is guaranteed unique and non-null before the dimension publishes.
checks = CheckConfig()
checks.error.isUnique("DIM_AccountKey").isComplete("DIM_AccountKey")

spark.table("vwAccount").write_delta(
    connection["core_default"] + "/DIM_Account/",
    retention="2d",
    checks=checks,
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
