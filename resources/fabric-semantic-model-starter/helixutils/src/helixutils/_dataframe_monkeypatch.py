"""Module to monkey patch spark DataFrame class."""

import time
from typing import Literal

from delta.tables import DeltaTable
from notebookutils import mssparkutils
from pyspark import StorageLevel
from pyspark.sql import DataFrame

from helixutils._debug import get_logger
from helixutils._var import connection, spark
from helixutils.helix_check import run_checks
from helixutils.helix_delta import (
    vacuum as vacuum_delta_table,
)

logger = get_logger(__name__)


def _write_delta(
    self,
    path,
    checks=None,
    tabular: bool = False,
    cache: Literal["memory", "disk", "memory_and_disk"] = "memory",
    mode="overwrite",
    optimize=True,
    vacuum=False,
    retention=None,
    **options,
):
    """
    Write DataFrame to Delta table.

    Args:
        self: DataFrame instance
        path: Target path for the Delta table
        checks: CheckConfig object with error/warn constraints (default: None)
        tabular: When True, route through process_tabular() (derives DIM_CalendarKey, auto-partitions) for downstream tabular use (default: False)
        cache: Cache level when checks are run - "memory", "disk", or "memory_and_disk" (default: "memory")
        mode: Write mode - "overwrite" or "append" (default: "overwrite")
        optimize: Run OPTIMIZE after write (default: True)
        vacuum: Run vacuum after write (default: False)
        retention: Retention for vacuum (e.g., "7d"). None uses Delta default.
        **options: Passed directly to DataFrameWriter (partitionBy, overwriteSchema, etc.)

    """
    cache_levels = {
        "memory": StorageLevel.MEMORY_ONLY,
        "disk": StorageLevel.DISK_ONLY,
        "memory_and_disk": StorageLevel.MEMORY_AND_DISK,
    }

    start_time = time.time()

    def elapsed():
        return f"[{time.time() - start_time:.1f}s]"

    try:
        if tabular:
            from helixutils.helix_tabular import _determine_partitions, process_tabular

            self = process_tabular(self, path)
        # Persist if checks will be run or downstream tabular operations require it
        if checks is not None or tabular:
            logger.info(f">>> {elapsed()} Caching DataFrame (level={cache})...")
            level = cache_levels.get(cache, StorageLevel.MEMORY_ONLY)
            self.persist(level)
            row_count = self.count()
            logger.info(f">>> {elapsed()} Cached {row_count:,} rows")

        if checks is not None:
            logger.info(f">>> {elapsed()} Running data quality checks...")
            run_checks(self, checks, create_incident=True)

        logger.info(f">>> {elapsed()} Writing to Delta ({mode})...")
        writer = self.write.mode(mode).format("delta")

        if tabular and "partitionBy" not in options:
            partitions = _determine_partitions(self, path.rstrip("/").split("/")[-1], row_count)
            if partitions:
                writer = writer.partitionBy(*partitions)
                logger.info(f">>> {elapsed()} Tabular write: partitioning by {', '.join(partitions)}")

        # Default overwriteSchema to True for overwrite mode unless explicitly set
        if mode == "overwrite" and "overwriteSchema" not in options:
            writer = writer.option("overwriteSchema", True)

        for k, v in options.items():
            writer = (
                writer.partitionBy(*([v] if isinstance(v, str) else v)) if k == "partitionBy" else writer.option(k, v)
            )
        writer.save(path)
        written_count = spark.read.format("delta").load(path).count()
        logger.info(f">>> {elapsed()} Wrote {written_count:,} rows to {path}")

        if optimize:
            delta_table = DeltaTable.forPath(spark, path)
            files_before = delta_table.detail().select("numFiles").collect()[0][0]
            logger.info(f">>> {elapsed()} Running OPTIMIZE...")
            delta_table.optimize().executeCompaction()
            files_after = delta_table.detail().select("numFiles").collect()[0][0]
            logger.info(f">>> {elapsed()} OPTIMIZE completed ({files_before} → {files_after} files)")

        if vacuum or retention is not None:
            logger.info(f">>> {elapsed()} Running VACUUM (retention={retention})...")
            vacuum_delta_table(path, retention)

    finally:
        if checks is not None or tabular:
            self.unpersist()


def _write_parquet(self, path, mode="overwrite", **options):
    """
    Write DataFrame to Parquet.

    Args:
        self: DataFrame instance
        path: Target path for the Parquet file
        mode: Write mode - "overwrite" or "append" (default: "overwrite")
        **options: Passed directly to DataFrameWriter (partitionBy, compression, etc.)

    """
    writer = self.write.mode(mode).format("parquet")
    for k, v in options.items():
        writer = writer.partitionBy(*([v] if isinstance(v, str) else v)) if k == "partitionBy" else writer.option(k, v)
    writer.save(path)

    logger.info(f"Wrote DataFrame to {path} (mode={mode})")


def _select_except(self, *cols_to_exclude):
    all_columns = self.columns
    selected_columns = [col for col in all_columns if col not in cols_to_exclude]
    return self.select(*selected_columns)


def _to_view(self, view_name):
    """Create a temporary view from a DataFrame"""
    self.createOrReplaceTempView(view_name)


def _to_staged_view(self, view_name):
    """
    Stage the DataFrame to parquet, then create a temp view from the staged copy.

    Retries the staging write a few times (transient OneLake/Spark write hiccups)
    before giving up.
    """
    max_retries = 3
    retry_delay_seconds = 180
    temp_location = connection["temp_default"] + view_name + mssparkutils.runtime.context["currentNotebookName"]
    last_error = None
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(retry_delay_seconds)
            self.write.mode("overwrite").parquet(temp_location)
            spark.read.parquet(temp_location).createOrReplaceTempView(view_name)
            logger.info(f"Data staged and {view_name} created")
            return
        except Exception as e:
            last_error = e
            logger.warning(f"Parquet staging write failed, retry {attempt + 1}/{max_retries}: {e!s}")

    msg = f"Failed to stage '{view_name}' after {max_retries} attempts: {last_error!s}"
    raise Exception(msg)


def _check(self, checks):
    """
    Run PyDeequ data quality checks on DataFrame. Returns self for chaining.

    For validation without writing. For validation + write, use write_delta(checks=...).

    Args:
        self: DataFrame instance
        checks: CheckConfig object with error/warn constraints

    Returns:
        self (DataFrame) for method chaining

    Example:
        checks = CheckConfig()
        checks.error.isComplete("id")
        df.check(checks)

    """
    run_checks(self, checks)
    return self


def initialize():
    """Initialize the DataFrame class with custom functions."""
    DataFrame.select_except = _select_except
    DataFrame.write_delta = _write_delta
    DataFrame.write_parquet = _write_parquet
    DataFrame.check = _check
    DataFrame.to_view = _to_view
    DataFrame.to_staged_view = _to_staged_view
