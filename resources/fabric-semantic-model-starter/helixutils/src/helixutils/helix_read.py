"""Module to read data from various sources"""

import re
from datetime import datetime

from notebookutils import mssparkutils

from helixutils._debug import get_logger
from helixutils._var import linked_service, spark
from helixutils.helix_vault import get_token

logger = get_logger(__name__)


def _normalize_paths(paths):
    """Normalize paths to a flat list, handling both varargs and list input."""
    if len(paths) == 1 and isinstance(paths[0], list | tuple):
        return list(paths[0])
    return list(paths)


def delta(*paths, schema=None, **options):
    """
    Read from delta file(s) to DataFrame object

    Args:
        *paths: One or more paths to delta tables
        schema: Optional schema to apply to the reader
        **options: Additional options to pass to the reader (e.g., versionAsOf, timestampAsOf)

    """
    reader = spark.read
    if schema:
        reader = reader.schema(schema)
    reader = reader.format("delta")
    for key, value in options.items():
        reader = reader.option(key, value)
    return reader.load(_normalize_paths(paths))


def parquet(*paths, schema=None, **options):
    """
    Read from parquet file(s) to DataFrame object

    Args:
        *paths: One or more paths to parquet files
        schema: Optional schema to apply to the reader
        **options: Additional options to pass to the reader (e.g., mergeSchema)

    """
    reader = spark.read
    if schema:
        reader = reader.schema(schema)
    reader = reader.format("parquet")
    for key, value in options.items():
        reader = reader.option(key, value)
    return reader.load(_normalize_paths(paths))


def csv(*paths, schema=None, **options):
    """
    Read from csv file(s) to DataFrame object

    Args:
        *paths: One or more paths to csv files
        schema: Optional schema to apply to the reader
        **options: Additional options to pass to the reader (e.g., delimiter, quote, header, inferSchema)

    """
    reader = spark.read
    if schema:
        reader = reader.schema(schema)
    reader = reader.format("csv")
    for key, value in options.items():
        reader = reader.option(key, value)
    return reader.load(_normalize_paths(paths))


def sql_endpoint(linked_service_name, script):
    """Read sql to DataFrame object"""
    server, database = extract_linked_service(linked_service_name)
    return (
        spark.read.format("jdbc")
        .option("url", f"jdbc:sqlserver://{server}:1433;database={database}")
        .option("query", script)
        .option("accessToken", get_token("https://database.windows.net/.default"))
        .option("encrypt", "true")
        .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
        .load()
    )


def kusto_endpoint(linked_service_name, script):
    """Read from Kusto to DataFrame object"""
    server, database = extract_linked_service(linked_service_name)
    return (
        spark.read.format("com.microsoft.kusto.spark.synapse.datasource")
        .option("kustoCluster", server)
        .option("accessToken", get_token("https://kusto.kusto.windows.net/.default"))
        .option("kustoDatabase", database)
        .option("kustoQuery", script)
        .option("readMode", "ForceDistributedMode")
        .load()
    )


def extract_linked_service(linked_service_name):
    """Get linked service details"""
    server = re.split(";", linked_service[linked_service_name])[0]
    database = re.split(";", linked_service[linked_service_name])[1]

    return server, database


def mismatched_schema_parquet(file_path, file_date_regex, file_cutover_date, pre_cutover_schema, post_cutover_schema):
    """Read parquet files with mismatched schema"""
    all_files = mssparkutils.fs.ls(file_path)
    cutover_date = datetime.strptime(file_cutover_date, "%Y-%m-%d")

    pre_cutover_list = []
    post_cutover_list = []

    for x in all_files:
        file_date = datetime.strptime(re.sub(file_date_regex, r"\1", x.path), "%Y_%m_%d")
        if file_date < cutover_date:
            pre_cutover_list.append(x.path)
        else:
            post_cutover_list.append(x.path)

    pre_cutover_df = spark.read.parquet(*pre_cutover_list).selectExpr(*pre_cutover_schema)
    post_cutover_df = spark.read.parquet(*post_cutover_list).selectExpr(*post_cutover_schema)

    return pre_cutover_df.union(post_cutover_df)
