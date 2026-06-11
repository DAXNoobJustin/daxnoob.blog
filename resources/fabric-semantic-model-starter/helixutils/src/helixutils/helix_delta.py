"""
Delta Lake Operations for HelixData

This module provides utilities for managing Delta Lake tables.
"""

from datetime import datetime

import pytz
from delta.tables import DeltaTable

from helixutils._debug import get_logger
from helixutils._var import spark

logger = get_logger(__name__)


def vacuum(path, retention=None):
    """
    Vacuum a Delta table to remove old data files.

    Args:
        path: Path to the Delta table
        retention: Retention in days as string (e.g., "7d", "30d"). None uses Delta default.

    """
    delta_table = DeltaTable.forPath(spark, path)

    if retention is not None:
        if not retention.endswith("d"):
            msg = f"Invalid retention format: '{retention}'. Use format like '7d', '30d'"
            raise ValueError(msg)
        retention_hours = int(retention[:-1]) * 24

        original_check = spark.conf.get("spark.databricks.delta.retentionDurationCheck.enabled", "true")
        spark.conf.set("spark.databricks.delta.retentionDurationCheck.enabled", "false")

        try:
            try:
                spark.sql(f"VACUUM '{path}' RETAIN {retention_hours} HOURS")
            except Exception:
                delta_table.vacuum(retention_hours)
        except Exception as e:
            logger.error(f"Vacuum failed for {path}: {e}")
        finally:
            spark.conf.set("spark.databricks.delta.retentionDurationCheck.enabled", original_check)
    else:
        delta_table.vacuum()


def rollback(path: str, max_date: str | None = None, commit: bool = False) -> None:
    """
    Rollback a Delta Lake table to the latest valid version.

    Excludes versions that were the result of a RESTORE operation and optionally
    filters by a maximum date.

    Args:
        path: ABFSS URI to the Delta table
        max_date: Optional PST date (ISO format) to roll back to, e.g. '2024-04-15T12:00:00'
        commit: If False (default), only shows what would be done. If True, performs the rollback

    """
    delta_table = DeltaTable.forPath(spark, path)
    history_df = delta_table.history(1000)

    record_modifying_ops = ["WRITE", "UPDATE", "MERGE", "RESTORE"]
    recent_versions = (
        history_df.filter(history_df["operation"].isin(record_modifying_ops))
        .orderBy("version", ascending=False)
        .limit(2)
        .collect()
    )

    current_version_info = recent_versions[0]
    current_version = current_version_info["version"]
    current_op = current_version_info["operation"]

    logger.info(f"Current version: {current_version}")

    # Special case: current is WRITE, previous is RESTORE
    if not max_date and len(recent_versions) > 1:
        prev_op = recent_versions[1]["operation"]
        if current_op == "WRITE" and prev_op == "RESTORE":
            restore_target_version = int(recent_versions[1]["operationParameters"]["version"])
            if commit:
                logger.info(f"Rolling back to version {restore_target_version}")
                delta_table.restoreToVersion(restore_target_version)
            else:
                logger.info(f"Dry-run: would rollback to version {restore_target_version}")
            return

    # Identify versions to exclude
    restore_targets = (
        history_df.filter(history_df["operation"] == "RESTORE")
        .select("operationParameters")
        .rdd.map(lambda row: int(row["operationParameters"]["version"]))
        .collect()
    )
    restore_versions = (
        history_df.filter(history_df["operation"] == "RESTORE")
        .select("version")
        .rdd.map(lambda row: row["version"])
        .collect()
    )

    filtered_df = history_df.filter(
        (~history_df["version"].isin(restore_targets))
        & (~history_df["version"].isin(restore_versions))
        & (history_df["version"] < current_version)
    )

    if max_date:
        local_tz = pytz.timezone("America/Los_Angeles")
        naive_ts = datetime.fromisoformat(max_date)
        max_ts = local_tz.localize(naive_ts).astimezone(pytz.utc)
        filtered_df = filtered_df.filter(filtered_df["timestamp"] <= max_ts)

    valid_versions = filtered_df.orderBy(filtered_df["version"].desc()).limit(1).collect()

    if not valid_versions:
        msg = f"No valid Delta version found{' before ' + max_date if max_date else ''}"
        raise ValueError(msg)

    target_version = valid_versions[0]["version"]

    if commit:
        logger.info(f"Rolling back to version {target_version}")
        delta_table.restoreToVersion(target_version)
    else:
        logger.info(f"Dry-run: would rollback to version {target_version}")
