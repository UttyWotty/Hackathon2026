"""Snowflake DDL for the synthetic dataset's tables.

Column names and types are copied from the authoritative production definitions so that the
analysis modules run unmodified against the synthetic account. Functions here build SQL
strings only; executing them is the loader's responsibility.
"""

from typing import Dict, Final, List

from .constants import (
    TABLE_VENDOR,
    TABLE_LOCATION,
    TABLE_MASTER_SHOT,
    TABLE_TOOL,
    TABLE_PRODUduration,
    TABLE_SHIFT_NOTE,
    TABLE_WORK_ORDER,
)

# Ordered column definitions per table. Order is significant: the loader writes CSV headers
# and INSERT column lists from these, so DDL and data can never drift apart.
TABLE_COLUMNS: Final[Dict[str, List[str]]] = {
    TABLE_MASTER_SHOT: [
        "VENDOR_NAME STRING",
        "MACHINE_ID STRING",
        "SENSOR_CODE STRING",
        "CT FLOAT",
        "TARGET_DURATION FLOAT",
        "TEMPERATURE FLOAT",
        "PRODUCT_NAME STRING",
        "TYPE STRING",
        "TYPE STRING",
        "STATUS STRING",
        "SHOT_TIME TIMESTAMP_NTZ(3)",
        "SHOT_TIME_UTC TIMESTAMP_NTZ(3)",
        "VOLUME NUMBER",
        "SENSOR_ID NUMBER",
        "TOOL_ID NUMBER",
        "VENDOR_ID NUMBER",
        "PRODUCT_ID STRING",
        "UPLOAD_TIME TIMESTAMP_NTZ",
        "PROCESSING_DATE STRING",
    ],
    TABLE_TOOL: [
        "ID NUMBER",
        "MACHINE_ID STRING",
        "SENSOR_CODE STRING",
        "SENSOR_ID NUMBER",
        "VENDOR_VENDOR_ID NUMBER",
        "LOCATION_ID NUMBER",
        "PRODUCT_ID NUMBER",
        "TYPE STRING",
        "TARGET_DURATION NUMBER",
        "TOTAL_CAVITIES NUMBER",
        "DESIGNED_SHOT NUMBER",
        "MAX_DAILY_OUTPUT NUMBER",
        "PRODUCTION_DAYS NUMBER",
        "SHIFTS_PER_DAY NUMBER",
    ],
    TABLE_VENDOR: [
        "ID NUMBER",
        "NAME STRING",
    ],
    TABLE_LOCATION: [
        "ID NUMBER",
        "NAME STRING",
        "TZ_CODE STRING",
        "UTC_OFFSET_HOURS NUMBER",
    ],
    TABLE_PRODUCT: [
        "ID NUMBER",
        "PRODUCT_CODE STRING",
        "NAME STRING",
    ],
    TABLE_SHIFT_NOTE: [
        "ID NUMBER",
        "MACHINE_ID STRING",
        "SHIFT_DATE TIMESTAMP_NTZ",
        "AUTHOR_ROLE STRING",
        "NOTE_TEXT STRING",
    ],
    TABLE_WORK_ORDER: [
        "ID NUMBER",
        "TOOL_ID NUMBER",
        "STATUS STRING",
        "COMPLETED_AT TIMESTAMP_NTZ",
        "ORDER_TYPE STRING",
    ],
}


def column_names(table: str) -> List[str]:
    """Return the bare column names for a table, in DDL order."""
    return [definition.split(" ", 1)[0] for definition in TABLE_COLUMNS[table]]


def create_table_statement(database: str, schema: str, table: str) -> str:
    """Build a CREATE TABLE IF NOT EXISTS statement for one synthetic table."""
    body = ",\n    ".join(TABLE_COLUMNS[table])
    return f"CREATE TABLE IF NOT EXISTS {database}.{schema}.{table} (\n    {body}\n)"


def create_schema_statement(database: str, schema: str) -> str:
    """Build the CREATE SCHEMA statement that hosts the synthetic dataset."""
    return f"CREATE SCHEMA IF NOT EXISTS {database}.{schema}"


def all_create_statements(database: str, schema: str) -> List[str]:
    """Return the schema statement followed by every table statement, in dependency order."""
    statements = [create_schema_statement(database, schema)]
    statements.extend(
        create_table_statement(database, schema, table) for table in TABLE_COLUMNS
    )
    return statements


def truncate_statement(database: str, schema: str, table: str) -> str:
    """Build a TRUNCATE statement used when reloading the dataset from scratch."""
    return f"TRUNCATE TABLE IF EXISTS {database}.{schema}.{table}"
