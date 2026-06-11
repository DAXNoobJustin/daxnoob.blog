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

# # BRIDGE pattern — Load_BRIDGE_SellerAccount
#
# A bridge resolves a many-to-many relationship — here, many sellers can be
# assigned to one account. The model uses it to fan seller-sliced measures out
# over accounts without double-counting.
#
# Pattern beats: read the assignment source -> `%%sql` filter to active
# assignments -> `write_delta(retention="2d")`. The bridge key (`DIM_AccountKey`)
# matches the account dimension so the relationship resolves in the model.

# CELL ********************

from helixutils import connection, helix_read

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

helix_read.delta(connection["source_lakehouse"] + "/raw_account_assignment/").to_view("vwRawAssignment")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TEMPORARY VIEW vwSellerAccount AS
# MAGIC SELECT DISTINCT
# MAGIC      SellerId
# MAGIC     ,DIM_AccountKey
# MAGIC FROM vwRawAssignment
# MAGIC WHERE IsActive = true

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

spark.table("vwSellerAccount").write_delta(
    connection["core_default"] + "/BRIDGE_SellerAccount/",
    retention="2d",
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
