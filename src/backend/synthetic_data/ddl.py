"""Snowflake DDL for every table the application needs.

Column names and types are copied from the authoritative production definitions so that the
analysis modules run unmodified against the synthetic account. TABLE_COLUMNS holds the
generated dataset and RUNTIME_TABLE_COLUMNS holds tables the application writes at execution
time; functions here build SQL strings only, and executing them is the caller's responsibility.
"""

from typing import Dict, Final, List

from .constants import (
    TABLE_AGENT_DECISION_TRAIL,
    TABLE_AUDIT_LOG,
    TABLE_LOCATION,
    TABLE_MASTER_SHOT,
    TABLE_PRODUCT,
    TABLE_SHIFT_NOTE,
    TABLE_TOOL,
    TABLE_VENDOR,
    TABLE_WORK_ORDER,
)

# Ordered column definitions per table. Order is significant: the loader writes CSV headers
# and INSERT column lists from these, so DDL and data can never drift apart.
TABLE_COLUMNS: Final[Dict[str, List[str]]] = {
    TABLE_MASTER_SHOT: [
        "VENDOR_NAME STRING",
        "MACHINE_ID STRING",
        "SENSOR_CODE STRING",
        "DURATION FLOAT",
        "TARGET_DURATION FLOAT",
        "TEMPERATURE FLOAT",
        "PRODUCT_NAME STRING",
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
        "VENDOR_COMPANY_ID NUMBER",
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


# Runtime tables the application writes at execution time. Held apart from TABLE_COLUMNS so the
# loader's CSV and COPY paths, which iterate the generated dataset, never touch them.
RUNTIME_TABLE_COLUMNS: Final[Dict[str, List[str]]] = {
    TABLE_AUDIT_LOG: [
        "TIMESTAMP TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()",
        "MACHINE_ID STRING",
        "ACTION_TYPE STRING",
        "SEVERITY STRING",
        "DESCRIPTION STRING",
        "INITIATED_BY STRING DEFAULT 'autonomous-agent'",
        "WEBHOOK_PAYLOAD VARIANT",
    ],
    TABLE_AGENT_DECISION_TRAIL: [
        "RUN_ID STRING",
        "RUN_TRIGGER STRING",
        "RUN_STATUS STRING",
        "LLM_BACKEND STRING",
        "MODEL_ID STRING",
        "STARTED_AT TIMESTAMP_NTZ",
        "COMPLETED_AT TIMESTAMP_NTZ",
        "RUN_DURATION_MS FLOAT",
        "SUMMARY STRING",
        "SEQUENCE NUMBER",
        "PHASE STRING",
        "TOOL_NAME STRING",
        "STEP_STATUS STRING",
        "RESULT_SUMMARY STRING",
        "STEP_DURATION_MS FLOAT",
        "STEP_CREATED_AT TIMESTAMP_NTZ",
        "PAYLOAD STRING",
    ],
}

# Every table the application needs, dataset and runtime alike.
ALL_TABLE_COLUMNS: Final[Dict[str, List[str]]] = {
    **TABLE_COLUMNS,
    **RUNTIME_TABLE_COLUMNS,
}


def column_names(table: str) -> List[str]:
    """Return the bare column names for a table, in DDL order."""
    return [definition.split(" ", 1)[0] for definition in ALL_TABLE_COLUMNS[table]]


def create_table_statement(database: str, schema: str, table: str) -> str:
    """Build a CREATE TABLE IF NOT EXISTS statement for one synthetic table."""
    body = ",\n    ".join(ALL_TABLE_COLUMNS[table])
    return f"CREATE TABLE IF NOT EXISTS {database}.{schema}.{table} (\n    {body}\n)"


def create_schema_statement(database: str, schema: str) -> str:
    """Build the CREATE SCHEMA statement that hosts the synthetic dataset."""
    return f"CREATE SCHEMA IF NOT EXISTS {database}.{schema}"


def all_create_statements(database: str, schema: str) -> List[str]:
    """Return the schema statement followed by every table statement, in dependency order."""
    statements = [create_schema_statement(database, schema)]
    statements.extend(
        create_table_statement(database, schema, table) for table in ALL_TABLE_COLUMNS
    )
    return statements


def truncate_statement(database: str, schema: str, table: str) -> str:
    """Build a TRUNCATE statement used when reloading the dataset from scratch."""
    return f"TRUNCATE TABLE IF EXISTS {database}.{schema}.{table}"
