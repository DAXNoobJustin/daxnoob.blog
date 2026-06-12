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

# # FACT pattern — Load_FACT_AdoptionSignals (external REST API + Key Vault)
#
# Pulls a fact table from an **external REST API** that needs an AAD bearer
# token, then writes it to the data product lakehouse. This is the pattern for
# any source that lives behind an HTTP endpoint rather than a database.
#
# Pattern beats: `%%configure` (request a bigger Spark allocation for a heavy
# pull) -> `helix_vault.get_token` (bearer auth) -> `requests` ->
# `spark.createDataFrame` -> `%%sql` shape -> `write_delta`. The ingestion call
# is wrapped so a source-side failure raises an incident via `helix_monitoring`.
#
# Because it carries a `%%configure` cell, this notebook binds to `Env_Custom`.
# The `api.example.com` host and the scope are illustrative -- swap in your own.

# CELL ********************

# MAGIC %%configure
# MAGIC {
# MAGIC     "driverMemory": "56g",
# MAGIC     "driverCores": 8,
# MAGIC     "executorMemory": "56g",
# MAGIC     "executorCores": 8,
# MAGIC     "numExecutors": 8
# MAGIC }

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import requests

from helixutils import connection, helix_monitoring, helix_vault

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Pull adoption signals from the source API. get_token returns a bearer token
# for the identity the notebook runs as (interactive user or the pipeline's
# service principal); point auth_resource at your API's app-registration scope.
# The ingestion is wrapped so a source-side failure raises an incident and then
# re-raises to fail the run.
api_url = "https://api.example.com/v1/adoption-signals"

try:
    token = helix_vault.get_token("https://api.example.com/.default")
    response = requests.get(
        api_url,
        headers={"Authorization": f"Bearer {token}"},
        params={"window": "P30D"},
        timeout=120,
    )
    response.raise_for_status()
    spark.createDataFrame(response.json()["value"]).to_view("vwRawAdoptionSignals")
except Exception as error:
    helix_monitoring.create_incident(
        title="Load_FACT_AdoptionSignals ingestion failed",
        description=f"Failed to pull adoption signals from the source API: {error!s}",
        severity=3,
        fields="Ingestion",
    )
    raise

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TEMPORARY VIEW vwFACT_AdoptionSignals AS
# MAGIC SELECT
# MAGIC      CAST(AccountId AS STRING) AS DIM_AccountId
# MAGIC     ,CAST(DateKey AS INT) AS DIM_CalendarId
# MAGIC     ,CAST(ProductId AS STRING) AS DIM_ProductMasterId
# MAGIC     ,CAST(ActiveUsers AS BIGINT) AS ActiveUsers
# MAGIC     ,CAST(SignalScore AS DOUBLE) AS SignalScore
# MAGIC FROM vwRawAdoptionSignals

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

spark.table("vwFACT_AdoptionSignals").write_delta(
    connection["core_default"] + "/FACT_AdoptionSignals/",
    retention="2d",
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
