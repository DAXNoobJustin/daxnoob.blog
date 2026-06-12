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

# # DIM pattern — Load_DIM_ExchangeRate (CSV reference data)
#
# Reads a flat **CSV** reference file (the kind of small lookup a finance team
# drops in a landing folder), applies the DIM data-quality checks, and writes
# the dimension to the data product lakehouse.
#
# Pattern beats: `helix_read.csv` (header + inferSchema) -> shape ->
# `CheckConfig` (`isUnique` + `isComplete`) -> `write_delta(checks=...)`.
#
# A natural-key dimension keyed by a surrogate built from the grain (one row
# per currency + month), so the uniqueness check runs on a single key. The
# file path is illustrative.

# CELL ********************

from helixutils import CheckConfig, connection, helix_read

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Read the CSV from the source landing area. helix_read.csv wraps the Spark CSV
# reader (the linter blocks raw spark.read.csv) and resolves the path from the
# variable library.
helix_read.csv(
    connection["source_lakehouse"] + "/reference/exchange_rates.csv",
    header=True,
    inferSchema=True,
).to_view("vwRawExchangeRate")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TEMPORARY VIEW vwDIM_ExchangeRate AS
# MAGIC SELECT
# MAGIC      CONCAT(CurrencyCode, '_', CAST(RateMonthKey AS INT)) AS DIM_ExchangeRateId
# MAGIC     ,CurrencyCode
# MAGIC     ,CAST(RateMonthKey AS INT) AS RateMonthKey
# MAGIC     ,CAST(RateToUSD AS DECIMAL(18, 6)) AS RateToUSD
# MAGIC FROM vwRawExchangeRate
# MAGIC WHERE CurrencyCode IS NOT NULL

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Surrogate-key DIM: uniqueness + completeness run on the single derived key.
# checks.error fails the load on violation.
checks = CheckConfig("DIM_ExchangeRate validation")
checks.error.isUnique("DIM_ExchangeRateId").isComplete("DIM_ExchangeRateId")

spark.table("vwDIM_ExchangeRate").write_delta(
    connection["core_default"] + "/DIM_ExchangeRate/",
    retention="2d",
    checks=checks,
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
