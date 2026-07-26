"""Snowflake DDL for the synthetic dataset's tables.

Column names and types are copied from the authoritative production definitions so that the
analysis modules run unmodified against the synthetic account. Functions here build SQL
strings only; executing them is the loader's responsibility.
"""

from typing import Dict, Final, List

from .constants import (
    TABLE_COMPANY,
    TABLE_LOCATION,
    TABLE_MASTER_SHOT,
    TABLE_MOLD,
    TABLE_PART,
    TABLE_SHIFT_NOTE,
    TABLE_WORK_ORDER,
)

# Ordered column definitions per table. Order is significant: the loader writes CSV headers
# and INSERT column lists from these, so DDL and data can never drift apart.
TABLE_COLUMNS: Final[Dict[str, List[str]]] = {
    TABLE_MASTER_SHOT: [
        "SUPPLIER_NAME STRING",
        "EQUIPMENT_CODE STRING",
        "COUNTER_CODE STRING",
        "CT FLOAT",
        "APPROVED_CT FLOAT",
        "TEMPERATURE FLOAT",
        "PART_NAME STRING",
        "TOOLING_TYPE STRING",
        "TOOLING_FAMILY STRING",
        "CT_STATUS STRING",
        "LOCAL_SHOT_TIME TIMESTAMP_NTZ(3)",
        "UTC_TIME_ZONE TIMESTAMP_NTZ(3)",
        "VOLUME NUMBER",
        "COUNTER_ID NUMBER",
        "MOLD_ID NUMBER",
        "COMPANY_ID NUMBER",
        "PART_ID STRING",
        "UPLOAD_TIME TIMESTAMP_NTZ",
        "PROCESSING_DATE STRING",
    ],
    TABLE_MOLD: [
        "ID NUMBER",
        "EQUIPMENT_CODE STRING",
        "COUNTER_CODE STRING",
        "COUNTER_ID NUMBER",
        "SUPPLIER_COMPANY_ID NUMBER",
        "LOCATION_ID NUMBER",
        "PART_ID NUMBER",
        "TOOLING_TYPE STRING",
        "CONTRACTED_CYCLE_TIME NUMBER",
        "TOTAL_CAVITIES NUMBER",
        "DESIGNED_SHOT NUMBER",
        "DAILY_MAX_CAPACITY NUMBER",
        "PRODUCTION_DAYS NUMBER",
        "SHIFTS_PER_DAY NUMBER",
    ],
    TABLE_COMPANY: [
        "ID NUMBER",
        "NAME STRING",
    ],
    TABLE_LOCATION: [
        "ID NUMBER",
        "NAME STRING",
        "TIME_ZONE_ID STRING",
        "UTC_OFFSET_HOURS NUMBER",
    ],
    TABLE_PART: [
        "ID NUMBER",
        "PART_CODE STRING",
        "NAME STRING",
    ],
    TABLE_SHIFT_NOTE: [
        "ID NUMBER",
        "EQUIPMENT_CODE STRING",
        "SHIFT_DATE TIMESTAMP_NTZ",
        "AUTHOR_ROLE STRING",
        "NOTE_TEXT STRING",
    ],
    TABLE_WORK_ORDER: [
        "ID NUMBER",
        "MOLD_ID NUMBER",
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
