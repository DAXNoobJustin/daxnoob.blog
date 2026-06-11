"""
Helix Data Quality Check Factory Functions

Factory functions that return fresh PyDeequ Check objects for data quality validation.
"""

from notebookutils import mssparkutils

from helixutils._var import spark


class DataQualityError(Exception):
    """Raised when data quality checks fail."""

    pass


class HelixCheck:
    """
    Wrapper around PyDeequ Check that adds custom Helix constraints.

    Delegates all standard PyDeequ methods and adds custom ones like consecutiveDates.
    """

    def __init__(self, check):
        """Initialize HelixCheck with a PyDeequ Check instance."""
        self._check = check
        self._custom_checks = []  # List of (name, check_fn) tuples
        self._deferred_pydeequ = []  # List of (name, setup_fn) tuples that add PyDeequ constraints at run time

    def get_deferred_pydeequ(self):
        """Return list of deferred PyDeequ setup tuples."""
        return self._deferred_pydeequ

    def hasConsecutiveDates(self, group_by=None, day_count=60, where=None):  # noqa: N802
        """
        Validate no date gaps exist per dimension within backfill window.

        Args:
            group_by: Dimension column to group by (None = check globally)
            day_count: Days to look back from each dimension's max date (default: 60)
            where: SQL filter expression to apply before checking (e.g., "Status = 'Active'")

        """
        from helixutils._debug import get_logger

        check_logger = get_logger(__name__)

        def check_fn(df):
            import datetime

            import pyspark.sql.functions as F

            check_logger.info(f">>> ConsecutiveDates check (group_by={group_by}, days={day_count})...")

            # Apply where filter if provided
            filtered_df = df.filter(where) if where else df

            date_col = F.to_date(F.col("DIM_DateId").cast("string"), "yyyyMMdd")

            # Get distinct dates per group using aggregation (works better with cached data)
            if group_by:
                # Get all dates and max date per group in one pass
                agg_df = (
                    filtered_df.groupBy(group_by, date_col.alias("_dt")).agg(F.lit(1).alias("_dummy")).drop("_dummy")
                )
                # Get max date per group
                max_dates = agg_df.groupBy(group_by).agg(F.max("_dt").alias("_max_dt"))
                # Join back and filter to window
                df_dates = agg_df.join(max_dates, group_by).filter(
                    F.col("_dt") > F.date_sub(F.col("_max_dt"), day_count)
                )
                # Collect dates per group and check for gaps in driver
                date_rows = df_dates.select(group_by, "_dt").orderBy(group_by, "_dt").collect()

                # Check gaps in Python (fast - only distinct dates, not full dataset)
                gaps = []
                prev_group = None
                prev_dt = None
                for row in date_rows:
                    grp, dt = row[group_by], row["_dt"]
                    if grp == prev_group and prev_dt and (dt - prev_dt).days > 1:
                        gaps.append((grp, prev_dt, dt))
                    prev_group, prev_dt = grp, dt

                if gaps:
                    check_logger.info(f">>> ConsecutiveDates FAILED: {len(gaps)} gap(s) found")
                    detail_str = "\n".join([f"  {g[0]}: gap between {g[1]} and {g[2]}" for g in gaps[:10]])
                    return f"ConsecutiveDates(by {group_by}): {len(gaps)} gap(s) found\n{detail_str}"
            else:
                # Global check - get all distinct dates
                agg_df = filtered_df.select(date_col.alias("_dt")).distinct()
                max_dt = agg_df.agg(F.max("_dt")).collect()[0][0]
                cutoff = max_dt - datetime.timedelta(days=day_count)
                date_rows = agg_df.filter(F.col("_dt") > cutoff).orderBy("_dt").collect()

                # Check gaps in Python
                gaps = []
                prev_dt = None
                for row in date_rows:
                    dt = row["_dt"]
                    if prev_dt and (dt - prev_dt).days > 1:
                        gaps.append((prev_dt, dt))
                    prev_dt = dt

                if gaps:
                    check_logger.info(f">>> ConsecutiveDates FAILED: {len(gaps)} gap(s) found")
                    detail_str = "\n".join([f"  gap between {g[0]} and {g[1]}" for g in gaps[:10]])
                    where_info = f" WHERE {where}" if where else ""
                    return f"ConsecutiveDates({where_info}): {len(gaps)} gap(s) found\n{detail_str}"

            check_logger.info(">>> ConsecutiveDates PASSED")
            return None  # Pass

        name = f"ConsecutiveDates({group_by}, {day_count}, {where})"
        self._custom_checks.append((name, check_fn))
        return self

    def get_custom_checks(self):
        """Return list of custom check tuples."""
        return self._custom_checks

    def hasRowcountDrift(  # noqa: N802
        self,
        previous_delta_path: str,
        lower_ratio: float = 0.75,
        upper_ratio: float = 1.25,
    ):
        """
        Add PyDeequ hasSize checks comparing rowcount to previous Delta table.

        Constraints are added at check runtime (not definition time).
        If the previous table does not exist or has 0 rows, no checks are added.

        Args:
            previous_delta_path: Path to the previous Delta table to compare against
            lower_ratio: Minimum allowed ratio of current/previous rowcount (default: 0.75)
            upper_ratio: Maximum allowed ratio of current/previous rowcount (default: 1.25)

        """

        def setup_fn(check):
            """Called at run_checks time to add PyDeequ constraints."""
            from delta.tables import DeltaTable

            from helixutils._debug import get_logger

            check_logger = get_logger(__name__)

            # Check if previous Delta table exists and has data
            if not DeltaTable.isDeltaTable(spark, previous_delta_path):
                check_logger.debug(">>> RowcountDrift skipped: no previous data")
                return check

            previous_row_count = spark.read.format("delta").load(previous_delta_path).count()
            if previous_row_count == 0:
                check_logger.debug(">>> RowcountDrift skipped: previous table empty")
                return check

            lower_bound = previous_row_count * lower_ratio
            upper_bound = previous_row_count * upper_ratio

            check_logger.info(
                f">>> RowcountDrift check: previous={previous_row_count:,}, "
                f"bounds=[{lower_bound:,.0f}, {upper_bound:,.0f}]"
            )

            check = check.hasSize(
                lambda c: c >= lower_bound,
                hint=f"Row count fell by more than {(1 - lower_ratio) * 100:.0f}% from {previous_row_count:,}",
            )
            return check.hasSize(
                lambda c: c <= upper_bound,
                hint=f"Row count rose by more than {(upper_ratio - 1) * 100:.0f}% from {previous_row_count:,}",
            )

        name = f"RowcountDrift({lower_ratio}, {upper_ratio})"
        self._deferred_pydeequ.append((name, setup_fn))
        return self

    def __getattr__(self, name):
        """Delegate all other methods to the underlying PyDeequ Check."""
        attr = getattr(self._check, name)
        if callable(attr):

            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                # If PyDeequ returns the Check (for chaining), return self instead
                if result is self._check:
                    return self
                return result

            return wrapper
        return attr


def _error_check(description=""):
    """Create a new PyDeequ Check with Error level, wrapped with Helix extensions."""
    from pydeequ.checks import Check, CheckLevel

    return HelixCheck(Check(spark, CheckLevel.Error, description))


def _warn_check(description=""):
    """Create a new PyDeequ Check with Warning level, wrapped with Helix extensions."""
    from pydeequ.checks import Check, CheckLevel

    return HelixCheck(Check(spark, CheckLevel.Warning, description))


def _format_constraint(s):
    """
    Clean up PyDeequ constraint string for readability.

    Examples:
        UniquenessConstraint(Uniqueness(List(a,b),None,None)) -> Uniqueness(a, b)
        CompletenessConstraint(Completeness(col,None)) -> Completeness(col)

    """
    import re

    # Strip outer *Constraint() wrapper
    s = re.sub(r"^\w+Constraint\((.+)\)$", r"\1", s)
    # Remove List() wrapper around columns
    s = re.sub(r"List\(([^)]+)\)", r"\1", s)
    # Remove trailing ,None patterns
    return re.sub(r"(,None)+\)", ")", s)


class CheckConfig:
    """
    Container for data quality checks to pass to write_delta.

    Example:
        checks = CheckConfig("Capacity validation")
        checks.error.isComplete("id").isUnique("id")
        checks.warn.isComplete("optional_field")
        df.write_delta(path, checks=checks)

    """

    def __init__(self, description: str = ""):
        """
        Initialize CheckConfig with optional description.

        Args:
            description: Description for checks (shows in error messages and PyDeequ results)

        """
        self._description = description
        self._error = None
        self._warn = None

    @property
    def error(self):
        """Get or create error-level Check. Constraints added here will fail the write."""
        if self._error is None:
            self._error = _error_check(self._description)
        return self._error

    @property
    def warn(self):
        """Get or create warning-level Check. Constraints added here log warnings but don't fail."""
        if self._warn is None:
            self._warn = _warn_check(self._description)
        return self._warn

    @property
    def description(self):
        """Get the description for this check config."""
        return self._description

    def get_checks(self):
        """Return list of configured Check objects (excludes None)."""
        return [c for c in [self._error, self._warn] if c is not None]


def _create_dq_incident(level: str, details: str):
    """
    Create an incident for data quality issues.

    Args:
        level: "Warning" or "Error"
        details: Formatted details message

    """
    from helixutils.helix_monitoring import create_incident

    context = mssparkutils.runtime.context
    notebook_name = context["currentNotebookName"]
    notebook_id = context["currentNotebookId"]
    livy_id = spark.sparkContext.applicationId

    monitor_url = f"https://app.fabric.microsoft.com/workloads/de-ds/monitor/{notebook_id}/{livy_id}?experience=fabric-developer&tab=related"
    severity = 4 if level == "Warning" else 3

    create_incident(
        title=f"[AUTOMATED] DQ {level}: {notebook_name}",
        description=f"{details}\n\nNotebookRunLink: {monitor_url}",
        severity=severity,
        fields="Quality",
    )


def run_checks(df, checks, create_incident=False):
    """
    Run PyDeequ data quality checks on DataFrame and process results.

    Args:
        df: DataFrame instance
        checks: CheckConfig or list of CheckConfig objects
        create_incident: Whether to create incidents for failures (default: False)

    """
    from pydeequ.verification import VerificationResult, VerificationSuite

    from helixutils._debug import get_logger

    logger = get_logger(__name__)

    # Normalize to list
    if checks is None:
        checks_list = []
    elif isinstance(checks, list):
        checks_list = checks
    else:
        checks_list = [checks]

    # Gather all HelixCheck wrappers
    all_helix_checks = []
    for cfg in checks_list:
        all_helix_checks.extend(cfg.get_checks())

    if not all_helix_checks:
        msg = "At least one check is required"
        raise ValueError(msg)

    # Apply deferred PyDeequ constraints (e.g., hasRowcountDrift reads previous table at run time)
    for hc in all_helix_checks:
        for name, setup_fn in hc.get_deferred_pydeequ():
            logger.debug(f"Setting up deferred PyDeequ check: {name}")
            hc._check = setup_fn(hc._check)

    # Separate PyDeequ checks from custom checks
    pydeequ_checks = [hc._check for hc in all_helix_checks]

    # Run custom checks first (they run against the DataFrame directly)
    custom_errors = []
    custom_warnings = []
    for hc in all_helix_checks:
        from pydeequ.checks import CheckLevel

        custom_checks = hc.get_custom_checks()
        logger.debug(f"HelixCheck has {len(custom_checks)} custom check(s)")
        is_error_level = hc._check.level == CheckLevel.Error
        for _name, check_fn in custom_checks:
            logger.debug(f"Running custom check: {_name}")
            result = check_fn(df)
            if result:  # Non-None means failure
                if is_error_level:
                    custom_errors.append(result)
                else:
                    custom_warnings.append(result)

    # Run PyDeequ verification suite
    suite = VerificationSuite(spark).onData(df)
    for check in pydeequ_checks:
        suite = suite.addCheck(check)
    result = suite.run()

    # Get detailed results as JSON
    check_results = VerificationResult.checkResultsAsJson(spark, result)

    # Collect failures grouped by check name
    errors_by_check = {}
    warnings_by_check = {}
    for cr in check_results:
        if cr["constraint_status"] == "Failure":
            constraint = _format_constraint(cr["constraint"])
            check_name = cr["check"] or ""
            msg = f"{constraint}: {cr['constraint_message']}"
            if cr["check_level"] == "Error":
                errors_by_check.setdefault(check_name, []).append(msg)
            else:
                warnings_by_check.setdefault(check_name, []).append(msg)

    # Handle warnings (PyDeequ + custom)
    all_warnings = list(custom_warnings)
    if warnings_by_check:
        parts = []
        for check_name, warns in warnings_by_check.items():
            warn_details = "\n".join(warns)
            if check_name:
                parts.append(f'Data quality check "{check_name}" had {len(warns)} warning(s):\n{warn_details}')
            else:
                parts.append(f"Data quality check had {len(warns)} warning(s):\n{warn_details}")
        all_warnings.extend(parts)

    if all_warnings:
        warning_msg = "\n".join(all_warnings)
        logger.warning(warning_msg)
        if create_incident:
            _create_dq_incident("Warning", warning_msg)

    # Handle errors (PyDeequ + custom)
    all_errors = list(custom_errors)
    if errors_by_check:
        parts = []
        for check_name, errs in errors_by_check.items():
            error_details = "\n".join(errs)
            if check_name:
                parts.append(f'Data quality check "{check_name}" failed with {len(errs)} error(s):\n{error_details}')
            else:
                parts.append(f"Data quality check failed with {len(errs)} error(s):\n{error_details}")
        all_errors.extend(parts)

    if all_errors:
        error_msg = "\n".join(all_errors)
        logger.error(error_msg)
        if create_incident:
            _create_dq_incident("Error", error_msg)
        raise DataQualityError(error_msg)
