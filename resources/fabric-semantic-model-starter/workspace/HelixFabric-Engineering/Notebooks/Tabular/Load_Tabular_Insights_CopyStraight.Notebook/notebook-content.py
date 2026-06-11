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

# # Tabular copy-straight pattern — Load_Tabular_Insights_CopyStraight
#
# Bulk-copies curated tables into the **Direct Lake** area the semantic model
# reads, in parallel. "Copy-straight" means no transform — the curated table is
# the model table verbatim.
#
# Pattern beats: `%%configure` to turn on **V-Order + optimized writes** (the
# data-layout lever that keeps Direct Lake scans fast) -> loop a `tableList`
# with a thread pool -> `write_delta(tabular=True)`.

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

# Curated tables to copy straight into the model's Direct Lake area.
tableList = [
    "DIM_Account",
    "DIM_Calendar",
    "DIM_ProductMaster",
    "BRIDGE_SellerAccount",
]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def process_table(table):
    df = helix_read.delta(connection["core_default"] + f"/{table}/")
    # tabular=True applies the model's Direct Lake write conventions.
    df.write_delta(connection["tabular_default"] + f"/{table}/", tabular=True)
    print(f"copied {table}")


with ThreadPoolExecutor(max_workers=4) as executor:
    list(executor.map(process_table, tableList))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
