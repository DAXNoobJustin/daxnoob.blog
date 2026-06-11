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

# # Restricted copy-straight variant — Load_Tabular_Insights_CopyStraight_Restricted
#
# Identical pattern to `Load_Tabular_Insights_CopyStraight`, but for
# row-level-security-sensitive tables: it reads and writes through **restricted**
# connections so the curated and Direct Lake copies stay inside the restricted
# security boundary.
#
# Same beats: `%%configure` V-Order -> loop `tableList` -> `write_delta(tabular=True)`,
# only the connection aliases change.

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

from concurrent.futures import ThreadPoolExecutor

from helixutils import connection, helix_read

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Restricted tables ship through the restricted connection pair only.
tableList = [
    "FACT_RestrictedRevenue",
    "DIM_RestrictedAccount",
]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def process_table(table):
    df = helix_read.delta(connection["restricted_core_default"] + f"/{table}/")
    df.write_delta(connection["restricted_tabular_default"] + f"/{table}/", tabular=True)
    print(f"copied {table}")


with ThreadPoolExecutor(max_workers=2) as executor:
    list(executor.map(process_table, tableList))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
