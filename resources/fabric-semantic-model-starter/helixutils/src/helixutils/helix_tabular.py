"""
Tabular model utilities for HelixData.

``process_tabular`` is the portable transform applied on every
``write_delta(tabular=True)`` -- it shapes a dataprod table for DirectLake
semantic-model consumption:

1. Derive a date-typed ``DIM_CalendarKey`` from the integer ``DIM_DateId`` so
   facts relate to (and can partition by) a real calendar key.
2. **Reduce each fact to the rows that survive in the trimmed dimensions** --
   a left-semi join per dimension (see ``TABULAR_DIMENSIONS``). The tabular
   model never carries fact rows pointing at a dimension member that was
   filtered out upstream, so reducing the fact to the model's actual dimension
   grain is the single biggest size lever on the tabular side.

``replace_dim_alt_key`` is a reusable primitive for swapping a surrogate key
for its model-facing alternate via a bridge table -- wire it into
``process_tabular`` for keys whose source still carries the raw id.

Partitioning for large tabular writes is decided by ``_determine_partitions``
(used by ``write_delta``): a per-table override in ``CUSTOM_PARTITIONS``, else
auto-partition ``FACT_``/``BRIDGE_`` tables above ``TABULAR_PARTITION_THRESHOLD``
rows by ``DIM_CalendarKey``.

Every step is guarded by column / target presence, so ``process_tabular`` is
safe to call on any DataFrame -- steps that don't apply are skipped.
"""

from pyspark.sql import DataFrame
from pyspark.sql.functions import col

from helixutils._var import connection, spark

# Dimensions the model trims, each with the alias key its facts join on plus the
# connection + folder its Delta table lives in. ``process_tabular`` left-semi
# joins every fact against these so only fact rows whose dimension members
# survived the trim are kept. Add an entry per dimension you reduce on.
TABULAR_DIMENSIONS = [
    {"table": "DIM_Capacity", "key": "DIM_CapacityId_Alt", "connection": "tabular_default"},
    {"table": "DIM_Environment", "key": "DIM_EnvironmentId", "connection": "tabular_default"},
]

# Per-table partition overrides: table name -> ordered partition columns. Use
# for large facts you want partitioned on something other than the
# DIM_CalendarKey default. Missing columns fall back to automatic partitioning.
CUSTOM_PARTITIONS: dict[str, list[str]] = {
    # "FACT_FabricCapacityUnits": ["DIM_CalendarKey", "DIM_CapacityId_Alt"],
}

# Auto-partition FACT_/BRIDGE_ tabular tables at or above this row count by
# DIM_CalendarKey. Overridable per write via the
# ``helixutils.tabular.partition_threshold`` Spark conf.
TABULAR_PARTITION_THRESHOLD = 10_000_000


def process_tabular(df: DataFrame, target_path: str = "") -> DataFrame:
    """
    Shape a DataFrame for tabular (semantic-model) consumption.

    Derives ``DIM_CalendarKey``, then reduces facts to the rows present in the
    trimmed dimensions via left-semi joins (see ``TABULAR_DIMENSIONS``). Extend
    with ``replace_dim_alt_key`` for surrogate-key swaps if your source still
    carries the raw ids.

    Args:
        df: DataFrame to process.
        target_path: Write target -- used to skip a dimension's own self-join.

    """
    df = replace_dateid_with_calendarkey(df)

    # Reduce facts to valid dimension members. left_semi = keep matching rows,
    # add no columns. Skip the self-join when writing the dimension itself.
    for dim in TABULAR_DIMENSIONS:
        dim_path = connection[dim["connection"]] + f"/{dim['table']}/"
        if dim["key"] in df.columns and target_path != dim_path:
            dim_keys = spark.read.format("delta").load(dim_path).select(dim["key"]).distinct()
            df = df.join(dim_keys, dim["key"], "left_semi")

    return df


def _determine_partitions(df: DataFrame, table_name: str, row_count: int | None = None) -> list[str] | None:
    """
    Pick partition columns for a tabular write.

    Returns the ``CUSTOM_PARTITIONS`` override when all its columns exist, else
    ``["DIM_CalendarKey"]`` for ``FACT_``/``BRIDGE_`` tables at or above the row
    threshold, else ``None`` (no partitioning).
    """
    if table_name in CUSTOM_PARTITIONS:
        cols = CUSTOM_PARTITIONS[table_name]
        if all(c in df.columns for c in cols):
            return cols

    if (table_name.startswith("FACT_") or table_name.startswith("BRIDGE_")) and "DIM_CalendarKey" in df.columns:
        threshold = int(str(spark.conf.get("helixutils.tabular.partition_threshold", str(TABULAR_PARTITION_THRESHOLD))))
        if row_count is None:
            row_count = df.count()
        if row_count >= threshold:
            return ["DIM_CalendarKey"]

    return None


def replace_dim_alt_key(df, df_bridge, key_name):
    """Replace a key column with alternative values from a bridge DataFrame."""
    if key_name not in df.columns:
        return df

    key_name_temp = f"{key_name}_temp"

    return (
        df.withColumnRenamed(key_name, key_name_temp)
        .alias("T")
        .join(df_bridge.alias("B"), col(f"T.{key_name_temp}") == col(f"B.{key_name}"), "left")
        .selectExpr(f"COALESCE(B.{key_name}_Alt, -1) AS {key_name}_Alt", "T.*")
        .select_except(key_name_temp, key_name)
    )


def replace_dateid_with_calendarkey(df):
    """For a given dataframe, add DIM_CalendarKey if DIM_DateId is present."""
    if "DIM_DateId" in df.columns and "DIM_CalendarKey" not in df.columns:
        return df.selectExpr("*", "TO_DATE(CAST(DIM_DateId AS String), 'yyyyMMdd') AS DIM_CalendarKey")
    return df