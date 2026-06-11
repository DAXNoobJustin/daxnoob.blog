"""
Tabular model utilities for HelixData.

The portable transform applied on every ``write_delta(tabular=True)`` lives in
``process_tabular``: derive a date-typed ``DIM_CalendarKey`` from an integer
``DIM_DateId`` so DirectLake facts can partition and relate on a real calendar
key. Two reusable primitives -- ``replace_dateid_with_calendarkey`` and
``replace_dim_alt_key`` -- are provided so you can extend ``process_tabular``
with model-specific steps (alt-key replacement via a bridge table, dimension
filtering, etc.) for your own star schema.
"""

from pyspark.sql.functions import col


def process_tabular(df, target_path: str = ""):  # noqa: ARG001
    """
    Prepare a DataFrame for tabular (semantic-model) consumption.

    Applies the portable step shipped with this starter -- deriving
    ``DIM_CalendarKey`` from ``DIM_DateId`` -- and returns the result. Extend
    this with your own model-specific transforms (e.g. ``replace_dim_alt_key``
    against a bridge table, or left-semi dimension filtering) as needed.

    Args:
        df: DataFrame to process.
        target_path: Reserved for extensions that need the write target (e.g.
            to skip a self-join when writing a dimension table).

    """
    return replace_dateid_with_calendarkey(df)


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